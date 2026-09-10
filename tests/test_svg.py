import pytest

from native_lens.geometry import CubicBezier, LineSegment, Point, Rect
from native_lens.svg import (
    SvgDocument,
    SvgError,
    SvgShape,
    SvgText,
    UnsupportedFeatureError,
    parse_svg,
)


def parsed(body: str) -> SvgDocument:
    return parse_svg(f'<svg xmlns="http://www.w3.org/2000/svg">{body}</svg>')


def test_line_element_yields_single_segment() -> None:
    document = parsed('<line x1="1" y1="2" x2="4" y2="6"/>')
    assert document.shapes == (
        SvgShape("line", "#000000", None, ((LineSegment(Point(1, 2), Point(4, 6)),),)),
    )


def test_rect_yields_closed_four_line_subpath() -> None:
    document = parsed('<rect x="1" y="2" width="3" height="4"/>')
    corners = (Point(1, 2), Point(4, 2), Point(4, 6), Point(1, 6))
    expected = tuple(LineSegment(corners[index], corners[(index + 1) % 4]) for index in range(4))
    assert document.shapes == (SvgShape("rect", "#000000", None, (expected,)),)


def test_polygon_closes_and_polyline_stays_open() -> None:
    document = parsed('<polygon points="0,0 10,0 10,10"/><polyline points="0,0 10,0 10,10"/>')
    polygon, polyline = document.shapes
    assert polygon.subpaths == (
        (
            LineSegment(Point(0, 0), Point(10, 0)),
            LineSegment(Point(10, 0), Point(10, 10)),
            LineSegment(Point(10, 10), Point(0, 0)),
        ),
    )
    assert polyline.subpaths == (
        (
            LineSegment(Point(0, 0), Point(10, 0)),
            LineSegment(Point(10, 0), Point(10, 10)),
        ),
    )


def test_circle_and_ellipse_use_cardinal_cubics() -> None:
    kappa = 4 / 3 * (2**0.5 - 1)
    document = parsed('<circle cx="10" cy="20" r="10"/><ellipse rx="20" ry="10"/>')
    first = document.shapes[0].subpaths[0]
    assert len(first) == 4
    leading = first[0]
    assert isinstance(leading, CubicBezier)
    assert leading.start == Point(10, 10)
    assert leading.end == Point(20, 20)
    assert leading.control_1.x == pytest.approx(10 + 10 * kappa)
    assert leading.control_1.y == 10
    assert leading.control_2.x == 20
    assert leading.control_2.y == pytest.approx(20 - 10 * kappa)
    midpoint = leading.evaluate(0.5)
    assert midpoint.x == pytest.approx(10 + 5 * 2**0.5)
    assert midpoint.y == pytest.approx(20 - 5 * 2**0.5)
    ellipse = document.shapes[1].subpaths[0]
    assert len(ellipse) == 4
    ellipse_leading = ellipse[0]
    assert isinstance(ellipse_leading, CubicBezier)
    assert ellipse_leading.start == Point(0, -10)
    assert ellipse_leading.end == Point(20, 0)
    assert ellipse_leading.control_1.x == pytest.approx(20 * kappa)
    assert ellipse_leading.control_2.y == pytest.approx(-10 * kappa)


def test_absolute_path_moveto_lineto_curveto_closepath() -> None:
    document = parsed('<path d="M 0 0 L 10 0 C 15 0 20 5 20 10 Z"/>')
    assert document.shapes[0].subpaths == (
        (
            LineSegment(Point(0, 0), Point(10, 0)),
            CubicBezier(Point(10, 0), Point(15, 0), Point(20, 5), Point(20, 10)),
            LineSegment(Point(20, 10), Point(0, 0)),
        ),
    )


def test_closepath_at_coincident_point_appends_no_segment() -> None:
    document = parsed('<path d="M 0 0 L 5 5 L 0 0 Z"/>')
    assert document.shapes[0].subpaths == (
        (
            LineSegment(Point(0, 0), Point(5, 5)),
            LineSegment(Point(5, 5), Point(0, 0)),
        ),
    )


