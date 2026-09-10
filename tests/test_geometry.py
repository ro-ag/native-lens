from native_lens.geometry import AffineTransform, CubicBezier, LineSegment, Point, Rect


def test_geometry_primitives() -> None:
    first = Point(0, 0)
    second = Point(3, 4)
    assert first.distance(second) == 5
    assert Rect(1, 2, 4, 6).center == Point(3, 5)
    assert AffineTransform(a=2, d=2, e=1).apply(Point(2, 3)) == Point(5, 6)
    first = AffineTransform(a=2, d=2, e=1, f=-1)
    following = AffineTransform(e=3, f=4)
    assert first.then(following).apply(Point(2, 3)) == following.apply(first.apply(Point(2, 3)))


def test_bezier_preserves_endpoints() -> None:
    curve = CubicBezier(Point(0, 1), Point(1, 0), Point(2, 0), Point(3, 1))
    assert curve.evaluate(0) == curve.start
    assert curve.evaluate(1) == curve.end


def test_line_segment_length_and_evaluation() -> None:
    segment = LineSegment(Point(1, 2), Point(4, 6))
    assert segment.length() == 5
    assert segment.evaluate(0) == segment.start
    assert segment.evaluate(1) == segment.end
    assert segment.evaluate(0.5) == Point(2.5, 4)
