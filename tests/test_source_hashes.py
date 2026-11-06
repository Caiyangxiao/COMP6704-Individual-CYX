"""Prove EOL-only compatibility without weakening historical raw identities.

These tests use temporary byte fixtures and mocked saved-data audits. They do
not execute a solver, alter a historical result, or copy an expected hash into
an observed/canonical hash field.
"""
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from provenance_integrity import (
    compare_environment, inspect_source_bytes, inspect_source_file,
)
import validate_study


def digest(data):
    return sha256(data).hexdigest()


def historical_environment():
    return {
        "python": "3.12.8 (historical build)", "numpy": "1.26.4", "scipy": "1.13.1",
        "platform": "Windows-reference", "processor": "reference CPU", "logical_cpu_count": 24,
        "thread_environment": {"OMP_NUM_THREADS": "1"},
    }


def current_environment():
    return {
        "python_version": "3.12.8", "python_build": "3.12.8 (historical build)",
        "numpy": "1.26.4", "scipy": "1.13.1", "platform": "Windows-reference",
        "processor": "reference CPU", "logical_cpu_count": 24,
        "thread_environment": {"OMP_NUM_THREADS": "1"},
    }


class SourceHashTests(unittest.TestCase):
    def test_exact_bytes_take_priority_over_eol_fallback(self):
        for actual in (b"value = 1\n", b"value = 1\r\n", b"value = 1\r"):
            with self.subTest(actual=actual):
                result = inspect_source_bytes(actual, digest(actual))
                self.assertTrue(result["passed"])
                self.assertEqual(result["match_kind"], "byte_exact")
                self.assertTrue(result["raw_comparison"]["matches"])
                self.assertFalse(result["eol_equivalence"]["checked"])
                self.assertEqual(result["eol_equivalence"]["variants"], {})

    def test_lf_actual_proves_identity_to_historical_crlf_bytes(self):
        actual = b"# same source\nvalue = 1\n"
        historical = actual.replace(b"\n", b"\r\n")
        result = inspect_source_bytes(actual, digest(historical))
        self.assertTrue(result["passed"])
        self.assertEqual(result["match_kind"], "eol_equivalent")
        self.assertEqual(result["actual_raw_sha256"], digest(actual))
        self.assertEqual(result["expected_raw_sha256"], digest(historical))
        self.assertFalse(result["raw_comparison"]["matches"])
        proof = result["eol_equivalence"]
        self.assertTrue(proof["proved"])
        self.assertEqual(proof["matching_variants"], ["crlf_only"])
        self.assertEqual(proof["variants"]["lf_only"]["reconstructed_actual_sha256"], digest(actual))
        self.assertEqual(proof["variants"]["crlf_only"]["reconstructed_actual_sha256"], digest(historical))

    def test_crlf_actual_proves_identity_to_historical_lf_bytes(self):
        historical = b"# same source\nvalue = 1\n"
        actual = historical.replace(b"\n", b"\r\n")
        result = inspect_source_bytes(actual, digest(historical))
        self.assertTrue(result["passed"])
        self.assertFalse(result["raw_comparison"]["matches"])
        self.assertEqual(result["eol_equivalence"]["matching_variants"], ["lf_only"])
        self.assertEqual(result["actual_raw_sha256"], digest(actual))

    def test_mixed_actual_eol_requires_a_matching_reconstructed_historical_hash(self):
        actual = b"a = 1\r\nb = 2\nc = 3\r\n"
        lf = b"a = 1\nb = 2\nc = 3\n"
        for historical, variant in ((lf, "lf_only"), (lf.replace(b"\n", b"\r\n"), "crlf_only")):
            with self.subTest(variant=variant):
                result = inspect_source_bytes(actual, digest(historical))
                self.assertTrue(result["passed"])
                self.assertEqual(result["line_endings"], {"crlf": 2, "lf_only": 1, "bare_cr": 0})
                self.assertEqual(result["eol_equivalence"]["matching_variants"], [variant])

    def test_mixed_historical_eol_is_not_invented_from_an_unmatched_digest(self):
        historical = b"a = 1\r\nb = 2\n"
        actual = b"a = 1\nb = 2\n"
        result = inspect_source_bytes(actual, digest(historical))
        self.assertFalse(result["passed"])
        self.assertFalse(result["eol_equivalence"]["proved"])
        self.assertEqual(result["eol_equivalence"]["matching_variants"], [])

    def test_code_edit_is_rejected_even_when_eol_also_changes(self):
        historical = b"value = 1\r\n"
        actual = b"value = 2\n"
        result = inspect_source_bytes(actual, digest(historical))
        self.assertFalse(result["passed"])
        self.assertEqual(result["actual_raw_sha256"], digest(actual))
        self.assertEqual(result["expected_raw_sha256"], digest(historical))
        self.assertTrue(result["errors"])
        self.assertFalse(any(item["matches_historical_raw_sha256"]
                             for item in result["eol_equivalence"]["variants"].values()))

    def test_bare_cr_is_rejected_when_raw_bytes_differ(self):
        result = inspect_source_bytes(b"a = 1\rb = 2\n", digest(b"a = 1\nb = 2\n"))
        self.assertFalse(result["passed"])
        self.assertEqual(result["match_kind"], "rejected_bare_cr")
        self.assertEqual(result["line_endings"]["bare_cr"], 1)
        self.assertFalse(result["eol_equivalence"]["checked"])

    def test_bom_whitespace_and_trailing_newline_are_not_discarded(self):
        historical = b"value = 1\r\n"
        for actual in (b"\xef\xbb\xbfvalue = 1\n", b"value = 1 \n", b"value = 1"):
            with self.subTest(actual=actual):
                self.assertFalse(inspect_source_bytes(actual, digest(historical))["passed"])
        original_with_bom = b"\xef\xbb\xbfvalue = 1\r\n"
        equivalent = original_with_bom.replace(b"\r\n", b"\n")
        self.assertTrue(inspect_source_bytes(equivalent, digest(original_with_bom))["passed"])

    def test_missing_file_has_no_fabricated_actual_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = inspect_source_file(Path(tmp) / "absent.py", digest(b"value = 1\n"))
        self.assertFalse(result["passed"])
        self.assertFalse(result["exists"])
        self.assertIsNone(result["actual_raw_sha256"])
        self.assertEqual(result["match_kind"], "missing_or_unreadable")
        self.assertTrue(result["errors"])

    def test_invalid_historical_digest_cannot_be_accepted(self):
        for expected in (None, "", "not-a-sha256"):
            with self.subTest(expected=expected):
                result = inspect_source_bytes(b"value = 1\n", expected)
                self.assertFalse(result["passed"])
                self.assertEqual(result["match_kind"], "invalid_expected_digest")


