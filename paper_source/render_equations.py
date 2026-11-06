"""Render black-on-white mathematical assets from equations.json.

Usage from the project root:
    .venv/Scripts/python.exe paper_source/render_equations.py

The source maps each asset key to one or more matplotlib mathtext lines. Width
is capped without changing the mathematics; related formula lines share one
font size. Rendering is independent of all optimization modules and results.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


DEFAULT_DPI = 220
DEFAULT_FONT_SIZE = 18.0
MAX_WIDTH_INCHES = 6.6
PADDING_INCHES = 0.075
LINE_GAP_INCHES = 0.10


def _measure(lines: list[str], fontsize: float, dpi: int) -> list[tuple[float, float]]:
    fig = plt.figure(figsize=(MAX_WIDTH_INCHES, 2), dpi=dpi, facecolor="white")
    artists = [fig.text(.5, .5, line, fontsize=fontsize, color="black",
                        ha="center", va="center") for line in lines]
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    sizes = [(artist.get_window_extent(renderer).width / dpi,
              artist.get_window_extent(renderer).height / dpi) for artist in artists]
    plt.close(fig)
    return sizes


def render_equations(source: Path, output: Path, dpi: int = DEFAULT_DPI,
                     fontsize: float = DEFAULT_FONT_SIZE) -> list[Path]:
    source, output = Path(source).resolve(), Path(output).resolve()
    definitions = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(definitions, dict) or not definitions:
        raise ValueError("equations.json must map asset keys to nonempty line lists")
    if dpi <= 0 or fontsize <= 0:
        raise ValueError("DPI and font size must be positive")
    output.mkdir(parents=True, exist_ok=True)
    rendered = []
    manifest = {"matplotlib_version": matplotlib.__version__, "dpi": dpi,
                "base_font_size": fontsize, "max_width_inches": MAX_WIDTH_INCHES,
                "equations_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "renderer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "assets": {}}
    for key, lines in definitions.items():
        if not key.replace("_", "").isalnum() or not isinstance(lines, list) or not lines:
            raise ValueError(f"Invalid equation definition: {key!r}")
        if not all(isinstance(line, str) and line.startswith("$") and line.endswith("$")
                   for line in lines):
            raise ValueError(f"Equation lines must be mathtext strings: {key!r}")
        actual_fontsize = fontsize
        sizes = _measure(lines, actual_fontsize, dpi)
        available = MAX_WIDTH_INCHES - 2 * PADDING_INCHES
        widest = max(width for width, _ in sizes)
        if widest > available:
            actual_fontsize *= available / widest * .99
            sizes = _measure(lines, actual_fontsize, dpi)
        width = max(w for w, _ in sizes) + 2 * PADDING_INCHES
        height = sum(h for _, h in sizes) + (len(lines) - 1) * LINE_GAP_INCHES + 2 * PADDING_INCHES
        fig = plt.figure(figsize=(width, height), dpi=dpi, facecolor="white")
        consumed = PADDING_INCHES
        for line, (_, line_height) in zip(lines, sizes):
            y = 1 - (consumed + line_height / 2) / height
            fig.text(.5, y, line, fontsize=actual_fontsize, color="black",
                     ha="center", va="center")
            consumed += line_height + LINE_GAP_INCHES
        target = output / f"{key}.png"
        fig.savefig(target, dpi=dpi, facecolor="white", transparent=False)
        plt.close(fig)
        manifest["assets"][key] = {"filename": target.name, "font_size": actual_fontsize,
                                    "width_inches": width, "height_inches": height,
                                    "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
        rendered.append(target)
    (output / "equations_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rendered


def main() -> None:
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=base / "equations.json")
    parser.add_argument("--output", type=Path, default=base / "assets")
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    parser.add_argument("--font-size", type=float, default=DEFAULT_FONT_SIZE)
    args = parser.parse_args()
    for path in render_equations(args.source, args.output, args.dpi, args.font_size):
        print(path)


if __name__ == "__main__":
    main()
