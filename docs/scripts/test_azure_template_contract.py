"""Offline regression tests against the packaged Azure reader expressions."""
import json
import unittest
import zipfile

from check_azure_template_contract import (
    CONTRACTS, ROOT, group_after, input_bindings, list_items, m_tokens, text,
)
from check_pbit_defaults import decode


def readers(path):
    with zipfile.ZipFile(path) as package:
        model = json.loads(decode(package.read("DataModelSchema")))["model"]
    return {
        table["name"]: text(table["partitions"][0]["source"]["expression"])
        for table in model["tables"] if table["name"] in CONTRACTS
    }


class AzureTemplateContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packaged = {
            label: readers(ROOT / folder / f"Consumption Central - {label}.pbit")
            for folder, label in (
                ("1. Local CSV", "Local CSV"),
                ("2. Fabric", "Fabric"),
                ("3. Viva Direct", "Viva Direct"),
            )
        }
        cls.legacy = readers(
            ROOT / "archive" / "Consumption Central - Local CSV 2026-09-03.pbit")

    def test_all_shipped_readers_pass(self):
        for label, queries in self.packaged.items():
            for name, query in queries.items():
                with self.subTest(label=label, name=name):
                    self.assertLessEqual(CONTRACTS[name], input_bindings(query))

    def test_actual_legacy_spend_and_tokens_pass(self):
        for name, query in self.legacy.items():
            with self.subTest(name=name):
                self.assertLessEqual(CONTRACTS[name], input_bindings(query))

    def test_canonical_mapping_does_not_need_lowercase_literal(self):
        query = self.packaged["Local CSV"]["AzureAiSpend"]
        self.assertNotIn('"resourcegroup"', query)
        self.assertIn('{"ResourceGroup", {"ResourceGroupName"}}', query)
        self.assertIn("ResourceGroup", input_bindings(query))

    def test_removing_each_canonical_spec_fails_despite_output_types(self):
        for label, queries in self.packaged.items():
            query = " ".join(m_tokens(queries["AzureAiSpend"]))
            specs = group_after(m_tokens(query), "Named = Normalize(Raw, {")
            for spec in list_items(specs):
                name = spec[1].strip('"')
                if name not in CONTRACTS["AzureAiSpend"]:
                    continue
                with self.subTest(label=label, name=name):
                    binding = " ".join(spec)
                    self.assertEqual(query.count(binding), 1)
                    broken = query.replace(binding + " ,", "", 1)
                    self.assertNotEqual(query, broken)
                    self.assertIn(f'"{name}" , type', broken)
                    self.assertNotIn(name, input_bindings(broken))

    def test_removing_legacy_binding_fails_despite_aliases_and_types(self):
        for query in (self.legacy["AzureAiSpend"],
                      self.packaged["Local CSV"]["AzureAiTokens"],
                      self.packaged["Fabric"]["AzureAiTokens"]):
            query = " ".join(m_tokens(query))
            renames = group_after(m_tokens(query), "Ren = List.RemoveNulls({")
            binding = next(" ".join(item) for item in list_items(renames)
                           if '"ResourceGroup"' in item)
            broken = query.replace(binding + " ,", "", 1)
            self.assertNotEqual(query, broken)
            self.assertIn('"ResourceGroup" , type text', broken)
            self.assertNotIn("ResourceGroup", input_bindings(
                broken + ' // "resourcegroup"\n'))
            for comment in (f"// {binding}\n", f"/* {binding} */",
                            f"/* outer /* nested */ {binding} */"):
                with self.subTest(comment=comment):
                    self.assertNotIn("ResourceGroup", input_bindings(comment + broken))

    def test_comments_and_strings_cannot_restore_missing_spec(self):
        query = " ".join(m_tokens(self.packaged["Local CSV"]["AzureAiSpend"]))
        binding = '{ "ResourceGroup" , { "ResourceGroupName" } }'
        broken = query.replace(binding + " ,", "", 1)
        self.assertNotEqual(query, broken)
        for decoy in (f"// {binding}\n", f"/* {binding} */",
                      f"/* outer /* nested */ {binding} */",
                      '"' + binding.replace('"', '""') + '"'):
            with self.subTest(decoy=decoy):
                self.assertNotIn("ResourceGroup", input_bindings(decoy + broken))

    def test_normalizer_requires_local_case_folding_and_binding_pipeline(self):
        query = self.packaged["Local CSV"]["AzureAiSpend"]
        replacements = (
            ('Text.Lower(Text.Select(s, {"a".."z", "A".."Z", "0".."9"}))',
             'Text.Select(s, {"a".."z", "A".."Z", "0".."9"})'),
            ("each Key(_) = Key(alias)", "each _ = alias"),
            ("each Key(_) = Key(alias)", "each Key(_) = alias"),
            ("{spec{0}} & spec{1}", "spec{1}"),
            ("List.Transform(Specs, each Pick(_))", "List.Transform(Required, each Pick(_))"),
            ("List.Transform(Specs, each _{0})", "List.Transform(Required, each _{0})"),
            ("else List.First(Best, null)", "else null"),
            ("List.Select(Candidates, each not List.IsEmpty(_))", "{}"),
            ("in\n    Result\n)", "in\n    Source\n)"),
            ("else Table.Column(Source, c)", "else {}"),
            ("Named = Normalize(Raw,", "Named = Other(Raw,"),
        )
        for old, new in replacements:
            with self.subTest(old=old):
                self.assertIn(old, query)
                broken = query.replace(old, new, 1)
                # The second, unrelated Key definition must not rescue the helper.
                self.assertIn("Text.Lower(Text.Select(s,", broken)
                self.assertFalse(input_bindings(broken + f"\n// {old}\n"))

    def test_spec_outside_normalize_call_cannot_restore_binding(self):
        query = " ".join(m_tokens(self.packaged["Local CSV"]["AzureAiSpend"]))
        binding = '{ "ResourceGroup" , { "ResourceGroupName" } }'
        broken = query.replace(binding + " ,", "", 1)
        self.assertNotEqual(query, broken)
        self.assertNotIn("ResourceGroup", input_bindings(
            f"let UnusedSpecs = {{ {binding} }} in ({broken})"))

    def test_legacy_requires_case_folding_find_and_rename(self):
        query = self.legacy["AzureAiSpend"]
        for old, new in (
            ('Text.Lower(Text.Remove(n, {" ", "_", "-"}))', "n"),
            ("List.Contains(aliases, Key(_))", "List.Contains(aliases, _)"),
            ("Table.RenameColumns(Headers, Ren,", "Table.RenameColumns(Headers, {},"),
        ):
            with self.subTest(old=old):
                self.assertIn(old, query)
                self.assertFalse(input_bindings(query.replace(old, new, 1)
                                                + f"\n/* {old} */"))

    def test_comment_markers_inside_strings_are_preserved(self):
        self.assertEqual(m_tokens('"https://example.invalid/*not a comment*/" // comment'),
                         ('"https://example.invalid/*not a comment*/"',))


if __name__ == "__main__":
    unittest.main()
