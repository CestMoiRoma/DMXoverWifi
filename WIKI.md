# DMX over WiFi: wiki

One page per subject. Start with [README.md](README.md) for what the project is,
which boards it runs on and how to flash one; this is the reference for using it
afterwards.

## Building a rig

| Page | What is in it |
|---|---|
| [Wiring](docs/wiki/wiring.md) | The MAX485 circuit, the XLR pinout, the DE/RE pin and when it needs a GPIO |
| [Lite fixtures](docs/wiki/lite-devices.md) | The plain fixture: channels, types, addressing, categories and labels |
| [EZ fixtures](docs/wiki/ez-devices.md) | The eight control cards, their roles, their settings and their presets |
| [Scenes](docs/wiki/scenes.md) | Named looks, captured from the rig and recalled from anywhere |
| [Groups](docs/wiki/groups.md) | One control driving the same channel across many fixtures |

## Driving it

| Page | What is in it |
|---|---|
| [Serial console](docs/wiki/serial-console.md) | Every command, and the binary protocol for anything driving faster than a person |
| [HTTP API](docs/wiki/http-api.md) | Every route, the access rules and the API key |
| [WebSocket](docs/wiki/websocket.md) | The live channel link on port 81, and what the UI falls back to |
| [MQTT and Home Assistant](docs/wiki/mqtt.md) | Discovery, topics, scenes, the emergency stop entity, and reading the status line |

## Looking after it

| Page | What is in it |
|---|---|
| [Configuration](docs/wiki/configuration.md) | The files on the board, `.env`, `dev.env`, backups and the save-guard |
| [Updates](docs/wiki/updates.md) | Installing firmware over the network, releases, and what survives |
| [Timing and latency](docs/wiki/timing.md) | What is dependable here and what is not. Read this before trusting it with a show |
| [Troubleshooting](docs/wiki/troubleshooting.md) | The failures that have actually happened, and what each one meant |

## The short version

- A fixture is a **start channel** plus channels at **offsets**, so the address
  driven is `start_channel + offset - 1`. Readdress the fixture and everything
  follows.
- Scenes and groups reference channels by **uid**, never by address, so editing
  or readdressing a fixture does not quietly point them at the wrong lamp.
- The web UI is trusted because it is served by the board. **Everything else
  needs the API key**, including the websocket, which has no such exemption.
- Timing is best effort. Fine for levels, looks and colour. Not for cues that
  have to land on a beat, and not for anything safety related.
