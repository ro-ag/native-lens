# Milestone 1 acceptance matrix

This checklist distinguishes demonstrated behavior from planned behavior. A row
is complete only when it has executable evidence. Test names refer to the
repository suite; packaging and performance rows use the documented commands.

| # | Capability | Executable evidence | Status |
| --- | --- | --- | --- |
| 1 | Accept two PNG inputs through `engravecmp compare` | `test_cli_prints_report_path` | Complete |
| 2 | Validate inputs and fail deterministically | `test_cli_rejects_invalid_inputs_without_output`, `test_failed_analysis_leaves_no_partial_report` | Complete |
| 3 | Detect five-line staves robustly | `test_multiple_staves_are_grouped_into_multiple_systems`, `test_malformed_four_line_staff_is_rejected` | Complete |
| 4 | Detect staff horizontal extents | `test_horizontal_margin_is_removed_by_structural_registration` | Complete |
| 5 | Estimate staff-space size | `test_multiple_staves_are_grouped_into_multiple_systems`, `test_scale_is_normalized_from_staff_space` | Complete |
| 6 | Detect and correct small global skew | Positive and negative cases in `test_small_skew_is_detected_and_removed` | Complete |
| 7 | Identify staff and system regions | Four-staff/two-system assertions in `test_multiple_staves_are_grouped_into_multiple_systems` | Complete |
| 8 | Normalize global scale and translation in both axes | Scale, horizontal-margin, and two-axis registration regressions | Complete |
| 9 | Preserve the full union canvas during alignment | Exact 460 x 220 artifact and transform assertions in `test_two_axis_registration_preserves_union_of_different_page_sizes` | Complete |
| 10 | Emit explicit, documented transforms | Deskew affine assertions plus source-to-canvas composition documentation | Complete |
| 11 | Keep local spacing and object-position differences measurable | Exact 1.0 `sp` component delta assertion | Complete |
| 12 | Isolate/remove staff lines conservatively | Retained note bounds/area assertions in `test_staff_removal_retains_normalized_note_geometry` | Complete |
| 13 | Extract connected components efficiently | Bounding-slice implementation and executable benchmark | Complete |
| 14 | Express component geometry in normalized `sp` coordinates | Exact normalized bounds and area assertions | Complete |
| 15 | Match components deterministically with bounded spatial search | Radius-index implementation, edge diagnostics, and repeated hash test | Complete |
| 16 | Report unmatched components and matching diagnostics | Added/removed/moved component regression | Complete |
| 17 | Calculate raster metrics only as secondary diagnostics | End-to-end report structure and registration regressions | Complete |
| 18 | Produce JSON and four PNG artifacts | `test_comparison_writes_stable_report_and_artifacts` | Complete |
| 19 | Conform to the published versioned JSON Schema | Recursive serialized-report validation in `test_report_schema.py` | Complete |
| 20 | Leave no partial report directory when analysis fails | Blank, malformed, missing, non-PNG, and corrupt-input failure tests | Complete |
| 21 | Cover the required deterministic synthetic fixture matrix | Translation, scale, both skew signs, page sizes, antialiasing, systems/staves, malformed inputs, and component-difference tests | Complete |
| 22 | Include an executable end-to-end benchmark | `test_executable_benchmark_smoke` and `uv run python benchmarks/benchmark_pipeline.py` | Complete |
| 23 | Keep benchmark work proportional to pixels/components and document the result | Complexity accounting and pixel/object/edge benchmark output in `docs/architecture.md` | Complete |
| 24 | Build valid wheel and source distributions with required material | `uv build`; wheel schema and sdist docs/tests/benchmark content inspection | Complete |
| 25 | Keep public files free of secrets, private paths, personal data, and live ptrack state | Tracked-file inventory and final public-data scan | Complete |

## Verified performance baseline

On the documented Apple-silicon macOS/Python 3.13 host, three full comparisons
of the 1600 x 2200 synthetic page produced 1,782 components and 4,774 local
candidate edges, with the component count measured per page, in 0.415-0.422
seconds. The 800 x 1100 comparison produced 780 components per page and 2,100
edges in 0.133-0.153 seconds. These timings are recorded diagnostics, not
portable pass/fail thresholds.

## Boundary after Milestone 1

Milestone 1 establishes deterministic raster structure, normalized component
geometry, local correspondence, and diagnostic artifacts. SVG/PDF extraction,
MusicXML/MEI assistance, semantic classification, full collision policy, HTML
reports, and N-way consensus remain later-milestone work.