class EnvironmentAndOutputTests(unittest.TestCase):
    def test_matching_versions_keep_platform_differences_explicit(self):
        actual = current_environment()
        actual.update(platform="Linux-other", processor="different CPU", logical_cpu_count=8)
        result = compare_environment(historical_environment(), actual)
        self.assertTrue(result["passed"])
        self.assertFalse(result["platform_context_identical"])
        self.assertFalse(result["platform_context"]["platform"]["matches"])
        self.assertTrue(all(item["matches"] for item in result["required_versions"].values()))

    def test_numerical_version_mismatches_are_errors(self):
        for name, version in (("scipy", "1.14.0"), ("numpy", "2.0.0"), ("python_version", "3.12.9")):
            actual = current_environment()
            actual[name] = version
            with self.subTest(name=name):
                result = compare_environment(historical_environment(), actual)
                self.assertFalse(result["passed"])
                self.assertTrue(result["errors"])

    @contextmanager
    def saved_project(self, source_mode="exact", scipy_version="1.13.1"):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            reference = project / "reference"
            reference.mkdir()
            historical = b"value = 1\r\n"
            source = project / "module.py"
            if source_mode != "missing":
                source.write_bytes({"exact": historical, "eol": b"value = 1\n", "edit": b"value = 2\r\n"}[source_mode])
            scipy_path = project / "_optimize_fixture.py"
            scipy_path.write_bytes(b"# trusted scipy fixture\n")
            metadata = historical_environment()
            metadata.update(source_sha256={"module.py": digest(historical)},
                            scipy_optimize_source_sha256=digest(scipy_path.read_bytes()),
                            started_at="2026-11-05T20:04:35+08:00")
            (reference / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
            actual = current_environment()
            actual["scipy"] = scipy_version
            data = {"passed": True, "errors": [], "warnings": [],
                    "counts": {"summary_rows": 90}, "result_label_totals": {"stationary": 73}}
            with patch.object(validate_study, "validate_data", return_value=data), \
                    patch.object(validate_study, "environment_snapshot", return_value=actual), \
                    patch.object(validate_study, "scipy_source_path", return_value=scipy_path):
                yield project, reference

    def test_eol_proof_does_not_replace_raw_equality(self):
        with self.saved_project(source_mode="eol") as (project, reference):
            report = validate_study.validate(reference, project)
        self.assertTrue(report["passed"])
        self.assertTrue(report["data_internal_integrity"]["passed"])
        self.assertEqual(report["source_integrity"]["eol_equivalent_files"], 1)
        source = report["source_integrity"]["files"]["module.py"]
        self.assertFalse(source["raw_comparison"]["matches"])
        self.assertTrue(source["eol_equivalence"]["proved"])

    def test_source_or_version_failure_keeps_data_passed_and_cli_nonzero(self):
        for mode, version, category in (("edit", "1.13.1", "source_integrity"),
                                        ("missing", "1.13.1", "source_integrity"),
                                        ("exact", "1.14.0", "environment_match")):
            with self.subTest(mode=mode, version=version):
                with self.saved_project(mode, version) as (project, reference):
                    historical_metadata = (reference / "metadata.json").read_bytes()
                    report = validate_study.validate(reference, project)
                    self.assertTrue(report["data_internal_integrity"]["passed"])
                    self.assertFalse(report["passed"])
                    self.assertFalse(report[category]["passed"])
                    if category == "environment_match":
                        self.assertTrue(report["source_integrity"]["passed"])
                    destination = project / "separate_audit.json"
                    with patch.object(validate_study, "validate", return_value=report), redirect_stdout(StringIO()):
                        code = validate_study.main(["--results", str(reference), "--output", str(destination)])
                    self.assertEqual(code, 1)
                    saved = json.loads(destination.read_text(encoding="utf-8"))
                    self.assertTrue(saved["data_internal_integrity"]["passed"])
                    self.assertFalse(saved["passed"])
                    self.assertEqual((reference / "metadata.json").read_bytes(), historical_metadata)

    def test_output_is_refused_inside_reference_or_any_results_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = root / "reference"
            for destination in (reference / "validation.json", root / "other/results/audit.json",
                                root / "other/Results/audit.json", root / "configs/overwrite.json"):
                with self.subTest(destination=destination):
                    with self.assertRaises(ValueError):
                        validate_study.check_output_destination(destination, reference, root)
            allowed = root / "audits/revision_20261105/current_validation.json"
            self.assertEqual(validate_study.check_output_destination(allowed, reference, root), allowed.resolve())

    def test_cli_refusal_does_not_validate_or_overwrite_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            reference = Path(tmp) / "reference"
            reference.mkdir()
            historical = reference / "validation.json"
            historical.write_text("historical evidence", encoding="utf-8")
            with patch.object(validate_study, "validate") as audit, redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as stopped:
                    validate_study.main(["--results", str(reference), "--output", str(historical)])
            self.assertEqual(stopped.exception.code, 2)
            audit.assert_not_called()
            self.assertEqual(historical.read_text(encoding="utf-8"), "historical evidence")

    def test_default_output_is_a_separate_current_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            reference = directory / "reference"
            reference.mkdir()
            history = reference / "metadata.json"
            history.write_text("historical evidence", encoding="utf-8")
            report = {"passed": True, "data_internal_integrity": {"passed": True},
                      "source_integrity": {"passed": True}, "environment_match": {"passed": True},
                      "counts": {}, "result_label_totals": {}, "errors": []}
            previous_directory = Path.cwd()
            try:
                os.chdir(directory)
                with patch.object(validate_study, "validate", return_value=report), redirect_stdout(StringIO()):
                    code = validate_study.main(["--results", str(reference)])
            finally:
                os.chdir(previous_directory)
            self.assertEqual(code, 0)
            self.assertTrue((directory / "audits/current_validation.json").is_file())
            self.assertEqual(history.read_text(encoding="utf-8"), "historical evidence")
            self.assertFalse((reference / "analysis/validation.json").exists())


if __name__ == "__main__":
    unittest.main()
