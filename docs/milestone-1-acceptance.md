# Milestone 1 acceptance matrix

This checklist distinguishes demonstrated behavior from planned behavior. A row
is complete only when it has executable evidence. Test names below refer to the
repository test suite; packaging and performance rows are verified by the
documented commands.

| # | Capability | Current evidence | Audit status |
| --- | --- | --- | --- |
| 1 | Accept two PNG inputs through `engravecmp compare` | CLI end-to-end test | Complete |
| 2 | Validate inputs and fail deterministically | Blank-page CLI regression only | Gap: missing path, non-PNG, and corrupt-PNG cases |
| 3 | Detect five-line staves robustly | Two-staff synthetic fixture | Gap: malformed-staff rejection is not covered |
| 4 | Detect staff horizontal extents | Horizontal-margin transform assertion | Complete |
| 5 | Estimate staff-space size | Scale regression exercises the estimate indirectly | Gap: no direct structural assertion |
| 6 | Detect and correct small global skew | Positive-skew regression | Gap: no negative-skew case or transform proof |
| 7 | Identify staff and system regions | Two separated synthetic staves | Gap: no direct multi-staff-system assertions |
| 8 | Normalize global scale and translation in both axes | Scale and horizontal-margin regressions | Gap: vertical translation is not covered |
| 9 | Preserve the full union canvas during alignment | Alignment implementation only | Gap: differing page sizes and preserved margins are not asserted |
| 10 | Emit explicit, documented transforms | Six-value affine shape assertion | Gap: reported affines omit deskew rotation and expansion offsets |
| 11 | Keep local spacing and object-position differences measurable | One-pixel note offset exercises matching | Gap: normalized displacement is not asserted |
| 12 | Isolate/remove staff lines conservatively | Component matching indirectly exercises removal | Gap: retained note/stem geometry is not asserted |
| 13 | Extract connected components efficiently | Bounding-slice implementation and executable benchmark | Complete |
| 14 | Express component geometry in normalized `sp` coordinates | Model and implementation inspection | Gap: no direct geometry assertion |
| 15 | Match components deterministically with bounded spatial search | `cKDTree` radius query and edge-count diagnostic | Gap: repeated-run determinism is not asserted |
| 16 | Report unmatched components and matching diagnostics | Report fields exist | Gap: added/removed component cases are not covered |
| 17 | Calculate raster metrics only as secondary diagnostics | End-to-end report test and report structure | Complete |
| 18 | Produce JSON and four PNG artifacts | End-to-end artifact test | Complete |
| 19 | Conform to the published versioned JSON Schema | Top-level keys and affine length only | Gap: emitted reports are not validated recursively |
| 20 | Leave no partial report directory when analysis fails | CLI blank-page failure test | Complete |
| 21 | Cover the required deterministic synthetic fixture matrix | Translation, scale, positive skew, and basic two-staff cases | Gap: several required variants are absent |
| 22 | Include an executable end-to-end benchmark | Benchmark smoke test | Complete |
| 23 | Keep benchmark work proportional to pixels/components and document the result | Bounded extraction/matching implementation | Gap: benchmark output and proportionality are not documented |
| 24 | Build valid wheel and source distributions with required material | sdist contains docs/tests/benchmark | Gap: wheel omits the published schema |
| 25 | Keep public files free of secrets, private paths, personal data, and live ptrack state | Clean tracked-file inventory | Complete; repeat during final verification |

## Current audit findings

1. `reference_to_canvas_px` and `candidate_to_canvas_px` describe registration
   after deskew, not the documented source-pixel-to-canvas transform. They must
   compose the deskew rotation, reshape offset, scale, and union translation.
2. The synthetic suite does not directly cover all required fixture variants:
   vertical translation, negative skew, differing margins and page sizes,
   antialiasing changes, malformed staffs, added/removed/moved components, and
   non-PNG or corrupt inputs.
3. The schema contract test does not recursively validate the emitted report,
   and the schema leaves most nested report structures unconstrained.
4. The source distribution contains the development evidence, but the wheel
   does not contain the published report schema needed by installed consumers.
5. The benchmark is executable, but its output and the implementation's
   pixel/component complexity bounds are not yet documented as acceptance
   evidence.
