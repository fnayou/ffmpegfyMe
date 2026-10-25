#!/usr/bin/env python3
"""Check generated documentation links and basic accessibility without network access."""

from __future__ import annotations

import argparse
import sys
import tomllib
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class PageParser(HTMLParser):
    def __init__(self, relative_path: Path) -> None:
        super().__init__(convert_charrefs=True)
        self.relative_path = relative_path
        self.errors: list[str] = []
        self.ids: set[str] = set()
        self.links: list[tuple[int, str, str]] = []
        self.language = ""
        self.title_parts: list[str] = []
        self.title_depth = 0
        self.h1_count = 0
        self.main_count = 0
        self.labelled_ids: set[str] = set()
        self.controls: list[tuple[int, dict[str, str], bool]] = []
        self.label_stack: list[str | None] = []
        self.interactive: list[dict[str, object]] = []

    def handle_starttag(self, tag: str, attributes: list[tuple[str, str | None]]) -> None:
        attrs = {name: value or "" for name, value in attributes}
        line = self.getpos()[0]

        if tag == "html":
            self.language = attrs.get("lang", "").strip()
        if tag == "title":
            self.title_depth += 1
        if tag == "h1":
            self.h1_count += 1
        if tag == "main":
            self.main_count += 1
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag == "a" and attrs.get("name"):
            self.ids.add(attrs["name"])

        if tag == "label":
            label_for = attrs.get("for") if "for" in attrs else None
            self.label_stack.append(label_for)
            if label_for:
                self.labelled_ids.add(label_for)

        if tag == "img" and "alt" not in attrs:
            self.errors.append(f"{self.relative_path}:{line}: image is missing alt text")

        if tag in {"input", "select", "textarea"}:
            hidden = "hidden" in attrs or attrs.get("aria-hidden", "").lower() == "true"
            hidden_input = tag == "input" and attrs.get("type", "text").lower() == "hidden"
            if not hidden and not hidden_input:
                wrapped_by_label = bool(self.label_stack and self.label_stack[-1] is None)
                self.controls.append((line, attrs, wrapped_by_label))

        if tag in {"a", "link", "script", "img"}:
            for attribute in ("href", "src"):
                value = attrs.get(attribute, "").strip()
                if value:
                    self.links.append((line, attribute, value))

        generated_code_anchor = tag == "a" and attrs.get("id", "").startswith("__codelineno-")
        is_interactive = tag == "button" or (tag == "a" and bool(attrs.get("href")) and not generated_code_anchor)
        if is_interactive:
            self.interactive.append(
                {
                    "tag": tag,
                    "line": line,
                    "named": bool(attrs.get("aria-label", "").strip() or attrs.get("aria-labelledby", "").strip() or attrs.get("title", "").strip()),
                    "text": [],
                }
            )
        if tag == "img" and attrs.get("alt"):
            for item in self.interactive:
                item["text"].append(attrs["alt"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self.title_depth:
            self.title_depth -= 1
        if tag == "label" and self.label_stack:
            self.label_stack.pop()
        if tag in {"a", "button"}:
            for index in range(len(self.interactive) - 1, -1, -1):
                if self.interactive[index]["tag"] == tag:
                    item = self.interactive.pop(index)
                    label = "".join(item["text"]).strip()
                    if not item["named"] and not label:
                        self.errors.append(
                            f"{self.relative_path}:{item['line']}: {tag} has no accessible name"
                        )
                    break

    def handle_data(self, data: str) -> None:
        if self.title_depth:
            self.title_parts.append(data)
        for item in self.interactive:
            item["text"].append(data)

    def finish(self) -> list[str]:
        if not self.language:
            self.errors.append(f"{self.relative_path}: document is missing an html lang attribute")
        if not "".join(self.title_parts).strip():
            self.errors.append(f"{self.relative_path}: document is missing a non-empty title")
        if not self.h1_count:
            self.errors.append(f"{self.relative_path}: document is missing an h1 heading")
        if not self.main_count:
            self.errors.append(f"{self.relative_path}: document is missing a main landmark")

        for line, attrs, wrapped_by_label in self.controls:
            if not wrapped_by_label and not any(
                attrs.get(name, "").strip() for name in ("aria-label", "aria-labelledby")
            ):
                control_id = attrs.get("id", "")
                if not control_id or control_id not in self.labelled_ids:
                    tag = attrs.get("type", "control") if "type" in attrs else "control"
                    self.errors.append(
                        f"{self.relative_path}:{line}: {tag} control has no accessible label"
                    )
        return self.errors


def _resolve_target(root: Path, page: Path, value: str, base_path: str) -> tuple[Path | None, str]:
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        return None, ""

    path = unquote(parsed.path)
    if not path:
        target = root / page
    elif path.startswith("/"):
        site_path = path.lstrip("/")
        prefix = base_path.strip("/")
        if prefix and (site_path == prefix or site_path.startswith(prefix + "/")):
            site_path = site_path[len(prefix):].lstrip("/")
        target = root / site_path
    else:
        target = root / page.parent / path

    target = target.resolve()
    root = root.resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return target, unquote(parsed.fragment)

    if target.is_dir():
        target = target / "index.html"
    elif not target.exists() and not target.suffix:
        target = target / "index.html"
    return target, unquote(parsed.fragment)


def check_site(site_dir: Path, base_path: str = "") -> list[str]:
    root = site_dir.resolve()
    if not root.is_dir():
        return [f"site directory does not exist: {site_dir}"]

    html_files = sorted(root.rglob("*.html"))
    if not html_files:
        return [f"no generated HTML pages found in {site_dir}"]

    scans: dict[Path, PageParser] = {}
    errors: list[str] = []
    for html_file in html_files:
        relative_path = html_file.relative_to(root)
        parser = PageParser(relative_path)
        parser.feed(html_file.read_text(encoding="utf-8"))
        scans[relative_path] = parser
        errors.extend(parser.finish())

    for relative_path, parser in scans.items():
        for line, attribute, value in parser.links:
            parsed = urlsplit(value)
            path = unquote(parsed.path)
            prefix = base_path.strip("/")
            site_path = path.lstrip("/")
            if (
                path.startswith("/")
                and not parsed.scheme
                and not parsed.netloc
                and prefix
                and site_path != prefix
                and not site_path.startswith(prefix + "/")
            ):
                errors.append(
                    f"{relative_path}:{line}: internal {attribute} target is outside configured base path: {value}"
                )
                continue
            target, fragment = _resolve_target(root, relative_path, value, base_path)
            if target is None:
                continue
            try:
                target_relative = target.relative_to(root)
            except ValueError:
                errors.append(f"{relative_path}:{line}: internal {attribute} target escapes the generated site: {value}")
                continue
            if not target.is_file():
                errors.append(f"{relative_path}:{line}: internal {attribute} target does not exist: {value}")
                continue
            if fragment and target.suffix.lower() == ".html":
                target_scan = scans.get(target_relative)
                if target_scan is None:
                    target_scan = PageParser(target_relative)
                    target_scan.feed(target.read_text(encoding="utf-8"))
                    scans[target_relative] = target_scan
                if fragment not in target_scan.ids:
                    errors.append(f"{relative_path}:{line}: internal fragment does not exist: {value}")

    return sorted(errors)


def _configured_base_path() -> str:
    config_path = Path(__file__).resolve().parents[1] / "zensical.toml"
    try:
        project = tomllib.loads(config_path.read_text(encoding="utf-8"))["project"]
        return urlsplit(project.get("site_url", "")).path.rstrip("/")
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return ""


def main() -> int:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("site_dir", nargs="?", type=Path, default=Path("site"))
    argument_parser.add_argument("--base-path", default=None)
    args = argument_parser.parse_args()

    base_path = args.base_path if args.base_path is not None else _configured_base_path()
    errors = check_site(args.site_dir, base_path)
    if errors:
        print("Documentation quality checks failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    page_count = sum(1 for _ in args.site_dir.rglob("*.html"))
    print(f"Documentation quality checks passed: {page_count} HTML pages, local links, and basic accessibility.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
