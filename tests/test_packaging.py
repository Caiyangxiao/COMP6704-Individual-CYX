"""Protect the distinction between current packaging proof and historical records."""
from pathlib import Path
from hashlib import sha256
import json
import tempfile
import unittest
import zipfile

from paper_source.package_reproducibility import select_files
from delivery_integrity import verify_archive_snapshot


class PackagingSelectionTests(unittest.TestCase):
    def test_current_report_is_excluded_but_history_remains_accessible(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current = root / "audits/revision_20261105/packaging_verification.json"
            historical = root / "audits/history/packaging_before_revision_20261105.json"
            for path in (current, historical):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")
            selected = select_files(root, exclude_paths=(current,))
            self.assertNotIn(current.relative_to(root), selected)
            self.assertIn(historical.relative_to(root), selected)

    def test_outer_delivery_records_are_not_code_archive_members(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record = root / "submission/packaging_verification.json"
            record.parent.mkdir()
            record.write_text("{}", encoding="utf-8")
            (root / "README.md").write_text("reproduce", encoding="utf-8")
            selected = select_files(root)
            self.assertEqual(selected, [Path("README.md")])


class DeliverySnapshotTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory)
        source = root / "README.md"
        source.write_bytes(b"current paper and evidence\n")
        archive = root / "bundle.zip"
        record = {"sha256": sha256(source.read_bytes()).hexdigest(), "size_bytes": source.stat().st_size}
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("README.md", source.read_bytes())
            bundle.writestr("archive_manifest.json", json.dumps({"files": {"README.md": record}}))
        return root, source, archive

    def test_matching_report_snapshot_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root, source, archive = self.fixture(directory)
            self.assertTrue(verify_archive_snapshot(archive, root, ("README.md",))["passed"])

    def test_old_archive_cannot_be_attached_to_new_report_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root, source, archive = self.fixture(directory)
            source.write_bytes(b"revised paper\n")
            with self.assertRaisesRegex(ValueError, "Current source differs"):
                verify_archive_snapshot(archive, root)

    def test_required_report_source_missing_from_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root, source, archive = self.fixture(directory)
            with self.assertRaisesRegex(ValueError, "Required current report source is absent"):
                verify_archive_snapshot(archive, root, ("paper_source/content.json",))


if __name__ == "__main__":
    unittest.main()
