# Architecture and Milestone 1 specification

## Product boundary

The system is an engraving analyzer:

```text
input -> normalization -> extraction -> geometric representation
      -> correspondence -> measurements -> reporting
```

Raster difference is diagnostic output, never the primary coordinate system or
score. Extracted page geometry is expressed in staff spaces (`sp`), where the
median distance between adjacent staff lines is `1.0 sp`.

Milestone 1 is complete when two PNG pages containing ordinary five-line staves
can be analyzed deterministically, aligned despite small translation, scale,
and skew differences, compared at connected-component level, and emitted as a
versioned JSON report plus four diagnostic PNGs. It does not classify notation
objects or claim engraving-semantic equivalence.

## Risk register

1. **Staff-line ambiguity.** Ledger lines, beams, text rules, and page borders
   can form horizontal peaks. Milestone 1 requires substantial horizontal
   coverage and groups only five approximately equidistant lines. Reports retain
   confidence and source-pixel evidence so later detectors can be substituted.
2. **Skew estimation cost and local optima.** Projection-profile search is
   deterministic and bounded to a documented angle and raster sample grid. It
   handles small scan/export rotations, not perspective distortion.
3. **Destructive staff removal.** Removing line pixels can split noteheads and
   stems. The initial algorithm removes only pixels belonging to long horizontal
   runs; it does not label the resulting components as notation objects.
4. **Correspondence ambiguity.** Geometrically similar components repeat across
   a score. Milestone 1 uses deterministic local matching after normalization
   and reports unmatched objects. Semantic IDs and measure constraints can later
   replace the matcher without changing report identity.
5. **Vector/raster convergence.** Pixel-specific state must not leak into the
   stable model. Source pixel transforms are provenance; public object geometry
   is normalized and source-independent.
6. **Meaningful normalization.** Only global deskew, uniform scale, and global
   translation are removed. Nonuniform warping, local measure stretching, and
   object displacement remain measurable engraving differences.

## Package boundaries

`native_lens.geometry` owns immutable points, axis-aligned rectangles, affine
transforms, line segments, and cubic Bézier evaluation. It contains no image or
notation logic.

`native_lens.model` owns stable serialization types: source provenance,
staff/system regions, extracted objects, correspondence, measurements,
normalization transforms, configuration, and the versioned report envelope.
Optional semantic identity is present without requiring a source-score parser.

`native_lens.raster` owns grayscale/binary buffers, thresholding, skew and staff
detection, resampling/alignment, staff isolation, connected components,
matching, scalar raster diagnostics, and diagnostic images.

`native_lens.pipeline` composes those stages. `native_lens.cli` owns argument
parsing, filesystem validation, and exit codes; it contains no analysis logic.

Additional packages for vector extraction, collision policy, or HTML reporting
should appear only when they carry real behavior and a useful dependency
boundary. The JSON schema is kept language-neutral so optimized components can
be introduced later behind measured bottlenecks.

## Stable data structures

- `SourceInfo` identifies format, role, and path without assuming an engine.
- `ObjectId` is analyzer-assigned and deterministic within one report.
- `SemanticId` is optional and can later hold MusicXML, MEI, color-mask, or
  engine-provided identity.
- `ExtractedObject` combines an extensible object kind, normalized bounds,
  centroid, area, and source provenance.
- `StaffRegion` and `SystemRegion` establish normalized structural coordinates.
- `AffineTransform` records the source-pixel to aligned-pixel operation.
- `ComparisonReport` has a schema version and distinct structural, component,
  and raster sections. New optional measurements can be added compatibly.

Future contours, polygons, and Bézier paths belong in geometry references on an
object, not in raster-only types. Future collision rules should be data-driven
policies over object roles and relationships; intentional overlaps such as
stem-notehead must not be encoded as universal geometric exceptions.

## Algorithms

### Binarization

Convert sRGB input to luma and use Otsu's global threshold. The threshold and
ink polarity are recorded. This handles clean exports and many scans while
remaining deterministic. Adaptive thresholding is a later fallback for uneven
illumination.

