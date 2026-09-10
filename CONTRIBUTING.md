# Contributing

Contributions should keep analysis deterministic, thresholds named and unitful,
and generic geometry separate from notation and raster concerns. Please include
focused tests for behavior changes.

Run before submitting a change:

```console
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest --cov
uv build
```

Do not commit generated reports, local ptrack state, virtual environments, or
build artifacts.

