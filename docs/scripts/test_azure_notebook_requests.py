"""Offline request tests using the notebook's actual function definitions."""
import ast
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


NOTEBOOK = Path(__file__).resolve().parents[2] / "2. Fabric" / "notebooks" / "Ingest_Azure_AI.ipynb"
ARM = "https://management.azure.com"


def functions():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    wanted = {"retry_delay", "arm_request", "cost_query", "finite_number"}
    definitions = []
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            tree = ast.parse("".join(cell["source"]))
            definitions.extend(node for node in tree.body
                               if isinstance(node, ast.FunctionDef) and node.name in wanted)
    if {node.name for node in definitions} != wanted:
        raise AssertionError("Notebook request functions changed; update the tests")
    from urllib.parse import urlsplit
    namespace = {
        "math": math, "datetime": datetime, "timezone": timezone,
        "parsedate_to_datetime": parsedate_to_datetime, "urlsplit": urlsplit,
        "requests": SimpleNamespace(request=Mock()), "time": SimpleNamespace(sleep=Mock()),
        "arm_headers": Mock(return_value={"Authorization": "Bearer offline-fixture"}),
    }
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(NOTEBOOK), "exec"), namespace)
    return namespace


def response(status=200, headers=None, page=None):
    result = Mock(status_code=status, headers=headers or {})
    result.json.return_value = page
    if status >= 400:
        result.raise_for_status.side_effect = RuntimeError(f"HTTP {status}")
    return result


class NotebookRequests(unittest.TestCase):
    def setUp(self):
        self.ns = functions()
        self.request = self.ns["requests"].request

    def test_throttled_continuation_retries_same_page_and_body(self):
        first = ARM + "/subscriptions/fixture/query"
        second = first + "?$skiptoken=next"
        def page(amount, next_link=None):
            return {"properties": {
                "columns": [{"name": name} for name in ("Cost", "UsageDate", "Currency")],
                "rows": [[amount, 20260901, "USD"]], "nextLink": next_link,
            }}
        self.request.side_effect = [
            response(page=page(1, second)),
            response(429, {"x-ms-ratelimit-microsoft.costmanagement-qpu-retry-after": "12"}),
            response(page=page(2)),
        ]
        body = {"dataset": {"aggregation": {"totalCost": {"name": "Cost"}}, "grouping": []}}
        rows = self.ns["cost_query"](first, body)
        self.assertEqual([row["Cost"] for row in rows], [1, 2])
        self.assertEqual([call.args for call in self.request.call_args_list],
                         [("POST", first), ("POST", second), ("POST", second)])
        self.assertTrue(all(call.kwargs["json"] == body for call in self.request.call_args_list))
        self.ns["time"].sleep.assert_called_once_with(12)

    def test_retry_budget_exhaustion_propagates(self):
        self.request.side_effect = [response(429) for _ in range(5)]
        with self.assertRaisesRegex(RuntimeError, "HTTP 429"):
            self.ns["arm_request"]("GET", ARM + "/resources")
        self.assertEqual(self.request.call_count, 5)
        self.assertEqual(self.ns["time"].sleep.call_count, 4)

    def test_auth_failure_is_not_retried(self):
        self.request.return_value = response(403)
        with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
            self.ns["arm_request"]("GET", ARM + "/resources")
        self.request.assert_called_once()
        self.ns["time"].sleep.assert_not_called()

    def test_foreign_continuation_never_receives_credentials(self):
        with self.assertRaises(ValueError):
            self.ns["arm_request"]("POST", "https://example.com/query")
        self.request.assert_not_called()
        self.ns["arm_headers"].assert_not_called()

    def test_retry_headers_honor_largest_delay(self):
        self.assertEqual(self.ns["retry_delay"]({
            "Retry-After": "2",
            "x-ms-ratelimit-microsoft.costmanagement-entity-retry-after": "30",
        }, 0), 30)

    def test_excessive_delay_defers_instead_of_retrying_early(self):
        with self.assertRaisesRegex(RuntimeError, "defer the job"):
            self.ns["retry_delay"]({"Retry-After": "301"}, 0)

    def test_invalid_delay_fails(self):
        with self.assertRaises(ValueError):
            self.ns["retry_delay"]({"Retry-After": "nan"}, 0)

    def test_retry_after_http_date(self):
        self.assertEqual(self.ns["retry_delay"]({
            "Retry-After": "Wed, 01 Jan 2020 00:00:00 GMT",
        }, 1), 2)


if __name__ == "__main__":
    unittest.main()
