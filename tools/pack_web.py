"""Pack the web UI into the firmware binary.

PlatformIO runs this as a `pre:` extra script. It reads the editable sources in
web/, splices the stylesheet and the script into the page where their tags sit,
gzips the result and writes it out as C arrays in src/web_assets.{h,cpp}.

Why one file: the board answers one HTTP client at a time, and a browser loading
the page opens a connection for it and then two more, in a burst, for the
stylesheet and the script. A subresource that loses that race takes the styling
of the whole UI with it. One file means one request, and nothing left to race.

Why in the firmware rather than on the filesystem: an over-the-air update writes
the application partition and leaves the data partition alone, which is the
whole point of it. With the UI on LittleFS, updating the firmware would leave
the old page in place to talk to a new API, and updating the page would mean
writing a filesystem image over the top of the config. Carrying the UI in the
binary means one artefact, always in step with the code that serves it, and a
LittleFS that holds nothing but settings nobody wants overwritten.

Sources stay separate and are edited normally. The generated files are build
output and gitignored.
"""

import gzip
import io
import json
import os

Import("env")  # noqa: F821  (injected by PlatformIO/SCons)

LINK_TAG = '<link rel="stylesheet" href="/style.css">'
SCRIPT_TAG = '<script src="/app.js"></script>'


def read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def squeeze(raw):
    """Deterministic gzip: no filename, no timestamp, so an unchanged page
    produces an unchanged source file and does not force a rebuild."""
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0) as gz:
        gz.write(raw)
    return buffer.getvalue()


def c_array(name, raw):
    """One byte per entry, twelve to a line. Verbose in the source, exact in the
    binary, and it needs no runtime decoding of any kind."""
    lines = []
    for start in range(0, len(raw), 12):
        chunk = raw[start:start + 12]
        lines.append("    " + " ".join("0x%02x," % byte for byte in chunk))
    return ("const uint8_t %s[] PROGMEM = {\n%s\n};\nconst size_t %s_LEN = %d;\n"
            % (name, "\n".join(lines), name, len(raw)))


def write_if_changed(path, text):
    """Rewriting an unchanged 500 KB source would rebuild it on every compile.

    Written through a temporary file and moved into place, because `pio run`
    with several environments runs them at once: two of these scripts firing
    together would otherwise have one compiler reading the file while the other
    is halfway through writing it. Found by a build that failed and then passed
    unchanged, which is the kind of flake worth closing rather than retrying.
    """
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as handle:
            if handle.read() == text:
                return False
    temporary = "%s.%d.tmp" % (path, os.getpid())
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(temporary, path)  # atomic on both Windows and POSIX
    return True


def main():
    project_dir = env.subst("$PROJECT_DIR")  # noqa: F821
    web_dir = os.path.join(project_dir, "web")
    src_dir = os.path.join(project_dir, "src")

    index_path = os.path.join(web_dir, "index.html")
    if not os.path.isfile(index_path):
        print("pack_web: no web/index.html, nothing to pack")
        return

    html = read(index_path)
    css = read(os.path.join(web_dir, "style.css"))
    js = read(os.path.join(web_dir, "app.js"))

    # A stray </style> or </script> inside the assets would close the block
    # early and dump the rest of the file into the page as text. Neither can
    # legitimately appear, so treat it as a build error rather than shipping a
    # page that half works.
    for name, body, closer in (("style.css", css, "</style"), ("app.js", js, "</script")):
        if closer in body:
            raise Exception("pack_web: %s contains %s>, which would break inlining" % (name, closer))

    for tag, name in ((LINK_TAG, "style.css"), (SCRIPT_TAG, "app.js")):
        if tag not in html:
            raise Exception("pack_web: web/index.html no longer contains %s; "
                            "the packer looks for it verbatim to know where %s goes" % (tag, name))

    # Every language rides inside the page. Switching is then instant and works
    # with no network at all, and the page stays the single request it was made
    # into. Four tables of interface strings cost about a kilobyte gzipped,
    # which is a fair price for not adding a second fetch back.
    languages = {}
    i18n_dir = os.path.join(web_dir, "i18n")
    if os.path.isdir(i18n_dir):
        for name in sorted(os.listdir(i18n_dir)):
            if name.endswith(".json"):
                languages[name[:-5]] = json.loads(read(os.path.join(i18n_dir, name)))

    html = html.replace(LINK_TAG, "<style>\n%s\n</style>" % css)
    html = html.replace(
        SCRIPT_TAG,
        "<script>\nwindow.I18N = %s;\n</script>\n<script>\n%s\n</script>"
        % (json.dumps(languages, ensure_ascii=False, separators=(",", ":")), js),
    )

    # Shipped gzipped, and only gzipped. The board writes the whole response
    # synchronously, so its main loop is stalled for as long as the transfer
    # takes and any connection arriving in that window queues behind it. Sending
    # a quarter of the bytes shortens that stall by the same factor, which
    # matters far more here than the flash it costs.
    raw = html.encode("utf-8")
    packed = squeeze(raw)

    # The UI links to a local copy of the wiki, carried the same way so the two
    # cannot drift and so it survives an update with no network.
    wiki_path = os.path.join(project_dir, "WIKI.md")
    wiki = squeeze(read(wiki_path).encode("utf-8")) if os.path.isfile(wiki_path) else b""

    header = ('// Generated by tools/pack_web.py. Do not edit.\n'
              '#pragma once\n\n'
              '#include <Arduino.h>\n\n'
              '#include "config.h"\n\n'
              '#if WITH_WEBUI\n'
              'extern const uint8_t WEB_INDEX_GZ[];\n'
              'extern const size_t WEB_INDEX_GZ_LEN;\n'
              'extern const uint8_t WEB_WIKI_GZ[];\n'
              'extern const size_t WEB_WIKI_GZ_LEN;\n'
              '#endif\n')

    # Guarded, so the headless builds do not carry 50 KB of a page they never
    # serve.
    source = ('// Generated by tools/pack_web.py. Do not edit.\n'
              '#include "web_assets.h"\n\n'
              '#if WITH_WEBUI\n\n'
              + c_array("WEB_INDEX_GZ", packed) + "\n"
              + c_array("WEB_WIKI_GZ", wiki) + "\n"
              '#endif\n')

    write_if_changed(os.path.join(src_dir, "web_assets.h"), header)
    changed = write_if_changed(os.path.join(src_dir, "web_assets.cpp"), source)

    print("pack_web: page %d bytes from %d (css %d, js %d, %.0f%% smaller), wiki %d bytes, "
          "%.1f KB of flash%s"
          % (len(packed), len(raw), len(css), len(js),
             100.0 * (1 - len(packed) / float(len(raw))), len(wiki),
             (len(packed) + len(wiki)) / 1024.0, "" if changed else ", unchanged"))


main()
