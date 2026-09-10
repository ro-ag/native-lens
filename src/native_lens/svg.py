"""
SVG parsing into flattened vector geometry in root user-space units.

Parses a practical subset of SVG 1.1: the seven shape elements, the full path
command set, transform lists, basic paints, and text placement. Arcs and
quadratic curves are converted to cubic Bezier curves, and every transform is
flattened into segment endpoints and control points, so consumers only ever
see line segments and cubic curves. Font glyphs are NOT resolved: <text>
records placement and content only. Constructs the module cannot honor (such
as <use> elements or rounded rectangles) raise UnsupportedFeatureError
instead of silently dropping content, while malformed markup and values raise
SvgError. Elements outside the modeled subset (for example gradients) and
elements in foreign namespaces are ignored.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING, Protocol
from xml.etree.ElementTree import ParseError, fromstring

from native_lens.geometry import (
    AffineTransform,
    CubicBezier,
    LineSegment,
    Point,
    Rect,
)

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element

SVG_NAMESPACE = "http://www.w3.org/2000/svg"

type Segment = LineSegment | CubicBezier

_KAPPA = 4.0 / 3.0 * (2.0**0.5 - 1.0)
_FULL_TURN = 2.0 * math.pi
_QUARTER_TURN = math.pi / 2
_MATRIX_ARGUMENTS = 6
_ARC_ARGUMENTS = 7
_VIEW_BOX_NUMBERS = 4
_MINIMUM_POINT_NUMBERS = 4

_BASIC_COLORS = {
    "aqua": "#00ffff",
    "black": "#000000",
    "blue": "#0000ff",
    "fuchsia": "#ff00ff",
    "gray": "#808080",
    "green": "#008000",
    "lime": "#00ff00",
    "maroon": "#800000",
    "navy": "#000080",
    "olive": "#808000",
    "purple": "#800080",
    "red": "#ff0000",
    "silver": "#c0c0c0",
    "teal": "#008080",
    "white": "#ffffff",
    "yellow": "#ffff00",
}

_SKIPPED_ELEMENTS = frozenset(
    {
        "defs",
        "clipPath",
        "mask",
        "marker",
        "symbol",
        "pattern",
        "style",
        "title",
        "desc",
        "metadata",
    }
)

_NUMBER_START = frozenset("+-.0123456789")
_SHORT_HEX = re.compile(r"[0-9a-f]{3}")
_LONG_HEX = re.compile(r"[0-9a-f]{6}")
_NUMBER_TOKEN = re.compile(r"[A-Za-z]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_TRANSFORM_FUNCTION = re.compile(r"([a-zA-Z]+)\s*\(([^)]*)\)")
_TRANSFORM_NAMES = frozenset({"matrix", "translate", "scale", "rotate", "skewX", "skewY"})


class SvgError(ValueError):
    """Raised when SVG input is malformed or carries an invalid value."""


class UnsupportedFeatureError(SvgError):
    """Raised when SVG input uses a feature this module does not support."""


@dataclass(frozen=True, slots=True)
class SvgShape:
    """A shape element flattened into subpaths of segments and curves."""

    kind: str
    fill: str | None
    stroke: str | None
    subpaths: tuple[tuple[LineSegment | CubicBezier, ...], ...]


@dataclass(frozen=True, slots=True)
class SvgText:
    """Text placement only; font glyphs are not resolved."""

    x: float
    y: float
    content: str
    fill: str | None


@dataclass(frozen=True, slots=True)
class SvgDocument:
    """The vector content of one SVG file in root user-space units."""

    view_box: Rect | None
    shapes: tuple[SvgShape, ...]
    texts: tuple[SvgText, ...]


@dataclass(frozen=True, slots=True)
class _ArcCommand:
    """The endpoint parameters of one elliptical arc command."""

    rx: float
    ry: float
    rotation: float
    large_arc: bool
    sweep: bool


@dataclass(frozen=True, slots=True)
class _Ellipse:
    """The center parameterization of an arc's ellipse in user space."""

    center: Point
    rx: float
    ry: float
    cos_rotation: float
    sin_rotation: float

    def point(self, angle: float) -> Point:
        """Return the ellipse point at parameter ``angle``."""
        return Point(
            self.center.x
            + self.rx * math.cos(angle) * self.cos_rotation
            - self.ry * math.sin(angle) * self.sin_rotation,
            self.center.y
            + self.rx * math.cos(angle) * self.sin_rotation
            + self.ry * math.sin(angle) * self.cos_rotation,
        )

    def tangent(self, angle: float) -> Point:
        """Return the tangent direction of the ellipse at parameter ``angle``."""
        return Point(
            -self.rx * math.sin(angle) * self.cos_rotation
            - self.ry * math.cos(angle) * self.sin_rotation,
            -self.rx * math.sin(angle) * self.sin_rotation
            + self.ry * math.cos(angle) * self.cos_rotation,
        )


