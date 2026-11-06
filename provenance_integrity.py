"""Read-only provenance checks against trusted historical raw SHA-256 values.

An EOL fallback is accepted only when a hash of reconstructed actual bytes
equals the recorded raw digest. No expected canonical hashes are fabricated.
"""
from __future__ import annotations

from hashlib import sha256
import importlib.metadata
import importlib.util
import os
from pathlib import Path
import platform
import re
import sys
from typing import Any


def inspect_source_bytes(data: bytes, expected_raw_sha256: str) -> dict[str, Any]:
    """Check exact bytes first, then prove a strictly EOL-only difference.

    A trusted exact baseline is authoritative even if it contains bare CR.
    If bytes differ, bare CR is rejected. Mixed LF/CRLF can be equivalent to
    a uniform historical baseline only if its LF or CRLF reconstruction hashes
    exactly to that baseline. BOMs, whitespace, and final newlines stay intact.
    """
    actual = sha256(data).hexdigest()
    expected = str(expected_raw_sha256).lower()
    valid_digest = re.fullmatch(r"[0-9a-f]{64}", expected) is not None
    raw_match = valid_digest and actual == expected
    crlf = data.count(b"\r\n")
    bare_cr = len(re.findall(b"\r(?!\n)", data))
    report: dict[str, Any] = {
        "expected_raw_sha256": expected_raw_sha256,
        "actual_raw_sha256": actual,
        "raw_comparison": {"matches": raw_match, "expected_digest_valid": valid_digest},
        "byte_length": len(data),
        "line_endings": {
            "crlf": crlf, "lf_only": data.count(b"\n") - crlf, "bare_cr": bare_cr,
        },
        "passed": False,
        "match_kind": "content_mismatch",
        "eol_equivalence": {
            "checked": False, "proved": False, "matching_variants": [], "variants": {},
            "proof_basis": "A reconstructed actual-byte SHA-256 must equal the trusted historical raw SHA-256.",
        },
        "errors": [],
    }
    if not valid_digest:
        report["match_kind"] = "invalid_expected_digest"
        report["errors"].append("Historical expected SHA-256 is missing or invalid.")
        return report
    if raw_match:
        report.update(passed=True, match_kind="byte_exact")
        return report
    if bare_cr:
        report["match_kind"] = "rejected_bare_cr"
        report["errors"].append("Raw bytes differ and contain bare CR; EOL equivalence is not permitted.")
        return report

    lf_bytes = data.replace(b"\r\n", b"\n")
    variants = {
        "lf_only": (lf_bytes, "Replace each CRLF with LF; preserve every other byte."),
        "crlf_only": (lf_bytes.replace(b"\n", b"\r\n"), "Replace each CRLF with LF, then each LF with CRLF; preserve every other byte."),
    }
    fallback = report["eol_equivalence"]
    fallback["checked"] = True
    for name, (variant, transformation) in variants.items():
        reconstructed_digest = sha256(variant).hexdigest()
        matches = reconstructed_digest == expected
        fallback["variants"][name] = {
            "reconstructed_actual_sha256": reconstructed_digest,
            "byte_length": len(variant), "matches_historical_raw_sha256": matches,
            "transformation": transformation,
        }
        if matches:
            fallback["matching_variants"].append(name)
    if fallback["matching_variants"]:
        fallback["proved"] = True
        report.update(passed=True, match_kind="eol_equivalent")
    else:
        report["errors"].append(
            "Neither LF-only nor CRLF-only reconstruction of actual bytes matches the historical raw SHA-256."
        )
    return report


def inspect_source_file(path: Path, expected_raw_sha256: str) -> dict[str, Any]:
    path = Path(path)
    try:
        report = inspect_source_bytes(path.read_bytes(), expected_raw_sha256)
        report.update(path=str(path), exists=True)
        return report
    except OSError as error:
        return {
            "path": str(path), "exists": False, "passed": False,
            "expected_raw_sha256": expected_raw_sha256, "actual_raw_sha256": None,
            "raw_comparison": {"matches": False}, "match_kind": "missing_or_unreadable",
            "eol_equivalence": {"checked": False, "proved": False, "matching_variants": [], "variants": {}},
            "errors": [f"Missing or unreadable source file: {error}"],
        }


def installed_version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def environment_snapshot() -> dict[str, Any]:
    return {
        "python_version": platform.python_version(), "python_build": sys.version,
        "python_implementation": platform.python_implementation(),
        "python_executable": sys.executable,
        "numpy": installed_version("numpy"), "scipy": installed_version("scipy"),
        "matplotlib": installed_version("matplotlib"),
        "platform": platform.platform(), "processor": platform.processor(),
        "logical_cpu_count": os.cpu_count(),
        "thread_environment": {key: os.environ.get(key) for key in (
            "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "BLIS_NUM_THREADS",
        )},
    }


def compare_environment(metadata: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    """Require numerical versions; report OS/build/thread differences separately.

    A passed version check is not a claim that hardware, thread settings,
    timings, or a newly executed numerical experiment have been reproduced.
    """
    python_match = re.match(r"^(\d+\.\d+\.\d+)", str(metadata.get("python", "")))
    expected_versions = {
        "python": python_match[1] if python_match else None,
        "numpy": metadata.get("numpy"), "scipy": metadata.get("scipy"),
    }
    actual_versions = {
        "python": actual.get("python_version"),
        "numpy": actual.get("numpy"), "scipy": actual.get("scipy"),
    }
    versions, errors = {}, []
    for name, expected in expected_versions.items():
        observed = actual_versions[name]
        matches = expected is not None and observed is not None and observed == expected
        versions[name] = {"expected": expected, "actual": observed, "matches": matches, "required": True}
        if not matches:
            errors.append(f"Required {name} version mismatch: historical={expected!r}, actual={observed!r}.")
    context = {}
    for name in ("platform", "processor", "logical_cpu_count", "thread_environment"):
        expected, observed = metadata.get(name), actual.get(name)
        context[name] = {
            "historical": expected, "actual": observed, "matches": expected == observed,
            "required_for_source_or_data_integrity": False,
        }
    context["python_build"] = {
        "historical": metadata.get("python"), "actual": actual.get("python_build"),
        "matches": metadata.get("python") == actual.get("python_build"),
        "required_for_source_or_data_integrity": False,
    }
    return {
        "passed": not errors, "required_versions": versions,
        "platform_context": context, "actual_environment": actual,
        "platform_context_identical": all(item["matches"] for item in context.values()),
        "policy": "Python semantic version, NumPy and SciPy must match. OS, build, CPU and thread context are reported separately; differences do not invalidate saved data or an EOL proof and do not establish timing equivalence.",
        "errors": errors,
    }


def scipy_source_path() -> Path | None:
    """Locate the installed Python source without invoking an optimizer."""
    try:
        specification = importlib.util.find_spec("scipy")
    except (ImportError, ValueError):
        return None
    if specification is None or not specification.submodule_search_locations:
        return None
    return Path(next(iter(specification.submodule_search_locations))) / "optimize" / "_optimize.py"
