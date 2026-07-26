# HTTP API

[Wiki index](../../WIKI.md)

Port 80, alongside the UI. JSON in, JSON out.

A headless build (`WITH_WEBUI=0`) drops the page route and keeps every `/api/*`
route, so the box stays fully controllable with no served UI.

## Access control

The served web UI is trusted and needs no key. Every other caller needs two
things: the **HTTP API module** switched on, and a valid key in an `X-API-Key`
header or an `api_key` query parameter.

| Caller | HTTP API on | HTTP API off |
|---|---|---|
| The UI served by the board | allowed | allowed |
| Anything else, right key | allowed | `403` |
| Anything else, wrong or missing key | `401` | `403` |

"The UI" means a request whose `Origin` or `Referer` points back at this board.
Browsers set those and will not let a page forge them, so it does stop a random
web page from driving your rig. It is **not** a defence against a hand-rolled
client: `curl` sets any header it likes. Treat the key, not the origin check, as
the thing gating scripted access, and treat the whole arrangement as suited to a
trusted LAN rather than the open internet.

The key is 64 hex characters, minted on first boot and stored in `api.json`. It
is never seeded from `.env`, so flashing one checkout onto several boards does
not give them all the same key. Regenerating it under **Settings**, **API**
invalidates the old one immediately.

```bash
curl -H "X-API-Key: <key>" http://esp-dmx.local/api/devices
```

## Pages

| Method | Route | |
|---|---|---|
| `GET` | `/` and `/index.html` | The whole UI, one gzipped file, served from flash |
| `GET` | `/favicon.ico` | `204`, so an unprompted browser request costs one short answer |

The wiki is not served by the board. It is on GitHub, where it is searchable and
current; `/api/info` carries the link.

## Fixtures

| Method | Route | Body and result |
|---|---|---|
| `GET` | `/api/devices` | Every fixture with its channels, each carrying its live `value` |
| `POST` | `/api/devices` | `{"name":…,"start_channel":…,"category":…,"channels":[{"offset":…,"name":…,"type":…}],"labels":[…],"card":…,"ez":{…}}`, returns the created fixture |
| `PUT` | `/api/devices/<id>` | Any subset of the same keys, returns the updated fixture or `404` |
| `DELETE` | `/api/devices/<id>` | `{"ok":true}`. Also drops the scene steps and group members that pointed at its channels, and withdraws its Home Assistant entities |
| `POST` | `/api/devices/<id>/channel/<offset>` | `{"value":0-255}` |
| `POST` | `/api/devices/<id>/burst` | `{"offset":…,"value":…,"ms":…}`. Drives a channel for a fixed time, then returns it to zero. Capped at 30 s, and the timer lives on the board so a browser that disappears cannot leave a smoke machine running |
| `POST` | `/api/channel/<uid>` | `{"value":0-255}`. Drives a channel by uid, which is how every EZ widget writes |
| `POST` | `/api/blackout` | Every channel to zero, in one request rather than a loop of writes from a browser that might not finish it |

Values are clamped to 0 through 255 and a missing `value` is treated as 0.

## Scenes and groups

| Method | Route | |
|---|---|---|
| `GET` `POST` | `/api/scenes` | List, or create from `{"name":…,"steps":[{"uid":…,"value":…}]}` |
| `PUT` `DELETE` | `/api/scenes/<id>` | Update or remove |
| `POST` | `/api/scenes/<id>/play` | `{"ok":true,"missing":[…]}`, where `missing` names uids this board does not carry |
| `GET` `POST` | `/api/groups` | List, or create |
| `PUT` `DELETE` | `/api/groups/<id>` | Update or remove |
| `POST` | `/api/groups/<id>/apply` | `{"role":…,"value":…}`. Omit `role` for a lite group |

See [Scenes](scenes.md) and [Groups](groups.md).

## Network