@dataclass
class _Context:
    """The accumulated transform, inherited paint, and collected output."""

    transform: AffineTransform
    fill: str | None
    stroke: str | None
    shapes: list[SvgShape]
    texts: list[SvgText]


class _PathState:
    """The mutable cursor tracking position, subpaths, and reflection controls."""

    def __init__(self) -> None:
        """Start an empty path with no current point."""
        self.current: Point | None = None
        self.subpath_start: Point | None = None
        self.cubic_control: Point | None = None
        self.quadratic_control: Point | None = None
        self.subpaths: list[list[Segment]] = []
        self.is_open = True

    def start_subpath(self, point: Point) -> None:
        """Begin a new subpath at ``point``, dropping a trailing empty subpath."""
        if self.subpaths and not self.subpaths[-1]:
            self.subpaths.pop()
        self.subpaths.append([])
        self.current = point
        self.subpath_start = point
        self.cubic_control = None
        self.quadratic_control = None
        self.is_open = True

    def open_subpath(self) -> tuple[list[Segment], Point]:
        """Return the active segment list and start point, opening a subpath if needed."""
        if self.current is None:
            raise SvgError("path drawing commands require a preceding moveto")
        if not self.is_open or not self.subpaths:
            if self.subpaths and not self.subpaths[-1]:
                self.subpaths.pop()
            self.subpaths.append([])
            self.subpath_start = self.current
            self.cubic_control = None
            self.quadratic_control = None
            self.is_open = True
        return self.subpaths[-1], self.current

    def close(self) -> None:
        """Append the closing segment, return to the start, and seal the subpath."""
        if self.current is not None and self.subpath_start is not None:
            if self.is_open and self.subpaths and self.current != self.subpath_start:
                self.subpaths[-1].append(LineSegment(self.current, self.subpath_start))
            self.current = self.subpath_start
        self.is_open = False
        self.cubic_control = None
        self.quadratic_control = None


class _CommandConsumer(Protocol):
    """The signature shared by every path command consumer."""

    def __call__(self, state: _PathState, tokens: list[str], index: int, *, relative: bool) -> int:
        """Consume one application of the command and return the next token index."""
        ...


class _ShapeBuilder(Protocol):
    """The signature shared by every shape element builder."""

    def __call__(
        self, element: Element, transform: AffineTransform
    ) -> tuple[tuple[Segment, ...], ...]:
        """Build the transformed subpaths for one shape element."""
        ...


def _to_float(token: str, what: str) -> float:
    """Convert one numeric token, raising a precise error otherwise."""
    try:
        value = float(token)
    except ValueError:
        raise SvgError(f"{what} must be a number, got {token!r}") from None
    if not math.isfinite(value):
        raise SvgError(f"{what} must be finite, got {token!r}")
    return value


def _number_attribute(value: str | None, what: str, default: float | None = None) -> float:
    """Read one numeric attribute, falling back to ``default`` when absent."""
    if value is None:
        if default is None:
            raise SvgError(f"{what} is required")
        return default
    return _to_float(value, what)


def _tokenize_numbers(data: str, what: str) -> list[str]:
    """Split path-style numeric data into tokens, rejecting any other content."""
    tokens: list[str] = []
    position = 0
    for match in _NUMBER_TOKEN.finditer(data):
        if data[position : match.start()].strip(" \t\r\n,"):
            raise SvgError(f"malformed {what} at offset {match.start()}")
        tokens.append(match.group(0))
        position = match.end()
    if data[position:].strip(" \t\r\n,"):
        raise SvgError(f"malformed {what} at offset {position}")
    return tokens


def _has_arguments(tokens: list[str], index: int, count: int) -> bool:
    """Return whether ``count`` numeric tokens are available at ``index``."""
    window = tokens[index : index + count]
    return len(window) == count and all(token[0] in _NUMBER_START for token in window)


def _offset_point(base: Point, x: float, y: float, *, relative: bool) -> Point:
    """Return the absolute point reached from ``base`` by ``x`` and ``y``."""
    if relative:
        return Point(base.x + x, base.y + y)
    return Point(x, y)


