"""Build and verify a deterministic, byte-preserving reproducibility archive.

This utility uses only the Python standard library. It never runs a solver,
rebuilds figures, or modifies the source results. Run with --dry-run to inspect
the selection without creating an archive or a verification report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
from typing import Any
import zipfile


ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
MANIFEST_NAME = "archive_manifest.json"
RESULT_SUFFIXES = {".csv", ".json", ".txt"}
ORIGINAL_SOURCE_FILES = (
    "cpu_optimization/__init__.py",
    "cpu_optimization/experiment.py",
    "cpu_optimization/objectives.py",
    "cpu_optimization/plotting.py",
    "cpu_optimization/solvers.py",
    "run_experiments.py",
    "plot_results.py",
)


class VerificationError(ValueError):
    """An archive does not match its manifest or original run provenance."""


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True,
                   allow_nan=False) + "\n"
    ).encode("utf-8")


def _file_record(path: Path) -> dict[str, int | str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(block)
            digest.update(block)
    return {"sha256": digest.hexdigest(), "size_bytes": size}


def select_files(project_root: Path, *, include_demo: bool = True) -> list[Path]:
    """Select reproducibility files without traversing environments or reports.

    Returned paths are relative to project_root and sorted as POSIX names.
    Selection includes raw results and analysis tables/metadata, while all
    regenerated result figures are excluded. Paper source PNG assets are kept.
    """
    root = project_root.resolve()
    selected: set[Path] = set()
    patterns = (
        "*.py", "requirements*.txt", "README", "README.*",
        "cpu_optimization/*.py", "tests/*.py", "configs/*.json",
        "paper_source/*.py", "paper_source/*.json", "paper_source/*.ps1",
        "paper_source/assets/*.png", "paper_source/assets/*.json",
    )
    candidates = []
    for pattern in patterns:
        candidates.extend(root.glob(pattern))
    result_directories = [root / "results" / "full_study"]
    if include_demo:
        result_directories.append(root / "results" / "demo_2d")
    for directory in result_directories:
        if directory.is_dir():
            candidates.extend(
                path for path in directory.rglob("*")
                if path.suffix.lower() in RESULT_SUFFIXES
            )
    for path in candidates:
        if not path.is_file():
            continue
        if path.is_symlink():
            raise ValueError(f"Refusing a symbolic-link input: {path}")
        relative = path.relative_to(root)
        if any(part in {".venv", "__pycache__", "submission", "reports"}
               for part in relative.parts):
            continue
        selected.add(relative)
    return sorted(selected, key=lambda path: path.as_posix())


def selection_summary(project_root: Path, files: list[Path]) -> dict[str, Any]:
    """Return sizes and categories without writing any files."""
    root = project_root.resolve()
    categories: dict[str, dict[str, int]] = {}
    total_bytes = 0
    for relative in files:
        size = (root / relative).stat().st_size
        total_bytes += size
        if relative.parts[0] == "results":
            category = "/".join(relative.parts[:2])
        elif len(relative.parts) == 1:
            category = "root"
        else:
            category = relative.parts[0]
        record = categories.setdefault(category, {"files": 0, "size_bytes": 0})
        record["files"] += 1
        record["size_bytes"] += size
    return {
        "selected_file_count": len(files),
        "source_size_bytes": total_bytes,
        "source_size_mib": total_bytes / (1024 * 1024),
        "categories": categories,
    }


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def _check_member_name(name: str) -> None:
    pure = PurePosixPath(name)
    if (not name or pure.is_absolute() or "\\" in name or ":" in name
            or any(part in {"", ".", ".."} for part in name.split("/"))):
        raise VerificationError(f"Unsafe archive member: {name!r}")


def _validate_destination(path: Path, project_root: Path) -> None:
    """Keep output options from overwriting inputs or the original results."""
    for directory in ("results", "cpu_optimization", "tests", "configs", "paper_source"):
        if path.is_relative_to(project_root / directory):
            raise ValueError(f"Output cannot be placed in a source/results directory: {path}")
    if path.parent == project_root and path.is_file():
        raise ValueError(f"Output cannot overwrite an existing project-root file: {path}")


def verify_archive(archive_path: Path) -> dict[str, Any]:
    """Extract temporarily and verify bytes, sizes, membership, and provenance.

    This does not import project modules or invoke numerical reproduction.
    The temporary extracted tree is deleted when verification finishes.
    """
    archive_path = archive_path.resolve()
    with tempfile.TemporaryDirectory(prefix="comp6704_verify_") as temporary:
        extracted = Path(temporary)
        with zipfile.ZipFile(archive_path, "r") as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(names) != len(set(names)):
                raise VerificationError("Archive contains duplicate member names.")
            if MANIFEST_NAME not in names:
                raise VerificationError(f"Missing {MANIFEST_NAME}.")
            for entry in entries:
                _check_member_name(entry.filename)
                if entry.is_dir() or ((entry.external_attr >> 16) & 0o170000) == 0o120000:
                    raise VerificationError("Only regular file entries are allowed.")
                if entry.date_time != ZIP_TIMESTAMP:
                    raise VerificationError("Archive member timestamp is not fixed.")
                if entry.compress_type != zipfile.ZIP_DEFLATED:
                    raise VerificationError("Archive members must use ZIP_DEFLATED.")
            if names != sorted(names):
                raise VerificationError("Archive entries are not sorted.")
            manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
            if (not isinstance(manifest, dict)
                    or manifest.get("format_version") != 1
                    or manifest.get("hash_algorithm") != "sha256"):
                raise VerificationError("Unsupported manifest format.")
            manifest_files = manifest.get("files")
            if not isinstance(manifest_files, dict) or MANIFEST_NAME in manifest_files:
                raise VerificationError("Manifest must list files excluding itself.")
            if set(names) != set(manifest_files) | {MANIFEST_NAME}:
                raise VerificationError("Archive and manifest file lists differ.")
            for name in names:
                destination = extracted.joinpath(*PurePosixPath(name).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target)

        verified_bytes = 0
        for name, expected in manifest_files.items():
            actual = _file_record(extracted.joinpath(*PurePosixPath(name).parts))
            if actual != expected:
                raise VerificationError(f"Manifest hash or size mismatch: {name}")
            verified_bytes += int(actual["size_bytes"])

        metadata_path = extracted / "results" / "full_study" / "metadata.json"
        if not metadata_path.is_file():
            raise VerificationError("Missing original full-study metadata.")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise VerificationError("Original full-study metadata must be an object.")
        recorded_hashes = metadata.get("source_sha256", {})
        provenance = {}
        for name in ORIGINAL_SOURCE_FILES:
            if name not in recorded_hashes:
                raise VerificationError(f"Original metadata lacks a source hash: {name}")
            source_path = extracted.joinpath(*PurePosixPath(name).parts)
            if not source_path.is_file():
                raise VerificationError(f"Original source is absent: {name}")
            actual_hash = _file_record(source_path)["sha256"]
            if actual_hash != recorded_hashes[name]:
                raise VerificationError(f"Original-run source hash mismatch: {name}")
            provenance[name] = {"sha256": actual_hash, "matches_original_run": True}

    archive_record = _file_record(archive_path)
    return {
        "status": "passed",
        "archive_path": str(archive_path),
        "archive_sha256": archive_record["sha256"],
        "archive_size_bytes": archive_record["size_bytes"],
        "verified_file_count": len(manifest_files),
        "verified_source_size_bytes": verified_bytes,
        "manifest_excludes_itself": True,
        "temporary_extraction_removed": True,
        "original_source_files_verified": len(provenance),
        "original_source_hashes": provenance,
        "full_study_metadata": {
            key: metadata.get(key)
            for key in ("execution_status", "expected_runs", "completed_runs")
        },
        "numerical_reproduction": "Not performed by this packaging utility.",
    }


def create_archive(
    project_root: Path,
    archive_path: Path,
    *,
    include_demo: bool = True,
) -> dict[str, Any]:
    """Archive exact source bytes in a deterministic ZIP, then verify it."""
    root = project_root.resolve()
    archive_path = archive_path.resolve()
    _validate_destination(archive_path, root)
    files = select_files(root, include_demo=include_demo)
    if not files:
        raise ValueError("No reproducibility files were selected.")
    records = {relative.as_posix(): _file_record(root / relative) for relative in files}
    manifest = {"format_version": 1, "hash_algorithm": "sha256", "files": records}
    manifest_bytes = _json_bytes(manifest)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=".comp6704_package_", suffix=".zip.tmp", dir=archive_path.parent,
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=9) as archive:
            for name in sorted([*records, MANIFEST_NAME]):
                if name == MANIFEST_NAME:
                    data = manifest_bytes
                else:
                    data = root.joinpath(*PurePosixPath(name).parts).read_bytes()
                    current = {"sha256": hashlib.sha256(data).hexdigest(),
                               "size_bytes": len(data)}
                    if current != records[name]:
                        raise RuntimeError(f"Source changed during packaging: {name}")
                archive.writestr(_zip_info(name), data, compresslevel=9)
        verification = verify_archive(temporary_path)
        temporary_path.replace(archive_path)
        verification["archive_path"] = str(archive_path)
        verification["selection"] = selection_summary(root, files)
        return verification
    finally:
        temporary_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path,
                        default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--output", type=Path,
                        help="ZIP path; default: PROJECT/submission/COMP6704_reproducibility.zip")
    parser.add_argument("--verification-output", type=Path,
                        help="JSON path; default: PROJECT/submission/packaging_verification.json")
    parser.add_argument("--verify-only", action="store_true",
                        help="Verify the existing archive by temporary extraction; do not create a ZIP")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print selected counts and sizes without writing anything")
    parser.add_argument("--list-files", action="store_true",
                        help="Also list selected paths when using --dry-run")
    parser.add_argument("--exclude-demo", action="store_true",
                        help="Omit optional results/demo_2d raw data")
    args = parser.parse_args(argv)
    if args.dry_run and args.verify_only:
        parser.error("--dry-run and --verify-only are mutually exclusive")
    if args.list_files and not args.dry_run:
        parser.error("--list-files requires --dry-run")
    root = args.project_root.resolve()
    archive_path = (args.output or root / "submission" / "COMP6704_reproducibility.zip").resolve()
    report_path = (args.verification_output or root / "submission" / "packaging_verification.json").resolve()
    try:
        _validate_destination(archive_path, root)
        _validate_destination(report_path, root)
        if archive_path == report_path:
            raise ValueError("Archive and verification report must use different paths.")
    except ValueError as exc:
        parser.error(str(exc))
    try:
        if args.dry_run:
            files = select_files(root, include_demo=not args.exclude_demo)
            report = selection_summary(root, files)
            report["status"] = "dry_run_no_files_written"
            if args.list_files:
                report["selected_files"] = [path.as_posix() for path in files]
            print(_json_bytes(report).decode("utf-8"), end="")
            return 0
        if args.verify_only:
            report = verify_archive(archive_path)
        else:
            report = create_archive(root, archive_path, include_demo=not args.exclude_demo)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        report = {"status": "failed", "archive_path": str(archive_path),
                  "error": f"{type(exc).__name__}: {exc}"}
        if args.dry_run:
            print(report["error"], file=sys.stderr)
            return 1
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_bytes(_json_bytes(report))
        print(report["error"], file=sys.stderr)
        return 1
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_bytes(_json_bytes(report))
    print(_json_bytes(report).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
