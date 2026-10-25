#!/usr/bin/env python3
"""Fail when coverage.py reports missing branches inside the core policy scope."""

import argparse
import ast
import json
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent / "ffmpegfyMe.py"

SCOPE_FUNCTIONS = (
    "_is_valid_env_reference",
    "_is_valid_http_token_header_name",
    "_is_valid_http_url",
    "_is_valid_output_filename",
    "_is_valid_stable_id",
    "load_downloads",
    "validate_output_filename",
    "item_state_key",
    "item_is_complete",
    "process_download_item",
    "load_item_state",
    "is_legacy_progress_state",
    "save_item_state",
    "resolve_request_auth",
    "_redact_line",
    "download_with_retry",
    "_resolve_ffmpeg_inactivity_timeout",
)


def _fail(message: str) -> int:
    print(f"policy-coverage: {message}")
    return 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check policy branch coverage scope.")
    parser.add_argument("coverage_json", type=Path, help="Path to coverage.py JSON report.")
    args = parser.parse_args(argv)

    try:
        data = json.loads(args.coverage_json.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return _fail(f"invalid coverage JSON at {args.coverage_json}: {exc}")

    files = data.get("files")
    if not isinstance(files, dict) or not files:
        return _fail("coverage JSON has no files.")

    report_files = {name: report for name, report in files.items() if name.endswith("ffmpegfyMe.py")}
    if len(report_files) != 1:
        return _fail(f"expected exactly one ffmpegfyMe.py coverage report, found {len(report_files)}.")
    report = next(iter(report_files.values()))

    missing_branches = report.get("missing_branches") or []
    totals = data.get("totals") or {}
    covered_branches = int(totals.get("covered_branches") or 0)
    missing_arc_count = len(missing_branches)

    try:
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        return _fail(f"could not parse policy source {SOURCE}: {exc}")

    spans = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            spans[node.name] = (node.lineno, node.end_lineno)

    absent_scopes = [name for name in SCOPE_FUNCTIONS if name not in spans]
    if absent_scopes:
        return _fail(f"scope function names absent from source: {', '.join(absent_scopes)}")

    measured = bool(int(totals.get("num_branches") or 0) > 0) or bool(missing_branches) or bool(report.get("executed_branches"))
    if not measured:
        return _fail("no scoped branches were measured.")

    missing_in_scope = []
    for arc in missing_branches:
        start, end = int(arc[0]), int(arc[1])
        for name in SCOPE_FUNCTIONS:
            span = spans.get(name)
            if span and span[0] <= start <= span[1]:
                missing_in_scope.append((start, end, name))
                break

    function_names = ", ".join(SCOPE_FUNCTIONS)
    print(f"policy-coverage: covered branches: {covered_branches}")
    print(f"policy-coverage: missing arcs: {missing_arc_count}")
    print(f"policy-coverage: scoped functions: {function_names}")

    if missing_in_scope:
        for start, end, name in sorted(missing_in_scope):
            print(f"policy-coverage: missing branch arc {start}->{end} in scoped function {name}")
        return 1

    print("policy-coverage: no missing branches in policy scope.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
