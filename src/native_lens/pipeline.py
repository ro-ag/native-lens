"""End-to-end comparison and artifact generation."""

from __future__ import annotations

import json
from dataclasses import asdict
from math import log
from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

from native_lens.config import AnalysisConfig
from native_lens.model import (
    REPORT_SCHEMA_VERSION,
    AffineTransform,
    ObjectMatch,
    Point,
    report_dict,
)
from native_lens.raster.analysis import RasterAnalysis, analyze_png

if TYPE_CHECKING:
    from pathlib import Path


def _matches(
    reference: RasterAnalysis, candidate: RasterAnalysis, config: AnalysisConfig
) -> dict[str, Any]:
    edges: list[tuple[float, int, int]] = []
    candidate_points = np.array(
        [(item.centroid_sp.x, item.centroid_sp.y) for item in candidate.page.objects],
        dtype=np.float64,
    )
    candidate_tree = cKDTree(candidate_points) if len(candidate_points) else None
    for left_index, left in enumerate(reference.page.objects):
        nearby = (
            candidate_tree.query_ball_point(
                (left.centroid_sp.x, left.centroid_sp.y),
                config.component_match_max_distance_sp,
            )
            if candidate_tree is not None
            else []
        )
        for right_index in sorted(nearby):
            right = candidate.page.objects[right_index]
            distance = left.centroid_sp.distance(right.centroid_sp)
            size_ratio = abs(log(max(left.area_sp2, 1e-9) / max(right.area_sp2, 1e-9)))
            if (
                distance <= config.component_match_max_distance_sp
                and size_ratio <= config.component_match_max_size_log_ratio
            ):
                edges.append((distance + 0.25 * size_ratio, left_index, right_index))
    used_left: set[int] = set()
    used_right: set[int] = set()
    matched: list[ObjectMatch] = []
    for cost, left_index, right_index in sorted(edges):
        if left_index in used_left or right_index in used_right:
            continue
        used_left.add(left_index)
        used_right.add(right_index)
        left = reference.page.objects[left_index]
        right = candidate.page.objects[right_index]
        delta = Point(
            right.centroid_sp.x - left.centroid_sp.x, right.centroid_sp.y - left.centroid_sp.y
        )
        matched.append(
            ObjectMatch(
                left.id,
                right.id,
                delta,
                left.centroid_sp.distance(right.centroid_sp),
                right.bounds_sp.width - left.bounds_sp.width,
                right.bounds_sp.height - left.bounds_sp.height,
                cost,
            )
        )
    denominator = max(len(reference.page.objects), len(candidate.page.objects), 1)
    return {
        "candidate_edge_count": len(edges),
        "matches": [report_dict(item) for item in matched],
        "unmatched_reference_ids": [
            item.id for index, item in enumerate(reference.page.objects) if index not in used_left
        ],
        "unmatched_candidate_ids": [
            item.id for index, item in enumerate(candidate.page.objects) if index not in used_right
        ],
        "match_ratio": round(len(matched) / denominator, 6),
        "mean_centroid_distance_sp": round(
            sum(item.centroid_distance_sp for item in matched) / len(matched), 6
        )
        if matched
        else None,
    }