def _reflect(control: Point | None, current: Point) -> Point:
    """Reflect ``control`` through ``current``, or return ``current`` when absent."""
    if control is None:
        return current
    return Point(2 * current.x - control.x, 2 * current.y - control.y)


def _elevated_quadratic(start: Point, control: Point, end: Point) -> CubicBezier:
    """Return the cubic that draws exactly the given quadratic curve."""
    share = 2.0 / 3.0
    control_1 = Point(
        start.x + share * (control.x - start.x),
        start.y + share * (control.y - start.y),
    )
    control_2 = Point(
        end.x + share * (control.x - end.x),
        end.y + share * (control.y - end.y),
    )
    return CubicBezier(start, control_1, control_2, end)


def _lineto(state: _PathState, x: float, y: float, *, relative: bool) -> None:
    """Append one line segment and update the current point."""
    segments, start = state.open_subpath()
    end = _offset_point(start, x, y, relative=relative)
    segments.append(LineSegment(start, end))
    state.current = end


def _consume_moveto(state: _PathState, tokens: list[str], index: int, *, relative: bool) -> int:
    """Consume one or more moveto coordinate pairs."""
    if not _has_arguments(tokens, index, 2):
        raise SvgError("path moveto requires a coordinate pair")
    leading = True
    while _has_arguments(tokens, index, 2):
        x = _to_float(tokens[index], "path coordinate")
        y = _to_float(tokens[index + 1], "path coordinate")
        index += 2
        if leading:
            base = state.current
            if base is not None and relative:
                point = _offset_point(base, x, y, relative=relative)
            else:
                point = Point(x, y)
            state.start_subpath(point)
            leading = False
        else:
            _lineto(state, x, y, relative=relative)
    return index


def _consume_lineto(state: _PathState, tokens: list[str], index: int, *, relative: bool) -> int:
    """Consume one or more lineto coordinate pairs."""
    if not _has_arguments(tokens, index, 2):
        raise SvgError("path lineto requires a coordinate pair")
    while _has_arguments(tokens, index, 2):
        x = _to_float(tokens[index], "path coordinate")
        y = _to_float(tokens[index + 1], "path coordinate")
        index += 2
        _lineto(state, x, y, relative=relative)
    return index


def _consume_horizontal(state: _PathState, tokens: list[str], index: int, *, relative: bool) -> int:
    """Consume one or more horizontal lineto coordinates."""
    if not _has_arguments(tokens, index, 1):
        raise SvgError("path horizontal lineto requires a coordinate")
    while _has_arguments(tokens, index, 1):
        x = _to_float(tokens[index], "path coordinate")
        index += 1
        segments, start = state.open_subpath()
        end = Point(start.x + x, start.y) if relative else Point(x, start.y)
        segments.append(LineSegment(start, end))
        state.current = end
    return index


def _consume_vertical(state: _PathState, tokens: list[str], index: int, *, relative: bool) -> int:
    """Consume one or more vertical lineto coordinates."""
    if not _has_arguments(tokens, index, 1):
        raise SvgError("path vertical lineto requires a coordinate")
    while _has_arguments(tokens, index, 1):
        y = _to_float(tokens[index], "path coordinate")
        index += 1
        segments, start = state.open_subpath()
        end = Point(start.x, start.y + y) if relative else Point(start.x, y)
        segments.append(LineSegment(start, end))
        state.current = end
    return index


def _consume_cubic(state: _PathState, tokens: list[str], index: int, *, relative: bool) -> int:
    """Consume one or more curveto triples of coordinate pairs."""
    if not _has_arguments(tokens, index, 6):
        raise SvgError("path curveto requires three coordinate pairs")
    while _has_arguments(tokens, index, 6):
        values = [_to_float(token, "path coordinate") for token in tokens[index : index + 6]]
        index += 6
        segments, start = state.open_subpath()
        control_1 = _offset_point(start, values[0], values[1], relative=relative)
        control_2 = _offset_point(start, values[2], values[3], relative=relative)
        end = _offset_point(start, values[4], values[5], relative=relative)
        segments.append(CubicBezier(start, control_1, control_2, end))
        state.current = end
        state.cubic_control = control_2
        state.quadratic_control = None
    return index


