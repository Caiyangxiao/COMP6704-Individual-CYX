"""Read-only preservation, table, and installed-source EOL checks for this revision.

Writes new audit JSON beside this script; never writes results or runs solvers.
Run after generating revised paper_source/content.json.
"""
from pathlib import Path
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import csv
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from provenance_integrity import environment_snapshot, inspect_source_bytes, scipy_source_path


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    started = datetime.now(timezone(timedelta(hours=8))).isoformat()
    environment = environment_snapshot()
    baseline = json.loads((HERE / "baseline_evidence/preservation_manifest.json").read_text(encoding="utf-8"))
    before_tables = json.loads((HERE / "baseline_evidence/tables_2_3_4_before.json").read_text(encoding="utf-8"))["tables"]
    changed, checked = [], {}
    for category in ("raw_reference_files", "original_solver_source_files", "historical_test_source_files"):
        checked[category] = len(baseline[category])
        for name, previous in baseline[category].items():
            path = ROOT / name
            if not path.is_file() or digest(path) != previous["sha256"] or path.stat().st_size != previous["size_bytes"]:
                changed.append(name)
    content = json.loads((ROOT / "paper_source/content.json").read_text(encoding="utf-8"))
    after_tables = {}
    for page in content["pages"]:
        current_table = None
        for block in page:
            if block["kind"] == "table":
                current_table = {"headers": block["headers"], "rows": block["rows"]}
            if block["kind"] == "caption":
                match = re.match(r"Table ([234])\.", block["text"])
                if match:
                    after_tables[match[1]] = current_table
    table_matches = {number: after_tables.get(number) == record["value"]
                     for number, record in before_tables.items()}
    data = ROOT / "results/full_study"
    runs = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((data / "runs").glob("*.json"))]
    counts = {"runs": len(runs), "S": sum(r["stationary"] for r in runs),
              "G": sum(r["global_hit"] for r in runs),
              "S_and_G": sum(r["stationary"] and r["global_hit"] for r in runs),
              "S_only": sum(r["stationary"] and not r["global_hit"] for r in runs),
              "neither": sum(not r["stationary"] and not r["global_hit"] for r in runs),
              "accepted_updates": sum(r["nit"] for r in runs), "trace_events": 0}
    for path in (data / "traces").glob("*.csv"):
        with path.open(encoding="utf-8", newline="") as handle:
            counts["trace_events"] += sum(1 for _ in csv.DictReader(handle))
    expected_counts = dict(runs=90, S=73, G=26, S_and_G=26, S_only=47, neither=17,
                           accepted_updates=80425, trace_events=80605)
    metadata = json.loads((data / "metadata.json").read_text(encoding="utf-8"))
    installed_path = scipy_source_path()
    if installed_path is None:
        raise RuntimeError("Cannot inspect the installed SciPy source")
    raw = installed_path.read_bytes()
    lf = raw.replace(b"\r\n", b"\n")
    probes = {"installed_raw_bytes": inspect_source_bytes(raw, metadata["scipy_optimize_source_sha256"]),
              "LF_reconstruction": inspect_source_bytes(lf, metadata["scipy_optimize_source_sha256"]),
              "CRLF_reconstruction": inspect_source_bytes(lf.replace(b"\n", b"\r\n"), metadata["scipy_optimize_source_sha256"])}
    probe_record = {"scope": "Installed source and in-memory LF/CRLF transformations; not a Linux numerical rerun",
                    "started_at": started, "recorded_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
                    "environment": environment, "source_path": str(installed_path),
                    "historical_metadata_sha256": digest(data / "metadata.json"),
                    "historical_expected_raw_sha256": metadata["scipy_optimize_source_sha256"],
                    "cases": probes, "source_file_not_modified": digest(installed_path) == sha256(raw).hexdigest(),
                    "passed": all(probe["passed"] for probe in probes.values())}
    (HERE / "source_hash_probe.json").write_text(json.dumps(probe_record, indent=2) + "\n", encoding="utf-8")
    record = {"scope": "Saved Windows data/source byte preservation and Tables 2/3/4 before/after; no solver execution",
              "started_at": started, "finished_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
              "environment": environment, "baseline_manifest_sha256": digest(HERE / "baseline_evidence/preservation_manifest.json"),
              "checked": checked, "changed_protected_files": changed,
              "tables_2_3_4_unchanged": table_matches, "original_windows_counts": counts,
              "expected_counts": expected_counts, "counts_match": counts == expected_counts,
              "content_sha256": digest(ROOT / "paper_source/content.json"),
              "passed": not changed and all(table_matches.values()) and counts == expected_counts}
    (HERE / "preservation_check.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": record["passed"] and probe_record["passed"], "checked": checked,
                      "tables_unchanged": table_matches, "counts": counts,
                      "source_probe": {name: result["match_kind"] for name, result in probes.items()}}, indent=2))
    return 0 if record["passed"] and probe_record["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
