# Updates

[Wiki index](../../WIKI.md)

The board carries two application partitions. An update writes the spare one and
reboots into it, and **the data partition is not touched**, so fixtures, scenes,
groups, labels and network settings come back exactly as they were.

That works because the web UI lives inside the firmware rather than on the
filesystem. One artefact, always in step with the code that serves it, and a
LittleFS holding nothing but settings nobody wants overwritten.

## From a file

**Settings**, **Config**, **Firmware**. Pick a `.bin` and press **Install**.

The file is `.pio/build/<environment>/firmware.bin` after a local build, or the
matching asset from a release.

The progress bar is the upload; the board writes as the bytes arrive. About a
megabyte over WiFi takes some 13 seconds, and the reboot another 4. DMX output
stops for the duration, so do this with the rig dark rather than mid-show.

Two guards on the way in: a filename mentioning `littlefs` or `spiffs` is refused
outright, and a first byte that is not `0xE9` stops the write. An image picked by
mistake is better found now than on the next boot.

## From a GitHub release

**Check GitHub** on the same panel compares the latest release with the running
version, and offers to install the asset matching this build. One press: the
board downloads it, checks it and reboots into it.

### Why the browser reads and the board downloads

The work is split, and not arbitrarily. **GitHub serves release assets with no
`Access-Control-Allow-Origin` header**, on the plain download URL and on the API
asset endpoint alike. A page served from the board therefore cannot read those
bytes however it asks: the file can reach your Downloads folder but never the
script. That is a GitHub decision and nothing in this firmware can talk it round.

What the browser *can* read is `api.github.com`, which does allow cross-origin
reads and publishes a **sha256 digest for every asset**. So:

1. The browser reads the release over a connection its own certificate store
   verified, and takes the digest.
2. It hands the board the download URL and that digest.
3. The board downloads over TLS **without checking the certificate chain**,
   hashing every byte as it arrives.
4. If the hash does not match, the download is thrown away.

Integrity comes from the hash rather than from the transport, which is the whole
point: substituting firmware would mean producing bytes that match a hash
obtained over a channel the attacker was not on. So the board needs **no
certificate bundle in flash**, and there is no root to expire and strand it.

Two rules fall out of that and are worth knowing. The digest is **not optional**:
a release that published none falls back to the manual path rather than
installing something unchecked. And the board will only fetch from `github.com`
or `githubusercontent.com`, so holding the API key does not turn it into a
general-purpose downloader.

The download runs from the main loop a couple of kilobytes at a time, so the page
stays responsive and DMX keeps going out while it works. Progress is polled from
`/api/ota/status`.

### The ESP8266 does not do this

It has neither the flash nor the RAM for a TLS client. **Check GitHub** still
compares versions there and still tells you what is available; it just hands over
a download link for the file picker instead of fetching. `/api/ota/status`
reports `can_fetch` so the page knows which of the two it is talking to.

## What is in a release

One image per build, named for its target:

| Asset | Board and build |
|---|---|
| `firmware-s2mini.bin` | ESP32-S2, full UI |
| `firmware-s2mini-headless.bin` | ESP32-S2, API only |
| `firmware-d1mini.bin` | ESP8266, full UI. **Beta** |
| `firmware-d1mini-headless.bin` | ESP8266, API only. **Beta** |

`/api/ota/status` reports which one this board wants, and the update button
refuses anything else rather than letting you install an ESP8266 image on an
ESP32.

These are application images. A board being flashed for the **first** time still
goes over USB with `pio run -e s2mini -t upload`, which writes the bootloader and
the partition table too.

## The partition table changed in 0.4.0

The ESP32 targets moved off the stock layout onto
[partitions_dmx.csv](../../partitions_dmx.csv): **1.75 MB per application slot**
instead of 1.25 MB, taken out of a filesystem that holds a few kilobytes of JSON
and had been given 1.4 MB. Giving the board its own HTTPS client cost 152 KB, and
the old slot was at 83.5% before it.

**A partition table is not an over-the-air change.** An update writes an
application image and nothing else, so a board that was flashed on the old layout
keeps the old layout, runs the new firmware perfectly well inside the smaller
slot, and simply never gets the extra room. Nothing breaks until an image grows
past 1.25 MB, at which point over-the-air updates to those boards start failing
for want of space.

To actually move a board across, flash it over USB. That rewrites the table, which
moves the filesystem to a new offset, which means **the board comes back with its
settings formatted away**. So:

1. **Settings**, **Config**, **Save .json**.
2. `pio run -e s2mini -t upload`.
3. **Load .json** to put it back.

## Cutting a release

1. Change `FW_VERSION` in [dev.env](../../dev.env). That is the only place it
   lives: the firmware, the update check and the release workflow all read it.
2. Commit and push.
3. Run the **firmware** workflow by hand, from the repository's Actions tab.

That is the whole of it. Nobody writes a tag, and no push produces a release on
its own.

[.github/workflows/firmware.yml](../../.github/workflows/firmware.yml) has no
trigger but `workflow_dispatch`, and refuses to run for anyone but the repository
owner. When the owner starts it, it reads `FW_VERSION`, builds all four
environments, checks each image actually reports that version, tags the commit it
built as `DD-MM-YYYY-VX.Y.Z` and publishes the four images under that tag.

Two things follow from the shape of it. The tag cannot disagree with the firmware
inside the release, because the workflow composes it from the same line the
firmware compiles: a release whose tag claimed a version the board did not report
after installing would offer itself for ever. And the date in front means a
rebuild of the same version is a visibly different release, which is the useful
question about a binary that carries no source change. The update check reads the
version out of the tail of the tag and ignores the date.

Releasing the same version twice on one day is refused rather than quietly
attached to the existing tag. Bump `FW_VERSION` instead.

## The ESP8266

Its update path is written and has never been tried. Treat over-the-air updates
there as untested, along with everything else on that target.

Space is not the obstacle, though this page used to say it was. The ESP8266 build
links against the `4m1m` layout, which gives sketch and over-the-air staging a
shared 3 MB with a 1000 KB filesystem above it. A 545 KB image therefore leaves
2.48 MB free, room for the update several times over. It works differently from
the ESP32, which keeps two fixed application partitions and switches between them:
here the new image is staged in free space and copied down over the old one at the
next boot. Same outcome, and the same rule that a half-written update cannot be
booted into.

## If an update goes wrong

The board only switches partitions after the whole image has been written and
verified, so an upload that fails halfway leaves the running firmware alone.
Reload the page and try again.

A board that does come back broken is recovered over USB with
`pio run -e s2mini -t upload`, which does not need the network or a working web
server. Keep a config backup (**Settings**, **Config**, **Save .json**) if the
settings matter, though an ordinary update does not touch them.
