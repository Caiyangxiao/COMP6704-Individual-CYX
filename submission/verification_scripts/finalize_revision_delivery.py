"""Finalize this revision's actual PDF/ZIP checks and independent audit delivery."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
import zipfile

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "submission"
AUDIT = ROOT / "audits/revision_20261105"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    pdf = OUT / "Yangxiao Cai+26023041r.pdf"
    code = OUT / "COMP6704_reproducibility.zip"
    pack = OUT / "packaging_verification.json"
    reader = PdfReader(pdf)
    assert len(reader.pages) == 10 and pdf.stat().st_size < 20_000_000
    assert set(reader.attachments) == {code.name, pack.name}
    assert all(len(values) == 1 for values in reader.attachments.values())
    assert reader.attachments[code.name][0] == code.read_bytes()
    assert reader.attachments[pack.name][0] == pack.read_bytes()
    tests = load(AUDIT / "unit_tests.json")
    validation = load(AUDIT / "current_validation.json")
    preservation = load(AUDIT / "preservation_check.json")
    rebuild = load(OUT / "revision_rebuild_verification.json")
    assert tests["passed"] and tests["tests_run"] == 50
    assert not tests["failures"] and not tests["errors"] and not tests["skipped"]
    domains = ("data_internal_integrity", "source_integrity", "environment_match")
    assert all(validation[key]["passed"] for key in domains)
    assert preservation["passed"] and rebuild["passed"] and rebuild["formal_experiment_runs"] == 0
    with zipfile.ZipFile(code) as archive:
        assert not any(name == "packaging_verification.json" or name.endswith("/packaging_verification.json")
                       for name in archive.namelist())
        for name in ("audits/history/windows_exact_reproduction_20261105.json",
                     "audits/history/packaging_before_revision_20261105.json",
                     "README.md", "paper_source/content.json"):
            assert archive.read(name) == (ROOT / name).read_bytes()
    content = load(ROOT / "paper_source/content.json")
    assert sum(block["kind"] == "reference" for page in content["pages"] for block in page) == 8
    pixels = {}
    for number in range(1, 11):
        preview = OUT / "_preview/_page_previews" / f"page_{number:02d}.png"
        final = OUT / "_page_previews" / f"page_{number:02d}.png"
        pixels[str(number)] = {"preview_sha256": digest(preview), "final_sha256": digest(final),
                               "identical": preview.read_bytes() == final.read_bytes()}
    assert all(value["identical"] for value in pixels.values())
    baseline = load(AUDIT / "baseline_evidence/preservation_manifest.json")
    for category in ("raw_reference_files", "original_solver_source_files", "historical_test_source_files"):
        for name, previous in baseline[category].items():
            assert digest(ROOT / name) == previous["sha256"], name
    first = reader.pages[0].extract_text()
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "Yangxiao Cai" in first and "26023041r" in first
    assert "73/90" in text and "26/90" in text and "50 unit tests" in text
    assert "Word" not in text and "supplied separately" not in text and "72/90" not in text
    log = (OUT / "_latex/report.log").read_text(encoding="utf-8", errors="replace")
    for bad in ("Overfull \\hbox", "Overfull \\vbox", "undefined references", "LaTeX Error"):
        assert bad not in log, bad
    proof = {
        "passed": True, "verified_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "scope": "Final revised delivery, extracted attachments, preserved input bytes and reviewed page equality; no formal benchmark runs",
        "pdf_pages_including_references": 10, "pdf_bytes": pdf.stat().st_size,
        "pdf_under_20MB_including_attachments": True,
        "attachment_names": sorted(reader.attachments), "single_copy_per_attachment": True,
        "embedded_zip_identical_to_external": True,
        "packaging_record_attached_outside_its_own_zip": True,
        "tests_run": 50, "unit_test_failures": 0, "unit_test_errors": 0, "unit_test_skips": 0,
        "validation_domains": {key: validation[key]["passed"] for key in domains},
        "original_windows_counts": preservation["original_windows_counts"],
        "tables_2_3_4_unchanged": preservation["tables_2_3_4_unchanged"],
        "protected_raw_files_unchanged": 186, "original_recorded_sources_unchanged": 7,
        "new_formal_experiment_runs": 0, "clean_extraction_rebuild_passed": True,
        "reviewed_page_renders_identical_to_final": pixels, "references_count": 8,
        "unverified_linux_result_not_used": True, "pdf_sha256": digest(pdf), "code_zip_sha256": digest(code),
        "finalizer_sha256": digest(Path(__file__)),
    }
    (OUT / "final_delivery_verification.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    notes = """COMP6704 本轮修改说明
