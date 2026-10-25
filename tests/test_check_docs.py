import tempfile
import unittest
from pathlib import Path

from scripts.check_docs import check_site


class CheckDocsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.site_dir = Path(self._temporary_directory.name)

    def write_page(self, relative_path: str, content: str) -> None:
        path = self.site_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def accessible_page(body: str) -> str:
        return (
            '<!doctype html><html lang="en"><head><title>Example</title></head>'
            f"<body><main><h1>Example</h1>{body}</main></body></html>"
        )

    def test_accepts_valid_local_links_and_external_links(self) -> None:
        self.write_page(
            "index.html",
            self.accessible_page(
                '<a href="guide/#details">Guide</a>'
                '<a href="https://example.com/">External</a>'
                '<button aria-label="Open menu"></button>'
                '<input type="search" aria-label="Search">'
                '<a id="__skip" tabindex="-1"></a>'
                '<input type="radio" name="__palette" id="__palette_0" aria-hidden="true">'
                '<code><a id="__codelineno-0-1" name="__codelineno-0-1" href="#__codelineno-0-1"></a></code>'
            ),
        )
        self.write_page(
            "guide/index.html",
            '<!doctype html><html lang="en"><head><title>Guide</title></head>'
            '<body><main><h1 id="details">Guide</h1></main></body></html>',
        )

        self.assertEqual(check_site(self.site_dir), [])

    def test_rejects_root_relative_links_outside_configured_base_path(self) -> None:
        self.write_page(
            "index.html",
            self.accessible_page(
                '<link rel="stylesheet" href="/assets/site.css">'
                '<a href="/">Root</a>'
                '<a href="/ffmpegfyMe/guide/">Guide</a>'
            ),
        )
        self.write_page("assets/site.css", "body {}")
        self.write_page(
            "guide/index.html",
            '<!doctype html><html lang="en"><head><title>Guide</title></head>'
            '<body><main><h1>Guide</h1></main></body></html>',
        )

        errors = check_site(self.site_dir, "/ffmpegfyMe")

        self.assertCountEqual(
            errors,
            [
                "index.html:1: internal href target is outside configured base path: /",
                "index.html:1: internal href target is outside configured base path: /assets/site.css",
            ],
        )

    def test_rejects_missing_internal_target(self) -> None:
        self.write_page("index.html", self.accessible_page('<a href="missing/">Missing</a>'))

        errors = check_site(self.site_dir)

        self.assertTrue(any("internal href target does not exist" in error for error in errors))

    def test_rejects_unnamed_navigation_link(self) -> None:
        self.write_page("index.html", self.accessible_page('<a href="guide/"> </a>'))
        self.write_page(
            "guide/index.html",
            '<!doctype html><html lang="en"><head><title>Guide</title></head>'
            '<body><main><h1>Guide</h1></main></body></html>',
        )

        errors = check_site(self.site_dir)

        self.assertTrue(any("a has no accessible name" in error for error in errors))

    def test_rejects_missing_fragment(self) -> None:
        self.write_page("index.html", self.accessible_page('<a href="guide/#missing">Guide</a>'))
        self.write_page(
            "guide/index.html",
            '<!doctype html><html lang="en"><head><title>Guide</title></head>'
            '<body><main><h1>Guide</h1></main></body></html>',
        )

        errors = check_site(self.site_dir)

        self.assertTrue(any("internal fragment does not exist" in error for error in errors))

    def test_rejects_basic_accessibility_failures(self) -> None:
        self.write_page(
            "index.html",
            '<html><head><title></title></head><body><main><h1>Example</h1>'
            '<img src="image.png"><button></button><input type="search">'
            '</main></body></html>',
        )

        errors = check_site(self.site_dir)

        self.assertTrue(any("html lang" in error for error in errors))
        self.assertTrue(any("non-empty title" in error for error in errors))
        self.assertTrue(any("missing alt text" in error for error in errors))
        self.assertTrue(any("button has no accessible name" in error for error in errors))
        self.assertTrue(any("control has no accessible label" in error for error in errors))

    def test_rejects_control_nested_in_label_with_mismatched_for(self) -> None:
        self.write_page(
            "index.html",
            self.accessible_page(
                '<label for="other">Region <input id="region" type="text"></label>'
            ),
        )

        errors = check_site(self.site_dir)

        self.assertTrue(any("text control has no accessible label" in error for error in errors))

    def test_accepts_label_wrapped_control_without_id(self) -> None:
        self.write_page(
            "index.html",
            self.accessible_page('<label>Region <input type="text"></label>'),
        )

        self.assertEqual(check_site(self.site_dir), [])

    def test_accepts_control_with_matching_explicit_label(self) -> None:
        self.write_page(
            "index.html",
            self.accessible_page(
                '<label for="region">Region</label><input id="region" type="text">'
            ),
        )

        self.assertEqual(check_site(self.site_dir), [])

    def test_rejects_control_adjacent_to_label(self) -> None:
        self.write_page(
            "index.html",
            self.accessible_page('<label>Region</label><input type="text">'),
        )

        errors = check_site(self.site_dir)

        self.assertTrue(any("text control has no accessible label" in error for error in errors))

    def test_rejects_paths_that_escape_site_directory(self) -> None:
        self.write_page("index.html", self.accessible_page('<a href="../../outside.html">Outside</a>'))

        errors = check_site(self.site_dir)

        self.assertTrue(any("escapes the generated site" in error for error in errors))

    def test_rejects_missing_required_page_structure(self) -> None:
        self.write_page("index.html", '<html lang="en"><head><title>Example</title></head><body></body></html>')

        errors = check_site(self.site_dir)

        self.assertTrue(any("missing an h1 heading" in error for error in errors))
        self.assertTrue(any("missing a main landmark" in error for error in errors))

    def test_rejects_missing_site_directory(self) -> None:
        missing = self.site_dir / "missing"

        self.assertTrue(any("site directory does not exist" in error for error in check_site(missing)))


if __name__ == "__main__":
    unittest.main()
