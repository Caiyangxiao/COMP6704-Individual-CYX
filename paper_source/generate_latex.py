"""Generate a native-math course paper using the unmodified NeurIPS 2025 style.

Run from the project root: python paper_source/generate_latex.py
This writes template/report.tex and generation_provenance.json; it does not
compile TeX, modify content/style files, attach an archive, or run experiments.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def source_fingerprint(content_path: Path, equations_path: Path, style: Path) -> str:
    """Bind the compiled PDF to current text, equations, style, generator and plots."""
    content = json.loads(content_path.read_text(encoding="utf-8"))
    figures = sorted({block["key"] for page in content["pages"] for block in page
                      if block["kind"] == "figure"})
    payload = {"content": digest(content_path), "equations": digest(equations_path),
               "style": digest(style), "generator": digest(Path(__file__)),
               "figures": {key: digest(HERE / "assets" / (key + ".png")) for key in figures}}
    return sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


SPECIAL = {
    "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}",
    "$": r"\$", "&": r"\&", "%": r"\%", "#": r"\#", "_": r"\_",
    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    "<": r"\ensuremath{<}", ">": r"\ensuremath{>}",
    "–": "--", "—": "---", "−": r"\ensuremath{-}", "‑": "-",
    "’": "'", "‘": "`", "“": "``", "”": "''", "\u00a0": "~",
    "≤": r"\ensuremath{\leq}", "≥": r"\ensuremath{\geq}",
    "×": r"\ensuremath{\times}", "²": r"\ensuremath{^2}",
    "³": r"\ensuremath{^3}", "ε": r"\ensuremath{\epsilon}",
    "α": r"\ensuremath{\alpha}", "β": r"\ensuremath{\beta}",
    "τ": r"\ensuremath{\tau}", "σ": r"\ensuremath{\sigma}",
    "π": r"\ensuremath{\pi}", "∞": r"\ensuremath{\infty}",
    "é": r"\'{e}", "è": r"\`{e}", "ö": r'\"{o}',
}


def escape_tex(text: str) -> str:
    return "".join(SPECIAL.get(character, character) for character in str(text))


def url_tex(url: str) -> str:
    if any(character in url for character in "{}\n\r"):
        raise ValueError(f"Unsupported character in URL: {url!r}")
    return r"\url{" + url + "}"


MATH_TOKENS = {
    "10d + sum_i[x_i^2 - 10 cos(2 pi x_i)]": r"10d+\sum_i[x_i^2-10\cos(2\pi x_i)]",
    "-400 x_i(x_{i+1}-x_i^2) + 2(x_i-1)": r"-400x_i(x_{i+1}-x_i^2)+2(x_i-1)",
    "200(x_{i+1}-x_i^2)": r"200(x_{i+1}-x_i^2)",
    "h_i = 10^-6 max(1, |x_i|)": r"h_i=10^{-6}\max(1,|x_i|)",
    "2 + 40 pi^2 cos(2 pi x_i)": r"2+40\pi^2\cos(2\pi x_i)",
    "alpha <= 2(1-c1)/L": r"\alpha\leq2(1-c_1)/L",
    "0 < c1 = 10^-4 < c2 = 0.4 < 1": r"0<c_1=10^{-4}<c_2=0.4<1",
    "p_k = -H_k g_k": r"p_k=-H_k g_k", "p_0 = -g_0": r"p_0=-g_0",
    "H_0 = I": "H_0=I", "H0=I": "H_0=I", "f* = 0": r"f^\star=0",
    "min f(x)": r"\min f(x)",
    "||grad f||_2": r"\|\nabla f\|_2", "|f-f*|": r"|f-f^\star|",
    "g_k^T p_k": r"g_k^\top p_k", "grad f(x_k)": r"\nabla f(x_k)",
    "grad f": r"\nabla f", "x in R^d": r"x\in\mathbb{R}^d",
    "R^d": r"\mathbb{R}^d", "alpha_0": r"\alpha_0", "f_inf": r"f_{\inf}",
    "f*": r"f^\star", "p_0": "p_0", "g_0": "g_0", "H_0": "H_0",
    "p_k": "p_k", "g_k": "g_k", "H_k": "H_k", "s_k": "s_k", "y_k": "y_k",
    "x_k": "x_k", "x_i": "x_i", "x_i^2": "x_i^2", "x_{i+1}": "x_{i+1}",
    "h_i": "h_i", "pi^2": r"\pi^2", "pi": r"\pi",
    "c1": "c_1", "c2": "c_2", "alpha": r"\alpha", "tau": r"\tau",
    "beta": r"\beta", "sigma": r"\sigma", "epsilon": r"\epsilon",
}
_math_alternatives = "|".join(re.escape(token) for token in sorted(MATH_TOKENS, key=len, reverse=True))
INLINE = re.compile(
    r"(?P<cite>\[(?:\d+)(?:\s*,\s*\d+)*\])"
    r"|(?P<path>[A-Za-z0-9_./+\-]+\.(?:zip|json|csv|py|txt|pdf|docx))"
    r"|(?P<call>scipy\.optimize\.minimize\(method='(?:CG|BFGS)'\))"
    r"|(?P<field>\b(?:solver_success|solver_status|solver_message|nfev|njev|gtol|xrtol|maxiter|norm|rosen_der|rosen|float64|PCG64|SeedSequence|symlog|linthresh)\b)"
    r"|(?P<complexity>\bO\((?:epsilon\^-2|d\^[23]|Kd|d)\))"
    r"|(?P<scientific>\b\d+(?:\.\d+)?e[+-]?\d+\b)"
    r"|(?P<power>\b10\^-?\d+\b)"
    r"|(?P<relation><=|>=)"
    r"|(?P<math>(?<![A-Za-z0-9_])(?:" + _math_alternatives + r")(?![A-Za-z0-9_]))"
)


def prose(text: str, reference_ids: set[str]) -> str:
    pieces, end = [], 0
    for match in INLINE.finditer(str(text)):
        pieces.append(escape_tex(text[end:match.start()]))
        token, kind = match.group(), match.lastgroup
        if kind == "cite":
            numbers = re.findall(r"\d+", token)
            rendered = (r"\cite{" + ",".join("ref" + n for n in numbers) + "}"
                        if set(numbers) <= reference_ids else escape_tex(token))
        elif kind in {"path", "call", "field"}:
            rendered = r"\texttt{" + escape_tex(token) + "}"
        elif kind == "complexity":
            inside = token[2:-1].replace("epsilon", r"\epsilon")
            inside = re.sub(r"\^(-?\d+)", r"^{\1}", inside)
            rendered = r"\(\mathcal{O}(" + inside + r")\)"
        elif kind == "scientific":
            value, exponent = re.split("e", token, flags=re.I)
            rendered = r"\(" + value + r"\times10^{" + str(int(exponent)) + r"}\)"
        elif kind == "power":
            rendered = r"\(10^{" + token.split("^")[1] + r"}\)"
        elif kind == "relation":
            rendered = r"\(\leq\)" if token == "<=" else r"\(\geq\)"
        else:
            rendered = r"\(" + MATH_TOKENS[token] + r"\)"
        pieces.append(rendered)
        end = match.end()
    pieces.append(escape_tex(text[end:]))
    return "".join(pieces)


def equation_line(source: str) -> tuple[str, bool]:
    line = source.strip()
    if line.startswith("$$") and line.endswith("$$"):
        line = line[2:-2]
    elif line.startswith("$") and line.endswith("$"):
        line = line[1:-1]
    elif line.startswith(r"\(") and line.endswith(r"\)"):
        line = line[2:-2]
    # Existing JSON mathtext assets encode every command with doubled slashes.
    # Only decode that consistent legacy form; native single-command TeX stays intact.
    legacy = "\\\\" in line and re.search(r"(?<!\\)\\(?!\\)[A-Za-z]", line) is None
    if legacy:
        line = line.replace("\\\\", "\\")
    if not line or "$" in line:
        raise ValueError(f"Invalid equation line: {source!r}")
    return line, legacy


def heading(text: str, reference_ids: set[str]) -> str:
    match = re.match(r"^(\d+(?:\.\d+){0,2})\.?\s+(.+)$", text)
    if not match:
        return r"\section*{" + prose(text, reference_ids) + "}"
    numbers = list(map(int, match[1].split(".")))
    counters = ("section", "subsection", "subsubsection")
    setup = [rf"\setcounter{{{counter}}}{{{value - (index == len(numbers) - 1)}}}"
             for index, (counter, value) in enumerate(zip(counters, numbers))]
    return "\n".join(setup + ["\\" + counters[len(numbers) - 1] + "{" + prose(match[2], reference_ids) + "}"])


def table_tex(block: dict, reference_ids: set[str]) -> str:
    headers, rows = block["headers"], block["rows"]
    count = len(headers)
    weights = block.get("widths", [1 / count] * count)
    if len(weights) != count or sum(weights) <= 0 or any(weight <= 0 for weight in weights):
        raise ValueError("Invalid table column widths")
    total = sum(weights)
    columns = []
    for weight in weights:
        fraction = weight / total
        padding = fraction * 6 * (count - 1)
        width = rf"\dimexpr {fraction:.8f}\linewidth-{padding:.6f}pt\relax"
        columns.append(r">{\raggedright\arraybackslash}p{" + width + "}")
    specification = "@{}" + "".join(columns) + "@{}"
    lines = [r"\begingroup", r"\fontsize{8}{9.2}\selectfont", r"\setlength{\tabcolsep}{3pt}",
             r"\renewcommand{\arraystretch}{1.05}", r"\centering", r"\begin{tabular}{" + specification + "}", r"\toprule"]
    for index, row in enumerate([headers] + rows):
        if len(row) != count:
            raise ValueError("Table row has the wrong column count")
        cells = [prose(str(cell), reference_ids).replace("\n", r"\newline{}") for cell in row]
        if index == 0:
            cells = [r"\textbf{" + cell + "}" for cell in cells]
        lines.append(" & ".join(cells) + r" \\")
        if index == 0:
            lines.append(r"\midrule")
    lines.extend([r"\bottomrule", r"\end{tabular}\par", r"\endgroup", r"\smallskip"])
    return "\n".join(lines)


def generate(content_path: Path, equations_path: Path, output: Path, keep_subtitle: bool = False) -> dict:
    content = json.loads(content_path.read_text(encoding="utf-8"))
    equations = json.loads(equations_path.read_text(encoding="utf-8"))
    pages = content["pages"]
    if not 1 <= len(pages) <= 10:
        raise ValueError("Content must contain between one and ten planned pages")
    style = output.parent / "neurips_2025.sty"
    if not style.is_file():
        raise FileNotFoundError(f"Place the original official style beside the output: {style}")
    style_before = digest(style)
    fingerprint = source_fingerprint(content_path, equations_path, style)
    for name, expected in content.get("source_sha256", {}).items():
        if digest(PROJECT / name) != expected:
            raise ValueError(f"Content input provenance mismatch: {name}")
    references = {match[1] for page in pages for block in page
                  if block["kind"] == "reference"
                  for match in [re.match(r"^\[(\d+)\]", block["text"])] if match}
    first_page = pages[0]
    title = next((block["text"] for block in first_page if block["kind"] == "title"), content["title"])
    author = next((block["text"] for block in first_page if block["kind"] == "author"),
                  content["author"] + "\nStudent ID: " + content["student_id"])
    author_tex = r" \\ ".join(escape_tex(line) for line in author.splitlines())
    if keep_subtitle:
        subtitle = next((block["text"] for block in first_page if block["kind"] == "subtitle"), "")
        if subtitle:
            author_tex += r" \\ \parbox{0.95\textwidth}{\centering\small\itshape " + escape_tex(subtitle) + "}"
    lines = [r"\documentclass[10pt]{article}", r"\usepackage[preprint,nonatbib]{neurips_2025}",
             r"\usepackage[T1]{fontenc}", r"\usepackage{amsmath,amssymb,graphicx,booktabs,array}",
             r"\usepackage{hyperref,url,microtype}",
             r"\hypersetup{hidelinks,pdfauthor={Yangxiao Cai},pdfsubject={COMP6704 source fingerprint: " + fingerprint + "}}",
             r"\makeatletter", r"\renewcommand{\@noticestring}{COMP6704 Individual Assignment, Fall 2026. Unconstrained Optimization.}",
             r"\makeatother", r"\newlength{\paperfigurewidth}",
             r"\title{" + escape_tex(title).replace("\n", r"\\ ") + "}",
             r"\author{" + author_tex + "}", r"\begin{document}", r"\maketitle"]
    abstract_open = False
    bibliography_open = False
    normalized_keys, figure_files = set(), set()
    equation_count = 0
    omitted = []
    for page_index, page in enumerate(pages):
        if page_index:
            if abstract_open:
                lines.append(r"\end{abstract}"); abstract_open = False
            if bibliography_open:
                lines.append(r"\end{thebibliography}"); bibliography_open = False
            lines.extend(["", rf"% Planned content page {page_index + 1}", r"\newpage"])
        for block in page:
            kind, text = block["kind"], block.get("text", "")
            if kind in {"title", "author", "subtitle"}:
                if kind == "subtitle" and not keep_subtitle:
                    omitted.append({"kind": kind, "text": text, "reason": "Optional subtitle omitted; title and author use official maketitle."})
                continue
            if abstract_open and kind != "p":
                lines.append(r"\end{abstract}"); abstract_open = False
            if bibliography_open and kind != "reference":
                lines.append(r"\end{thebibliography}"); bibliography_open = False
            if kind == "h":
                if text.strip().lower() == "abstract":
                    lines.append(r"\begin{abstract}"); abstract_open = True
                elif text.strip().lower() != "references":
                    lines.append(heading(text, references))
            elif kind == "p":
                lines.append(prose(text, references) + "\n")
            elif kind == "small":
                lines.append(r"{\small " + prose(text, references) + r"\par}")
            elif kind == "caption":
                lines.append(r"{\small\itshape " + prose(text, references) + r"\par}\smallskip")
            elif kind == "eq":
                key = block["key"]
                decoded = [equation_line(source) for source in equations[key]]
                if any(legacy for _, legacy in decoded):
                    normalized_keys.add(key)
                lines.extend([rf"\setcounter{{equation}}{{{int(block['number']) - 1}}}",
                              r"\begin{equation}", r"\begin{aligned}",
                              (" \\\\\n").join((r"\relax " if line.lstrip().startswith("[") else "") + line for line, _ in decoded),
                              r"\end{aligned}", rf"\label{{eq:{key}}}", r"\end{equation}"])
                equation_count += 1
            elif kind == "table":
                lines.append(table_tex(block, references))
            elif kind == "figure":
                image = HERE / "assets" / (block["key"] + ".png")
                if not image.is_file():
                    raise FileNotFoundError(image)
                figure_files.add(image)
                relative = Path(os.path.relpath(image, output.parent)).as_posix()
                width, height = float(block.get("width", 396)), float(block.get("maxheight", 648))
                lines.extend([r"\begingroup", rf"\setlength{{\paperfigurewidth}}{{{width:g}pt}}",
                              r"\ifdim\paperfigurewidth>\linewidth\setlength{\paperfigurewidth}{\linewidth}\fi",
                              r"\noindent\makebox[\linewidth][c]{\includegraphics[width=\paperfigurewidth,height=" + f"{height:g}pt" + r",keepaspectratio]{" + relative + r"}}\par", r"\endgroup"])
            elif kind == "reference":
                match = re.match(r"^\[(\d+)\]\s*(.*)$", text)
                if not match:
                    raise ValueError(f"Reference requires an explicit numeric label: {text}")
                if not bibliography_open:
                    lines.extend([r"\begin{thebibliography}{99}", r"\small\raggedright", r"\setlength{\itemsep}{2pt}"])
                    bibliography_open = True
                lines.append(r"\bibitem{ref" + match[1] + "}" + escape_tex(match[2]) + " " + url_tex(block["url"]))
            elif kind == "url":
                lines.append(r"{\small\raggedright " + escape_tex(text) + ": " + url_tex(block["url"]) + r"\par}")
            elif kind == "code":
                lines.append(r"\begingroup\fontsize{8}{9.2}\selectfont\raggedright")
                for command in text.splitlines():
                    lines.append(r"\noindent\texttt{" + escape_tex(command) + r"}\par")
                lines.append(r"\endgroup")
            else:
                raise ValueError(f"Unsupported content block: {kind!r}")
    if abstract_open:
        lines.append(r"\end{abstract}")
    if bibliography_open:
        lines.append(r"\end{thebibliography}")
    lines.extend([r"\end{document}", ""])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    if digest(style) != style_before:
        raise RuntimeError("Official style unexpectedly changed during generation")
    return {
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "source_fingerprint": fingerprint,
        "generator_sha256": digest(Path(__file__)), "content_sha256": digest(content_path),
        "equations_sha256": digest(equations_path), "style_sha256": style_before,
        "official_style_modified": False, "latex_source": str(output), "latex_sha256": digest(output),
        "planned_pages": len(pages), "manual_page_breaks": len(pages) - 1,
        "native_equation_blocks": equation_count, "normalized_legacy_equations": sorted(normalized_keys),
        "figure_sha256": {path.name: digest(path) for path in sorted(figure_files)},
        "omitted_blocks": omitted,
        "compilation_performed": False,
        "limitations": [
            "Planned page breaks do not prove that compiled output fits ten pages; compile and inspect it.",
            "Only the course notice is overridden in the main document; official style geometry is retained.",
            "The reproducibility ZIP must be attached by the final PDF builder after compilation.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content", type=Path, default=HERE / "content.json")
    parser.add_argument("--equations", type=Path, default=HERE / "equations.json")
    parser.add_argument("--output", type=Path, default=HERE / "template" / "report.tex")
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--keep-subtitle", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    report = generate(args.content.resolve(), args.equations.resolve(), output, args.keep_subtitle)
    provenance = args.provenance or output.parent / "generation_provenance.json"
    provenance.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