def _consume_smooth_cubic(
    state: _PathState, tokens: list[str], index: int, *, relative: bool
) -> int:
    """Consume one or more smooth curveto pairs of coordinate pairs."""
    if not _has_arguments(tokens, index, 4):
        raise SvgError("path smooth curveto requires two coordinate pairs")
    while _has_arguments(tokens, index, 4):
        values = [_to_float(token, "path coordinate") for token in tokens[index : index + 4]]
        index += 4
        segments, start = state.open_subpath()
        control_1 = _reflect(state.cubic_control, start)
        control_2 = _offset_point(start, values[0], values[1], relative=relative)
        end = _offset_point(start, values[2], values[3], relative=relative)
        segments.append(CubicBezier(start, control_1, control_2, end))
        state.current = end
        state.cubic_control = control_2
        state.quadratic_control = None
    return index


def _consume_quadratic(state: _PathState, tokens: list[str], index: int, *, relative: bool) -> int:
    """Consume one or more quadratic curveto pairs of coordinate pairs."""
    if not _has_arguments(tokens, index, 4):
        raise SvgError("path quadratic curveto requires two coordinate pairs")
    while _has_arguments(tokens, index, 4):
        values = [_to_float(token, "path coordinate") for token in tokens[index : index + 4]]
        index += 4
        segments, start = state.open_subpath()
        control = _offset_point(start, values[0], values[1], relative=relative)
        end = _offset_point(start, values[2], values[3], relative=relative)
        segments.append(_elevated_quadratic(start, control, end))
        state.current = end
        state.quadratic_control = control
        state.cubic_control = None
    return index


def _consume_smooth_quadratic(
    state: _PathState, tokens: list[str], index: int, *, relative: bool
) -> int:
    """Consume one or more smooth quadratic curveto coordinate pairs."""
    if not _has_arguments(tokens, index, 2):
        raise SvgError("path smooth quadratic curveto requires a coordinate pair")
    while _has_arguments(tokens, index, 2):
        x = _to_float(tokens[index], "path coordinate")
        y = _to_float(tokens[index + 1], "path coordinate")
        index += 2
        segments, start = state.open_subpath()
        control = _reflect(state.quadratic_control, start)
        end = _offset_point(start, x, y, relative=relative)
        segments.append(_elevated_quadratic(start, control, end))
        state.current = end
        state.quadratic_control = control
        state.cubic_control = None
    return index


def _arc_command(values: list[float]) -> _ArcCommand:
    """Interpret the seven raw arc numbers as endpoint parameters."""
    return _ArcCommand(
        rx=abs(values[0]),
        ry=abs(values[1]),
        rotation=values[2],
        large_arc=values[3] != 0.0,
        sweep=values[4] != 0.0,
    )


def _angle_between(first: Point, second: Point) -> float:
    """Return the signed angle from vector ``first`` to vector ``second`` (F.6.2)."""
    scale = math.hypot(first.x, first.y) * math.hypot(second.x, second.y)
    cosine = max(-1.0, min(1.0, (first.x * second.x + first.y * second.y) / scale))
    angle = math.acos(cosine)
    if first.x * second.y - first.y * second.x < 0:
        return -angle
    return angle


def _arc_cubic(ellipse: _Ellipse, first_angle: float, second_angle: float) -> CubicBezier:
    """Approximate the arc span between the two angles with one cubic."""
    handle = 4.0 / 3.0 * math.tan((second_angle - first_angle) / 4.0)
    start = ellipse.point(first_angle)
    end = ellipse.point(second_angle)
    start_tangent = ellipse.tangent(first_angle)
    end_tangent = ellipse.tangent(second_angle)
    return CubicBezier(
        start,
        Point(start.x + handle * start_tangent.x, start.y + handle * start_tangent.y),
        Point(end.x - handle * end_tangent.x, end.y - handle * end_tangent.y),
        end,
    )