def test_command_after_closepath_starts_new_subpath() -> None:
    document = parsed('<path d="M 0 0 L 5 5 Z L 5 5"/>')
    assert document.shapes[0].subpaths == (
        (LineSegment(Point(0, 0), Point(5, 5)), LineSegment(Point(5, 5), Point(0, 0))),
        (LineSegment(Point(0, 0), Point(5, 5)),),
    )


def test_relative_commands_repeat_implicitly() -> None:
    document = parsed('<path d="m 10 10 20 0 0 20 l -20 0 z"/>')
    assert document.shapes[0].subpaths == (
        (
            LineSegment(Point(10, 10), Point(30, 10)),
            LineSegment(Point(30, 10), Point(30, 30)),
            LineSegment(Point(30, 30), Point(10, 30)),
            LineSegment(Point(10, 30), Point(10, 10)),
        ),
    )


def test_horizontal_and_vertical_commands() -> None:
    document = parsed('<path d="M 0 0 H 10 V 10 h -5 v -5"/>')
    assert document.shapes[0].subpaths == (
        (
            LineSegment(Point(0, 0), Point(10, 0)),
            LineSegment(Point(10, 0), Point(10, 10)),
            LineSegment(Point(10, 10), Point(5, 10)),
            LineSegment(Point(5, 10), Point(5, 5)),
        ),
    )


def test_packed_number_tokens() -> None:
    document = parsed('<path d="M0 0L1-2 3.5.5 1e1 2e-1"/>')
    assert document.shapes[0].subpaths == (
        (
            LineSegment(Point(0, 0), Point(1, -2)),
            LineSegment(Point(1, -2), Point(3.5, 0.5)),
            LineSegment(Point(3.5, 0.5), Point(10, 0.2)),
        ),
    )


def test_smooth_cubic_reflects_preceding_curve_control() -> None:
    document = parsed('<path d="M 0 0 C 5 0 10 5 10 10 S 20 20 30 30"/>')
    subpath = document.shapes[0].subpaths[0]
    assert subpath[1] == CubicBezier(Point(10, 10), Point(10, 15), Point(20, 20), Point(30, 30))


def test_smooth_cubic_without_preceding_curve_uses_current_point() -> None:
    document = parsed('<path d="M 0 0 S 10 10 20 20"/>')
    assert document.shapes[0].subpaths == (
        (CubicBezier(Point(0, 0), Point(0, 0), Point(10, 10), Point(20, 20)),),
    )


def test_quadratic_is_elevated_to_cubic() -> None:
    document = parsed('<path d="M 0 0 Q 5 10 10 0"/>')
    curve = document.shapes[0].subpaths[0][0]
    assert isinstance(curve, CubicBezier)
    assert curve.start == Point(0, 0)
    assert curve.end == Point(10, 0)
    assert curve.control_1.x == pytest.approx(10 / 3)
    assert curve.control_1.y == pytest.approx(20 / 3)
    assert curve.control_2.x == pytest.approx(20 / 3)
    assert curve.control_2.y == pytest.approx(20 / 3)
    midpoint = curve.evaluate(0.5)
    assert midpoint.x == pytest.approx(5)
    assert midpoint.y == pytest.approx(5)


def test_smooth_quadratic_reflects_previous_control() -> None:
    document = parsed('<path d="M 0 0 Q 5 10 10 0 T 20 0"/>')
    second = document.shapes[0].subpaths[0][1]
    assert isinstance(second, CubicBezier)
    assert second.start == Point(10, 0)
    assert second.end == Point(20, 0)
    assert second.control_1.x == pytest.approx(40 / 3)
    assert second.control_1.y == pytest.approx(-20 / 3)
    assert second.control_2.x == pytest.approx(50 / 3)
    assert second.control_2.y == pytest.approx(-20 / 3)