| Method | Route | |
|---|---|---|
| `GET` | `/api/wifi` | Saved networks, highest priority first, each with its own addressing |
| `POST` | `/api/wifi` | `{"ssid":…,"password":…,"priority":…}`, adds or updates one entry without connecting |
| `PUT` | `/api/wifi` | Replaces the whole list from an ordered array. The order **is** the priority: first is highest |
| `DELETE` | `/api/wifi/<ssid>` | Returns the updated list |
| `GET` | `/api/wifi/scan` | Visible networks. Asynchronous: the first call starts a scan and answers `{"scanning":true}`, later calls return the result |
| `GET` `POST` | `/api/ethernet` | W5500 config and link status. **Beta, never run against the chip** |

On `PUT`, an entry with **no** `password` key keeps the one it had, so reordering
the list or editing an address cannot wipe a credential the caller never
mentioned. An explicit `"password": ""` still sets an open network.

Each entry carries its own addressing, since the same rig meets DHCP at one venue
and a fixed address at the next:

```json
{
  "ssid": "Venue WiFi",
  "password": "…",
  "ip_mode": "static",
  "static_ip": "192.168.1.100",
  "static_netmask": "255.255.255.0",
  "static_gateway": "192.168.1.1",
  "static_dns": "1.1.1.1"
}
```

A `static` entry whose address or gateway does not parse falls back to DHCP
rather than dropping the board off the network.

## MQTT

| Method | Route | |
|---|---|---|
| `GET` | `/api/mqtt` | The config, plus a `status` block |
| `POST` | `/api/mqtt` | Merge the config, restart the client, and answer with the result of the attempt it just made |
| `GET` | `/api/mqtt/status` | Connection state on its own, with no passwords, cheap enough to poll |
| `POST` | `/api/mqtt/connect` | An attempt now, jumping the backoff, answering with the outcome |

See [MQTT](mqtt.md) for what the status block says.

## Firmware

| Method | Route | |
|---|---|---|
| `GET` | `/api/ota/status` | Running version, build target, and the release asset name that fits this board |
| `POST` | `/api/ota` | `multipart/form-data` with the firmware `.bin`. Answers, then reboots |

See [Updates](updates.md).

## Configuration and system

| Method | Route | |
|---|---|---|
| `GET` | `/api/bootstrap` | Everything the UI needs at boot, in one request. It used to make five, and on a server handling one client at a time each extra connection in that opening burst was another chance to be refused |
| `GET` | `/api/info` | Version, board, hostname, websocket port, uptime, free heap, `loop_per_sec`, `loop_max_us`, author and repository |
| `GET` | `/api/categories` | The fixed category vocabulary |
| `GET` `POST` | `/api/labels`, `PUT` `DELETE` `/api/labels/<id>` | Labels. Deleting strips the id from every fixture that carried it |
| `GET` `POST` | `/api/system` | `system.json`: pins, hostname, hotspot, save-guard, the WiFi switch |
| `GET` `POST` | `/api/mesh` | `mesh.json`. Work in progress, stored only |
| `GET` `POST` | `/api/modules` | The module switches. `GET` returns `api_key` too, but only to the UI |
| `POST` | `/api/modules/key` | Mints a fresh key and revokes the old one |
| `GET` `POST` | `/api/config` | The whole live config as `.json`, and restoring one. Sections absent from the body are left alone |
| `GET` | `/api/export-env` | The same config as a `.env` file |
| `POST` | `/api/reboot` | Answers, then restarts |

`POST` merges, so a single key is a valid body.

> The `.json` from `/api/config` carries every WiFi and MQTT password and the API
> key in clear text. It is a secret. Treat it like one.

## Examples

```bash
KEY=<your key>
BOARD=http://esp-dmx.local

curl -H "X-API-Key: $KEY" $BOARD/api/devices

curl -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
     -d '{"value":128}' $BOARD/api/devices/dev-a1b2c3/channel/1

curl -X POST -H "X-API-Key: $KEY" $BOARD/api/blackout

curl -X POST -H "X-API-Key: $KEY" $BOARD/api/scenes/scn-a8d2f9/play
```
