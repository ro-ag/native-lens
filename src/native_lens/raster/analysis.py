"""Classical raster analysis used by the first milestone."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from native_lens.config import AnalysisConfig
from native_lens.geometry import Point, Rect
from native_lens.model import ExtractedObject, PageAnalysis, StaffRegion, SystemRegion


class AnalysisError(ValueError):
    """Raised when a page cannot establish notation coordinates."""


@dataclass(frozen=True, slots=True)
class RasterAnalysis:
    page: PageAnalysis
    gray: np.ndarray
    ink: np.ndarray
    staff_rows_px: tuple[tuple[float, ...], ...]
    staff_bounds_px: tuple[tuple[int, int], ...]
    anchor_px: Point


def load_gray(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        if image.format != "PNG":
            raise AnalysisError(f"expected PNG input: {path}")
        return np.asarray(image.convert("L"), dtype=np.uint8)


def otsu_threshold(gray: np.ndarray) -> int:
    histogram = np.bincount(gray.ravel(), minlength=256).astype(np.float64)
    count = gray.size
    total = np.dot(np.arange(256), histogram)
    background_count = 0.0
    background_sum = 0.0
    best_threshold = 0
    best_variance = -1.0
    for threshold, frequency in enumerate(histogram):
        background_count += frequency
        if background_count == 0:
            continue
        foreground_count = count - background_count
        if foreground_count == 0:
            break
        background_sum += threshold * frequency
        mean_background = background_sum / background_count
        mean_foreground = (total - background_sum) / foreground_count
        variance = background_count * foreground_count * (mean_background - mean_foreground) ** 2
        if variance > best_variance:
            best_variance = variance
            best_threshold = threshold
    return best_threshold


def estimate_skew(ink: np.ndarray, config: AnalysisConfig) -> float:
    y, x = np.nonzero(ink)
    if not len(x):
        return 0.0
    stride = max(1, len(x) // config.skew_sample_limit)
    x = x[::stride].astype(np.float64)
    y = y[::stride].astype(np.float64)
    angles = np.arange(
        -config.max_abs_skew_degrees,
        config.max_abs_skew_degrees + config.skew_step_degrees / 2,
        config.skew_step_degrees,
    )
    best = (float("-inf"), 0.0)
    for angle in angles:
        radians = np.deg2rad(angle)
        bins = np.rint(y * np.cos(radians) - x * np.sin(radians)).astype(np.int64)
        bins -= bins.min()
        counts = np.bincount(bins)
        score = float(np.dot(counts, counts))
        if score > best[0]:
            best = (score, float(angle))
    return round(best[1], 6)


def _runs(indices: np.ndarray) -> list[np.ndarray]:
    if indices.size == 0:
        return []
    splits = np.flatnonzero(np.diff(indices) > 1) + 1
    return list(np.split(indices, splits))


def detect_staff_rows(ink: np.ndarray, config: AnalysisConfig) -> tuple[tuple[float, ...], ...]:
    projection = ink.sum(axis=1)
    cutoff = max(
        ink.shape[1] * config.min_staff_line_page_width_ratio,
        float(projection.max()) * 0.55,
    )
    centers = [
        float(np.average(run, weights=projection[run]))
        for run in _runs(np.flatnonzero(projection >= cutoff))
    ]
    groups: list[tuple[float, ...]] = []
    index = 0
    while index <= len(centers) - 5:
        rows = tuple(centers[index : index + 5])
        gaps = np.diff(rows)
        spacing = float(np.median(gaps))
        if (
            spacing >= 2
            and np.max(np.abs(gaps - spacing)) <= spacing * config.staff_gap_relative_tolerance
        ):
            groups.append(rows)
            index += 5
        else:
            index += 1
    if not groups:
        raise AnalysisError("no five-line staff detected")
    return tuple(groups)


def detect_staff_extents(
    ink: np.ndarray, rows: tuple[tuple[float, ...], ...], spacing: float
) -> tuple[tuple[int, int], ...]:
    """Find the horizontal span supported by at least three staff lines."""
    extents: list[tuple[int, int]] = []
    gap_fill = np.ones(max(1, round(spacing)), dtype=bool)
    for staff in rows:
        support = np.zeros(ink.shape[1], dtype=np.uint8)
        for value in staff:
            row = round(value)
            band = ink[max(0, row - 1) : min(ink.shape[0], row + 2)]
            support += band.any(axis=0)
        continuous = ndimage.binary_closing(support >= 3, structure=gap_fill)
        candidates = _runs(np.flatnonzero(continuous))
        if not candidates:
            raise AnalysisError("staff lines have no common horizontal extent")
        longest = max(candidates, key=lambda run: (len(run), -int(run[0])))
        extents.append((int(longest[0]), int(longest[-1]) + 1))
    return tuple(extents)


def _remove_staff(
    ink: np.ndarray, rows: tuple[tuple[float, ...], ...], spacing: float, config: AnalysisConfig
) -> np.ndarray:
    result = ink.copy()
    minimum_run = max(2, round(spacing * config.staff_removal_min_run_sp))
    for row in {round(value) for staff in rows for value in staff}:
        for y in range(max(0, row - 1), min(result.shape[0], row + 2)):
            for run in _runs(np.flatnonzero(result[y])):
                if len(run) >= minimum_run:
                    result[y, run] = False
    return result


def analyze_png(path: Path, role: str, config: AnalysisConfig) -> RasterAnalysis:
    source_gray = load_gray(path)
    source_threshold = otsu_threshold(source_gray)
    source_ink = source_gray <= source_threshold
    skew = estimate_skew(source_ink, config)
    gray = ndimage.rotate(source_gray, -skew, reshape=True, order=1, mode="constant", cval=255)
    gray = np.clip(np.rint(gray), 0, 255).astype(np.uint8)
    threshold = otsu_threshold(gray)
    ink = gray <= threshold
    rows = detect_staff_rows(ink, config)
    spaces = [gap for staff in rows for gap in np.diff(staff)]
    spacing = float(np.median(spaces))
    extents = detect_staff_extents(ink, rows, spacing)
    anchor = Point(float(extents[0][0]), rows[0][0])

    staves: list[StaffRegion] = []
    for index, (staff, extent) in enumerate(zip(rows, extents, strict=True), 1):
        bounds = Rect(
            (extent[0] - anchor.x) / spacing,
            (staff[0] - anchor.y) / spacing,
            (extent[1] - extent[0]) / spacing,
            4.0,
        )
        staves.append(
            StaffRegion(
                f"staff-{index}",
                bounds,
                tuple((row - anchor.y) / spacing for row in staff),
                1.0 - float(np.std(np.diff(staff)) / spacing),
            )
        )

    systems: list[SystemRegion] = []
    current: list[StaffRegion] = []
    for staff in staves:
        if (
            current
            and staff.bounds_sp.y - current[-1].bounds_sp.bottom > config.system_break_gap_sp
        ):
            systems.append(_system(len(systems) + 1, current))
            current = []
        current.append(staff)
    systems.append(_system(len(systems) + 1, current))

    without_staff = _remove_staff(ink, rows, spacing, config)
    labels, count = ndimage.label(without_staff, structure=np.ones((3, 3), dtype=np.uint8))
    objects: list[ExtractedObject] = []
    for label_id in range(1, count + 1):
        y, x = np.nonzero(labels == label_id)
        area = len(x) / spacing**2
        if area < config.min_component_area_sp2:
            continue
        bounds = Rect(
            (x.min() - anchor.x) / spacing,
            (y.min() - anchor.y) / spacing,
            (x.max() - x.min() + 1) / spacing,
            (y.max() - y.min() + 1) / spacing,
        )
        objects.append(
            ExtractedObject(
                "",
                "unclassified_component",
                None,
                bounds,
                Point(
                    float((x.mean() - anchor.x) / spacing),
                    float((y.mean() - anchor.y) / spacing),
                ),
                float(area),
            )
        )
    objects.sort(key=lambda item: (item.centroid_sp.y, item.centroid_sp.x, item.area_sp2))
    objects = [
        ExtractedObject(
            f"component-{index}", item.kind, None, item.bounds_sp, item.centroid_sp, item.area_sp2
        )
        for index, item in enumerate(objects, 1)
    ]
    page = PageAnalysis(
        {
            "role": role,
            "format": "png",
            "path": str(path),
            "width_px": source_gray.shape[1],
            "height_px": source_gray.shape[0],
        },
        spacing,
        skew,
        threshold,
        tuple(staves),
        tuple(systems),
        tuple(objects),
    )
    return RasterAnalysis(page, gray, ink, rows, extents, anchor)


def _system(index: int, staves: list[StaffRegion]) -> SystemRegion:
    left = min(staff.bounds_sp.x for staff in staves)
    top = staves[0].bounds_sp.y
    right = max(staff.bounds_sp.right for staff in staves)
    bottom = staves[-1].bounds_sp.bottom
    return SystemRegion(
        f"system-{index}",
        Rect(left, top, right - left, bottom - top),
        tuple(item.id for item in staves),
    )
