"""Guarded, standard-library-only patcher for two report-layer slicer defects.

The report layer is normally off limits (docs/scripts/check_model_only.py) because
Desktop twice rejected hand-edited PBIR visuals. Neither fix here is reachable
from the model, so this script keeps the edits as small and as checked as the
model patchers are:

1. "GROUP BY" defaults to Department. Department is an Org attribute, so it only
   exists when the customer supplied org data - the "Group By" calculated table
   unions it behind FILTER( OrgRows, NOT ISEMPTY( 'Org Attribute Source' ) ).
   "All users" is unioned unconditionally, so it is the only grouping guaranteed
   to resolve in every tenant and every template. Only slicers that actually
   carry the Department default are retouched; slicers that ship with no
   selection are left exactly as they are.

2. The ServiceName slicers on the four Cowork pages are advancedSlicerVisual
   (the button slicer), which needs more room than the 222x88 rail slot and so
   renders without its three service buttons. They become ordinary list slicers,
   built from the object set of the "GROUP BY" slicer already shipping and
   working on the same page, so nothing unproven is introduced.

Both edits rewrite only Report/definition/pages/*/visuals/*/visual.json parts.
The archive is rebuilt through fix_viva_query_org.Package, so every untouched
part - DataModelSchema, DataMashup-free query state, SecurityBindings, static
resources - is copied verbatim, byte for byte.

    python docs/scripts/fix_slicer_defaults.py --dry-run
    python docs/scripts/fix_slicer_defaults.py

Re-running is a no-op: an already patched file is left byte identical. Desktop
render validation is separate - open the patched template and check the rail.
"""

import argparse
import copy
import json
import os
from pathlib import Path
import re
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fix_viva_query_org import Package, require  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = (
    ROOT / "1. Local CSV" / "Consumption Central - Local CSV.pbit",
    ROOT / "2. Fabric" / "Consumption Central - Fabric.pbit",
    ROOT / "3. Viva Direct" / "Consumption Central - Viva Direct.pbit",
)

VISUAL = re.compile(
    r"^Report/definition/pages/([^/]+)/visuals/([^/]+)/visual\.json$")

GROUP_BY_REF = "Group By.Attribute"
SERVICE_REF = "CreditsWeekly.ServiceName"
OLD_ATTRIBUTE = "'Department'"
NEW_ATTRIBUTE = "'All users'"
BUTTON_SLICER = "advancedSlicerVisual"
LIST_SLICER = "slicer"

# Every page that ships the Department default, and every page that ships the
# button slicer. Named so a template that has drifted fails loudly rather than
# being patched into a shape nobody reviewed.
EXPECTED_GROUP_BY = 5
EXPECTED_SERVICE = 4

# The rail runs 222 wide with the next slicer at y=167; the button slicer sits at
# y=69 h=88. A list slicer also has to show a header, so it takes the spare room
# up to a 4px gap and no further.
SERVICE_HEIGHT = 94
SERVICE_NEXT_Y = 167

# Lifted from the "GROUP BY" slicer on the same pages so the two match.
HEADER_SIZE = "9D"
HEADER_TEXT = "'SERVICE'"


def literal(value):
    return {"expr": {"Literal": {"Value": value}}}


def service_objects(existing):
    """A list slicer's objects, keeping the button slicer's selection rules."""
    selection = existing.get("selection")
    require(selection is not None, "ServiceName slicer has no selection object")
    return {
        "header": [{"properties": {
            "show": literal("true"),
            "textSize": literal(HEADER_SIZE),
            "fontColor": {"solid": {"color": {
                "expr": {"ThemeDataColor": {"ColorId": 1, "Percent": 0.4}}}}},
            "text": literal(HEADER_TEXT),
        }}],
        "selection": selection,
        "items": [{"properties": {"textSize": literal(HEADER_SIZE)}}],
        "general": [{"properties": {"responsive": literal("false")},
                     "selector": {"id": "default"}}],
        "data": [{"properties": {"mode": literal("'Basic'")}}],
    }


def projection_ref(visual):
    projections = (visual.get("query", {}).get("queryState", {})
                   .get("Values", {}).get("projections", []))
    if len(projections) != 1:
        return None
    return projections[0].get("queryRef")


def selected_values(visual):
    """Return (general entry, values) for the slicer's saved selection."""
    for entry in visual.get("objects", {}).get("general", []):
        stored = entry.get("properties", {}).get("filter")
        if not stored:
            continue
        where = stored.get("filter", {}).get("Where", [])
        values = []
        for clause in where:
            for group in clause.get("Condition", {}).get("In", {}).get("Values", []):
                for item in group:
                    values.append(item.get("Literal", {}).get("Value"))
        return entry, values
    return None, []


