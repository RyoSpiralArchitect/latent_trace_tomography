"""Bilingual entry points, executable examples, and immutable archive identities."""

import hashlib
import json
from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
PAIRS = (
    "README.md",
    "CONTRIBUTING.md",
    "RESPONSIBLE_USE.md",
    "docs/README.md",
    "reports/output_only_bridge_20261023/README.md",
    "successors/oss_reliance_regime_v0/output_only_bridge_v2/README.md",
    "docs/next_bridge_pilot.md",
    "reports/gpt6luna_answer_mapping_20261031/README.md",
    "successors/oss_reliance_regime_v0/output_contract_probe_v1/README.md",
)


def japanese(path):
    return path.with_name(path.stem + ".ja.md")


def command_blocks(text):
    return re.findall(r"(?:```|~~~)(?:bash|sh)\n(.*?)(?:```|~~~)", text, re.S)


class DocumentationTests(unittest.TestCase):
    def test_gpt6luna_report_counts_match_both_languages(self):
        report = ROOT / "reports/gpt6luna_answer_mapping_20261031/README.md"
        analysis = json.loads((report.parent / "data/analysis.json").read_text())
        groups = analysis["prespecified_format_secondary"]["by_condition"]
        names = (
            "full_task/direct",
            "full_task/standard",
            "full_task/inverted",
            "mapping_only/standard",
            "mapping_only/inverted",
        )
        expected = [
            [
                f"{groups[k]['correct_under_frozen_parser']}/{groups[k]['n']}",
                str(groups[k]["exact_marker"]),
                str(groups[k]["bare_symbol"]),
            ]
            for k in names
        ]
        expected.append(["112/112", "86", "26"])
        for path in (report, japanese(report)):
            rows = [
                [c.strip() for c in line.strip("|").split("|")][1:]
                for line in path.read_text().splitlines()
                if line.startswith("|") and re.search(r"\| \d+/\d+ \|", line)
            ]
            self.assertEqual(rows, expected)

    def test_language_pairs_link_to_each_other(self):
        for name in PAIRS:
            english = ROOT / name
            translated = japanese(english)
            with self.subTest(path=name):
                self.assertIn(f"]({translated.name})", english.read_text())
                self.assertIn(f"]({english.name})", translated.read_text())

    def test_translated_commands_remain_identical(self):
        for name in PAIRS:
            path = ROOT / name
            with self.subTest(path=name):
                self.assertEqual(
                    command_blocks(path.read_text()), command_blocks(japanese(path).read_text())
                )

    def test_local_documentation_links_resolve(self):
        for name in PAIRS:
            for path in (ROOT / name, japanese(ROOT / name)):
                for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
                    parsed = urlsplit(target)
                    if parsed.scheme or not parsed.path:
                        continue
                    with self.subTest(path=path.relative_to(ROOT), target=target):
                        self.assertTrue((path.parent / unquote(parsed.path)).exists())

    def test_report_counts_match_both_languages_and_saved_analysis(self):
        report = ROOT / "reports/output_only_bridge_20261023/README.md"
        analysis = json.loads((report.parent / "data/analysis.json").read_text())
        expected = {}
        for row in analysis["per_projection"]:
            counts = expected.setdefault(row["target_id"][-2:], [0, 0, 0])
            if row["projection_id"].startswith("weak_"):
                counts[0] += row["semantic_consistent"]
            else:
                counts[1] += row["semantic_consistent"]
                counts[2] += row["parseable"]
        for path in (report, japanese(report)):
            actual = {}
            for line in path.read_text().splitlines():
                if re.match(r"\| \d{2} \|", line):
                    cells = [cell.strip() for cell in line.strip("|").split("|")]
                    actual[cells[0]] = [int(cell) for cell in cells[-3:]]
            with self.subTest(path=path.name):
                self.assertEqual(actual, expected)

    def test_translation_preserves_all_as_run_source_hashes(self):
        manifest = json.loads(
            (ROOT / "reports/output_only_bridge_20261023/data/manifest.json").read_text()
        )
        archive = ROOT / "successors/oss_reliance_regime_v0/output_only_bridge_v1"
        self.assertEqual(len(manifest["archived_source_sha256"]), 6)
        for name, expected in manifest["archived_source_sha256"].items():
            with self.subTest(source=name):
                self.assertEqual(
                    hashlib.sha256((archive / name).read_bytes()).hexdigest(), expected
                )


if __name__ == "__main__":
    unittest.main()
