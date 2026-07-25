"""Pack the web UI into a single HTML file for the LittleFS image.

PlatformIO runs this as a `pre:` extra script, so it fires before `buildfs`
packs $PROJECT_DATA_DIR. It reads the editable sources in web/ and writes one
self-contained page to fsdata/www/index.html, with the stylesheet and the script
spliced in where their tags sit.

Why bother: the board answers one HTTP client at a time, and a browser loading
the page opens a connection for it and then two more, in a burst, for the
stylesheet and the script. A subresource that loses that race takes the styling
of the whole UI with it. One file means one request, and nothing left to race.

Doing it here rather than at send time keeps the firmware trivial: it streams a
static file with a real Content-Length instead of splicing three files into a
chunked response on every load.

Sources stay separate and are edited normally. fsdata/ is build output and is
gitignored in full, which also stops the served copy of the wiki drifting from
WIKI.md, since that copy is made here too.
"""

import gzip
import json
import os
import shutil

Import("env")  # noqa: F821  (injected by PlatformIO/SCons)

LINK_TAG = '<link rel="stylesheet" href="/style.css">'
SCRIPT_TAG = '<script src="/app.js"></script>'


def read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def main():
    project_dir = env.subst("$PROJECT_DIR")  # noqa: F821
    data_dir = env.subst("$PROJECT_DATA_DIR")  # noqa: F821
    web_dir = os.path.join(project_dir, "web")
    out_dir = os.path.join(data_dir, "www")

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

    # Start clean, so a file this script no longer produces cannot linger in the
    # image and be served in place of the one it does.
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)

    # Shipped gzipped, and only gzipped. The board writes the whole response
    # synchronously, so its main loop is stalled for as long as the transfer
    # takes and any connection arriving in that window queues behind it. Sending
    # a quarter of the bytes shortens that stall by the same factor, which
    # matters far more here than the flash it saves.
    raw = html.encode("utf-8")
    packed = os.path.join(out_dir, "index.html.gz")
    with gzip.GzipFile(filename="", mode="wb", fileobj=open(packed, "wb"), mtime=0) as gz:
        gz.write(raw)
    compressed = os.path.getsize(packed)

    # The UI links to a local copy of the wiki, kept in step with the real one
    # here so the two cannot drift.
    wiki = os.path.join(project_dir, "WIKI.md")
    if os.path.isfile(wiki):
        shutil.copyfile(wiki, os.path.join(out_dir, "wiki.md"))

    print("pack_web: index.html.gz %d bytes from %d (css %d, js %d), %.0f%% smaller -> %s"
          % (compressed, len(raw), len(css), len(js),
             100.0 * (1 - compressed / float(len(raw))), os.path.relpath(out_dir, project_dir)))


main()
