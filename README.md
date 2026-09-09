# native-lens

`native-lens` is a deterministic engraving analyzer for comparing rendered
music notation. It measures notation geometry in staff-space units (`sp`)
rather than treating a score as an arbitrary picture. It has no generative-AI,
cloud-service, or neural-network dependency.

Milestone 1 provides the `engravecmp` command for two PNG inputs. It detects
and deskews staves, estimates staff-space scale, aligns the renderings, extracts
non-staff connected components, and writes numerical and visual diagnostics.

```console
uv run engravecmp compare \
  --reference reference.png \
  --candidate candidate.png \
  --output report
```

The output directory contains:

- `report.json` — versioned, machine-readable structural and geometric data;
- `aligned-reference.png` and `aligned-candidate.png` — normalized canvases;
- `overlay.png` — reference ink in magenta and candidate ink in cyan;
- `diff.png` — absolute raster difference, retained as a secondary diagnostic.

The report contract is published as
[`docs/report.schema.json`](docs/report.schema.json).

The command exits with an error when either page has no detectable five-line
staff. A missing structural coordinate system must not be silently replaced by
pixel similarity.

## Install and run

The project requires Python 3.12 or newer and uses `uv` for dependency,
environment, lockfile, run, and build workflows.

```console
uv sync
uv run engravecmp --help
```

Build a wheel and source distribution with `uv build`.

## Scope and architecture

Milestone 1 accepts PNG only. SVG/PDF path and glyph extraction, semantic color
masks, MusicXML/MEI assistance, notation-object classification, collision
policies, and N-way reference analysis are roadmap work. Their constraints are
captured in [docs/architecture.md](docs/architecture.md); empty placeholder
packages are intentionally avoided.

The source tree is organized by responsibility:

- `geometry.py` contains source-independent geometry primitives;
- `model.py` defines stable, versioned report contracts;
- `raster/` contains deterministic image-analysis stages;
- `pipeline.py` orchestrates comparison and artifact generation;
- `cli.py` owns argument parsing and process exit behavior.

## Development

```console
uv sync
uv run ruff check .
uv run ruff format --check .
uv run pytest --cov
uv build
```

Run the synthetic end-to-end performance baseline with:

```console
uv run python benchmarks/benchmark_pipeline.py
```

The JSON result records page dimensions and pixels, extracted component count,
local match-candidate edge count, repeats, and min/mean/max elapsed seconds.
Timing is intentionally benchmark output rather than part of deterministic
comparison reports.

Synthetic score pages are generated in tests, making fixtures reproducible and
keeping their geometry explicit. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).
