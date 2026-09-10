"""Source-independent two-dimensional geometry."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot


@dataclass(frozen=True, slots=True)
class Point:
    x: float
    y: float

    def distance(self, other: Point) -> float:
        return hypot(self.x - other.x, self.y - other.y)

    def lerp(self, other: Point, amount: float) -> Point:
        return Point(self.x + (other.x - self.x) * amount, self.y + (other.y - self.y) * amount)


@dataclass(frozen=True, slots=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center(self) -> Point:
        return Point(self.x + self.width / 2, self.y + self.height / 2)


@dataclass(frozen=True, slots=True)
class AffineTransform:
    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    def apply(self, point: Point) -> Point:
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
    start: Point
    end: Point

    def length(self) -> float:
        return self.start.distance(self.end)

    def evaluate(self, amount: float) -> Point:
        return self.start.lerp(self.end, amount)


@dataclass(frozen=True, slots=True)
class CubicBezier:
    start: Point
    control_1: Point
    control_2: Point
    end: Point

    def evaluate(self, amount: float) -> Point:
        amount = min(1.0, max(0.0, amount))
        a = self.start.lerp(self.control_1, amount)
        b = self.control_1.lerp(self.control_2, amount)
        c = self.control_2.lerp(self.end, amount)
        return a.lerp(b, amount).lerp(b.lerp(c, amount), amount)
