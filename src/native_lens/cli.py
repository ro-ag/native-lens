"""Command-line interface for native-lens."""

from __future__ import annotations

import argparse
from pathlib import Path

from native_lens.pipeline import compare_pngs
from native_lens.raster.analysis import AnalysisError


def parser() -> argparse.ArgumentParser:
    """Build the ``engravecmp`` argument parser."""
    root = argparse.ArgumentParser(prog="engravecmp", description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    compare = commands.add_parser("compare", help="compare two PNG score renderings")
    compare.add_argument("--reference", required=True, type=Path)
    compare.add_argument("--candidate", required=True, type=Path)
    compare.add_argument("--output", required=True, type=Path)
    return root


def main(argv: list[str] | None = None) -> int:
    """Run one comparison and return the process exit code."""
    arguments = parser().parse_args(argv)
    try:
        report = compare_pngs(arguments.reference, arguments.candidate, arguments.output)
    except (AnalysisError, OSError) as error:
        parser().error(str(error))
    print(arguments.output / "report.json")
    print(f"overall score: {report['overall_score']:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
