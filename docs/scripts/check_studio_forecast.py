"""Check the shipped Studio DAX, visual bindings, and synthetic forecast cases."""

import copy
from pathlib import Path
import unittest

import fix_studio_forecast as fix


class StudioForecastContracts(unittest.TestCase):
    def test_all_active_templates_contain_current_forecast(self):
        manifest = fix.load_json(fix.MANIFEST_PATH)
        for relative in manifest["activeTemplates"]:
            with self.subTest(template=relative):
                path = fix.ROOT.joinpath(*relative.replace("\\", "/").split("/"))
                package = fix.Package(path.read_bytes())
                schema, _ = fix.decode_part(package.contents["DataModelSchema"], "DataModelSchema")
                before = copy.deepcopy(schema)
                self.assertEqual(fix.patch_schema(schema), ([], []))
                self.assertEqual(schema, before)
                fix.ensure_report_bindings(package, manifest)

    def test_synthetic_requirements(self):
        self.assertEqual(fix.run_self_test(), 0)

    def test_missing_dates_and_zero_history_are_explicit(self):
        dax = fix.source_text(fix.NEW_MEASURES["Studio Fitted Monthly Growth %"]["expression"])
        self.assertIn("COALESCE(", dax)
        self.assertIn("COUNTROWS( FILTER( _daily, [@credits] > 0 ) ) >= 7", dax)
        self.assertIn("EXP( _boundedSlope )", dax)

    def test_projection_headlines_use_selected_growth(self):
        for name in ("Projected Credits (30d)", "Projected Credits (Horizon)"):
            expression = fix.source_text(fix.UPDATED_MEASURES[name]["expression"])
            self.assertIn("[Studio Growth Applied %]", expression)

    def test_decline_and_extreme_ramps_are_bounded(self):
        decline = [120 * (0.85 ** (day / 30)) for day in range(90)]
        self.assertAlmostEqual(fix.fit_growth(decline), -0.15, delta=0.01)
        ramp = [120 * (10001 ** (day / 30)) for day in range(30)]
        self.assertAlmostEqual(fix.fit_growth(ramp), 0.30)


if __name__ == "__main__":
    unittest.main()
