import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from native_lens.cli import main
from native_lens.pipeline import compare_pngs
from native_lens.raster.analysis import AnalysisError, analyze_png, otsu_threshold


def score_page(
    path: Path,
    *,
    note_offset: int = 0,
    left: int = 25,
    top_offset: int = 0,
    size: tuple[int, int] = (420, 180),
) -> None:
    image = Image.new("L", size, 255)
    draw = ImageDraw.Draw(image)
    for staff_top in (35 + top_offset, 110 + top_offset):
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
    assert report["components"]["candidate_edge_count"] >= len(report["components"]["matches"])
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


def test_failed_analysis_leaves_no_partial_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    reference = tmp_path / "reference.png"
    candidate = tmp_path / "blank.png"
    output = tmp_path / "report"
    score_page(reference)
    Image.new("L", (100, 100), 255).save(candidate)

    with pytest.raises(SystemExit) as exit_info:
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

    assert exit_info.value.code == 2
    assert "no five-line staff detected" in capsys.readouterr().err
    assert not output.exists()


def test_report_satisfies_published_top_level_contract(tmp_path: Path) -> None:
    reference = tmp_path / "reference.png"
    score_page(reference)
    report = compare_pngs(reference, reference, tmp_path / "report")
    schema_path = Path(__file__).parents[1] / "docs" / "report.schema.json"
    schema = json.loads(schema_path.read_text())

    assert schema["properties"]["schema_version"]["const"] == report["schema_version"]
    assert set(schema["required"]) == set(report)
    assert len(report["alignment"]["reference_to_canvas_px"]) == 6
    assert len(report["alignment"]["candidate_to_canvas_px"]) == 6


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


def test_two_axis_registration_preserves_union_of_different_page_sizes(tmp_path: Path) -> None:
    reference = tmp_path / "reference.png"
    candidate = tmp_path / "candidate.png"
    output = tmp_path / "report"
    score_page(reference)
    score_page(candidate, left=45, top_offset=20, size=(460, 220))

    report = compare_pngs(reference, candidate, output)

    assert report["alignment"]["canvas_width_px"] == 460
    assert report["alignment"]["canvas_height_px"] == 220
    assert report["alignment"]["reference_to_canvas_px"][4:] == [20.0, 20.0]
    assert report["alignment"]["candidate_to_canvas_px"][4:] == [0.0, 0.0]
    assert Image.open(output / "aligned-reference.png").size == (460, 220)
    assert Image.open(output / "aligned-candidate.png").size == (460, 220)
    assert report["raster_secondary"]["foreground_disagreement_ratio"] == 0


def test_scale_is_normalized_from_staff_space(tmp_path: Path) -> None:
    reference = tmp_path / "reference.png"
    candidate = tmp_path / "candidate.png"
    score_page(reference)
    with Image.open(reference) as image:
        image.resize((525, 225), Image.Resampling.NEAREST).save(candidate)

    report = compare_pngs(reference, candidate, tmp_path / "report")

    assert report["alignment"]["candidate_scale"] == pytest.approx(0.8, abs=0.02)
    assert report["components"]["match_ratio"] > 0.8


def test_small_skew_is_detected_and_removed(tmp_path: Path) -> None:
    reference = tmp_path / "reference.png"
    candidate = tmp_path / "candidate.png"
    score_page(reference)
    with Image.open(reference) as image:
        image.rotate(0.8, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255).save(
            candidate
        )

    report = compare_pngs(reference, candidate, tmp_path / "report")

    assert abs(report["candidate"]["estimated_skew_degrees"]) == pytest.approx(0.8, abs=0.11)
    assert report["structural"]["staff_count_matches"] is True
    candidate_transform = report["alignment"]["candidate_to_canvas_px"]
    assert abs(candidate_transform[1]) > 0.01
    assert abs(candidate_transform[2]) > 0.01


def test_executable_benchmark_smoke() -> None:
    root = Path(__file__).parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(root / "benchmarks" / "benchmark_pipeline.py"),
            "--width",
            "600",
            "--height",
            "500",
            "--repeat",
            "1",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    metrics = json.loads(result.stdout)
    assert metrics["objects"] > 0
    assert metrics["max_seconds"] > 0
