"""Run existing and added unit tests; write a dated audit outside saved results.

Example: python run_tests_audit.py --output audits/local_check/unit_tests.json
Temporary unit-test fixtures are not new formal benchmark experiments.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import importlib.metadata
import io
import json
from pathlib import Path
import platform
import sys
import tempfile
import unittest

from validate_study import check_output_destination

ROOT = Path(__file__).resolve().parent


def test_ids(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from test_ids(item)
        else:
            yield item.id()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("audits/current_unit_tests.json"))
    args = parser.parse_args()
    try:
        output = check_output_destination(args.output, ROOT / "results/full_study", ROOT)
    except ValueError as error:
        parser.error(str(error))
    started = datetime.now(timezone(timedelta(hours=8))).isoformat()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    ids = list(test_ids(suite))
    stream = io.StringIO()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="unit_test_fixtures_", dir=output.parent) as temporary:
        previous_tempdir = tempfile.tempdir
        try:
            tempfile.tempdir = temporary
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        finally:
            tempfile.tempdir = previous_tempdir
    versions = {}
    for package in ("numpy", "scipy", "matplotlib"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    record = {
        "schema_version": 1,
        "scope": "Existing and source-hash unit tests; no new formal benchmark runs",
        "started_at": started,
        "finished_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "timezone": "Asia/Shanghai",
        "environment": {"python": sys.version, "executable": sys.executable,
                        "platform": platform.platform(), "package_versions": versions},
        "passed": result.wasSuccessful(), "tests_discovered": len(ids),
        "tests_run": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "skipped": len(result.skipped),
        "test_ids": ids,
        "failure_details": [{"test": test.id(), "traceback": detail}
                            for test, detail in result.failures],
        "error_details": [{"test": test.id(), "traceback": detail}
                          for test, detail in result.errors],
        "test_sources": {path.relative_to(ROOT).as_posix(): sha256(path.read_bytes()).hexdigest()
                         for path in sorted((ROOT / "tests").glob("*.py"))},
        "runner_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    output.with_suffix(".log").write_text(stream.getvalue(), encoding="utf-8")
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: record[key] for key in ("passed", "tests_run", "failures", "errors", "skipped")}))
    return 0 if record["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
