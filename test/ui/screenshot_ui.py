#!/usr/bin/env python3
"""Screenshot every page of the web UI against the mock board.

No hardware and no live rig involved: mock_server.py serves the real www/ files
backed by demo data, so the shots always show a populated UI and never leak
someone's actual wifi list.

    python test/ui/screenshot_ui.py --out docs/images

Needs playwright:

    pip install playwright && playwright install chromium
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from browser import launch_chromium  # noqa: E402
from mock_server import serve_in_background  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

PAGES = [
    ("home", "Home"),
    ("devices", "Device Manager"),
    ("settings", "Settings"),
    ("info", "Info"),
]

WIDTH = 860
MAX_HEIGHT = 4000

# Values the Home page sliders are dragged to before the shot, so the page does
# not look like a factory reset.
DEMO_SLIDER_VALUES = [255, 200, 40, 120]


def capture(page, view, out_dir):
    page.evaluate(
        "name => document.querySelector('.nav-btn[data-view=\"' + name + '\"]').click()", view
    )
    page.wait_for_timeout(600)

    if view == "home":
        page.evaluate(
            """values => {
                const sliders = document.querySelectorAll('#view-home input[type="range"]');
                values.forEach((value, i) => {
                    if (!sliders[i]) return;
                    sliders[i].value = value;
                    sliders[i].dispatchEvent(new Event('input', { bubbles: true }));
                });
            }""",
            DEMO_SLIDER_VALUES,
        )
        page.wait_for_timeout(200)

    height = page.evaluate(
        """() => {
            const view = document.querySelector('.view.active');
            return Math.ceil(view.getBoundingClientRect().bottom + window.scrollY + 24);
        }"""
    )
    height = max(320, min(height, MAX_HEIGHT))

    path = out_dir / ("ui-%s.png" % view)
    page.screenshot(path=str(path), clip={"x": 0, "y": 0, "width": WIDTH, "height": height})
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "docs" / "images"),
        help="Directory to write ui-<page>.png into.",
    )
    parser.add_argument(
        "--color-scheme",
        choices=("dark", "light"),
        default="dark",
        help="Which half of the stylesheet to shoot. Headless Chromium reports "
        "light by default, but the board is usually looked at in the dark.",
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "playwright is required: pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        return 1

    server, _state, url = serve_in_background()
    print("mock board on %s" % url)

    try:
        with sync_playwright() as pw:
            browser = launch_chromium(pw)
            page = browser.new_page(
                viewport={"width": WIDTH, "height": MAX_HEIGHT},
                device_scale_factor=2,
                color_scheme=args.color_scheme,
            )
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            for view, label in PAGES:
                page.goto(url, wait_until="networkidle")
                page.wait_for_timeout(400)
                path = capture(page, view, out_dir)
                print("  %-16s -> %s" % (label, path.name))

            browser.close()

            if errors:
                print("JavaScript errors on the page:", file=sys.stderr)
                for error in errors:
                    print("  " + error, file=sys.stderr)
                return 1
    finally:
        server.shutdown()

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
