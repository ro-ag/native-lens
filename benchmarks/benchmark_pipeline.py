"""Executable end-to-end benchmark for a dense synthetic score page."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from time import perf_counter

from PIL import Image, ImageDraw

from native_lens import compare_pngs

MIN_DIMENSION_PX = 200


def make_page(path: Path, width: int, height: int) -> None:
    image = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(image)
    margin = width // 16
    spacing = max(6, width // 180)
    system_step = spacing * 12
    for top in range(spacing * 5, height - spacing * 6, system_step):
        for line in range(5):
            y = top + line * spacing
            draw.line((margin, y, width - margin, y), fill=0, width=1)
        for x in range(margin + spacing * 5, width - margin, spacing * 7):
            y = top + ((x // spacing) % 4) * spacing
            draw.ellipse((x - spacing // 2, y - 2, x + spacing // 2, y + 3), fill=0)
            draw.line((x + spacing // 2, y, x + spacing // 2, y - spacing * 3), fill=0)
    image.save(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=2200)
    parser.add_argument("--repeat", type=int, default=3)
    arguments = parser.parse_args()
    if (
        arguments.width < MIN_DIMENSION_PX
        or arguments.height < MIN_DIMENSION_PX
        or arguments.repeat < 1
    ):
        parser.error(
            f"width and height must be at least {MIN_DIMENSION_PX}; repeat must be positive"
        )

    with tempfile.TemporaryDirectory(prefix="native-lens-benchmark-") as directory:
        root = Path(directory)
        page = root / "score.png"
        make_page(page, arguments.width, arguments.height)
        durations = []
        object_count = 0
        candidate_edge_count = 0
        for run in range(arguments.repeat):
            started = perf_counter()
            report = compare_pngs(page, page, root / f"report-{run}")
            durations.append(perf_counter() - started)
            object_count = len(report["reference"]["objects"])
            candidate_edge_count = report["components"]["candidate_edge_count"]
    print(
        json.dumps(
            {
                "candidate_edges": candidate_edge_count,
                "height_px": arguments.height,
                "max_seconds": round(max(durations), 6),
                "mean_seconds": round(sum(durations) / len(durations), 6),
                "min_seconds": round(min(durations), 6),
                "objects": object_count,
                "page_pixels": arguments.width * arguments.height,
                "repeat": arguments.repeat,
                "width_px": arguments.width,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
