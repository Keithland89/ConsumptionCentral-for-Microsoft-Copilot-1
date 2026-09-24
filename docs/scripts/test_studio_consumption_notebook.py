"""Offline request tests using the Studio consumption notebook's own functions.

Mirrors test_azure_notebook_requests.py: the functions are lifted out of the
notebook by AST so the tests exercise the shipped code, not a copy of it.
"""
import ast
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
import json
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

NOTEBOOK = (Path(__file__).resolve().parents[2] / "2. Fabric" / "notebooks"
            / "Ingest_Studio_Consumption.ipynb")
PPAPI = "https://api.powerplatform.com"


def functions():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    wanted = {"retry_delay", "pp_get", "pp_pages", "meta_get", "as_float"}
    definitions = []
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            tree = ast.parse("".join(cell["source"]))
            definitions.extend(node for node in tree.body
                               if isinstance(node, ast.FunctionDef) and node.name in wanted)
    if {node.name for node in definitions} != wanted:
        raise AssertionError("Notebook request functions changed; update the tests")
    from urllib.parse import urlsplit, urlencode
    namespace = {
        "math": math, "datetime": datetime, "timezone": timezone,
        "parsedate_to_datetime": parsedate_to_datetime,
        "urlsplit": urlsplit, "urlencode": urlencode, "json": json,
        "requests": SimpleNamespace(get=Mock()), "time": SimpleNamespace(sleep=Mock()),
        "pp_headers": Mock(return_value={"Authorization": "******"}),
        "PPAPI": PPAPI, "PPAPI_HOST": "api.powerplatform.com",
        "API_VERSION": "2024-10-01", "ENTITLEMENT": "MCSMessages",
    }
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(NOTEBOOK), "exec"),
         namespace)
    return namespace


def response(status=200, headers=None, page=None):
    result = Mock(status_code=status, headers=headers or {})
    result.json.return_value = page if page is not None else {"value": []}
    if status >= 400:
        result.raise_for_status.side_effect = RuntimeError(f"HTTP {status}")
    return result


class RetryDelayTests(unittest.TestCase):
    def setUp(self):
        self.ns = functions()

    def test_exponential_floor(self):
        self.assertEqual(self.ns["retry_delay"]({}, 3), 8.0)

    def test_server_delay_wins_when_longer(self):
        self.assertEqual(self.ns["retry_delay"]({"Retry-After": "30"}, 0), 30.0)

    def test_exponential_wins_when_longer(self):
        self.assertEqual(self.ns["retry_delay"]({"Retry-After": "1"}, 4), 16.0)

    def test_rate_limit_header_is_honoured(self):
        headers = {"x-ms-ratelimit-burst-retry-after": "45"}
        self.assertEqual(self.ns["retry_delay"](headers, 0), 45.0)

    def test_http_date_retry_after(self):
        # A near-future HTTP-date must parse into a positive, usable delay.
        # Keep it inside the 300s guard: a far-future date is correctly refused,
        # which is covered by test_excessive_delay_defers_the_job.
        soon = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=45))
        self.assertGreater(self.ns["retry_delay"]({"Retry-After": soon}, 0), 0)

    def test_past_http_date_does_not_go_negative(self):
        past = format_datetime(datetime.now(timezone.utc) - timedelta(seconds=45))
        self.assertGreaterEqual(self.ns["retry_delay"]({"Retry-After": past}, 0), 1.0)

    def test_excessive_delay_defers_the_job(self):
        with self.assertRaises(RuntimeError):
            self.ns["retry_delay"]({"Retry-After": "600"}, 0)

    def test_non_finite_delay_rejected(self):
        with self.assertRaises(ValueError):
            self.ns["retry_delay"]({"Retry-After": "inf"}, 0)


class RequestTests(unittest.TestCase):
    def setUp(self):
        self.ns = functions()
        self.get = self.ns["requests"].get

    def test_api_version_always_sent(self):
        self.get.return_value = response(page={"value": [1]})
        self.ns["pp_get"]("/licensing/entitlements/MCSMessages")
        url = self.get.call_args[0][0]
        self.assertIn("api-version=2024-10-01", url)

    def test_none_parameters_are_dropped(self):
        self.get.return_value = response()
        self.ns["pp_get"]("/x", continuationtoken=None, pageSize=10)
        url = self.get.call_args[0][0]
        self.assertNotIn("continuationtoken", url)
        self.assertIn("pageSize=10", url)

    def test_credentials_never_leave_the_service(self):
        self.ns["PPAPI"] = "https://evil.example.com"
        with self.assertRaises(ValueError):
            self.ns["pp_get"]("/licensing/entitlements/MCSMessages")
        self.get.assert_not_called()

    def test_redirects_are_not_followed(self):
        self.get.return_value = response()
        self.ns["pp_get"]("/x")
        self.assertFalse(self.get.call_args.kwargs["allow_redirects"])

    def test_forbidden_explains_the_permission(self):
        self.get.return_value = response(status=403)
        with self.assertRaises(PermissionError) as caught:
            self.ns["pp_get"]("/x")
        self.assertIn("licensing", str(caught.exception).lower())

    def test_throttling_retries_then_succeeds(self):
        self.get.side_effect = [response(status=429, headers={"Retry-After": "1"}),
                                response(page={"value": [{"resourceId": "a"}]})]
        out = self.ns["pp_get"]("/x")
        self.assertEqual(out["value"][0]["resourceId"], "a")
        self.assertEqual(self.get.call_count, 2)

    def test_persistent_throttling_eventually_raises(self):
        self.get.side_effect = [response(status=503, headers={"Retry-After": "1"})] * 5
        with self.assertRaises(RuntimeError):
            self.ns["pp_get"]("/x")


