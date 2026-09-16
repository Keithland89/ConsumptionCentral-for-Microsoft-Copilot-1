"""Patch the three Consumption Central templates.

1. Azure page SOURCE COVERAGE note is hardcoded to "Local CSV sample data"
   in every template. Only template 1 actually reads CSVs.
2. viva_credits_weekly rows whose ServiceName is empty arrive as a blank
   entry in the Cowork/WorkIQ slicer. They carry real credits, so label
   them instead of dropping them.
3. The Cowork trend fit is gated at 6 weeks. Studio gates the equivalent
   fit at 28 days, so a tenant with 4-5 weeks of Viva history silently
   forecasts flat. Align the Cowork gate to 4 weeks and keep the extra
   uncertainty visible through a new confidence tier.

Only 2 and 3 are applied. 1 lives in the report layer, which cannot be
hand-edited - see the PATCH_AZ_NOTE comment below.
"""
import json
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Fix 1 is disabled: it is the only one of the three that lives in the report
# layer, and the report layer cannot be hand-edited. Verified against Power BI
# Desktop 2.158.758.0:
#
#   Report/ edit + SecurityBindings kept    -> "Unable to open template"
#   Report/ edit + SecurityBindings deleted -> opens
#   model-only edit + SecurityBindings kept -> opens
#
# So SecurityBindings covers the Report/ parts but not DataModelSchema or
# UnappliedChanges. Deleting it to sneak a report edit through is exactly what
# docs/scripts/check_model_only.py exists to forbid, so az_note has to be
# corrected in Power BI Desktop and the template re-exported per docs/BUILD.md.
#
# Note: dropping SecurityBindings was NOT shown to break Fabric SQL auth. That
# was hypothesised and then disproved - the login failures seen while testing
# reproduced on an untouched template too, so they were environmental.
PATCH_AZ_NOTE = False

TEMPLATES = {
    "1. Local CSV": None,  # Azure really is CSV here - leave the note alone
    "2. Fabric": "Fabric Lakehouse tables. Cost Management may lag usage.",
    "3. Viva Direct": "Azure Cost Management CSV export. Cost Management may lag usage.",
}

OLD_NOTE = "Local CSV sample data. Cost Management may lag usage."

AZ_NOTE_PATH = "Report/definition/pages/foundry-spend/visuals/az_note/visual.json"

SECURITY_BINDINGS = "SecurityBindings"
CONTENT_TYPES = "[Content_Types].xml"
SB_OVERRIDE = '<Override PartName="/SecurityBindings" ContentType="" />'

# Removing SecurityBindings is how a report-layer edit can be forced to open,
# and it is deliberately off. Every fix this script still applies is model-only,
# so the signature stays valid and the part stays put. check_model_only.py
# fails the build if a report part ever changes.
DROP_SECURITY_BINDINGS = False

MARKER = "__VivaCreditMetricsUnlabelled"

# The three templates end this expression differently (Result / Typed /
# "if Bin = null then Empty else Loaded"), so wrap the whole body rather than
# appending to a step whose name varies.
SERVICE_LABEL_WRAP = '''let
    // Some exports leave ServiceName empty for a service the tenant has not
    // named yet. Left blank it surfaces as an empty entry in the Cowork /
    // Work IQ slicer, so label it rather than dropping the rows - they still
    // carry real credits.
    {marker} = (
{body}
    ),
    ServiceNameLabelled = Table.TransformColumns(
        {marker},
        {{{{"ServiceName", each if _ = null or Text.Trim(Text.From(_)) = "" then "Other" else _, type text}}}}
    )
in
    ServiceNameLabelled'''


def decode(data):
    """DataModelSchema / UnappliedChanges are UTF-16LE with no BOM."""
    if data[:2] == b"\xff\xfe":
        return data.decode("utf-16"), "utf-16"
    if len(data) > 1 and data[1] == 0:
        return data.decode("utf-16-le"), "utf-16-le"
    return data.decode("utf-8"), "utf-8"


def encode(text, enc):
    return text.encode(enc)


def patch_m(expr_text):
    """Wrap a VivaCreditMetrics expression so blank ServiceName is labelled."""
    if MARKER in expr_text:
        return expr_text, False
    body = "\n".join("        " + line for line in expr_text.rstrip().split("\n"))
    return SERVICE_LABEL_WRAP.format(marker=MARKER, body=body), True


