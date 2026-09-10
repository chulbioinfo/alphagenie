"""The language guard catches literal and JSON-escaped script regressions."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.language_check import check_english_release


class EnglishReleaseTests(unittest.TestCase):
    def test_english_scientific_symbols_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "methods.md"
            path.write_text("RNA Δ = ALT − REF; 1,000 × 371; FDR ≤ 0.05; Brain9 → cortex\n")
            self.assertEqual(check_english_release([path]), 1)

    def test_literal_and_json_escaped_non_english_scripts_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            for name in ("comment.py", "metadata.json"):
                path = Path(temporary) / name
                sample = chr(0xAC00)
                path.write_text(json.dumps({"note": sample}) if path.suffix == ".json" else "# " + sample)
                with self.assertRaisesRegex(ValueError, "Non-English script"):
                    check_english_release([path])
