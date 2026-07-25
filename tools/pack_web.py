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

    html = html.replace(LINK_TAG, "<style>\n%s\n</style>" % css)
    html = html.replace(SCRIPT_TAG, "<script>\n%s\n</script>" % js)

    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(html)

    # The UI links to a local copy of the wiki, kept in step with the real one
    # here so the two cannot drift.
    wiki = os.path.join(project_dir, "WIKI.md")
    if os.path.isfile(wiki):
        shutil.copyfile(wiki, os.path.join(out_dir, "wiki.md"))

    print("pack_web: index.html %d bytes (css %d, js %d) -> %s"
          % (len(html), len(css), len(js), os.path.relpath(out_dir, project_dir)))


main()
