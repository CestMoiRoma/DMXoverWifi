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
version, and offers to install the asset matching this build.

**The browser fetches the release, not the board.** That is deliberate: the board
would need a bundle of certificate authorities in flash, which goes stale and
costs 65 KB of a partition already at 84%, and skipping the check instead would
mean accepting firmware from anything able to sit in the middle of that
connection. Your laptop already has a current set of authorities and keeps them
current, so it does the trusting and the board only ever accepts bytes from the
LAN.

The cost is stated rather than hidden: **a board with no laptop nearby cannot
update itself.** Where the browser refuses to read the asset cross-origin, the
page hands over a direct link and the file goes in through the picker instead.

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

## Cutting a release

1. Change `FW_VERSION` in [dev.env](../../dev.env). That is the only place it
   lives: the firmware, the update check and the release workflow all read it.
2. Commit, then tag `vX.Y.Z` and push the tag.

[.github/workflows/firmware.yml](../../.github/workflows/firmware.yml) builds all
four environments on every push. On a `v*` tag it also checks the tag agrees with
`dev.env` and publishes the four images. A tag that disagreed would leave every
board thinking an update was available for ever, since the version reported after
installing would still be the old one.

## The ESP8266

Its update path is written and has never been tried. It also has no room for two
full application images unless the flash layout is changed. Treat over-the-air
updates there as untested, along with everything else on that target.

## If an update goes wrong

The board only switches partitions after the whole image has been written and
verified, so an upload that fails halfway leaves the running firmware alone.
Reload the page and try again.

A board that does come back broken is recovered over USB with
`pio run -e s2mini -t upload`, which does not need the network or a working web
server. Keep a config backup (**Settings**, **Config**, **Save .json**) if the
settings matter, though an ordinary update does not touch them.
