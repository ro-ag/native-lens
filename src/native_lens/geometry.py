"""Source-independent two-dimensional geometry."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot


@dataclass(frozen=True, slots=True)
class Point:
    """A position on a two-dimensional plane."""

    x: float
    y: float

    def distance(self, other: Point) -> float:
        """Return the Euclidean distance to ``other``."""
        return hypot(self.x - other.x, self.y - other.y)

    def lerp(self, other: Point, amount: float) -> Point:
        """Return the point interpolated toward ``other`` by ``amount``."""
        return Point(self.x + (other.x - self.x) * amount, self.y + (other.y - self.y) * amount)


@dataclass(frozen=True, slots=True)
class Rect:
    """An axis-aligned rectangle."""

    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        """Return the x coordinate of the right edge."""
        return self.x + self.width

    @property
    def bottom(self) -> float:
        """Return the y coordinate of the bottom edge."""
        return self.y + self.height

    @property
    def center(self) -> Point:
        """Return the rectangle's center point."""
        return Point(self.x + self.width / 2, self.y + self.height / 2)


@dataclass(frozen=True, slots=True)
class AffineTransform:
    """A two-dimensional affine transform in ``(a, b, c, d, e, f)`` matrix order."""

    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    def apply(self, point: Point) -> Point:
        """Return the image of ``point`` under this transform."""
        return Point(
            self.a * point.x + self.c * point.y + self.e,
            self.b * point.x + self.d * point.y + self.f,
        )

    def then(self, following: AffineTransform) -> AffineTransform:
        """Return the transform that applies this transform, then ``following``."""
        return AffineTransform(
            a=following.a * self.a + following.c * self.b,
            b=following.b * self.a + following.d * self.b,
            c=following.a * self.c + following.c * self.d,
            d=following.b * self.c + following.d * self.d,
            e=following.a * self.e + following.c * self.f + following.e,
            f=following.b * self.e + following.d * self.f + following.f,
        )


@dataclass(frozen=True, slots=True)
class LineSegment:
    """A straight segment between two points."""

    start: Point
    end: Point

    def length(self) -> float:
        """Return the Euclidean length of the segment."""
        return self.start.distance(self.end)

    def evaluate(self, amount: float) -> Point:
        """Return the point ``amount`` of the way from ``start`` to ``end``."""
        return self.start.lerp(self.end, amount)


@dataclass(frozen=True, slots=True)
class CubicBezier:
    """A cubic Bezier curve defined by four control points."""

    start: Point
    control_1: Point
    control_2: Point
    end: Point

    def evaluate(self, amount: float) -> Point:
        """Return the point on the curve at parameter ``amount``."""
        amount = min(1.0, max(0.0, amount))
        a = self.start.lerp(self.control_1, amount)
        b = self.control_1.lerp(self.control_2, amount)
        c = self.control_2.lerp(self.end, amount)
        return a.lerp(b, amount).lerp(b.lerp(c, amount), amount)