MEASURE_EDITS = [
    (
        "Implied Monthly Growth %",
        [(re.compile(r"\[Trend Window Weeks\]\s*<\s*6"), "[Trend Window Weeks] < 4")],
    ),
    (
        "Growth Rate Was Capped",
        [(re.compile(r"\[Trend Window Weeks\]\s*>=\s*6"), "[Trend Window Weeks] >= 4")],
    ),
    (
        "Cowork Forecast Confidence",
        [
            (
                re.compile(r'Wks\s*<\s*6,\s*"Too early to say",'),
                'Wks < 4,                     "Too early to say",\n        '
                'Wks < 6,                     "Indicative only",',
            )
        ],
    ),
    (
        "Cowork Forecast Confidence Note",
        [
            (
                re.compile(
                    r'"Too early to say",\s*"Not enough weeks of history yet\. '
                    r'Revisit once six weeks are available\.",'
                ),
                '"Indicative only",  "Only four or five weeks of history. The trend is '
                'fitted but a backtest needs six weeks, so treat it as a direction rather '
                'than a number.",\n    "Too early to say", "Not enough weeks of history yet. '
                'Revisit once four weeks are available.",',
            )
        ],
    ),
    (
        "Growth Applied %",
        [
            (
                re.compile(
                    r'IF\(\s*Chosen\s*=\s*"Fitted from history",\s*'
                    r"\[Implied Monthly Growth %\],\s*Rate\s*\)"
                ),
                'IF( Chosen = "Fitted from history", '
                "COALESCE( [Implied Monthly Growth %], 0 ), Rate )",
            )
        ],
    ),
    (
        # Growth Applied % no longer returns blank, so the "too early" branch has
        # to test the fit itself or the summary would claim 0.0% growth instead.
        # Two shapes ship across the templates, so try both.
        "Cowork Forecast Summary",
        [
            (
                re.compile(r"ISBLANK\(\s*g\s*\)\s*\|\|\s*ISBLANK\(\s*Wks\s*\),"),
                "ISBLANK( Wks ) || ( NOT [Growth Is Override] "
                "&& ISBLANK( [Implied Monthly Growth %] ) ),",
            ),
            (
                re.compile(r"ISBLANK\(\s*g\s*\),"),
                "NOT [Growth Is Override] && ISBLANK( [Implied Monthly Growth %] ),",
            ),
        ],
    ),
    (
        # Same blank-inheritance bug on the GitHub page: GHCP Observed Growth %
        # is blank whenever the usage spans a single calendar month, and
        # GHCP Growth Applied % passed that blank straight through. Studio
        # already coalesces (Studio Growth Applied %), and Cowork does now, so
        # this brings the third forecast family into line.
        "GHCP Growth Applied %",
        [
            (
                re.compile(
                    r'IF\(\s*Chosen\s*=\s*"Fitted from history",\s*'
                    r"\[GHCP Observed Growth %\],\s*Rate\s*\)"
                ),
                'IF( Chosen = "Fitted from history", '
                "COALESCE( [GHCP Observed Growth %], 0 ), Rate )",
            )
        ],
    ),
]

DESC_EDITS = [
    (
        "Implied Monthly Growth %",
        [
            (
                re.compile(r"Blank under six weeks of history\."),
                "Blank under four weeks of history.",
            ),
            (
                re.compile(r"quintillions\. Six weeks is the\nsame threshold"),
                "quintillions. Four weeks is the\nsame threshold",
            ),
            (
                # The anchor survives the edit, so guard against appending the
                # same sentence again on a re-run.
                re.compile(
                    r'say", so the rate and the rating can never contradict each other\.'
                    r"(?!\nBetween four and six weeks)"
                ),
                'say", so the rate and the rating can never contradict each other.\n'
                "Between four and six weeks the fit is reported but rated\n"
                '"indicative only", because the backtest needs six weeks to run.',
            ),
        ],
    ),
]


def as_text(expr):
    return "\n".join(expr) if isinstance(expr, list) else (expr or "")


def restore(original, text):
    return text.split("\n") if isinstance(original, list) else text


