"""Build matching Word/PDF course reports from content.json and supplied assets.

Numerical experiments are never invoked. If submission/COMP6704_reproducibility.zip
exists, it is embedded in the PDF and verified byte-for-byte. An optional native
Word export can replace the ReportLab PDF before attachment embedding.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (Image, PageBreak, Paragraph, SimpleDocTemplate,
                               Spacer, Table, TableStyle)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "submission"
ASSETS = HERE / "assets"
STEM = "Yangxiao Cai+26023041r"
PAGE_SIZE = letter
WIDTH = 396.0  # Official NeurIPS 2025: 5.5 in x 9 in on US Letter.
MARGIN = (PAGE_SIZE[0] - WIDTH) / 2


def verify_inputs(content):
    for name, expected in content["source_sha256"].items():
        assert sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    assert 1 <= len(content["pages"]) <= 10


def image_size(key, width, maxheight):
    path = ASSETS / (key + ".png")
    with PILImage.open(path) as im:
        w, h = im.size
    scale = min(min(width, WIDTH) / w, maxheight / h)
    return path, w * scale, h * scale


def equation_size(key):
    manifest = json.loads((ASSETS / "equations_manifest.json").read_text(encoding="utf-8"))
    info = manifest["assets"][key]
    # Match equation glyphs to approximately 11.7 pt body math, preserving aspect.
    return image_size(key, min(WIDTH - 38, info["width_inches"] * 72 * .60),
                      info["height_inches"] * 72 * .65)


def word_field(paragraph, instruction):
    run = paragraph.add_run()
    start = OxmlElement("w:fldChar"); start.set(qn("w:fldCharType"), "begin")
    text = OxmlElement("w:instrText"); text.set(qn("xml:space"), "preserve")
    text.text = " " + instruction + " "
    end = OxmlElement("w:fldChar"); end.set(qn("w:fldCharType"), "end")
    run._r.extend([start, text, end])


def shade(cell, fill):
    props = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd"); shd.set(qn("w:fill"), fill); props.append(shd)


class NumberedCanvas(pdfcanvas.Canvas):
    """Draw actual total page counts after ReportLab finishes pagination."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_pages = []

    def showPage(self):
        self._saved_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_pages)
        for state in self._saved_pages:
            self.__dict__.update(state)
            self.setFont("Times-Roman", 8)
            self.setFillColor(colors.HexColor("#576472"))
            self.drawCentredString(PAGE_SIZE[0] / 2, 36,
                                   f"CAI Yangxiao  |  26023041r     {self._pageNumber} / {total}")
            super().showPage()
        super().save()