def dump(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def patch_group_by(document):
    """Swap a Department default for All users, leaving the rest untouched."""
    visual = document["visual"]
    entry, values = selected_values(visual)
    if values != [OLD_ATTRIBUTE]:
        return []
    require(entry is not None, "Department default without a filter object")
    where = entry["properties"]["filter"]["filter"]["Where"]
    require(len(where) == 1, "Group By slicer has more than one filter clause")
    condition = where[0]["Condition"]["In"]
    old = [[{"Literal": {"Value": OLD_ATTRIBUTE}}]]
    new = [[{"Literal": {"Value": NEW_ATTRIBUTE}}]]
    require(condition["Values"] == old, "Unexpected Group By selection shape")
    condition["Values"] = new
    return [(f'"Values":{dump(old)}', f'"Values":{dump(new)}')]


def patch_service(document):
    """Turn the button slicer into the ordinary list slicer beside it."""
    visual = document["visual"]
    if visual["visualType"] != BUTTON_SLICER:
        return []
    position = document["position"]
    height = position["height"]
    require(position["y"] + SERVICE_HEIGHT < SERVICE_NEXT_Y,
            "Resized ServiceName slicer would reach the slicer below it")
    _, values = selected_values(visual)
    require(values == [], "ServiceName slicer carries a saved selection")
    old_objects = visual.get("objects", {})
    new_objects = service_objects(old_objects)
    edits = [
        (f'"visualType":{dump(BUTTON_SLICER)}', f'"visualType":{dump(LIST_SLICER)}'),
        (f'"objects":{dump(old_objects)}', f'"objects":{dump(new_objects)}'),
        (f'"height":{dump(height)}', f'"height":{dump(SERVICE_HEIGHT)}'),
    ]
    visual["visualType"] = LIST_SLICER
    visual["objects"] = new_objects
    position["height"] = SERVICE_HEIGHT
    return edits


def apply_edits(name, text, edits):
    """Splice the text, so every byte this script did not intend to move stays."""
    for old, new in edits:
        require(text.count(old) == 1,
                f"{name}: expected exactly one {old[:40]}..., "
                f"found {text.count(old)}")
        text = text.replace(old, new)
    return text


def patch_document(name, raw):
    """Return patched bytes for one visual, or None if it needs no change."""
    text = raw.decode("utf-8")
    document = json.loads(text)
    visual = document.get("visual", {})
    ref = projection_ref(visual)
    before = copy.deepcopy(document)

    if ref == GROUP_BY_REF and visual.get("visualType") == LIST_SLICER:
        edits = patch_group_by(document)
        kind = "group-by"
    elif ref == SERVICE_REF:
        edits = patch_service(document)
        kind = "service"
    else:
        return None, None

    if not edits:
        return None, None
    require(document != before, f"{name}: patch reported a change but made none")
    patched = apply_edits(name, text, edits)
    # The splices are only trusted once they reparse into the reviewed document.
    require(json.loads(patched) == document,
            f"{name}: patched text does not match the intended document")
    return kind, patched.encode("utf-8")


def collect(package):
    """Every visual part this script is allowed to touch, in archive order."""
    return [n for n in package.local_order if VISUAL.match(n)]


def validate(original, candidate_bytes, updates):
    candidate = Package(candidate_bytes, parts=updates.keys())
    require(list(original.infos) == list(candidate.infos),
            "Candidate changed ZIP parts/order")
    require(original.local_order == candidate.local_order,
            "Candidate changed local order")
    require(original.prefix == candidate.prefix
            and original.comment == candidate.comment,
            "Candidate changed archive prefix/comment")
    before_end = bytearray(original.end_record)
    after_end = bytearray(candidate.end_record)
    before_end[12:20] = after_end[12:20]
    require(before_end == after_end, "Candidate changed end-record metadata")
    for name in original.infos:
        before = bytearray(original.central[name])
        after = candidate.central[name]
        before[42:46] = after[42:46]
        if name in updates:
            before[16:28] = after[16:28]
            old_header_end, old_payload_end = original.payloads[name]
            new_header_end, new_payload_end = candidate.payloads[name]
            old_header = bytearray(original.locals[name][:old_header_end])
            new_header = candidate.locals[name][:new_header_end]
            old_header[14:26] = new_header[14:26]
            require(old_header == new_header, f"{name}: changed local metadata")
            require(original.locals[name][old_payload_end:]
                    == candidate.locals[name][new_payload_end:],
                    f"{name}: changed local trailer")
        else:
            require(original.locals[name] == candidate.locals[name],
                    f"{name}: changed raw local record/compressed bytes")
        require(before == after, f"{name}: changed central-directory metadata")
        require(candidate.contents[name]
                == updates.get(name, original.contents[name]),
                f"{name}: candidate content mismatch")
    # Nothing outside the four Cowork pages' visuals may move.
    for name in updates:
        require(VISUAL.match(name), f"{name}: not a report visual")
        json.loads(candidate.contents[name])


def patch(path, dry_run=False):
    path = Path(path).resolve()
    require(path.is_file(), f"Source does not exist: {path}")
    raw = path.read_bytes()
    visuals = collect(Package(raw, parts=()))
    original = Package(raw, parts=visuals)

    updates = {}
    counts = {"group-by": 0, "service": 0}
    for name in visuals:
        kind, patched = patch_document(name, original.contents[name])
        if patched is None:
            continue
        updates[name] = patched
        counts[kind] += 1

    print(f"\n{path.name}")
    for kind, found in sorted(counts.items()):
        print(f"  {kind:10} visuals rewritten: {found}")

    if updates:
        require(counts["group-by"] == EXPECTED_GROUP_BY,
                f"{path.name}: expected {EXPECTED_GROUP_BY} Department defaults, "
                f"found {counts['group-by']}")
        require(counts["service"] == EXPECTED_SERVICE,
                f"{path.name}: expected {EXPECTED_SERVICE} button slicers, "
                f"found {counts['service']}")

    candidate_bytes = original.rebuild(updates)
    validate(original, candidate_bytes, updates)

    if not updates:
        print("  already patched; left byte-for-byte unchanged")
        return 0
    if dry_run:
        print("  dry run; nothing written")
        return len(updates)

    scratch = ROOT / f".fix-slicer-defaults-{uuid.uuid4().hex}.pbit"
    owned = False
    try:
        with scratch.open("xb") as stream:
            owned = True
            stream.write(candidate_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        written = scratch.read_bytes()
        require(written == candidate_bytes, "Scratch write verification failed")
        validate(original, written, updates)
        require(path.read_bytes() == raw,
                "Source changed during patch; refusing to publish")
        os.replace(scratch, path)
        owned = False
    finally:
        if owned:
            scratch.unlink()
    print(f"  validated patch written: {path}")
    return len(updates)


def patch_project(project, dry_run=False, only=None):
    """Patch an expanded PBIP project, where no signature covers the report."""
    project = Path(project).resolve()
    require(project.is_dir(), f"Project does not exist: {project}")
    visuals = sorted(project.glob("*.Report/definition/pages/*/visuals/*/visual.json"))
    require(bool(visuals), f"{project.name}: no PBIR visuals found")

    updates = {}
    counts = {"group-by": 0, "service": 0}
    for visual in visuals:
        name = visual.relative_to(project).as_posix()
        kind, patched = patch_document(name, visual.read_bytes())
        if patched is None or (only and kind != only):
            continue
        updates[visual] = patched
        counts[kind] += 1

    print(f"\n{project.name}  ({len(visuals)} visuals scanned)")
    for kind, found in sorted(counts.items()):
        print(f"  {kind:10} visuals rewritten: {found}")

    if not updates:
        print("  already patched; left unchanged")
        return 0

    expected = {"group-by": EXPECTED_GROUP_BY, "service": EXPECTED_SERVICE}
    for kind, total in expected.items():
        if only and kind != only:
            continue
        require(counts[kind] == total,
                f"{project.name}: expected {total} {kind} visuals, found {counts[kind]}")
    if dry_run:
        print("  dry run; nothing written")
        return len(updates)

    for visual, patched in updates.items():
        scratch = visual.with_name(f".{uuid.uuid4().hex}.tmp")
        owned = False
        try:
            with scratch.open("xb") as stream:
                owned = True
                stream.write(patched)
                stream.flush()
                os.fsync(stream.fileno())
            require(scratch.read_bytes() == patched, "Scratch write verification failed")
            os.replace(scratch, visual)
            owned = False
        finally:
            if owned:
                scratch.unlink()
    print(f"  {len(updates)} visuals written under {project}")
    return len(updates)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--path", type=Path, action="append",
                        help="Template to patch; defaults to all three")
    parser.add_argument("--pbip", type=Path, action="append",
                        help="Expanded PBIP project folder to patch instead")
    parser.add_argument("--only", choices=("group-by", "service"),
                        help="Apply just one of the two changes (for isolation)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate without writing files")
    args = parser.parse_args(argv)
    if args.pbip:
        require(not args.path, "Use either --path or --pbip, not both")
        for project in args.pbip:
            patch_project(project, dry_run=args.dry_run, only=args.only)
    else:
        require(not args.only, "--only is supported for --pbip projects")
        for template in (args.path or TEMPLATES):
            patch(template, dry_run=args.dry_run)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
