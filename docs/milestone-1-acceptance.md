# Milestone 1 acceptance matrix

This checklist distinguishes demonstrated behavior from planned behavior. A row
is complete only when it has executable evidence.

| Capability | Evidence | Status |
| --- | --- | --- |
| Accept two PNG inputs | CLI and end-to-end test | Complete |
| Detect five-line staves | Synthetic two-staff test | Complete |
| Estimate staff-space size | Structural report assertions | Complete |
| Detect and remove small global skew | Rotated synthetic regression | Open |
| Normalize scale without local warping | Scaled synthetic regression | Open |
| Detect staff and system regions including x-extents | Region assertions | Complete |
| Align on both axes using a union canvas | Translation regression and transform assertions | Complete |
| Calculate secondary raster metrics | End-to-end report test | Complete |
| Extract components without full-page work per component | Bounding-slice extraction and spatial match index | Complete |
| Compare normalized component geometry | Offset component regression | Complete |
| Produce versioned JSON conforming to a published schema | Schema contract test | Open |
| Produce four diagnostic PNG artifacts | End-to-end artifact test | Complete |
| Fail deterministically without partial output | CLI/pipeline failure tests | Open |
| Include executable benchmark | `uv run python benchmarks/benchmark_pipeline.py` | Open |

## Audit findings

1. Staff bounds currently span the full page and set the structural x-origin to
   zero, so horizontal margin differences cannot be normalized correctly.
2. Registration translates only on y and chooses a maximum width rather than a
   true two-dimensional union canvas.
3. Component extraction evaluates `labels == id` over the full page once per
   component, making runtime proportional to page area times component count.
4. The report is versioned but has no published schema or contract test.
5. The CLI's analysis failure is tested only through the library; partial-output
   and parser exit behavior need direct coverage.
6. No executable benchmark exists despite the earlier completion record.