def build_word(content, path):
    doc = Document()
    sec = doc.sections[0]
    sec.page_width = Pt(PAGE_SIZE[0]); sec.page_height = Pt(PAGE_SIZE[1])
    sec.left_margin = sec.right_margin = Pt(MARGIN)
    sec.top_margin = Pt(72); sec.bottom_margin = Pt(72)
    sec.header_distance = Pt(36); sec.footer_distance = Pt(36)
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"; normal.font.size = Pt(10)
    normal.paragraph_format.line_spacing = Pt(11)
    normal.paragraph_format.space_after = Pt(5)
    normal.paragraph_format.widow_control = True
    for style_name in ("Normal", "Heading 1", "Heading 2"):
        doc.styles[style_name]._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    heading = doc.styles["Heading 1"]
    heading.font.name = "Times New Roman"; heading.font.size = Pt(11)
    heading.font.color.rgb = RGBColor.from_string("000000")
    heading.paragraph_format.space_before = Pt(7)
    heading.paragraph_format.space_after = Pt(4)
    heading.paragraph_format.line_spacing = Pt(13)
    header = sec.header.paragraphs[0]
    header.text = "COMP6704  |  Individual Assignment  |  Unconstrained Optimization"
    header.runs[0].font.size = Pt(8)
    header.runs[0].font.color.rgb = RGBColor.from_string("576472")
    footer = sec.footer.paragraphs[0]; footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run(f"{content['author']}  |  {content['student_id']}     ").font.size = Pt(8)
    word_field(footer, "PAGE"); footer.add_run(" / "); word_field(footer, "NUMPAGES")
    for page_index, blocks in enumerate(content["pages"]):
        if page_index:
            doc.add_page_break()
        for block in blocks:
            kind, text = block["kind"], block.get("text", "")
            if kind == "h":
                doc.add_paragraph(text, "Heading 1")
            elif kind in {"title", "subtitle", "author"}:
                par = doc.add_paragraph(); par.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = par.add_run(text)
                run.bold = kind != "author"
                run.font.size = Pt({"title": 17, "subtitle": 11, "author": 10.1}[kind])
                run.font.color.rgb = RGBColor.from_string("000000")
                par.paragraph_format.line_spacing = Pt({"title": 20, "subtitle": 14, "author": 13}[kind])
                par.paragraph_format.space_after = Pt(7)
                if kind == "title":
                    borders = OxmlElement("w:pBdr")
                    for position, size in (("top", "32"), ("bottom", "8")):
                        border = OxmlElement("w:" + position)
                        for attr, value in (("val", "single"), ("sz", size), ("space", "8"), ("color", "000000")):
                            border.set(qn("w:" + attr), value)
                        borders.append(border)
                    par._p.get_or_add_pPr().append(borders)
            elif kind in {"p", "small", "caption", "reference", "url", "code"}:
                par = doc.add_paragraph()
                par.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY if kind == "p" else WD_ALIGN_PARAGRAPH.LEFT
                if kind == "reference": text += "\n" + block["url"]
                if kind == "url": text += ": " + block["url"]
                run = par.add_run(text)
                if kind in {"small", "caption", "reference", "url"}:
                    run.font.size = Pt(8.5 if kind != "reference" else 9)
                    par.paragraph_format.line_spacing = Pt(10 if kind != "reference" else 10.5)
                    par.paragraph_format.space_after = Pt(5 if kind != "reference" else 9)
                if kind == "caption":
                    run.italic = True
                if kind == "code":
                    run.font.name = "Consolas"; run.font.size = Pt(7.2)
                    par.paragraph_format.line_spacing = Pt(9.5)
                if kind in {"caption", "small"}:
                    run.font.color.rgb = RGBColor.from_string("42505D")
            elif kind == "table":
                tbl = doc.add_table(rows=1, cols=len(block["headers"]))
                tbl.autofit = False
                for col, frac in zip(tbl.columns, block["widths"]): col.width = Pt(WIDTH * frac)
                for ri, row in enumerate([block["headers"]] + block["rows"]):
                    cells = tbl.rows[0].cells if ri == 0 else tbl.add_row().cells
                    props = tbl.rows[ri]._tr.get_or_add_trPr()
                    cant_split = OxmlElement("w:cantSplit"); props.append(cant_split)
                    for cell, value, frac in zip(cells, row, block["widths"]):
                        cell.width = Pt(WIDTH * frac)
                        par = cell.paragraphs[0]; run = par.add_run(str(value))
                        run.font.name = "Times New Roman"; run.font.size = Pt(8)
                        run.bold = ri == 0
                        par.paragraph_format.line_spacing = Pt(9.2)
                        par.paragraph_format.space_before = Pt(2)
                        par.paragraph_format.space_after = Pt(2)
                        if ri == 0:
                            shade(cell, "E8EFF4")
                        elif ri % 2 == 0:
                            shade(cell, "F6F8FA")
                par = doc.add_paragraph(); par.paragraph_format.space_after = Pt(0)
                par.paragraph_format.line_spacing = Pt(2)
                par.add_run().font.size = Pt(2)
            elif kind in {"figure", "eq"}:
                if kind == "eq": img, w, ht = equation_size(block["key"])
                else: img, w, ht = image_size(block["key"], block["width"], block["maxheight"])
                par = doc.add_paragraph(); par.alignment = WD_ALIGN_PARAGRAPH.CENTER
                par.paragraph_format.space_after = Pt(3)
                par.paragraph_format.line_spacing = 1
                run = par.add_run(); run.add_picture(str(img), width=Pt(w), height=Pt(ht))
                if kind == "eq":
                    par.add_run("   (" + str(block["number"]) + ")").font.size = Pt(9)
    doc.core_properties.title = content["title"]
    doc.core_properties.author = content["author"]
    doc.core_properties.subject = "COMP6704: Unconstrained Optimization"
    doc.save(path)