def _arc_segments(start: Point, end: Point, command: _ArcCommand) -> list[Segment]:
    """Return the cubic approximation of one elliptical arc (SVG 1.1 F.6.5)."""
    if command.rx == 0 or command.ry == 0:
        return [LineSegment(start, end)]
    if start == end:
        return []
    rx, ry = command.rx, command.ry
    cos_rotation = math.cos(math.radians(command.rotation))
    sin_rotation = math.sin(math.radians(command.rotation))
    offset_x = (cos_rotation * (start.x - end.x) + sin_rotation * (start.y - end.y)) / 2
    offset_y = (-sin_rotation * (start.x - end.x) + cos_rotation * (start.y - end.y)) / 2
    ratio = offset_x**2 / rx**2 + offset_y**2 / ry**2
    if ratio > 1:
        scale = math.sqrt(ratio)
        rx *= scale
        ry *= scale
    numerator = rx**2 * ry**2 - rx**2 * offset_y**2 - ry**2 * offset_x**2
    denominator = rx**2 * offset_y**2 + ry**2 * offset_x**2
    factor = math.sqrt(max(0.0, numerator / denominator))
    sign = 1.0 if command.large_arc != command.sweep else -1.0
    center_prime_x = sign * factor * rx * offset_y / ry
    center_prime_y = -sign * factor * ry * offset_x / rx
    center = Point(
        cos_rotation * center_prime_x - sin_rotation * center_prime_y + (start.x + end.x) / 2,
        sin_rotation * center_prime_x + cos_rotation * center_prime_y + (start.y + end.y) / 2,
    )
    start_angle = math.atan2(
        (offset_y - center_prime_y) / ry,
        (offset_x - center_prime_x) / rx,
    )
    sweep_angle = _angle_between(
        Point((offset_x - center_prime_x) / rx, (offset_y - center_prime_y) / ry),
        Point((-offset_x - center_prime_x) / rx, (-offset_y - center_prime_y) / ry),
    )
    if not command.sweep and sweep_angle > 0:
        sweep_angle -= _FULL_TURN
    elif command.sweep and sweep_angle < 0:
        sweep_angle += _FULL_TURN
    count = max(1, math.ceil(abs(sweep_angle) / _QUARTER_TURN))
    step = sweep_angle / count
    ellipse = _Ellipse(
        center=center, rx=rx, ry=ry, cos_rotation=cos_rotation, sin_rotation=sin_rotation
    )
    angles = [start_angle + step * number for number in range(count + 1)]
    return [
        _arc_cubic(ellipse, first_angle, second_angle)
        for first_angle, second_angle in pairwise(angles)
    ]


def _consume_arc(state: _PathState, tokens: list[str], index: int, *, relative: bool) -> int:
    """Consume one or more arc argument groups."""
    if not _has_arguments(tokens, index, _ARC_ARGUMENTS):
        raise SvgError(f"path arc requires {_ARC_ARGUMENTS} arguments")
    while _has_arguments(tokens, index, _ARC_ARGUMENTS):
        values = [
            _to_float(tokens[index + offset], "path coordinate") for offset in range(_ARC_ARGUMENTS)
        ]
        index += _ARC_ARGUMENTS
        segments, start = state.open_subpath()
        end = _offset_point(start, values[5], values[6], relative=relative)
        segments.extend(_arc_segments(start, end, _arc_command(values)))
        state.current = end
        state.cubic_control = None
        state.quadratic_control = None
    return index


def _consume_close(state: _PathState, _tokens: list[str], index: int) -> int:
    """Consume a closepath, appending the closing segment when it has length."""
    state.close()
    return index


_CONSUMERS: dict[str, _CommandConsumer] = {
    "m": _consume_moveto,
    "l": _consume_lineto,
    "h": _consume_horizontal,
    "v": _consume_vertical,
    "c": _consume_cubic,
    "s": _consume_smooth_cubic,
    "q": _consume_quadratic,
    "t": _consume_smooth_quadratic,
    "a": _consume_arc,
}


def _transform_segment(segment: Segment, transform: AffineTransform) -> Segment:
    """Return the image of one segment under ``transform``."""
    if isinstance(segment, LineSegment):
        return LineSegment(transform.apply(segment.start), transform.apply(segment.end))
    return CubicBezier(
        transform.apply(segment.start),
        transform.apply(segment.control_1),
        transform.apply(segment.control_2),
        transform.apply(segment.end),
    )


def _transform_subpaths(
    subpaths: list[list[Segment]], transform: AffineTransform
) -> tuple[tuple[Segment, ...], ...]:
    """Flatten every subpath under ``transform``, dropping empty subpaths."""
    return tuple(
        tuple(_transform_segment(segment, transform) for segment in subpath)
        for subpath in subpaths
        if subpath
    )


def _parse_path(data: str, transform: AffineTransform) -> tuple[tuple[Segment, ...], ...]:
    """Interpret full path data into transformed subpaths."""
    tokens = _tokenize_numbers(data, "path data")
    state = _PathState()
    command = ""
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token[0] in _NUMBER_START:
            if not command:
                raise SvgError(f"path data must begin with a command, got {token!r}")
        else:
            command = token
            index += 1
        if command.lower() == "z":
            index = _consume_close(state, tokens, index)
        else:
            consumer = _CONSUMERS.get(command.lower())
            if consumer is None:
                raise SvgError(f"unknown path command {command!r}")
            index = consumer(state, tokens, index, relative=command.islower())
    return _transform_subpaths(state.subpaths, transform)