def test_arc_preserves_endpoints() -> None:
    document = parsed('<path d="M 0 0 A 5 5 0 0 1 6 8"/>')
    subpath = document.shapes[0].subpaths[0]
    assert len(subpath) == 2
    assert isinstance(subpath[0], CubicBezier)
    assert isinstance(subpath[1], CubicBezier)
    assert subpath[0].start.x == pytest.approx(0)
    assert subpath[0].start.y == pytest.approx(0)
    assert subpath[1].end.x == pytest.approx(6)
    assert subpath[1].end.y == pytest.approx(8)


def test_semicircle_arc_apex_stays_on_true_curve() -> None:
    document = parsed('<path d="M 0 0 A 1 1 0 0 1 2 0"/>')
    subpath = document.shapes[0].subpaths[0]
    assert subpath[0].end.x == pytest.approx(1, abs=0.001)
    assert subpath[0].end.y == pytest.approx(-1, abs=0.001)
    midpoint = subpath[1].evaluate(0.5)
    assert midpoint.x == pytest.approx(1 + 2**0.5 / 2, abs=0.001)
    assert midpoint.y == pytest.approx(-(2**0.5) / 2, abs=0.001)


def test_zero_radius_arc_degenerates_to_line() -> None:
    document = parsed('<path d="M 0 0 A 0 5 0 0 1 3 4"/>')
    assert document.shapes[0].subpaths == ((LineSegment(Point(0, 0), Point(3, 4)),),)


def test_small_arc_radii_scale_up() -> None:
    document = parsed('<path d="M 0 0 A 1 1 0 0 1 4 0"/>')
    subpath = document.shapes[0].subpaths[0]
    assert subpath[0].end.x == pytest.approx(2, abs=0.002)
    assert subpath[0].end.y == pytest.approx(-2, abs=0.002)
    assert subpath[1].end.x == pytest.approx(4, abs=1e-09)
    assert subpath[1].end.y == pytest.approx(0, abs=1e-09)


def test_full_circle_from_two_arcs() -> None:
    document = parsed('<path d="M 0 -1 A 1 1 0 1 1 0 1 A 1 1 0 1 1 0 -1"/>')
    subpath = document.shapes[0].subpaths[0]
    assert len(subpath) == 4
    endpoints = [segment.end for segment in subpath] + [subpath[0].start]
    for endpoint in endpoints:
        assert Point(0, 0).distance(endpoint) == pytest.approx(1)


def test_nonpositive_circle_or_ellipse_radius_is_rejected() -> None:
    with pytest.raises(SvgError, match="radius"):
        parsed('<circle cx="0" cy="0" r="0"/>')
    with pytest.raises(SvgError, match="radius"):
        parsed('<circle cx="0" cy="0" r="-1"/>')
    with pytest.raises(SvgError, match="radii"):
        parsed('<ellipse cx="0" cy="0" rx="0" ry="5"/>')


def test_translate_then_scale_flattens_points() -> None:
    document = parsed('<line x1="0" y1="0" x2="1" y2="0" transform="translate(10, 20) scale(2)"/>')
    assert document.shapes[0].subpaths == (((LineSegment(Point(10, 20), Point(12, 20)),),))


def test_rotate_about_center() -> None:
    document = parsed('<rect x="0" y="0" width="2" height="2" transform="rotate(90, 1, 1)"/>')
    subpath = document.shapes[0].subpaths[0]
    expected = (Point(2, 0), Point(2, 2), Point(0, 2), Point(0, 0))
    for index, segment in enumerate(subpath):
        assert isinstance(segment, LineSegment)
        assert segment.start.x == pytest.approx(expected[index].x)
        assert segment.start.y == pytest.approx(expected[index].y)


def test_matrix_transform_matches_field_order() -> None:
    document = parsed('<line x1="1" y1="0" x2="1" y2="1" transform="matrix(1, 0, 1, 1, 0, 0)"/>')
    assert document.shapes[0].subpaths == (((LineSegment(Point(1, 0), Point(2, 1)),),))


