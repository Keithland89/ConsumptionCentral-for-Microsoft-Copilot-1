"""Resettle query bodies that drifted between the two model parts.

A .pbit stores every query twice: once in DataModelSchema, which is the
model, and once in UnappliedChanges, which is what Desktop would apply if
you clicked Apply changes on a pending edit. They are meant to agree.

A Desktop re-export trims trailing blank lines from the UnappliedChanges
copy but not from the schema copy, so queries whose M ends on a blank
line drift apart by one newline. M does not care - but
check_viva_query_org.py compares the two and fails the whole file, which
is why that check has been red on main with 25 errors reading

    VivaOrgFromMetrics: schema/UnappliedChanges source mismatch

The difference is whitespace at the very end of the body and nothing
else; this refuses to touch anything where that is not true, so it
cannot paper over a real divergence. The schema copy wins, because that
is the one the model actually loads.

    python docs/scripts/fix_query_body_drift.py --dry-run
    python docs/scripts/fix_query_body_drift.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fix_pbit_defaults import layout_for  # noqa: E402
from fix_viva_query_org import Package, PatchError, require  # noqa: E402

REPO = Path(__file__).resolve().parents[2]

TEMPLATES = (
    REPO / "1. Local CSV" / "Consumption Central - Local CSV.pbit",
    REPO / "2. Fabric" / "Consumption Central - Fabric.pbit",
    REPO / "3. Viva Direct" / "Consumption Central - Viva Direct.pbit",
)

SCHEMA = "DataModelSchema"
UNAPPLIED = "UnappliedChanges"


def as_text(body):
    return "\n".join(body) if isinstance(body, list) else body


def reshape(original, text):
    return text.split("\n") if isinstance(original, list) else text


def patch_template(path, dry_run):
    print(path.parent.name)
    package = Package(path.read_bytes())
    schema, encode_schema = layout_for(package.contents[SCHEMA], SCHEMA)
    unapplied, encode_unapplied = layout_for(package.contents[UNAPPLIED], UNAPPLIED)

    stored = {}
    for query in unapplied.get("queries", []):
        name = query.get("name")
        require(name not in stored, f"{name}: duplicate entry in UnappliedChanges")
        stored[name] = query

    repaired = []
    for expression in schema["model"].get("expressions", []):
        name = expression["name"]
        query = stored.get(name)
        if query is None:
            continue
        authoritative = as_text(expression["expression"])
        current = as_text(query["text"])
        if current == authoritative:
            continue
        # Whitespace at the end is the only difference this is allowed to
        # settle. Anything else is a genuine divergence and wants a human.
        require(current.rstrip() == authoritative.rstrip(),
                f"{name}: bodies differ by more than trailing whitespace")
        query["text"] = reshape(query["text"], authoritative)
        repaired.append(name)

    if not repaired:
        print("  no drift")
        return False
    for name in repaired:
        print(f"  {name} - UnappliedChanges resettled on the schema body")
    if dry_run:
        return True

    updates = {SCHEMA: encode_schema(schema), UNAPPLIED: encode_unapplied(unapplied)}
    rebuilt = package.rebuild(updates)

    check = Package(rebuilt)
    moved = sorted(n for n in package.contents
                   if check.contents[n] != package.contents[n])
    # The schema is re-encoded but unchanged, so only UnappliedChanges may move.
    require(moved == [UNAPPLIED], f"unexpected parts changed: {moved}")

    path.write_bytes(rebuilt)
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("templates", nargs="*", type=Path,
                        help="defaults to all three shipped templates")
    args = parser.parse_args(argv)

    changed = 0
    for path in (args.templates or list(TEMPLATES)):
        require(path.exists(), f"missing template: {path}")
        try:
            changed += bool(patch_template(path, args.dry_run))
        except PatchError as exc:
            print(f"  FAILED: {exc}", file=sys.stderr)
            return 1
    print(f"\n{changed} template(s) {'would be ' if args.dry_run else ''}repaired")
    return 0


if __name__ == "__main__":
    sys.exit(main())
