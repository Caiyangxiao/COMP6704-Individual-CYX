"""Check that a delivered ZIP contains the exact current project snapshot.

Standard-library only. The check is read-only and does not run experiments.
"""
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import zipfile


def verify_archive_snapshot(archive_path, project, required_files=()):
    project = Path(project).resolve()
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate archive members are not permitted")
        manifest = json.loads(archive.read("archive_manifest.json"))
        records = manifest.get("files", {})
        if not records or set(names) != set(records) | {"archive_manifest.json"}:
            raise ValueError("Archive members do not match the manifest")
        for required in required_files:
            if required not in records:
                raise ValueError(f"Required current report source is absent from archive: {required}")
        total = 0
        for name, expected in records.items():
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name:
                raise ValueError(f"Unsafe archive source path: {name}")
            path = project.joinpath(*relative.parts).resolve()
            if not path.is_relative_to(project) or not path.is_file():
                raise ValueError(f"Current source is missing: {name}")
            data = archive.read(name)
            if sha256(data).hexdigest() != expected.get("sha256") or len(data) != expected.get("size_bytes"):
                raise ValueError(f"Archive manifest mismatch: {name}")
            if data != path.read_bytes():
                raise ValueError(f"Current source differs from archive: {name}; rebuild the ZIP")
            total += len(data)
    return {"passed": True, "members_matching_current_project": len(records),
            "bytes_matching_current_project": total, "required_report_files": list(required_files)}
