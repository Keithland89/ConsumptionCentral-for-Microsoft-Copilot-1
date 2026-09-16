"""Assert the Cowork forecast gate and blank-slicer fixes are in the templates.

Pairs with fix_cowork_forecast_gate.py. Checks the package is still well
formed and that each behavioural change is actually present in the model:

  * the Cowork trend fit is gated at 4 weeks, not 6, so a tenant with only
    4-5 weeks of Viva history stops silently forecasting flat
  * Growth Applied % coalesces, so a missing fit reads 0 rather than blank
  * the "Indicative only" confidence tier exists to carry the extra
    uncertainty that the shorter window buys
  * Cowork Forecast Summary branches on the fit, not on ISBLANK
  * VivaCreditMetrics labels blank ServiceName, so the Cowork / Work IQ
    slicer stops showing an empty entry

The az_note "Local CSV sample data" text is reported but never fails the
run: it lives in the report layer, which cannot be hand-edited, so it is
tracked as deferred rather than treated as a regression.

    python docs/scripts/check_cowork_forecast_gate.py
"""
import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AZ = "Report/definition/pages/foundry-spend/visuals/az_note/visual.json"
FOLDERS = ("1. Local CSV", "2. Fabric", "3. Viva Direct")
WANT = [
    "Implied Monthly Growth %",
    "Growth Rate Was Capped",
    "Growth Applied %",
    "GHCP Growth Applied %",
    "Cowork Forecast Confidence",
    "Cowork Forecast Confidence Note",
    "Cowork Forecast Summary",
]


def decode(data):
    if data[:2] == b"\xff\xfe":
        return data.decode("utf-16")
    if len(data) > 1 and data[1] == 0:
        return data.decode("utf-16-le")
    return data.decode("utf-8")


def text_of(value):
    return "\n".join(value) if isinstance(value, list) else (value or "")


def check(pbit, problems, deferred):
    before = len(problems)

    def fail(message):
        problems.append(f"{pbit.name}: {message}")

    with zipfile.ZipFile(pbit) as z:
        names = z.namelist()
        if z.testzip() is not None:
            fail(f"corrupt package part {z.testzip()}")
        if "SecurityBindings" not in names:
            fail("SecurityBindings was dropped - the report layer must stay signed")
        try:
            ET.fromstring(decode(z.read("[Content_Types].xml")))
        except ET.ParseError as exc:
            fail(f"[Content_Types].xml does not parse: {exc}")

        for name in names:
            if name.endswith(".json") or name in (
                "DataModelSchema", "UnappliedChanges", "Settings", "Metadata",
            ):
                try:
                    json.loads(decode(z.read(name)))
                except Exception as exc:  # noqa: BLE001
                    fail(f"{name} does not parse: {exc}")

        model = json.loads(decode(z.read("DataModelSchema")))["model"]
        found = {
            m["name"]: text_of(m.get("expression"))
            for t in model.get("tables", [])
            for m in t.get("measures", [])
            if m["name"] in WANT
        }
        for want in WANT:
            if want not in found:
                fail(f"measure missing: {want}")

        implied = found.get("Implied Monthly Growth %", "")
        if "[Trend Window Weeks] < 4" not in implied:
            fail("Implied Monthly Growth % is not gated at 4 weeks")
        if "< 6" in implied:
            fail("Implied Monthly Growth % still carries the old 6-week gate")
        if "COALESCE" not in found.get("Growth Applied %", ""):
            fail("Growth Applied % does not coalesce a missing fit to 0")
        if "COALESCE" not in found.get("GHCP Growth Applied %", ""):
            fail("GHCP Growth Applied % does not coalesce a missing fit to 0")
        if "Indicative only" not in found.get("Cowork Forecast Confidence", ""):
            fail("Cowork Forecast Confidence has no 'Indicative only' tier")
        if "Implied Monthly Growth %" not in found.get("Cowork Forecast Summary", ""):
            fail("Cowork Forecast Summary does not branch on the fit")

        expression = next(
            (text_of(e.get("expression"))
             for e in model.get("expressions", [])
             if e.get("name") == "VivaCreditMetrics"),
            "",
        )
        if "ServiceNameLabelled" not in expression:
            fail("VivaCreditMetrics does not label blank ServiceName")

        if AZ in names and "Local CSV sample data" in decode(z.read(AZ)):
            deferred.append(f"{pbit.name}: az_note still reads 'Local CSV sample data'")

    if len(problems) == before:
        print(f"  {pbit.name}: forecast gate and slicer fixes present")
    else:
        print(f"  {pbit.name}: {len(problems) - before} problem(s)")


def main():
    problems, deferred = [], []
    for folder in FOLDERS:
        check(next((ROOT / folder).glob("*.pbit")), problems, deferred)

    for note in deferred:
        print(f"  DEFERRED (report layer, not patchable) {note}")
    if problems:
        print()
        for problem in problems:
            print(f"  FAIL {problem}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