def _aligned(
    reference: RasterAnalysis, candidate: RasterAnalysis
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    scale = reference.page.staff_space_px / candidate.page.staff_space_px
    candidate_image = Image.fromarray(candidate.gray).resize(
        (round(candidate.gray.shape[1] * scale), round(candidate.gray.shape[0] * scale)),
        Image.Resampling.BICUBIC,
    )
    candidate_gray = np.asarray(candidate_image)
    shift_x = round(reference.anchor_px.x - candidate.anchor_px.x * scale)
    shift_y = round(reference.anchor_px.y - candidate.anchor_px.y * scale)
    left = min(0, shift_x)
    top = min(0, shift_y)
    right = max(reference.gray.shape[1], shift_x + candidate_gray.shape[1])
    bottom = max(reference.gray.shape[0], shift_y + candidate_gray.shape[0])
    left_canvas = np.full((bottom - top, right - left), 255, dtype=np.uint8)
    right_canvas = left_canvas.copy()
    left_canvas[-top : -top + reference.gray.shape[0], -left : -left + reference.gray.shape[1]] = (
        reference.gray
    )
    right_canvas[
        shift_y - top : shift_y - top + candidate_gray.shape[0],
        shift_x - left : shift_x - left + candidate_gray.shape[1],
    ] = candidate_gray
    reference_to_canvas = reference.source_to_deskew_px.then(AffineTransform(e=-left, f=-top))
    candidate_to_canvas = candidate.source_to_deskew_px.then(
        AffineTransform(a=scale, d=scale)
    ).then(AffineTransform(e=shift_x - left, f=shift_y - top))
    alignment = {
        "candidate_scale": round(scale, 6),
        "reference_to_canvas_px": _affine_values(reference_to_canvas),
        "candidate_to_canvas_px": _affine_values(candidate_to_canvas),
        "canvas_width_px": right - left,
        "canvas_height_px": bottom - top,
    }
    return left_canvas, right_canvas, alignment


def _affine_values(transform: AffineTransform) -> list[float]:
    return [
        round(value, 6)
        for value in (transform.a, transform.b, transform.c, transform.d, transform.e, transform.f)
    ]


def _save_artifacts(reference: np.ndarray, candidate: np.ndarray, output: Path) -> dict[str, str]:
    names = {
        "aligned_reference": "aligned-reference.png",
        "aligned_candidate": "aligned-candidate.png",
        "overlay": "overlay.png",
        "diff": "diff.png",
    }
    Image.fromarray(reference).save(output / names["aligned_reference"])
    Image.fromarray(candidate).save(output / names["aligned_candidate"])
    reference_ink = 255 - reference
    candidate_ink = 255 - candidate
    overlay = np.full((*reference.shape, 3), 255, dtype=np.uint8)
    overlay[..., 0] = 255 - candidate_ink
    overlay[..., 1] = 255 - reference_ink
    overlay[..., 2] = 255 - candidate_ink
    Image.fromarray(overlay).save(output / names["overlay"])
    Image.fromarray(
        np.abs(reference.astype(np.int16) - candidate.astype(np.int16)).astype(np.uint8)
    ).save(output / names["diff"])
    return names


def compare_pngs(
    reference_path: Path, candidate_path: Path, output: Path, config: AnalysisConfig | None = None
) -> dict[str, Any]:
    """Compare two PNG score pages and write a deterministic report directory."""
    config = config or AnalysisConfig()
    reference = analyze_png(reference_path, "reference", config)
    candidate = analyze_png(candidate_path, "candidate", config)
    aligned_reference, aligned_candidate, alignment = _aligned(reference, candidate)
    output.mkdir(parents=True, exist_ok=True)
    artifacts = _save_artifacts(aligned_reference, aligned_candidate, output)
    components = _matches(reference, candidate, config)
    foreground_left = aligned_reference <= reference.page.binarization_threshold
    foreground_right = aligned_candidate <= candidate.page.binarization_threshold
    structural = {
        "reference_staff_count": len(reference.page.staves),
        "candidate_staff_count": len(candidate.page.staves),
        "reference_system_count": len(reference.page.systems),
        "candidate_system_count": len(candidate.page.systems),
        "staff_count_matches": len(reference.page.staves) == len(candidate.page.staves),
        "system_count_matches": len(reference.page.systems) == len(candidate.page.systems),
    }
    structural_score = (
        float(structural["staff_count_matches"]) + float(structural["system_count_matches"])
    ) / 2
    overall = 0.6 * structural_score + 0.4 * components["match_ratio"]
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "overall_score": round(overall, 6),
        "config": asdict(config),
        "reference": report_dict(reference.page),
        "candidate": report_dict(candidate.page),
        "alignment": alignment,
        "structural": structural,
        "components": components,
        "raster_secondary": {
            "mean_absolute_luma_error": round(
                float(
                    np.mean(
                        np.abs(
                            aligned_reference.astype(np.int16) - aligned_candidate.astype(np.int16)
                        )
                    )
                )
                / 255,
                6,
            ),
            "foreground_disagreement_ratio": round(
                float(np.mean(foreground_left != foreground_right)), 6
            ),
        },
        "artifacts": artifacts,
    }
    (output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report
