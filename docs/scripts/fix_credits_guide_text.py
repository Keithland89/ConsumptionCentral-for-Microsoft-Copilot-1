#!/usr/bin/env python3
"""Align the report wording with the Copilot Credits Guide, September 2026.

Four text changes, all in textboxes:

  * Microsoft 365 Copilot -> Microsoft Copilot. The August 2026 rebrand is
    recorded in the guide's own change log, so the two places the report still
    used the old name are now wrong.
  * The four cost buckets - Models, Runtime, Context, Tools - named on the
    Cowork guide page, which explained how credits are metered but never what
    makes the number move. The flat 0.1 credit Work IQ Tools API call goes in
    the same sentence, because it is the one part of Cowork metering that is
    not variable.
  * A warning that "GitHub Copilot" means two different products. The GHCP
    pages mean the per-seat developer product; Copilot Studio now also has a
    GitHub Copilot harness, which bills in credits and lands under Studio.
  * A warning that pre-purchased credits expire at the end of the annual term.
    The report shows an unused balance without saying it lapses.

This edits the report layer, so it only runs against a PBIP project - Desktop
rejects a .pbit whose report parts were touched. See docs/BUILD.md.

    python docs/scripts/pbit_to_pbip.py "<template>.pbit" --out C:\\pbip
    python docs/scripts/fix_credits_guide_text.py --pbip C:\\pbip
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fix_viva_query_org import require  # noqa: E402

BODY = {"fontFamily": "Segoe UI", "fontSize": "10.5pt", "color": "#1c2632"}
LABEL = {"fontFamily": "Segoe (Bold)", "fontSize": "10.5pt", "color": "#0b2c57",
         "fontWeight": "bold"}

OLD_BRAND = "Microsoft 365 Copilot"
NEW_BRAND = "Microsoft Copilot"

BUCKETS = (
    "Credit use scales with task complexity across four cost buckets \u2014 ",
    "Models", ", ", "Runtime", ", ", "Context", " and ", "Tools",
    ". Work IQ Tools API calls are a flat 0.1 credit each; Chat and Context calls vary.",
)

GHCP_WARNING = (
    "     ",
    "Two different GitHub Copilots",
    " \u2014 these pages mean the per-seat developer product. Copilot Studio also has a "
    "GitHub Copilot harness, which bills in Copilot Credits and reports under Studio, not here.",
)

STUDIO_WARNING = (
    "     ",
    "Prepaid credits expire",
    " \u2014 a Copilot Credit Pre-Purchase Plan runs for one year and unused credits lapse at "
    "the end of the term. An underused balance is a loss, not a saving carried forward.",
)


def run(value, style):
    return {"value": value, "textStyle": dict(style)}


def alternating(parts, first=BODY):
    """Build runs from a tuple that alternates body/label styling."""
    styles = (first, LABEL) if first is BODY else (LABEL, BODY)
    return [run(v, styles[i % 2]) for i, v in enumerate(parts)]


def paragraphs_of(document):
    general = document["visual"]["objects"]["general"]
    require(len(general) == 1, "textbox has more than one general object")
    return general[0]["properties"]["paragraphs"]


def contains(paragraphs, needle):
    return any(needle in r.get("value", "")
               for p in paragraphs for r in p.get("textRuns", []))


def rebrand(paragraphs):
    """Microsoft 365 Copilot -> Microsoft Copilot, in place."""
    changed = 0
    for paragraph in paragraphs:
        for text in paragraph.get("textRuns", []):
            if OLD_BRAND in text.get("value", ""):
                text["value"] = text["value"].replace(OLD_BRAND, NEW_BRAND)
                changed += 1
    return changed


def add_buckets(paragraphs):
    """Name the four cost buckets, after the paragraph introducing Cowork."""
    if contains(paragraphs, "four cost buckets"):
        return 0
    anchor = next((i for i, p in enumerate(paragraphs)
                   if any("metered per person" in r.get("value", "")
                          for r in p.get("textRuns", []))), None)
    require(anchor is not None, "cannot find the Cowork introduction paragraph")
    paragraphs.insert(anchor + 1, {"textRuns": [run("", BODY)]})
    paragraphs.insert(anchor + 2, {"textRuns": alternating(BUCKETS)})
    return 1


def append_warning(paragraphs, parts, marker):
    """Add another item to a 'Watch out for' paragraph."""
    if contains(paragraphs, marker):
        return 0
    anchor = next((p for p in reversed(paragraphs) if len(p.get("textRuns", [])) > 1), None)
    require(anchor is not None, "cannot find the warnings paragraph")
    anchor["textRuns"].extend(alternating(parts))
    return 1


EDITS = (
    ("guide-cowork", "guidecowor_left", rebrand),
    ("guide-cowork", "guidecowor_left", add_buckets),
    ("glossary", "p8_notes", rebrand),
    ("guide-ghcp", "guideghcp_foot",
     lambda p: append_warning(p, GHCP_WARNING, "Two different GitHub Copilots")),
    ("guide-studio", "guidestudi_foot",
     lambda p: append_warning(p, STUDIO_WARNING, "Prepaid credits expire")),
)


def visual_path(root, page, visual):
    matches = list(root.glob(f"**/pages/{page}/visuals/{visual}/visual.json"))
    require(len(matches) == 1,
            f"{page}/{visual}: expected one visual.json, found {len(matches)}")
    return matches[0]


def patch_project(root, dry_run=False):
    root = Path(root).resolve()
    require(root.is_dir(), f"Not a folder: {root}")
    print(f"\n{root.name}")

    pending = {}
    for page, visual, edit in EDITS:
        path = visual_path(root, page, visual)
        document = pending.get(path)
        if document is None:
            document = pending[path] = json.loads(path.read_text(encoding="utf-8"))
        changed = edit(paragraphs_of(document))
        status = f"{changed} applied" if changed else "already current"
        print(f"  {page}/{visual}: {edit.__name__ if edit.__name__ != '<lambda>' else 'warning'}"
              f" - {status}")

    if dry_run:
        print("  dry run; nothing written")
        return

    for path, document in pending.items():
        text = json.dumps(document, ensure_ascii=False, indent=2)
        path.write_text(text + "\n", encoding="utf-8", newline="\n")
        require(json.loads(path.read_text(encoding="utf-8")) == document,
                f"{path}: written file does not reparse to the intended document")
    print(f"  {len(pending)} visuals written")


def is_project(folder):
    return any(folder.glob("*.pbip")) or any(folder.glob("*/definition.pbir"))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pbip", type=Path, required=True,
                        help="folder holding the PBIP projects, or one project folder")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    root = args.pbip.resolve()
    require(root.is_dir(), f"Not a folder: {root}")
    roots = [root] if is_project(root) else [p for p in sorted(root.iterdir())
                                             if p.is_dir() and is_project(p)]
    require(roots, f"No PBIP project found under {root}")
    for project in roots:
        patch_project(project, dry_run=args.dry_run)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
