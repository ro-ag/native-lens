import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from native_lens.cli import main
from native_lens.pipeline import compare_pngs
from native_lens.raster.analysis import AnalysisError, analyze_png, otsu_threshold


def score_page(path: Path, *, note_offset: int = 0, left: int = 25) -> None:
    image = Image.new("L", (420, 180), 255)
    draw = ImageDraw.Draw(image)
    for staff_top in (35, 110):
        for line in range(5):
            y = staff_top + line * 8
            draw.line((left, y, left + 370, y), fill=0, width=1)
        x = left + 65 + note_offset
        draw.ellipse((x - 5, staff_top + 12, x + 5, staff_top + 18), fill=0)
        draw.line((x + 5, staff_top + 15, x + 5, staff_top - 5), fill=0, width=2)
    image.save(path)


def test_otsu_separates_black_and_white() -> None:
    gray = np.array([[0, 0, 255, 255]], dtype=np.uint8)
    assert otsu_threshold(gray) == 0


def test_blank_page_has_no_notation_coordinates(tmp_path: Path) -> None:
    path = tmp_path / "blank.png"
    Image.new("L", (100, 100), 255).save(path)
    with pytest.raises(AnalysisError, match="five-line staff"):
        analyze_png(path, "reference", config=__import__("native_lens").AnalysisConfig())


def test_comparison_writes_stable_report_and_artifacts(tmp_path: Path) -> None:
    reference = tmp_path / "reference.png"
    candidate = tmp_path / "candidate.png"
    output = tmp_path / "report"
    score_page(reference)
    score_page(candidate, note_offset=1)

    report = compare_pngs(reference, candidate, output)

    assert report["schema_version"] == 1
    assert report["structural"]["staff_count_matches"] is True
    assert report["components"]["matches"]
    assert report["reference"]["staves"][0]["bounds_sp"]["x"] == 0
    assert set(report["artifacts"].values()) == {
        "aligned-reference.png",
        "aligned-candidate.png",
        "overlay.png",
        "diff.png",
    }
    assert all((output / name).is_file() for name in report["artifacts"].values())
    assert (
        json.loads((output / "report.json").read_text())["overall_score"] == report["overall_score"]
    )


def test_cli_prints_report_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    reference = tmp_path / "reference.png"
    candidate = tmp_path / "candidate.png"
    output = tmp_path / "report"
    score_page(reference)
    score_page(candidate)
    assert (
        main(
            [
                "compare",
                "--reference",
                str(reference),
                "--candidate",
                str(candidate),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert str(output / "report.json") in capsys.readouterr().out


def test_horizontal_margin_is_removed_by_structural_registration(tmp_path: Path) -> None:
    reference = tmp_path / "reference.png"
    candidate = tmp_path / "candidate.png"
    score_page(reference, left=15)
    score_page(candidate, left=35)

    report = compare_pngs(reference, candidate, tmp_path / "report")

    candidate_transform = report["alignment"]["candidate_to_canvas_px"]
    reference_transform = report["alignment"]["reference_to_canvas_px"]
    assert candidate_transform[4] - reference_transform[4] == -20
    assert report["raster_secondary"]["foreground_disagreement_ratio"] < 0.01