def _rotation(angle_degrees: float) -> AffineTransform:
    """Return the rotation transform for an angle in degrees."""
    angle = math.radians(angle_degrees)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return AffineTransform(a=cosine, b=sine, c=-sine, d=cosine)


def _checked_arguments(name: str, arguments: str, counts: tuple[int, ...]) -> list[float]:
    """Parse the numeric arguments of one transform function and check their count."""
    numbers = [
        _to_float(token, f"{name} argument") for token in re.split(r"[\s,]+", arguments) if token
    ]
    if len(numbers) not in counts:
        expected = " or ".join(str(count) for count in counts)
        raise SvgError(f"{name} expects {expected} arguments, got {len(numbers)}")
    return numbers


def _parse_transform_function(name: str, arguments: str) -> AffineTransform:
    """Return the transform for one parsed function, validating name and arity."""
    if name not in _TRANSFORM_NAMES:
        raise SvgError(f"unsupported transform function {name!r}")
    if name == "matrix":
        numbers = _checked_arguments(name, arguments, (_MATRIX_ARGUMENTS,))
        return AffineTransform(
            a=numbers[0], b=numbers[1], c=numbers[2], d=numbers[3], e=numbers[4], f=numbers[5]
        )
    if name == "translate":
        numbers = _checked_arguments(name, arguments, (1, 2))
        return AffineTransform(e=numbers[0], f=numbers[1] if len(numbers) > 1 else 0.0)
    if name == "scale":
        numbers = _checked_arguments(name, arguments, (1, 2))
        return AffineTransform(a=numbers[0], d=numbers[1] if len(numbers) > 1 else numbers[0])
    if name == "rotate":
        numbers = _checked_arguments(name, arguments, (1, 3))
        rotation = _rotation(numbers[0])
        if len(numbers) > 1:
            rotation = (
                AffineTransform(e=-numbers[1], f=-numbers[2])
                .then(rotation)
                .then(AffineTransform(e=numbers[1], f=numbers[2]))
            )
        return rotation
    tangent = math.tan(math.radians(_checked_arguments(name, arguments, (1,))[0]))
    if name == "skewX":
        return AffineTransform(c=tangent)
    return AffineTransform(b=tangent)


def _parse_transform(value: str | None) -> AffineTransform:
    """Parse a transform list so that the rightmost function applies to points first."""
    if value is None:
        return AffineTransform()
    result = AffineTransform()
    position = 0
    for match in _TRANSFORM_FUNCTION.finditer(value):
        if value[position : match.start()].strip(" \t\r\n,"):
            raise SvgError(f"malformed transform list: {value!r}")
        result = _parse_transform_function(match.group(1), match.group(2)).then(result)
        position = match.end()
    if value[position:].strip(" \t\r\n,"):
        raise SvgError(f"malformed transform list: {value!r}")
    return result


def _parse_style(value: str | None) -> dict[str, str]:
    """Parse a CSS style attribute into a property mapping."""
    if value is None:
        return {}
    properties: dict[str, str] = {}
    for declaration in value.split(";"):
        if not declaration.strip():
            continue
        name, separator, property_value = declaration.partition(":")
        if not separator:
            raise SvgError(f"malformed style declaration {declaration!r}")
        properties[name.strip()] = property_value.strip()
    return properties


def _paint(value: str) -> str | None:
    """Normalize one paint value to lowercase hex, or None for no paint."""
    lowered = value.strip().lower()
    if lowered == "none":
        return None
    if lowered.startswith("#"):
        digits = lowered[1:]
        if _LONG_HEX.fullmatch(digits):
            return f"#{digits}"
        if _SHORT_HEX.fullmatch(digits):
            return "#" + "".join(char * 2 for char in digits)
        raise SvgError(f"invalid color {value!r}")
    if lowered in _BASIC_COLORS:
        return _BASIC_COLORS[lowered]
    raise SvgError(f"unsupported paint {value!r}")


def _paint_value(
    element: Element, style: dict[str, str], name: str, inherited: str | None
) -> str | None:
    """Resolve one paint property, preferring style, then attributes, then inheritance."""
    raw = style.get(name, element.get(name))
    if raw is None:
        return inherited
    return _paint(raw)


def _resolve_paints(
    element: Element, fill: str | None, stroke: str | None
) -> tuple[str | None, str | None]:
    """Return the fill and stroke established by one element."""
    style = _parse_style(element.get("style"))
    return (
        _paint_value(element, style, "fill", fill),
        _paint_value(element, style, "stroke", stroke),
    )


