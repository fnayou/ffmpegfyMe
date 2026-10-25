#!/usr/bin/env python3
"""Deterministic brand asset generator for ffmpegfyMe."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
BRAND_DIR = ROOT_DIR / "brand"
SRC_DIR = BRAND_DIR / "src"
DATA_DIR = BRAND_DIR / "data"
GENERATED_DIR = BRAND_DIR / "generated"

BRAND_DATA_FILE = DATA_DIR / "brand.json"
FACTS_DATA_FILE = DATA_DIR / "facts.json"

SOURCE_NAMES = ("favicon.svg", "logo.svg", "readme-banner.svg", "social-preview.svg")
GENERATED_NAMES = ("favicon.svg", "logo.svg", "readme-banner.svg", "social-preview.png", "social-preview.svg", "social-preview.json")
SOCIAL_PREVIEW_METADATA = "social-preview.json"

SOCIAL_PREVIEW_WIDTH = 1280
SOCIAL_PREVIEW_HEIGHT = 640
SOCIAL_PREVIEW_MAX_BYTES = 1_000_000
WEBSITE_ASSET_NAMES = ("logo.svg", "favicon.svg")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

PALETTE_KEYS = ("base", "mantle", "crust", "text", "subtext1", "surface0", "surface1", "sky")
HEX_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")


class BrandError(Exception):
    """Raised when brand data, templates, or generated assets are invalid."""


def _read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_palette(palette: dict) -> list[str]:
    if not isinstance(palette, dict):
        return ["brand palette must be a JSON object"]
    errors: list[str] = []
    for key in PALETTE_KEYS:
        value = palette.get(key)
        if not isinstance(value, str) or not HEX_COLOR_PATTERN.fullmatch(value):
            errors.append(f"brand palette entry {key} must be a hex color like #24273a")
    return errors


def validate_facts(facts: dict) -> list[str]:
    if not isinstance(facts, dict):
        return ["brand facts must be a JSON object"]
    errors: list[str] = []
    if facts.get("output_formats") != ["MP4", "MKV"]:
        errors.append("brand facts output_formats must be exactly [MP4, MKV]")
    if facts.get("max_attempts_per_item") != 3:
        errors.append("brand facts max_attempts_per_item must be 3")
    if facts.get("default_inactivity_timeout_seconds") != 60:
        errors.append("brand facts default_inactivity_timeout_seconds must be 60")
    pillars = facts.get("social_pillars")
    if not isinstance(pillars, list) or len(pillars) != 3 or not all(isinstance(pillar, str) and pillar.strip() for pillar in pillars):
        errors.append("brand facts social_pillars must list three non-empty strings")
    tagline = facts.get("readme_banner_tagline")
    if not isinstance(tagline, str) or not tagline.strip():
        errors.append("brand facts readme_banner_tagline must be a non-empty string")
    return errors


def _token_values(palette: dict, facts: dict) -> dict[str, str]:
    values: dict[str, str] = {}
    for key, value in palette.items():
        if isinstance(key, str) and isinstance(value, str):
            values[key.upper()] = value
    pillars = facts.get("social_pillars") or []
    values["PILLARS"] = ", ".join(pillars)
    values["PILLAR_1"] = pillars[0] if len(pillars) > 0 else ""
    values["PILLAR_2"] = pillars[1] if len(pillars) > 1 else ""
    values["PILLAR_3"] = pillars[2] if len(pillars) > 2 else ""
    values["TAGLINE"] = facts.get("readme_banner_tagline") or ""
    return values


def _finalize(svg_text: str, palette: dict, facts: dict) -> str:
    rendered = svg_text
    for token, value in sorted(_token_values(palette, facts).items()):
        rendered = rendered.replace("{{" + token + "}}", value)
    if "{{" in rendered:
        raise BrandError("brand SVG template has unresolved placeholders")
    return rendered


def _load_source(name: str) -> str:
    path = SRC_DIR / name
    if not path.is_file():
        raise BrandError(f"missing brand source template: brand/src/{name}")
    return path.read_text(encoding="utf-8")


def render_logo_svg(palette: dict, facts: dict) -> str:
    return _finalize(_load_source("logo.svg"), palette, facts)


def render_favicon_svg(palette: dict, facts: dict) -> str:
    return _finalize(_load_source("favicon.svg"), palette, facts)


def render_readme_banner_svg(palette: dict, facts: dict) -> str:
    return _finalize(_load_source("readme-banner.svg"), palette, facts)


def render_social_preview_svg(palette: dict, facts: dict) -> str:
    return _finalize(_load_source("social-preview.svg"), palette, facts)


def render_social_preview_png(svg_text: str) -> bytes:
    with tempfile.TemporaryDirectory(prefix="ffmpegfy-brand-") as tmp_dir:
        svg_path = Path(tmp_dir) / "social-preview.svg"
        png_path = Path(tmp_dir) / "social-preview.png"
        svg_path.write_text(svg_text, encoding="utf-8")
        try:
            completed = subprocess.run(
                ["rsvg-convert", "--output", str(png_path), str(svg_path)],
                capture_output=True,
                check=False,
            )
        except FileNotFoundError as error:
            raise BrandError("rsvg-convert is not installed; install librsvg2-bin to generate brand PNG assets") from error
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise BrandError(f"rsvg-convert failed to render social preview PNG: {detail}")
        return png_path.read_bytes()


def rsvg_convert_version() -> str:
    try:
        completed = subprocess.run(["rsvg-convert", "--version"], capture_output=True, check=False)
    except FileNotFoundError as error:
        raise BrandError("rsvg-convert is not installed; install librsvg2-bin to generate brand PNG assets") from error
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise BrandError(f"rsvg-convert failed to report its version: {detail}")
    return completed.stdout.decode("utf-8", errors="replace").strip()


def validate_social_preview_png(png_bytes: bytes) -> list[str]:
    if png_bytes[:8] != PNG_SIGNATURE:
        return ["social preview PNG must start with a PNG signature"]
    if len(png_bytes) < 24:
        return ["social preview PNG must include an IHDR chunk"]
    width = int.from_bytes(png_bytes[16:20], "big")
    height = int.from_bytes(png_bytes[20:24], "big")
    errors: list[str] = []
    if width != SOCIAL_PREVIEW_WIDTH or height != SOCIAL_PREVIEW_HEIGHT:
        errors.append(f"social preview PNG must be {SOCIAL_PREVIEW_WIDTH}x{SOCIAL_PREVIEW_HEIGHT}, got {width}x{height}")
    if len(png_bytes) > SOCIAL_PREVIEW_MAX_BYTES:
        errors.append(f"social preview PNG must be under {SOCIAL_PREVIEW_MAX_BYTES} bytes, got {len(png_bytes)}")
    return errors


def render_generated_assets(palette: dict, facts: dict) -> dict[str, bytes]:
    errors = validate_palette(palette) + validate_facts(facts)
    if errors:
        raise BrandError("brand data validation failed: " + "; ".join(errors))
    logo_svg = render_logo_svg(palette, facts)
    favicon_svg = render_favicon_svg(palette, facts)
    readme_banner_svg = render_readme_banner_svg(palette, facts)
    social_preview_svg = render_social_preview_svg(palette, facts)
    png_bytes = render_social_preview_png(social_preview_svg)
    png_errors = validate_social_preview_png(png_bytes)
    if png_errors:
        raise BrandError("social preview PNG validation failed: " + "; ".join(png_errors))
    metadata = {
        "source_sha256": hashlib.sha256(social_preview_svg.encode("utf-8")).hexdigest(),
        "png_sha256": hashlib.sha256(png_bytes).hexdigest(),
        "rsvg_convert_version": rsvg_convert_version(),
    }
    return {
        "favicon.svg": favicon_svg.encode("utf-8"),
        "logo.svg": logo_svg.encode("utf-8"),
        "readme-banner.svg": readme_banner_svg.encode("utf-8"),
        "social-preview.svg": social_preview_svg.encode("utf-8"),
        "social-preview.png": png_bytes,
        SOCIAL_PREVIEW_METADATA: (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    }


def check_generated_assets(root: Path, assets: dict[str, bytes]) -> list[str]:
    errors: list[str] = []
    generated_dir = root / "brand" / "generated"
    with tempfile.TemporaryDirectory(prefix="ffmpegfy-brand-check-") as tmp_dir:
        temp_dir = Path(tmp_dir)
        for filename, content in sorted(assets.items()):
            (temp_dir / filename).write_bytes(content)
        for filename, content in sorted(assets.items()):
            temp_path = temp_dir / filename
            path = generated_dir / filename
            if not path.is_file():
                errors.append(f"missing generated asset: brand/generated/{filename}")
                continue
            if path.read_bytes() != temp_path.read_bytes():
                errors.append(f"stale generated asset: brand/generated/{filename}")
    return errors


def write_generated_assets(root: Path, assets: dict[str, bytes]) -> None:
    generated_dir = root / "brand" / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in sorted(assets.items()):
        (generated_dir / filename).write_bytes(content)


def check_website_assets(root: Path, assets: dict[str, bytes]) -> list[str]:
    errors: list[str] = []
    website_assets_dir = root / "website" / "assets"
    for filename in sorted(WEBSITE_ASSET_NAMES):
        expected_bytes = assets[filename]
        path = website_assets_dir / filename
        if not path.is_file():
            errors.append(f"missing website asset: website/assets/{filename}")
            continue
        if path.read_bytes() != expected_bytes:
            errors.append(f"stale website asset: website/assets/{filename}")
    return errors


def write_website_assets(root: Path, assets: dict[str, bytes]) -> None:
    website_assets_dir = root / "website" / "assets"
    website_assets_dir.mkdir(parents=True, exist_ok=True)
    for filename in sorted(WEBSITE_ASSET_NAMES):
        (website_assets_dir / filename).write_bytes(assets[filename])


def generate_brand_assets(root: Path) -> dict[str, bytes]:
    palette = _read_json(root / "brand" / "data" / "brand.json")
    facts = _read_json(root / "brand" / "data" / "facts.json")
    return render_generated_assets(palette, facts)


def check_brand_assets(root: Path) -> list[str]:
    palette = _read_json(root / "brand" / "data" / "brand.json")
    facts = _read_json(root / "brand" / "data" / "facts.json")
    errors = validate_palette(palette) + validate_facts(facts)
    if errors:
        raise BrandError("brand data validation failed: " + "; ".join(errors))
    svg_assets = {
        "favicon.svg": render_favicon_svg(palette, facts).encode("utf-8"),
        "logo.svg": render_logo_svg(palette, facts).encode("utf-8"),
        "readme-banner.svg": render_readme_banner_svg(palette, facts).encode("utf-8"),
        "social-preview.svg": render_social_preview_svg(palette, facts).encode("utf-8"),
    }
    errors = check_generated_assets(root, svg_assets)
    errors.extend(check_website_assets(root, svg_assets))
    generated_dir = root / "brand" / "generated"
    png_path = generated_dir / "social-preview.png"
    metadata_path = generated_dir / SOCIAL_PREVIEW_METADATA
    if not png_path.is_file():
        errors.append("missing generated asset: brand/generated/social-preview.png")
        return errors
    if not metadata_path.is_file():
        errors.append("missing generated asset: brand/generated/social-preview.json")
        return errors
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        errors.append("invalid generated metadata: brand/generated/social-preview.json")
        return errors
    if not isinstance(metadata, dict):
        errors.append("invalid generated metadata: brand/generated/social-preview.json")
        return errors
    png_bytes = png_path.read_bytes()
    source_hash = hashlib.sha256(svg_assets["social-preview.svg"]).hexdigest()
    png_hash = hashlib.sha256(png_bytes).hexdigest()
    if metadata.get("source_sha256") != source_hash:
        errors.append("stale generated metadata: brand/generated/social-preview.json source_sha256")
    if metadata.get("png_sha256") != png_hash:
        errors.append("stale generated metadata: brand/generated/social-preview.json png_sha256")
    if not isinstance(metadata.get("rsvg_convert_version"), str) or not metadata["rsvg_convert_version"].strip():
        errors.append("invalid generated metadata: brand/generated/social-preview.json rsvg_convert_version")
    errors.extend(validate_social_preview_png(png_bytes))
    return errors


def write_brand_assets(root: Path) -> None:
    assets = generate_brand_assets(root)
    write_generated_assets(root, assets)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate and check ffmpegfyMe brand assets.")
    parser.add_argument("--generate", action="store_true", help="Write generated brand assets.")
    parser.add_argument("--check", action="store_true", help="Check generated brand assets are current.")
    args = parser.parse_args(argv)
    if args.generate == args.check:
        parser.error("specify exactly one of --generate or --check")
    try:
        if args.generate:
            assets = generate_brand_assets(ROOT_DIR)
            write_generated_assets(ROOT_DIR, assets)
            write_website_assets(ROOT_DIR, assets)
            for filename in sorted(assets):
                content = assets[filename]
                detail = f"{len(content)} bytes" if filename.endswith(".png") else "JSON" if filename.endswith(".json") else "SVG"
                print(f"generated brand asset: brand/generated/{filename} ({detail})")
        else:
            errors = check_brand_assets(ROOT_DIR)
            if errors:
                for error in errors:
                    print(f"brand check failed: {error}", file=sys.stderr)
                return 1
            print("Brand assets are up to date.")
    except BrandError as error:
        print(f"brand error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
