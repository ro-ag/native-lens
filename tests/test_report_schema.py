import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

import native_lens
from native_lens import compare_pngs
from tests.test_pipeline import score_page


def _resolve_ref(root: dict[str, Any], reference: str) -> dict[str, Any]:
    assert reference.startswith("#/")
    resolved = root
    for part in reference[2:].split("/"):
        resolved = resolved[part]
    return resolved


def _is_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "null":
        return value is None
    raise AssertionError(f"unsupported schema type: {expected}")


def assert_matches_schema(
    value: Any, schema: dict[str, Any], root: dict[str, Any], path: str = "$"
) -> None:
    if "$ref" in schema:
        assert_matches_schema(value, _resolve_ref(root, schema["$ref"]), root, path)
        return

    if "const" in schema:
        assert value == schema["const"], f"{path}: expected {schema['const']!r}"
    if "enum" in schema:
        assert value in schema["enum"], f"{path}: not in enum"
    if "type" in schema:
        expected = schema["type"]
        expected_types = [expected] if isinstance(expected, str) else expected
        assert any(_is_type(value, item) for item in expected_types), (
            f"{path}: expected {expected_types}, got {type(value).__name__}"
        )

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema:
            assert value >= schema["minimum"], f"{path}: below minimum"
        if "maximum" in schema:
            assert value <= schema["maximum"], f"{path}: above maximum"
        if "exclusiveMinimum" in schema:
            assert value > schema["exclusiveMinimum"], f"{path}: below exclusive minimum"
    if isinstance(value, str) and "minLength" in schema:
        assert len(value) >= schema["minLength"], f"{path}: string is too short"

    if isinstance(value, dict):
        required = set(schema.get("required", ()))
        assert required <= value.keys(), f"{path}: missing {sorted(required - value.keys())}"
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            assert value.keys() <= properties.keys(), (
                f"{path}: unexpected {sorted(value.keys() - properties.keys())}"
            )
        for key, child in value.items():
            if key in properties:
                assert_matches_schema(child, properties[key], root, f"{path}.{key}")

    if isinstance(value, list):
        if "minItems" in schema:
            assert len(value) >= schema["minItems"], f"{path}: too few items"
        if "maxItems" in schema:
            assert len(value) <= schema["maxItems"], f"{path}: too many items"
        prefix = schema.get("prefixItems", ())
        for index, child_schema in enumerate(prefix[: len(value)]):
            assert_matches_schema(value[index], child_schema, root, f"{path}[{index}]")
        items = schema.get("items")
        if items is False:
            assert len(value) <= len(prefix), f"{path}: unexpected trailing items"
        elif isinstance(items, dict):
            for index in range(len(prefix), len(value)):
                assert_matches_schema(value[index], items, root, f"{path}[{index}]")


def test_serialized_report_recursively_conforms_to_published_schema(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    output = tmp_path / "report"
    score_page(source)
    compare_pngs(source, source, output)
    report = json.loads((output / "report.json").read_text())
    schema = json.loads((Path(__file__).parents[1] / "docs" / "report.schema.json").read_text())

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert_matches_schema(report, schema, schema)

    malformed = deepcopy(report)
    malformed["reference"]["staves"][0]["line_y_sp"].append(5.0)
    with pytest.raises(AssertionError, match="too many items"):
        assert_matches_schema(malformed, schema, schema)


def test_published_and_installed_schema_copies_are_identical() -> None:
    published = Path(__file__).parents[1] / "docs" / "report.schema.json"
    installed = Path(native_lens.__file__).with_name("report.schema.json")

    assert installed.read_bytes() == published.read_bytes()