### Skew

Search a bounded angle range at a fixed increment. For sampled ink pixels, each
candidate projects points onto a rotated y-axis; the sum of squared row-bin
occupancies is the objective. Staff lines make the correct angle a strong peak.
The page is inverse-mapped with bilinear interpolation and a white border.

### Staff detection and scale

On the deskewed binary page, find horizontal-projection runs with enough width
coverage. Collapse thick runs to weighted center rows, then find non-overlapping
groups of five whose four gaps agree within a relative tolerance. Median gap is
the page's staff-space scale. Staff x-extents come from cross-line support, and
nearby staves are grouped into systems by a gap threshold expressed in `sp`.

### Registration

Deskew both pages independently. Uniformly scale the candidate so its median
staff space equals the reference, then translate its first staff-line origin to
the reference origin. Place both images on a union canvas, preserving all
content. This deliberately avoids elastic or measure-local registration.
`reference_to_canvas_px` and `candidate_to_canvas_px` are six-value affine
transforms in `[a, b, c, d, e, f]` order. They map original source pixel centers
directly to aligned artifact coordinates by composing the center-based deskew
rotation and reshape offset, candidate scale, and union-canvas translation.

### Components and comparison

Remove only staff-line pixels that are members of long horizontal runs. Extract
8-connected components, discard dust using an area threshold in `sp^2`, and
express bounds and centroids relative to the first staff origin. Candidate
matches are gated by centroid distance and size ratio; sorted cost edges are
consumed greedily with stable ID tie-breaks. The report includes deltas, costs,
and both unmatched sets so ambiguity remains diagnosable.

The raster stages make a constant number of page passes. Component extraction
examines each component's bounding slice rather than rescanning the full page
for every label. Matching uses a staff-space radius index, then sorts only the
reported local candidate edges. The resulting work is proportional to page
pixels, the sum of component bounding-slice areas, and local match edges; the
benchmark reports all three observable proxies (pixels, objects, and edges).

### Milestone 1 performance baseline

Run `uv run python benchmarks/benchmark_pipeline.py` for the full synthetic
baseline. On an Apple-silicon macOS host with Python 3.13, three comparisons of
a 1600 x 2200 page containing 1,782 extracted components and 4,774 local
candidate edges completed in 0.414-0.422 seconds each. A half-width,
half-height 800 x 1100 page containing 780 components and 2,100 edges completed
in 0.130-0.153 seconds. Timings are diagnostics, not a portable pass/fail
threshold; benchmark JSON reports the work counts so future changes can be
compared at equivalent work.

### Secondary raster metrics

Mean absolute luma error and foreground disagreement are calculated on the
aligned canvas. They are explicitly reported under `raster_secondary` and do
not determine structural validity.

## Configuration and determinism

Every threshold has a named configuration field and a documented unit: degrees,
pixels, page-width ratio, `sp`, or `sp^2`. Collections are spatially sorted
before IDs and matches are assigned. No randomized algorithms, wall-clock data,
or platform services affect reports. Floating measurements are rounded before
serialization.

## Dependencies and packaging

The runtime dependency set stays focused:

- NumPy provides numeric arrays and projection calculations;
- SciPy provides interpolation and connected-component primitives;
- Pillow handles PNG decoding, encoding, and RGB diagnostic artifacts;
- the standard library provides the CLI, dataclasses, paths, and JSON output.

Development uses pytest, pytest-cov, and Ruff. All dependency, environment,
lockfile, command, and build activity runs through `uv`.

## Roadmap after Milestone 1

1. Preserve SVG paths, text/glyph placement, colors, transforms, and cubic
   Béziers; investigate PDF content streams without premature rasterization.
2. Add semantic RGB masks and stable object/color mappings.
3. Add source-assisted identity from bounded MusicXML/MEI features.
4. Add notation-object classifiers, measure-constrained matching, and N-way
   consensus/outlier analysis.
5. Add broad/narrow collision phases, clearance policies, curve metrics, and
   failure-crop/HTML reporting.