def _parse_view_box(value: str | None) -> Rect | None:
    """Return the recorded view box, validating its four numbers."""
    if value is None:
        return None
    tokens = [token for token in re.split(r"[\s,]+", value) if token]
    if len(tokens) != _VIEW_BOX_NUMBERS:
        raise SvgError(f"viewBox expects {_VIEW_BOX_NUMBERS} numbers, got {value!r}")
    numbers = [_to_float(token, "viewBox number") for token in tokens]
    return Rect(numbers[0], numbers[1], numbers[2], numbers[3])


def _parse_points(element: Element, element_name: str) -> list[Point]:
    """Parse a points attribute into at least two vertices."""
    raw = element.get("points")
    if raw is None:
        raise SvgError(f"{element_name} points is required")
    numbers = [
        _to_float(token, f"{element_name} coordinate")
        for token in _tokenize_numbers(raw, f"{element_name} points")
    ]
    if len(numbers) % 2:
        raise SvgError(f"{element_name} has an odd number of coordinates: {raw!r}")
    if len(numbers) < _MINIMUM_POINT_NUMBERS:
        raise SvgError(f"{element_name} requires at least two points: {raw!r}")
    return [Point(numbers[index], numbers[index + 1]) for index in range(0, len(numbers), 2)]


def _build_path(element: Element, transform: AffineTransform) -> tuple[tuple[Segment, ...], ...]:
    """Build the subpaths of a path element."""
    data = element.get("d")
    if data is None:
        raise SvgError("path d is required")
    return _parse_path(data, transform)


def _build_line(element: Element, transform: AffineTransform) -> tuple[tuple[Segment, ...], ...]:
    """Build the single segment of a line element."""
    start = Point(
        _number_attribute(element.get("x1"), "line x1", 0.0),
        _number_attribute(element.get("y1"), "line y1", 0.0),
    )
    end = Point(
        _number_attribute(element.get("x2"), "line x2", 0.0),
        _number_attribute(element.get("y2"), "line y2", 0.0),
    )
    return _transform_subpaths([[LineSegment(start, end)]], transform)


def _build_rect(element: Element, transform: AffineTransform) -> tuple[tuple[Segment, ...], ...]:
    """Build the closed four-line subpath of a rect element."""
    x = _number_attribute(element.get("x"), "rect x", 0.0)
    y = _number_attribute(element.get("y"), "rect y", 0.0)
    width = _number_attribute(element.get("width"), "rect width")
    height = _number_attribute(element.get("height"), "rect height")
    if width <= 0 or height <= 0:
        raise SvgError(f"rect width and height must be positive, got {width}x{height}")
    for name in ("rx", "ry"):
        raw = element.get(name)
        if raw is not None and _to_float(raw, f"rect {name}") != 0:
            raise UnsupportedFeatureError(f"rounded rect ({name}) is not supported")
    corners = (
        Point(x, y),
        Point(x + width, y),
        Point(x + width, y + height),
        Point(x, y + height),
    )
    segments: list[Segment] = [
        LineSegment(corners[index], corners[(index + 1) % 4]) for index in range(4)
    ]
    return _transform_subpaths([segments], transform)


def _ellipse_subpaths(
    center: Point, rx: float, ry: float, transform: AffineTransform
) -> tuple[tuple[Segment, ...], ...]:
    """Build the closed four-cubic subpath through the cardinal points."""
    kappa_x = _KAPPA * rx
    kappa_y = _KAPPA * ry
    top = Point(center.x, center.y - ry)
    right = Point(center.x + rx, center.y)
    bottom = Point(center.x, center.y + ry)
    left = Point(center.x - rx, center.y)
    segments: list[Segment] = [
        CubicBezier(
            top,
            Point(center.x + kappa_x, top.y),
            Point(right.x, center.y - kappa_y),
            right,
        ),
        CubicBezier(
            right,
            Point(right.x, center.y + kappa_y),
            Point(bottom.x + kappa_x, bottom.y),
            bottom,
        ),
        CubicBezier(
            bottom,
            Point(bottom.x - kappa_x, bottom.y),
            Point(left.x, center.y + kappa_y),
            left,
        ),
        CubicBezier(
            left,
            Point(left.x, center.y - kappa_y),
            Point(top.x - kappa_x, top.y),
            top,
        ),
    ]
    return _transform_subpaths([segments], transform)


