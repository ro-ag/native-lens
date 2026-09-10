"""Stable report structures and JSON conversion."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from native_lens.geometry import AffineTransform, Point, Rect

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

REPORT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class StaffRegion:
    """A detected five-line staff measured in staff-space units."""

    id: str
    bounds_sp: Rect
    line_y_sp: tuple[float, float, float, float, float]
    confidence: float


@dataclass(frozen=True, slots=True)
class SystemRegion:
    """A group of staves joined into a single system."""

    id: str
    bounds_sp: Rect
    staff_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExtractedObject:
    """A non-staff connected component measured in staff-space units."""

    id: str
    kind: str
    semantic_id: str | None
    bounds_sp: Rect
    centroid_sp: Point
    area_sp2: float


@dataclass(frozen=True, slots=True)
class PageAnalysis:
    """The complete structural analysis of one rendered page."""

    source: dict[str, Any]
    staff_space_px: float
    estimated_skew_degrees: float
    binarization_threshold: int
    staves: tuple[StaffRegion, ...]
    systems: tuple[SystemRegion, ...]
    objects: tuple[ExtractedObject, ...]


@dataclass(frozen=True, slots=True)
class ObjectMatch:
    """A correspondence between one reference and one candidate component."""

    reference_id: str
    candidate_id: str
    centroid_delta_sp: Point
    centroid_distance_sp: float
    width_delta_sp: float
    height_delta_sp: float
    cost: float


def report_dict(value: DataclassInstance) -> dict[str, Any]:
    """Convert a report dataclass tree and round floating output."""

    def clean(item: Any) -> Any:
        if isinstance(item, float):
            return round(item, 6)
        if isinstance(item, dict):
            return {key: clean(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [clean(child) for child in item]
        return item

    result: dict[str, Any] = clean(asdict(value))
    return result


__all__ = [
    "REPORT_SCHEMA_VERSION",
    "AffineTransform",
    "ExtractedObject",
    "ObjectMatch",
    "PageAnalysis",
    "Point",
    "Rect",
    "StaffRegion",
    "SystemRegion",
    "report_dict",
]
