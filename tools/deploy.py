#!/usr/bin/env python3
"""
Copy firmware source (boot.py, code.py, src/, www/) onto the board's
CIRCUITPY drive. Does not touch lib/ (vendored libraries) or data/
(runtime config) on the target.

The board's filesystem must be PC-writable to do this - either the
board is in config mode (double-tap reset, or "Set-System unlock-write"
after ejecting the drive), or nothing has booted normal mode since it
was last put in config mode.

Usage:
    python tools/deploy.py [TARGET]

TARGET is the mount point of the CIRCUITPY drive (default: E:\\ on
Windows).
"""
import shutil
import sys
from pathlib import Path

DEFAULT_TARGET = "E:\\"
ITEMS = ("boot.py", "code.py", "src", "www")


def main():
    target = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TARGET)
    repo_root = Path(__file__).resolve().parent.parent

    if not target.exists():
        print(f"Target {target} not found.", file=sys.stderr)
        sys.exit(1)

    test_file = target / ".deploy_write_test"
    try:
        test_file.write_text("test")
        test_file.unlink()
    except OSError as e:
        print(f"{target} is read-only right now: {e}", file=sys.stderr)
        print(
            "Put the board in config mode first (double-tap reset) and retry.",
            file=sys.stderr,
        )
        sys.exit(1)

    for item in ITEMS:
        src = repo_root / item
        dst = target / item
        if not src.exists():
            print(f"Skipping {item} (not found in repo)")
            continue
        print(f"Syncing {item} ...")
        if src.is_dir():
            # Wipe destination first: copytree(dirs_exist_ok=True) merges,
            # but we want a clean overwrite so removed files don't linger.
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

    print("Deploy complete. Reboot the board to run the new code.")


if __name__ == "__main__":
    main()
