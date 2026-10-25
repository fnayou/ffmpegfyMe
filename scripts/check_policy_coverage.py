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
    "main",
)


def _fail(message: str) -> int:
    print(f"policy-coverage: {message}")
    return 2


# Scope boundary: ffmpegfyMe.py intentionally ships no argparse/sys.argv CLI.
# `main(runner)` is the deterministic test seam; no CLI features are added under
# this coverage ticket. `_resolve_ffmpeg_inactivity_timeout` stays in scope as the
# existing explicit-value/environment resolver.


def _is_not_check_ffmpeg(test: ast.expr) -> bool:
    return (
        isinstance(test, ast.UnaryOp)
        and isinstance(test.op, ast.Not)
        and isinstance(test.operand, ast.Call)
        and isinstance(test.operand.func, ast.Name)
        and test.operand.func.id == "check_ffmpeg"
    )


def _is_use_saved_not_y(test: ast.expr) -> bool:
    return (
        isinstance(test, ast.Compare)
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.NotEq)
        and isinstance(test.left, ast.Name)
        and test.left.id == "use_saved"
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value == "y"
    )


def _is_mode_in_1_2(test: ast.expr) -> bool:
    return (
        isinstance(test, ast.Compare)
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.In)
        and isinstance(test.comparators[0], ast.List)
        and [elt.value for elt in test.comparators[0].elts] == ["1", "2"]
    )


def _is_action_eq(test: ast.expr, value: str) -> bool:
    return (
        isinstance(test, ast.Compare)
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.Eq)
        and isinstance(test.left, ast.Name)
        and test.left.id == "action"
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value == value
    )


def _is_output_path_overwrite_prompt(test: ast.expr) -> bool:
    return (
        isinstance(test, ast.BoolOp)
        and isinstance(test.op, ast.And)
        and len(test.values) == 2
        and isinstance(test.values[0], ast.Call)
        and isinstance(test.values[0].func, ast.Attribute)
        and test.values[0].func.attr == "exists"
        and isinstance(test.values[0].func.value, ast.Name)
        and test.values[0].func.value.id == "output_path"
        and isinstance(test.values[1], ast.Compare)
        and len(test.values[1].ops) == 1
        and isinstance(test.values[1].ops[0], ast.Eq)
        and isinstance(test.values[1].left, ast.Name)
        and test.values[1].left.id == "mode"
        and isinstance(test.values[1].comparators[0], ast.Constant)
        and test.values[1].comparators[0].value == "1"
    )


EXCLUSIONS = (
    ("not check_ffmpeg()", _is_not_check_ffmpeg, "host FFmpeg availability integration"),
    ("use_saved != 'y'", _is_use_saved_not_y, "interactive handoff to start-index menu"),
    ("mode in ['1', '2']", _is_mode_in_1_2, "interactive mode input validation loop"),
    ("action == 'q'", lambda test: _is_action_eq(test, "q"), "manual quit UI action"),
    ("action == 's'", lambda test: _is_action_eq(test, "s"), "manual skip UI action"),
    ("output_path.exists() and mode == '1'", _is_output_path_overwrite_prompt, "interactive overwrite prompt"),
)


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

    scope_names = frozenset(SCOPE_FUNCTIONS)
    excluded_lines = set()
    absent_exclusions = []
    for label, predicate, _reason in EXCLUSIONS:
        found = False
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name != "main":
                continue
            for sub_node in ast.walk(node):
                if isinstance(sub_node, ast.If) and predicate(sub_node.test):
                    found = True
                    excluded_lines.add(sub_node.lineno)
                    break
            if found:
                break
        if not found:
            absent_exclusions.append(label)
    if absent_exclusions:
        return _fail(f"expected exclusion condition(s) missing from source: {', '.join(absent_exclusions)}")

    executed_arcs = [tuple(arc) for arc in (report.get("executed_branches") or [])]
    missing_arcs = [tuple(arc) for arc in (report.get("missing_branches") or [])]

    def scope_of(line: int):
        for name in SCOPE_FUNCTIONS:
            span = spans.get(name)
            if span and span[0] <= line <= span[1]:
                return name
        return None

    scoped_executed = []
    for arc in executed_arcs:
        start, end = int(arc[0]), int(arc[1])
        name = scope_of(start)
        if name is None or start in excluded_lines:
            continue
        scoped_executed.append((start, end, name))

    scoped_missing = []
    for arc in missing_arcs:
        start, end = int(arc[0]), int(arc[1])
        name = scope_of(start)
        if name is None or start in excluded_lines:
            continue
        scoped_missing.append((start, end, name))

    scoped_covered = len(scoped_executed)
    scoped_missing_count = len(scoped_missing)
    scoped_total = scoped_covered + scoped_missing_count

    function_names = ", ".join(SCOPE_FUNCTIONS)
    print(f"policy-coverage: scoped covered branches: {scoped_covered}")
    print(f"policy-coverage: scoped total branches: {scoped_total}")
    print(f"policy-coverage: scoped missing arcs: {scoped_missing_count}")
    print(f"policy-coverage: scoped functions: {function_names}")
    for label, _predicate, reason in EXCLUSIONS:
        print(f"policy-coverage: explicit exclusion: {label} ({reason})")

    if scoped_total <= 0:
        return _fail("no scoped branches were measured.")

    if scoped_missing:
        for start, end, name in sorted(scoped_missing):
            print(f"policy-coverage: missing branch arc {start}->{end} in scoped function {name}")
        return 1

    print("policy-coverage: no missing branches in policy scope.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
