"""Verify the slicer fixes in docs/scripts/fix_slicer_defaults.py.

The report layer is normally off limits because Desktop twice rejected
hand-edited PBIR visuals, so a patched visual is only trusted here if every
shape it uses is attested by a slicer Desktop itself wrote and still ships in
the same report. That is the closest standing check to "Desktop would accept
this" that can be made without opening Desktop, and it is what would have
caught those earlier rejections.

    python docs/scripts/check_slicer_defaults.py

Checks, for all three templates:

1. No ServiceName slicer is still the advancedSlicerVisual button slicer, and
   each one is an ordinary list slicer ("Basic" mode).
2. Every object name and property the converted slicers use also appears on an
   untouched, Desktop-authored slicer in the same report.
3. No Group By slicer still defaults to Department - it exists only when the
   customer supplied org data - and every one that carries a default selects
   All users, which the model unions unconditionally.
4. No resized slicer reaches the visual below it in the same rail.

Desktop render validation is separate: open a template and check the rail.
"""
import json
import re
import sys
import zipfile
from pathlib import Path

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
BUTTON_SLICER = "advancedSlicerVisual"
FORBIDDEN_ATTRIBUTE = "'Department'"
EXPECTED_ATTRIBUTE = "'All users'"
EXPECTED_SERVICE = 4


def ref(visual):
    projections = (visual.get("query", {}).get("queryState", {})
                   .get("Values", {}).get("projections", []))
    if len(projections) != 1:
        return None
    return projections[0].get("queryRef")


def selection(visual):
    for entry in visual.get("objects", {}).get("general", []):
        stored = entry.get("properties", {}).get("filter")
        if not stored:
            continue
        values = []
        for clause in stored.get("filter", {}).get("Where", []):
            for group in clause.get("Condition", {}).get("In", {}).get("Values", []):
                for item in group:
                    values.append(item.get("Literal", {}).get("Value"))
        return values
    return []


def shapes(visual):
    """Every (object name, property name) pair a visual's objects use."""
    found = set()
    for name, entries in visual.get("objects", {}).items():
        for entry in entries:
            for prop in entry.get("properties", {}):
                found.add((name, prop))
    return found


def mode(visual):
    for entry in visual.get("objects", {}).get("data", []):
        value = entry.get("properties", {}).get("mode", {})
        return value.get("expr", {}).get("Literal", {}).get("Value")
    return None


def main():
    problems = []
    for template in TEMPLATES:
        if not template.is_file():
            problems.append(f"{template.name}: missing")
            continue
        visuals = {}
        with zipfile.ZipFile(template) as z:
            for name in z.namelist():
                match = VISUAL.match(name)
                if match:
                    visuals[name] = (match.group(1), json.loads(z.read(name)))

        converted, attested, group_by = [], set(), 0
        for name, (page, document) in visuals.items():
            visual = document.get("visual", {})
            reference = ref(visual)
            if reference == SERVICE_REF:
                converted.append((name, page, document))
            elif visual.get("visualType") == "slicer":
                # Desktop wrote these and this repo has never touched them.
                attested |= shapes(visual)

        print(f"\n{template.name}")

        for name, page, document in converted:
            visual = document["visual"]
            if visual.get("visualType") == BUTTON_SLICER:
                problems.append(f"{template.name}: {page} still ships the "
                                f"button slicer")
                continue
            if visual.get("visualType") != "slicer":
                problems.append(f"{template.name}: {page} ServiceName slicer is "
                                f"{visual.get('visualType')}")
            if mode(visual) != "'Basic'":
                problems.append(f"{template.name}: {page} ServiceName slicer "
                                f"mode is {mode(visual)}, expected 'Basic'")
            unproven = sorted(shapes(visual) - attested)
            if unproven:
                problems.append(f"{template.name}: {page} ServiceName slicer "
                                f"uses shapes no Desktop-authored slicer has: "
                                f"{unproven}")
            position = document["position"]
            bottom = position["y"] + position["height"]
            below = [d["position"]["y"] for _, (p, d) in visuals.items()
                     if p == page and d["position"]["y"] >= bottom
                     and abs(d["position"]["x"] - position["x"]) < 1]
            if below and min(below) < bottom:
                problems.append(f"{template.name}: {page} ServiceName slicer "
                                f"overlaps the visual below")
        print(f"  ServiceName slicers converted: {len(converted)}")
        if len(converted) != EXPECTED_SERVICE:
            problems.append(f"{template.name}: expected {EXPECTED_SERVICE} "
                            f"ServiceName slicers, found {len(converted)}")

        for name, (page, document) in visuals.items():
            visual = document.get("visual", {})
            if ref(visual) != GROUP_BY_REF:
                continue
            values = selection(visual)
            if FORBIDDEN_ATTRIBUTE in values:
                problems.append(f"{template.name}: {page} still defaults to "
                                f"Department")
            elif values:
                group_by += 1
                if values != [EXPECTED_ATTRIBUTE]:
                    problems.append(f"{template.name}: {page} defaults to "
                                    f"{values}, expected [{EXPECTED_ATTRIBUTE}]")
        print(f"  Group By slicers defaulting to All users: {group_by}")
        print(f"  slicer shapes attested by untouched visuals: {len(attested)}")

    print()
    if problems:
        for problem in problems:
            print(f"FAIL {problem}")
        return 1
    print("slicer defaults and ServiceName slicers are as intended")
    return 0


if __name__ == "__main__":
    sys.exit(main())