def test_nested_groups_and_element_transform_compose() -> None:
    document = parsed(
        '<g transform="translate(10, 0)"><g transform="scale(2)">'
        '<rect x="1" y="1" width="2" height="2" transform="translate(0, 5)"/></g></g>'
    )
    subpath = document.shapes[0].subpaths[0]
    expected = (Point(12, 12), Point(16, 12), Point(16, 16), Point(12, 16))
    for index, segment in enumerate(subpath):
        assert isinstance(segment, LineSegment)
        assert segment.start.x == pytest.approx(expected[index].x)
        assert segment.start.y == pytest.approx(expected[index].y)


def test_short_hex_paint_expands() -> None:
    document = parsed('<rect x="0" y="0" width="1" height="1" fill="#abc"/>')
    assert document.shapes[0].fill == "#aabbcc"


def test_hex_paint_is_normalized_lowercase() -> None:
    document = parsed('<rect x="0" y="0" width="1" height="1" fill="#AABBCC"/>')
    assert document.shapes[0].fill == "#aabbcc"


def test_named_paint_converts_to_hex() -> None:
    document = parsed('<rect x="0" y="0" width="1" height="1" fill="red" stroke="white"/>')
    assert document.shapes[0].fill == "#ff0000"
    assert document.shapes[0].stroke == "#ffffff"


def test_none_paint_becomes_no_paint() -> None:
    document = parsed('<rect x="0" y="0" width="1" height="1" fill="none" stroke="none"/>')
    assert document.shapes[0].fill is None
    assert document.shapes[0].stroke is None


def test_default_paints() -> None:
    document = parsed('<rect x="0" y="0" width="1" height="1"/>')
    assert document.shapes[0].fill == "#000000"
    assert document.shapes[0].stroke is None


def test_group_paint_inheritance() -> None:
    document = parsed(
        '<g fill="blue" stroke="white"><rect x="0" y="0" width="1" height="1"/><circle r="2"/></g>'
    )
    rect, circle = document.shapes
    assert rect.fill == "#0000ff"
    assert rect.stroke == "#ffffff"
    assert circle.fill == "#0000ff"
    assert circle.stroke == "#ffffff"


def test_style_overrides_presentation_attributes() -> None:
    document = parsed(
        '<rect x="0" y="0" width="1" height="1" fill="red" stroke="white" '
        'style="fill: none; stroke: green"/>'
    )
    assert document.shapes[0].fill is None
    assert document.shapes[0].stroke == "#008000"


def test_text_capture() -> None:
    document = parsed('<text x="10" y="20">Hello <tspan>world</tspan></text>')
    assert document.texts == (SvgText(10.0, 20.0, "Hello world", "#000000"),)


def test_text_inherits_group_fill() -> None:
    document = parsed('<g fill="blue"><text x="1" y="2">note</text></g>')
    assert document.texts == (SvgText(1.0, 2.0, "note", "#0000ff"),)


def test_non_rendering_subtrees_are_skipped() -> None:
    document = parsed(
        '<defs><rect x="0" y="0" width="5" height="5"/></defs>'
        "<title>chart</title><desc>note</desc><metadata>x</metadata>"
        '<path d="M 0 0 L 1 1"/>'
    )
    assert len(document.shapes) == 1
    assert document.shapes[0].kind == "path"


def test_foreign_namespace_elements_are_skipped() -> None:
    document = parse_svg(
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:f="http://example.com/f">'
        '<f:rect x="0" y="0" width="9" height="9"/>'
        '<rect x="1" y="1" width="2" height="2"/></svg>'
    )
    assert len(document.shapes) == 1
    assert document.shapes[0].kind == "rect"


def test_use_element_is_unsupported() -> None:
    with pytest.raises(UnsupportedFeatureError, match="use"):
        parsed("<use href='#thing'/>")


def test_rounded_rect_is_unsupported() -> None:
    with pytest.raises(UnsupportedFeatureError, match="rounded"):
        parsed('<rect x="0" y="0" width="2" height="2" rx="1"/>')
    with pytest.raises(UnsupportedFeatureError, match="rounded"):
        parsed('<rect x="0" y="0" width="2" height="2" ry="1"/>')


