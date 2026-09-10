"""Named, unitful analysis thresholds."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AnalysisConfig:
    """Tunable thresholds that control the analysis pipeline."""

    max_abs_skew_degrees: float = 2.0
    skew_step_degrees: float = 0.1
    skew_sample_limit: int = 250_000
    min_staff_line_page_width_ratio: float = 0.25
    staff_gap_relative_tolerance: float = 0.22
    system_break_gap_sp: float = 7.5
    staff_removal_min_run_sp: float = 3.5
    min_component_area_sp2: float = 0.04
    component_match_max_distance_sp: float = 2.0
    component_match_max_size_log_ratio: float = 1.4
