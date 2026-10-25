import tempfile
import unittest
from pathlib import Path

from scripts.brand_generate import (
    BrandError,
    check_generated_assets,
    render_favicon_svg,
    render_generated_assets,
    render_logo_svg,
    render_readme_banner_svg,
    render_social_preview_svg,
    validate_facts,
    validate_palette,
    validate_social_preview_png,
    write_generated_assets,
)


VALID_PALETTE = {
    "base": "#24273a",
    "mantle": "#1e2030",
    "crust": "#181926",
    "text": "#cad3f5",
    "subtext1": "#b8c0e0",
    "surface0": "#363a4f",
    "surface1": "#494d64",
    "sky": "#91d7e3",
}

VALID_FACTS = {
    "output_formats": ["MP4", "MKV"],
    "max_attempts_per_item": 3,
    "default_inactivity_timeout_seconds": 60,
    "social_pillars": [
        "Authenticated HTTP/HLS",
        "MP4/MKV stream copy",
        "Resumable batches with retries",
    ],
    "readme_banner_tagline": "Download HTTP/HLS streams as MP4 or MKV — no transcoding.",
}


class BrandGenerateTests(unittest.TestCase):
    def test_palette_requires_accepted_hex_colors(self) -> None:
        self.assertEqual(validate_palette(VALID_PALETTE), [])

        invalid = dict(VALID_PALETTE, sky="91d7e3")
        self.assertIn(
            "brand palette entry sky must be a hex color like #24273a",
            validate_palette(invalid),
        )

    def test_facts_must_match_verified_metrics(self) -> None:
        self.assertEqual(validate_facts(VALID_FACTS), [])

        invalid_attempts = dict(VALID_FACTS, max_attempts_per_item=5)
        self.assertTrue(any("max_attempts_per_item" in error for error in validate_facts(invalid_attempts)))

        invalid_timeout = dict(VALID_FACTS, default_inactivity_timeout_seconds=30)
        self.assertTrue(any("default_inactivity_timeout_seconds" in error for error in validate_facts(invalid_timeout)))

    def test_rendered_brand_svg_assets_are_deterministic(self) -> None:
        self.assertEqual(render_logo_svg(VALID_PALETTE, VALID_FACTS), render_logo_svg(VALID_PALETTE, VALID_FACTS))
        self.assertEqual(render_favicon_svg(VALID_PALETTE, VALID_FACTS), render_favicon_svg(VALID_PALETTE, VALID_FACTS))
        self.assertEqual(render_readme_banner_svg(VALID_PALETTE, VALID_FACTS), render_readme_banner_svg(VALID_PALETTE, VALID_FACTS))
        self.assertEqual(render_social_preview_svg(VALID_PALETTE, VALID_FACTS), render_social_preview_svg(VALID_PALETTE, VALID_FACTS))

    def test_rendered_brand_svg_assets_use_accepted_copy(self) -> None:
        logo = render_logo_svg(VALID_PALETTE, VALID_FACTS)
        self.assertIn(VALID_PALETTE["sky"], logo)
        self.assertIn(VALID_PALETTE["text"], logo)

        banner = render_readme_banner_svg(VALID_PALETTE, VALID_FACTS)
        self.assertIn(VALID_FACTS["readme_banner_tagline"], banner)

    def test_rendered_brand_assets_validate_social_preview_png(self) -> None:
        assets = render_generated_assets(VALID_PALETTE, VALID_FACTS)
        self.assertEqual(validate_social_preview_png(assets["social-preview.png"]), [])

        invalid_png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0D" + b"IHDR" + b"\x00\x00\x00\x05" + b"\x00\x00\x00\x03" + b"\x00" * 20
        invalid_png_errors = validate_social_preview_png(invalid_png)
        self.assertTrue(any("social preview PNG must be 1280x640" in error for error in invalid_png_errors))

    def test_rendered_brand_assets_reject_invalid_data(self) -> None:
        with self.assertRaises(BrandError):
            render_generated_assets(dict(VALID_PALETTE, sky="red"), VALID_FACTS)

    def test_social_preview_renders_three_separate_pillar_lines(self) -> None:
        social_preview = render_social_preview_svg(VALID_PALETTE, VALID_FACTS)
        self.assertIn(VALID_FACTS["social_pillars"][0], social_preview)
        self.assertIn(VALID_FACTS["social_pillars"][1], social_preview)
        self.assertIn(VALID_FACTS["social_pillars"][2], social_preview)

    def test_check_detects_missing_and_stale_generated_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            assets = render_generated_assets(VALID_PALETTE, VALID_FACTS)
            write_generated_assets(root, assets)

            self.assertEqual(check_generated_assets(root, assets), [])

            logo_path = root / "brand" / "generated" / "logo.svg"
            logo_path.write_bytes(b"stale")
            self.assertEqual(check_generated_assets(root, assets), ["stale generated asset: brand/generated/logo.svg"])

            favicon_path = root / "brand" / "generated" / "favicon.svg"
            favicon_path.unlink()
            self.assertEqual(
                check_generated_assets(root, assets),
                [
                    "missing generated asset: brand/generated/favicon.svg",
                    "stale generated asset: brand/generated/logo.svg",
                ],
            )


if __name__ == "__main__":
    unittest.main()
