from __future__ import annotations

import pathlib
import tempfile
import unittest

from verify_dependency_lock import LockError, normalize_name, parse_pins, verify_contract


class DependencyLockTests(unittest.TestCase):
    def write_requirements(self, text: str) -> pathlib.Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = pathlib.Path(directory.name) / "requirements.txt"
        path.write_text(text, encoding="utf-8")
        return path

    def test_name_normalization_matches_python_distribution_rules(self) -> None:
        self.assertEqual(normalize_name("typing_extensions"), "typing-extensions")
        self.assertEqual(normalize_name("JSONSchema.Specifications"), "jsonschema-specifications")

    def test_parser_rejects_floating_requirement(self) -> None:
        path = self.write_requirements("numpy>=2\n")
        with self.assertRaisesRegex(LockError, "exact name==version pin"):
            parse_pins(path)

    def test_parser_rejects_duplicate_normalized_name(self) -> None:
        path = self.write_requirements("typing_extensions==4.16.0\ntyping-extensions==4.16.0\n")
        with self.assertRaisesRegex(LockError, "duplicate normalized package"):
            parse_pins(path)

    def test_direct_requirement_must_match_lock(self) -> None:
        with self.assertRaisesRegex(LockError, "direct requirements disagree with lock"):
            verify_contract(
                {"numpy": "2.5.3"},
                {"numpy": "2.5.2"},
                {"numpy": "2.5.2"},
            )

    def test_installed_environment_must_match_lock_exactly(self) -> None:
        with self.assertRaisesRegex(LockError, "installed environment disagrees with lock"):
            verify_contract(
                {"numpy": "2.5.3"},
                {"numpy": "2.5.3", "scipy": "1.18.1"},
                {"numpy": "2.5.2", "extra": "1.0"},
            )

    def test_exact_contract_passes(self) -> None:
        verify_contract(
            {"numpy": "2.5.3"},
            {"numpy": "2.5.3", "scipy": "1.18.1"},
            {"numpy": "2.5.3", "scipy": "1.18.1"},
        )


if __name__ == "__main__":
    unittest.main()