def _build_circle(element: Element, transform: AffineTransform) -> tuple[tuple[Segment, ...], ...]:
    """Build the closed four-cubic subpath of a circle element."""
    center = Point(
        _number_attribute(element.get("cx"), "circle cx", 0.0),
        _number_attribute(element.get("cy"), "circle cy", 0.0),
    )
    radius = _number_attribute(element.get("r"), "circle r")
    if radius <= 0:
        raise SvgError(f"circle radius must be positive, got {radius}")
    return _ellipse_subpaths(center, radius, radius, transform)


def _build_ellipse(element: Element, transform: AffineTransform) -> tuple[tuple[Segment, ...], ...]:
    """Build the closed four-cubic subpath of an ellipse element."""
    center = Point(
        _number_attribute(element.get("cx"), "ellipse cx", 0.0),
        _number_attribute(element.get("cy"), "ellipse cy", 0.0),
    )
    rx = _number_attribute(element.get("rx"), "ellipse rx")
    ry = _number_attribute(element.get("ry"), "ellipse ry")
    if rx <= 0 or ry <= 0:
        raise SvgError(f"ellipse radii must be positive, got {rx} and {ry}")
    return _ellipse_subpaths(center, rx, ry, transform)


def _build_polygon(element: Element, transform: AffineTransform) -> tuple[tuple[Segment, ...], ...]:
    """Build the closed line subpath of a polygon element."""
    points = _parse_points(element, "polygon")
    segments: list[Segment] = [LineSegment(first, second) for first, second in pairwise(points)]
    segments.append(LineSegment(points[-1], points[0]))
    return _transform_subpaths([segments], transform)


def _build_polyline(
    element: Element, transform: AffineTransform
) -> tuple[tuple[Segment, ...], ...]:
    """Build the open line subpath of a polyline element."""
    points = _parse_points(element, "polyline")
    segments: list[Segment] = [LineSegment(first, second) for first, second in pairwise(points)]
    return _transform_subpaths([segments], transform)


_SHAPE_BUILDERS: dict[str, _ShapeBuilder] = {
    "path": _build_path,
    "line": _build_line,
    "rect": _build_rect,
    "circle": _build_circle,
    "ellipse": _build_ellipse,
    "polygon": _build_polygon,
    "polyline": _build_polyline,
}


def _build_text(element: Element, transform: AffineTransform, fill: str | None) -> SvgText:
    """Record text placement only; font glyphs are deliberately not resolved."""
    x = _number_attribute(element.get("x"), "text x")
    y = _number_attribute(element.get("y"), "text y")
    position = transform.apply(Point(x, y))
    return SvgText(position.x, position.y, "".join(element.itertext()).strip(), fill)


def _split_tag(tag: str) -> tuple[str | None, str]:
    """Split one XML tag into its namespace URI and local name."""
    if tag.startswith("{"):
        namespace, _, local = tag[1:].partition("}")
        return namespace, local
    return None, tag


def _walk(element: Element, context: _Context) -> None:
    """Render one element subtree into the context."""
    tag = element.tag
    if not isinstance(tag, str):
        return
    namespace, local = _split_tag(tag)
    if namespace not in (None, SVG_NAMESPACE) or local in _SKIPPED_ELEMENTS:
        return
    if local == "use":
        raise UnsupportedFeatureError("<use> elements are not supported")
    fill, stroke = _resolve_paints(element, context.fill, context.stroke)
    transform = _parse_transform(element.get("transform")).then(context.transform)
    child = _Context(transform, fill, stroke, context.shapes, context.texts)
    if local == "g":
        for element_child in element:
            _walk(element_child, child)
    elif local in _SHAPE_BUILDERS:
        context.shapes.append(
            SvgShape(local, fill, stroke, _SHAPE_BUILDERS[local](element, transform))
        )
    elif local == "text":
        context.texts.append(_build_text(element, transform, fill))


def parse_svg(data: str | bytes) -> SvgDocument:
    """Parse SVG markup into flattened shapes, text placements, and the view box."""
    try:
        root = fromstring(data)  # noqa: S314 - defusedxml would add a new dependency
    except ParseError as error:
        raise SvgError(f"malformed XML: {error}") from error
    namespace, local = _split_tag(root.tag if isinstance(root.tag, str) else "")
    if local != "svg" or namespace not in (None, SVG_NAMESPACE):
        raise SvgError(f"root element must be svg, got {local!r}")
    shapes: list[SvgShape] = []
    texts: list[SvgText] = []
    fill, stroke = _resolve_paints(root, "#000000", None)
    context = _Context(AffineTransform(), fill, stroke, shapes, texts)
    for child in root:
        _walk(child, context)
    return SvgDocument(_parse_view_box(root.get("viewBox")), tuple(shapes), tuple(texts))