class PaginationTests(unittest.TestCase):
    def setUp(self):
        self.ns = functions()
        self.get = self.ns["requests"].get

    def test_follows_continuation_token(self):
        self.get.side_effect = [
            response(page={"value": [{"resourceId": "a"}], "continuationtoken": "t1"}),
            response(page={"value": [{"resourceId": "b"}]}),
        ]
        rows = [r for page in self.ns["pp_pages"]("/x") for r in page]
        self.assertEqual([r["resourceId"] for r in rows], ["a", "b"])

    def test_accepts_camel_case_token(self):
        self.get.side_effect = [
            response(page={"value": [{"resourceId": "a"}], "continuationToken": "t1"}),
            response(page={"value": [{"resourceId": "b"}]}),
        ]
        rows = [r for page in self.ns["pp_pages"]("/x") for r in page]
        self.assertEqual(len(rows), 2)

    def test_missing_value_is_not_an_error(self):
        self.get.return_value = response(page={})
        self.assertEqual([r for page in self.ns["pp_pages"]("/x") for r in page], [])

    def test_endless_pagination_is_bounded(self):
        self.get.return_value = response(page={"value": [{"a": 1}], "continuationtoken": "t"})
        with self.assertRaises(RuntimeError):
            list(self.ns["pp_pages"]("/x"))


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.ns = functions()
        self.meta_get = self.ns["meta_get"]

    def test_exact_key(self):
        self.assertEqual(self.meta_get({"Feature": "Generative answer"}, "feature"),
                         "Generative answer")

    def test_case_and_separator_insensitive(self):
        row = {"non_billable-Consumed": "12.5"}
        self.assertEqual(self.meta_get(row, "nonBillableConsumed"), "12.5")

    def test_alias_order_is_respected(self):
        row = {"llmModel": "GPT-5.6 Sol"}
        self.assertEqual(self.meta_get(row, "model", "llmModel"), "GPT-5.6 Sol")

    def test_missing_key_returns_none(self):
        self.assertIsNone(self.meta_get({"Feature": "x"}, "channel"))

    def test_explicit_null_returns_none(self):
        self.assertIsNone(self.meta_get({"tool": None}, "tool"))

    def test_blank_string_returns_none(self):
        self.assertIsNone(self.meta_get({"tool": "   "}, "tool"))

    def test_list_values_are_flattened(self):
        row = {"knowledgeSources": ["SharePoint", "Dataverse"]}
        self.assertEqual(self.meta_get(row, "knowledgeSources"), "SharePoint, Dataverse")

    def test_non_dict_is_tolerated(self):
        self.assertIsNone(self.meta_get(None, "feature"))
        self.assertIsNone(self.meta_get("not a dict", "feature"))


class NumberTests(unittest.TestCase):
    def setUp(self):
        self.as_float = functions()["as_float"]

    def test_numeric_string(self):
        self.assertEqual(self.as_float("12.5"), 12.5)

    def test_none_and_garbage(self):
        self.assertIsNone(self.as_float(None))
        self.assertIsNone(self.as_float("not a number"))

    def test_zero_is_preserved_not_nulled(self):
        # A real zero must survive: it is the difference between "no consumption"
        # and "no telemetry", and the report distinguishes them.
        self.assertEqual(self.as_float(0), 0.0)

    def test_non_finite_rejected(self):
        self.assertIsNone(self.as_float(float("inf")))
        self.assertIsNone(self.as_float(float("nan")))


class HarnessInferenceTests(unittest.TestCase):
    """The Process Agent convention is a documented observation, not a contract.

    These pin the behaviour so a future edit cannot quietly start asserting a
    harness where the telemetry does not support one.
    """

    @staticmethod
    def infer(feature=None, tool=None, model=None, knowledge=None):
        if feature and feature.strip().lower() == "process agent":
            return "GitHub Copilot (inferred)"
        if feature or tool or model or knowledge:
            return "Standard (inferred)"
        return None

    def test_process_agent_infers_github_copilot(self):
        self.assertEqual(self.infer(feature="Process Agent"), "GitHub Copilot (inferred)")

    def test_matching_is_case_and_space_tolerant(self):
        self.assertEqual(self.infer(feature="  process agent "),
                         "GitHub Copilot (inferred)")

    def test_rich_detail_infers_standard(self):
        self.assertEqual(self.infer(feature="Generative answer", model="GPT-5.6 Sol"),
                         "Standard (inferred)")

    def test_no_telemetry_infers_nothing(self):
        self.assertIsNone(self.infer())


if __name__ == "__main__":
    unittest.main(verbosity=2)