def build_pdf(content, path):
    styles = {
        "p": ParagraphStyle("p", fontName="Times-Roman", fontSize=10, leading=11, spaceAfter=5, alignment=TA_JUSTIFY),
        "h": ParagraphStyle("h", fontName="Times-Bold", fontSize=11, leading=13, spaceBefore=7, spaceAfter=4, textColor=colors.black),
        "title": ParagraphStyle("title", fontName="Times-Bold", fontSize=17, leading=20, spaceAfter=7, alignment=TA_CENTER, textColor=colors.black),
        "subtitle": ParagraphStyle("sub", fontName="Times-Bold", fontSize=11, leading=14, spaceAfter=7, alignment=TA_CENTER),
        "author": ParagraphStyle("author", fontName="Times-Roman", fontSize=10.1, leading=13, spaceAfter=7, alignment=TA_CENTER),
        "small": ParagraphStyle("small", fontName="Times-Roman", fontSize=8.5, leading=10, spaceAfter=5, textColor=colors.HexColor("#42505D")),
        "caption": ParagraphStyle("caption", fontName="Times-Italic", fontSize=8.5, leading=10, spaceAfter=5, textColor=colors.HexColor("#42505D")),
        "reference": ParagraphStyle("ref", fontName="Times-Roman", fontSize=9, leading=10.5, spaceAfter=9),
        "url": ParagraphStyle("url", fontName="Times-Roman", fontSize=8.5, leading=10, spaceAfter=5),
        "code": ParagraphStyle("code", fontName="Courier", fontSize=7.2, leading=9.5, spaceAfter=5),
        "cell": ParagraphStyle("cell", fontName="Times-Roman", fontSize=8, leading=9.2),
        "cellhead": ParagraphStyle("cellhead", fontName="Times-Bold", fontSize=8, leading=9.2),
    }
    def para(text, style): return Paragraph(escape(text).replace("\n", "<br/>"), styles[style])
    story = []
    for i, blocks in enumerate(content["pages"]):
        if i: story.append(PageBreak())
        for block in blocks:
            kind, text = block["kind"], block.get("text", "")
            if kind in styles and kind not in {"cell", "cellhead"}:
                if kind in {"reference", "url"}:
                    label = "Source" if kind == "reference" else text
                    escaped = escape(text) if kind == "reference" else ""
                    story.append(Paragraph(escaped + ('<br/>' if escaped else '') + '<link color="#285E83" href="' + escape(block["url"]) + '">' + escape(label + ": " + block["url"]) + '</link>', styles[kind]))
                else:
                    story.append(para(text, kind))
            elif kind == "table":
                data = [[para(str(v), "cellhead" if j == 0 else "cell") for v in row]
                        for j, row in enumerate([block["headers"]] + block["rows"])]
                tbl = Table(data, colWidths=[WIDTH * f for f in block["widths"]], hAlign="LEFT")
                tbl.setStyle(TableStyle([
                    ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#E8EFF4")),
                    ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F6F8FA")]),
                    ("VALIGN", (0,0), (-1,-1), "TOP"),
                    ("LEFTPADDING", (0,0), (-1,-1), 3), ("RIGHTPADDING", (0,0), (-1,-1), 3),
                    ("TOPPADDING", (0,0), (-1,-1), 2), ("BOTTOMPADDING", (0,0), (-1,-1), 2),
                    ("LINEBELOW", (0,0), (-1,0), .5, colors.HexColor("#B3C4D0")),
                ]))
                story.extend([tbl, Spacer(1, 4)])
            elif kind in {"eq", "figure"}:
                if kind == "eq": img, w, ht = equation_size(block["key"])
                else: img, w, ht = image_size(block["key"], block["width"], block["maxheight"])
                image = Image(str(img), width=w, height=ht)
                if kind == "eq":
                    row = Table([[image, para("("+str(block["number"])+")", "small")]], colWidths=[WIDTH-32, 32])
                    row.setStyle(TableStyle([("ALIGN", (0,0), (0,0), "CENTER"), ("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("TOPPADDING", (0,0), (-1,-1), 0), ("BOTTOMPADDING", (0,0), (-1,-1), 2)]))
                    story.append(row)
                else: story.append(image)
                story.append(Spacer(1, 3))
    def furniture(canvas, document):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#576472")); canvas.setFont("Times-Roman", 8)
        canvas.drawString(MARGIN, PAGE_SIZE[1]-36, "COMP6704  |  Individual Assignment  |  Unconstrained Optimization")
        canvas.restoreState()
    doc = SimpleDocTemplate(str(path), pagesize=PAGE_SIZE, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=72, bottomMargin=72, title=content["title"], author=content["author"])
    doc.build(story, onFirstPage=furniture, onLaterPages=furniture, canvasmaker=NumberedCanvas)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--word-pdf", type=Path, help="Use an already exported native Word PDF as the final page source")
    parser.add_argument("--latex-pdf", type=Path, help="Use the compiled official NeurIPS 2025 course-adapted PDF as page source")
    parser.add_argument("--packaging-report", type=Path,
                        default=OUT / "packaging_verification.json",
                        help="External verification of the current ZIP; attached separately, never stored in its own ZIP")
    parser.add_argument("--no-attachment", action="store_true", help="Preview only, before a complete archive exists")
    parser.add_argument("--render-preview", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    builddir = OUT / "_preview" if args.no_attachment else OUT
    builddir.mkdir(exist_ok=True)
    content = json.loads((HERE / "content.json").read_text(encoding="utf-8"))
    verify_inputs(content)
    word = builddir / (STEM + ".docx")
    build_word(content, word)
    base = builddir / "_reportlab_pages.pdf"
    build_pdf(content, base)
    if args.word_pdf and args.latex_pdf:
        parser.error("Choose one page source: --word-pdf or --latex-pdf")
    page_source = args.latex_pdf or args.word_pdf or base
    reader = PdfReader(page_source)
    assert not reader.attachments, "Use a clean compiled page source with no existing attachments"
    fingerprint = None
    if args.latex_pdf:
        from generate_latex import source_fingerprint
        fingerprint = source_fingerprint(HERE / "content.json", HERE / "equations.json",
                                         HERE / "template/neurips_2025.sty")
        assert reader.metadata.get("/Subject") == "COMP6704 source fingerprint: " + fingerprint, \
            "Compiled LaTeX PDF is stale or does not match current report sources; regenerate and recompile it."
    assert 1 <= len(reader.pages) <= 10, f"Expected <=10 pages including references; got {len(reader.pages)}"
    archive = OUT / "COMP6704_reproducibility.zip"
    writer = PdfWriter(clone_from=reader)
    writer.add_metadata({"/Title": content["title"], "/Author": content["author"], "/Subject":
                         "COMP6704 source fingerprint: " + fingerprint if fingerprint else
                         "COMP6704 / Unconstrained Optimization / 90 CPU experiments"})
    attached = not args.no_attachment
    packaging = None
    archive_snapshot = None
    if attached:
        if not archive.is_file(): raise FileNotFoundError("Build and verify the reproducibility archive first, or use --no-attachment for preview.")
        packaging = json.loads(args.packaging_report.read_text(encoding="utf-8"))
        assert packaging.get("status") == "passed", "Current archive packaging verification did not pass"
        assert packaging.get("archive_sha256") == sha256(archive.read_bytes()).hexdigest(), "Packaging record describes a different archive"
        assert packaging.get("archive_size_bytes") == archive.stat().st_size
        assert packaging.get("current_verification_report_in_archive") is False, "Packaging record must remain outside its own ZIP"
        sys.path.insert(0, str(ROOT))
        from delivery_integrity import verify_archive_snapshot
        archive_snapshot = verify_archive_snapshot(archive, ROOT, required_files=(
            "README.md", "paper_source/content.json", "paper_source/equations.json",
            "paper_source/generate_latex.py", "paper_source/build_final_report.py",
            "paper_source/template/report.tex", "paper_source/template/neurips_2025.sty",
            "provenance_integrity.py", "validate_study.py", "run_tests_audit.py",
            "audits/revision_20261105/unit_tests.json",
        ))
        writer.add_attachment(archive.name, archive.read_bytes())
        writer.add_attachment("packaging_verification.json", args.packaging_report.read_bytes())
    final = builddir / (STEM + ".pdf")
    writer.write(final)
    check = PdfReader(final)
    assert 1 <= len(check.pages) <= 10
    assert final.stat().st_size < 20_000_000, final.stat().st_size
    if attached:
        assert check.attachments[archive.name][0] == archive.read_bytes()
        assert check.attachments["packaging_verification.json"][0] == args.packaging_report.read_bytes()
        assert set(check.attachments) == {archive.name, "packaging_verification.json"}
        assert all(len(values) == 1 for values in check.attachments.values())
    full_text = "\n".join(p.extract_text() for p in check.pages)
    for text in ("26023041r", "Unconstrained Optimization", "References", "73/90", "26/90"):
        assert text in full_text, text
    manifest = {"page_count": len(check.pages), "includes_references": True,
                "pdf_bytes": final.stat().st_size, "pdf_under_20MB": True,
                "embedded_archive_verified": attached, "page_source": page_source.name,
                "packaging_report_attached_separately": attached,
                "attachment_names": sorted(check.attachments) if attached else [],
                "archive_sources_match_current_project": archive_snapshot,
                "pdf_format": "Official NeurIPS 2025 style with a course notice" if args.latex_pdf else "NeurIPS-dimension course adaptation",
                "word_format": "Editable course adaptation; not an official NeurIPS Word template",
                "compiled_source_fingerprint": fingerprint,
                "files": {f.name: {"bytes": f.stat().st_size, "sha256": sha256(f.read_bytes()).hexdigest()}
                          for f in ([word, final, archive] if attached else [word, final])},
                "planned_page_word_counts": [len(re.findall(r"\S+", " ".join(b.get("text", "") for b in p))) for p in content["pages"]]}
    (builddir / "report_verification.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (builddir / "_pdf_text.txt").write_text(full_text, encoding="utf-8")
    if args.render_preview:
        import pypdfium2 as pdfium
        previews = builddir / "_page_previews"; previews.mkdir(exist_ok=True)
        document = pdfium.PdfDocument(str(final))
        for i in range(len(document)):
            document[i].render(scale=1.5).to_pil().save(previews / f"page_{i+1:02d}.png")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__": main()