def patch_model(schema_text, report):
    model = json.loads(schema_text)
    m = model["model"]

    for e in m.get("expressions", []):
        if e["name"] == "VivaCreditMetrics":
            src = as_text(e.get("expression"))
            new, ok = patch_m(src)
            if ok:
                e["expression"] = restore(e.get("expression"), new)
                report.append("  expr VivaCreditMetrics: ServiceName label added")
            else:
                report.append("  expr VivaCreditMetrics: NO CHANGE (check tail)")

    for t in m.get("tables", []):
        for ms in t.get("measures", []):
            for name, edits in MEASURE_EDITS:
                if ms["name"] != name:
                    continue
                if not isinstance(edits, list):
                    edits = [edits]
                src = as_text(ms.get("expression"))
                applied = 0
                for pat, repl in edits:
                    new, n = pat.subn(repl, src)
                    if n:
                        src = new
                        applied += n
                        break
                if applied:
                    ms["expression"] = restore(ms.get("expression"), src)
                    report.append(f"  measure {name}: {applied} edit(s)")
                else:
                    report.append(f"  measure {name}: NO MATCH")

            for name, edits in DESC_EDITS:
                if ms["name"] != name or "description" not in ms:
                    continue
                src = as_text(ms["description"])
                applied = 0
                for pat, repl in edits:
                    src, n = pat.subn(repl, src)
                    applied += n
                if applied:
                    ms["description"] = restore(ms["description"], src)
                    report.append(f"  desc {name}: {applied} edit(s)")
                else:
                    report.append(f"  desc {name}: NO MATCH")

    return json.dumps(model, indent=2, ensure_ascii=False)


def patch_unapplied(text, report):
    doc = json.loads(text)
    changed = 0
    for q in doc.get("queries", []):
        if q.get("name") != "VivaCreditMetrics":
            continue
        for key in ("text", "lastLoadedAsTableFormulaText"):
            if key not in q:
                continue
            src = as_text(q[key])
            new, ok = patch_m(src)
            if ok:
                q[key] = restore(q[key], new)
                changed += 1
    report.append(f"  UnappliedChanges: {changed} VivaCreditMetrics field(s) patched")
    return json.dumps(doc, indent=2, ensure_ascii=False)


def run():
    for folder, note in TEMPLATES.items():
        src = next((ROOT / folder).glob("*.pbit"))
        report = [f"=== {src.name} ==="]
        report_changed = False
        backup = src.with_suffix(".pbit.bak")
        shutil.copy2(src, backup)

        zin = zipfile.ZipFile(backup, "r")
        entries = zin.infolist()
        payload = {}

        for info in entries:
            data = zin.read(info.filename)

            if info.filename == "DataModelSchema":
                text, enc = decode(data)
                data = encode(patch_model(text, report), enc)

            elif info.filename == "UnappliedChanges":
                text, enc = decode(data)
                data = encode(patch_unapplied(text, report), enc)

            elif info.filename == AZ_NOTE_PATH and note and PATCH_AZ_NOTE:
                text, enc = decode(data)
                if OLD_NOTE in text:
                    text = text.replace(OLD_NOTE, note)
                    report.append("  az_note: source coverage text updated")
                    report_changed = True
                else:
                    report.append("  az_note: NO MATCH")
                data = encode(text, enc)

            payload[info.filename] = data

        zin.close()

        # SecurityBindings carries hashes over the report parts. Power BI
        # rejects the template with "unable to open" once they no longer
        # match, so drop the part - and its content-type override - whenever
        # anything under Report/ changed. Model-side edits are not covered
        # by it and need no such handling.
        if report_changed and DROP_SECURITY_BINDINGS:
            payload.pop(SECURITY_BINDINGS, None)
            ct = payload.get(CONTENT_TYPES)
            if ct is not None:
                text, enc = decode(ct)
                payload[CONTENT_TYPES] = encode(text.replace(SB_OVERRIDE, ""), enc)
            entries = [e for e in entries if e.filename != SECURITY_BINDINGS]
            report.append("  SecurityBindings: removed (report content changed)")

        with zipfile.ZipFile(src, "w") as zout:
            for info in entries:
                zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                zi.compress_type = info.compress_type
                zi.external_attr = info.external_attr
                zi.internal_attr = info.internal_attr
                zi.create_system = info.create_system
                zout.writestr(zi, payload[info.filename])

        print("\n".join(report))
        print()


if __name__ == "__main__":
    run()
