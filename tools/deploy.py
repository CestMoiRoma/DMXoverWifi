#!/usr/bin/env python3
"""
Copy firmware source (boot.py, code.py, src/, www/, lib/) onto the
board's CIRCUITPY drive. Does not touch data/ (runtime config) on the
target.

The board's filesystem must be PC-writable to do this - either the
board is in config mode (double-tap reset, or "Set-System unlock-write"
after ejecting the drive), or nothing has booted normal mode since it
was last put in config mode.

Usage:
    python tools/deploy.py [TARGET]

If TARGET is omitted, the script asks where the CIRCUITPY drive is
mounted.
"""
import shutil
import sys
from pathlib import Path

ITEMS = ("boot.py", "code.py", "src", "www", "lib")


def prompt_target():
    if sys.platform == "win32":
        hint = "e.g. E:\\ or L:\\"
    elif sys.platform == "darwin":
        hint = "e.g. /Volumes/CIRCUITPY"
    else:
        hint = "e.g. /media/$USER/CIRCUITPY or /run/media/$USER/CIRCUITPY"
    answer = input("Path to the CIRCUITPY drive (%s): " % hint).strip()
    if not answer:
        print("No target provided.", file=sys.stderr)
        sys.exit(1)
    return answer


def main():
    target = Path(sys.argv[1] if len(sys.argv) > 1 else prompt_target())
    repo_root = Path(__file__).resolve().parent.parent

    if not target.exists():
        print("Target %s not found." % target, file=sys.stderr)
        sys.exit(1)

    test_file = target / ".deploy_write_test"
    try:
        test_file.write_text("test")
        test_file.unlink()
    except OSError as e:
        print("%s is read-only right now: %s" % (target, e), file=sys.stderr)
        print(
            "Put the board in config mode first (double-tap reset) and retry.",
            file=sys.stderr,
        )
        sys.exit(1)

    for item in ITEMS:
        src = repo_root / item
        dst = target / item
        if not src.exists():
            print("Skipping %s (not found in repo)" % item)
            continue
        print("Syncing %s ..." % item)
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