def test_rect_zero_corner_radius_renders_sharp() -> None:
    document = parsed('<rect x="0" y="0" width="2" height="2" rx="0" ry="0"/>')
    assert len(document.shapes[0].subpaths[0]) == 4


def test_rect_nonpositive_size_is_rejected() -> None:
    with pytest.raises(SvgError, match="positive"):
        parsed('<rect x="0" y="0" width="0" height="4"/>')
    with pytest.raises(SvgError, match="positive"):
        parsed('<rect x="0" y="0" width="4" height="-1"/>')


def test_polygon_rejects_wrong_point_counts() -> None:
    with pytest.raises(SvgError, match="odd"):
        parsed('<polygon points="0 0 10 20 30"/>')
    with pytest.raises(SvgError, match="at least two"):
        parsed('<polyline points="0 0"/>')


def test_text_coordinates_are_validated() -> None:
    with pytest.raises(SvgError, match="text x"):
        parsed('<text x="1 2" y="3">hi</text>')
    with pytest.raises(SvgError, match="text y"):
        parsed('<text x="1">hi</text>')


def test_unknown_transform_function_is_rejected() -> None:
    with pytest.raises(SvgError, match="frobnicate"):
        parsed('<rect x="0" y="0" width="1" height="1" transform="frobnicate(1)"/>')


def test_transform_argument_counts_are_validated() -> None:
    with pytest.raises(SvgError, match="translate"):
        parsed('<rect x="0" y="0" width="1" height="1" transform="translate(1, 2, 3)"/>')
    with pytest.raises(SvgError, match="matrix"):
        parsed('<rect x="0" y="0" width="1" height="1" transform="matrix(1, 2)"/>')


def test_invalid_paint_is_rejected() -> None:
    with pytest.raises(SvgError, match="chartreuse"):
        parsed('<rect x="0" y="0" width="1" height="1" fill="chartreuse"/>')


def test_non_svg_root_is_rejected() -> None:
    with pytest.raises(SvgError, match="root element"):
        parse_svg("<html><body/></html>")


def test_malformed_xml_is_rejected() -> None:
    with pytest.raises(SvgError, match="XML"):
        parse_svg("<svg><rect></svg>")


def test_bytes_input_is_accepted() -> None:
    document = parse_svg(
        b'<svg xmlns="http://www.w3.org/2000/svg"><rect x="0" y="0" width="1" height="1"/></svg>'
    )
    assert len(document.shapes) == 1


def test_incomplete_path_command_is_rejected() -> None:
    with pytest.raises(SvgError, match="lineto"):
        parsed('<path d="M 0 0 L"/>')


def test_unknown_path_command_is_rejected() -> None:
    with pytest.raises(SvgError, match="unknown path command"):
        parsed('<path d="M 0 0 X 5 5"/>')


def test_garbled_path_data_is_rejected() -> None:
    with pytest.raises(SvgError, match="malformed path data"):
        parsed('<path d="M 0 0 ; L 5 5"/>')


def test_path_requires_d_attribute() -> None:
    with pytest.raises(SvgError, match="path d"):
        parsed("<path/>")


def test_view_box_is_recorded() -> None:
    document = parse_svg('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50"/>')
    assert document.view_box == Rect(0, 0, 100, 50)


def test_missing_view_box_is_none() -> None:
    assert parsed('<rect x="0" y="0" width="1" height="1"/>').view_box is None


def test_malformed_view_box_is_rejected() -> None:
    with pytest.raises(SvgError, match="viewBox"):
        parse_svg('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100"/>')


def test_parse_twice_is_deterministic() -> None:
    markup = (
        '<g transform="translate(5, 5) rotate(30)"><rect x="0" y="0" width="4" '
        'height="4" fill="teal"/></g><text x="1" y="2">hi</text>'
    )
    assert parsed(markup) == parsed(markup)
