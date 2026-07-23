"""Getting a Chromium in front of the UI, wherever the suite happens to run.

In the Docker image Playwright's own bundled Chromium is present. On a developer
machine it often is not, but Chrome or Edge usually is, and Playwright can drive
either through its channel mechanism. Try them in that order rather than making
everyone download a second browser.
"""

# Ghost-painted controls show up in screenshots of pages taller than the
# viewport unless GPU compositing is off.
DEFAULT_ARGS = ["--disable-gpu", "--hide-scrollbars"]

CHANNELS = (None, "chrome", "msedge")


class NoBrowserFound(RuntimeError):
    pass


def launch_chromium(playwright, args=None, **kwargs):
    attempts = []
    for channel in CHANNELS:
        options = dict(kwargs)
        options["args"] = list(args if args is not None else DEFAULT_ARGS)
        if channel:
            options["channel"] = channel
        try:
            return playwright.chromium.launch(**options)
        except Exception as exc:  # noqa: BLE001  any launch failure is a miss
            attempts.append("%s: %s" % (channel or "bundled chromium", str(exc).split("\n")[0]))

    raise NoBrowserFound(
        "no usable Chromium. Tried:\n  "
        + "\n  ".join(attempts)
        + "\nInstall one with: playwright install chromium"
    )