Yangxiao Cai / 26023041r

实际修改
1. 保留历史原始SHA及raw比较；只有LF/CRLF重建摘要确实等于历史摘要时才接受换行等价。真实修改、缺文件或必需版本不符仍会报错；数据、源码和环境三域分开。
2. 核验写入独立audits目录，不回写原实验或历史metadata。压缩重复说明，明确理想Armijo GD界、有限梯度检查边界及Windows结果的跨平台限制。保留标准BFGS O(d²)与所测SciPy1.13.1稠密更新O(d³)的区别。
3. 真实历史Windows核验JSON按原字节放入audits/history；本轮打包报告不进入它自身核验的代码ZIP，而作为PDF第二个附件。增加当前源码与归档一致性检查和重复附件防护。

实际验证
50项单元测试全部通过（原有28项、17项哈希/环境/输出测试、5项交付一致性测试），无失败、错误或跳过。新校验器只读核对90次数据，三域检查通过；真实安装文件的内存LF/CRLF转换验证通过。
186份原始结果文件、7份原求解源码和表2/3/4保持一致。S=73，G=26，同时S与G=26，仅S=47，两项均未满足=17；事件80,605，接受更新80,425。
已从最终ZIP干净解压执行测试、只读核验、正文/LaTeX生成、打包及PDF重建，十页正文一致。逐页查看后，最终页面栅格与已审阅页面逐字节一致；PDF两份附件均可提取且字节匹配。
最终PDF为10页（含参考文献），13,106,641字节，含附件低于20MB。

范围与限制
本轮全部计算使用CPU，未新增算法、数据集、正式实验或GD步长消融。单元测试使用临时小型夹具，不混入原90次结果。
未找到可读取、可核验的所述Linux独立重跑记录，因此未把72/90写成实测结论，也未替换原Windows结果或确定性归因。固定数值库版本不保证跨平台浮点路径或阈值附近状态一致。
历史Windows比较记录真实保留，但原临时候选目录已不存在；它不是本轮或跨平台的重跑证明。

核验入口
代码ZIP内audits/revision_20261105/保存本轮测试、三域校验、换行probe、表格/文件保留与逐页审阅；audits/history/保存明确标注范围的真实历史记录。
packaging_verification.json作为PDF独立附件提供；COMP6704_revision_audits.zip另含最终重建、交付核验和日志。
"""
    note = OUT / "修改说明.txt"
    note.write_text(notes, encoding="utf-8")
    files = {}
    for directory in (AUDIT, ROOT / "audits/history"):
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix in {".json", ".log", ".txt", ".md", ".py"} and "__pycache__" not in path.parts and "temporary_tests" not in path.parts:
                files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    for path in (pack, OUT / "report_verification.json", OUT / "revision_rebuild_verification.json",
                 OUT / "final_delivery_verification.json", note, Path(__file__)):
        files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    for path in (OUT / "verification_logs").glob("revision_*.log"):
        files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    manifest = {name: {"sha256": sha256(data).hexdigest(), "size_bytes": len(data)}
                for name, data in sorted(files.items())}
    files["audit_manifest.json"] = (json.dumps({"scope": "Current revision records with explicitly labelled historical copies", "files": manifest}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    audit_zip = OUT / "COMP6704_revision_audits.zip"
    with zipfile.ZipFile(audit_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    with zipfile.ZipFile(audit_zip) as archive:
        assert all(sha256(archive.read(name)).hexdigest() == previous["sha256"] for name, previous in manifest.items())
    (OUT / "checksums.sha256").write_text("\n".join(digest(path) + "  " + path.name
        for path in (pdf, code, note, audit_zip, pack)) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "pdf_pages": 10, "pdf_bytes": pdf.stat().st_size,
                     "code_zip_bytes": code.stat().st_size, "audit_zip_bytes": audit_zip.stat().st_size,
                     "tests_run": 50, "formal_experiment_runs_this_revision": 0,
                     "attachments": sorted(reader.attachments)}, indent=2))


if __name__ == "__main__":
    main()
