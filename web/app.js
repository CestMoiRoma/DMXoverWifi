async function api(path, method, body) {
  const opts = { method: method || "GET" };
  if (body !== undefined) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  return res.json();
}

function el(tag, attrs, children) {
  const node = document.createElement(tag);
  for (const key in attrs || {}) {
    if (key.startsWith("on")) node[key] = attrs[key];
    else node.setAttribute(key, attrs[key]);
  }
  (children || []).forEach((child) => {
    if (typeof child === "string") node.appendChild(document.createTextNode(child));
    else if (child) node.appendChild(child);
  });
  return node;
}

// Icons are inline SVG rather than a font or sprite sheet, so the UI stays a
// single self-contained file set with no extra request.
const SVG_NS = "http://www.w3.org/2000/svg";

function svgIcon(paths) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  (Array.isArray(paths) ? paths : [paths]).forEach((d) => {
    const p = document.createElementNS(SVG_NS, "path");
    p.setAttribute("d", d);
    svg.appendChild(p);
  });
  return svg;
}

const ICON_TRASH = ["M4 7h16", "M9 7V4h6v3", "M6 7l1 13h10l1-13", "M10 11v6", "M14 11v6"];
const ICON_GEAR = [
  "M12 15.5a3.5 3.5 0 100-7 3.5 3.5 0 000 7z",
  "M19.4 13a1.7 1.7 0 00.4 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.4 1.7 1.7 0 00-1 1.5V19a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.4l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.4-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.4-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.4H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.4l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.4 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z",
];
const ICON_PLUS = ["M12 5v14", "M5 12h14"];
const ICON_EXPORT = ["M12 19V5", "M5 12l7-7 7 7"];

function iconButton(paths, title, onClick) {
  const btn = el("button", { type: "button", class: "icon-btn", title: title, "aria-label": title });
  btn.appendChild(svgIcon(paths));
  btn.addEventListener("click", onClick);
  return btn;
}

// ---- live channel transport ----
//
// A slider dragged across its travel emits values far faster than one HTTP
// request each can carry, so writes are coalesced per channel and flushed on a
// short timer. The socket is preferred when it is up; when the module is off or
// the connection drops, the exact same calls fall back to POST and nothing
// upstream has to care which one is in use.

const REALTIME_INTERVAL_MS = 30;
const WS_RETRY_MIN_MS = 3000;
const WS_RETRY_MAX_MS = 60000;

let wsRetryDelay = WS_RETRY_MIN_MS;
let ws = null;
let apiKey = null;
let pendingValues = new Map();
let flushTimer = null;
let channelControls = new Map();

function transportName() {
  return ws && ws.readyState === WebSocket.OPEN ? "websocket" : "http";
}

function flushPendingValues() {
  const items = Array.from(pendingValues.values());
  pendingValues.clear();
  const live = ws && ws.readyState === WebSocket.OPEN;
  items.forEach((item) => {
    if (live) {
      ws.send(JSON.stringify({ t: "set", d: item.deviceId, o: item.offset, v: item.value }));
    } else {
      api("/api/devices/" + item.deviceId + "/channel/" + item.offset, "POST", {
        value: item.value,
      });
    }
  });
}

// Coalescing by channel means a fast drag costs one message per channel per
// interval rather than one per pixel, and the last value always wins.
function sendValue(deviceId, offset, value, immediate) {
  // Write through immediately, whatever the throttle then does with the wire
  // traffic. A widget that reads the value back must see what it just asked
  // for, not what the last fetch happened to contain.
  cacheChannelValue(deviceId, offset, value);
  lastLocalWrite.set(deviceId + ":" + offset, Date.now());
  pendingValues.set(deviceId + ":" + offset, { deviceId: deviceId, offset: offset, value: value });
  if (immediate) {
    if (flushTimer) {
      clearTimeout(flushTimer);
      flushTimer = null;
    }
    flushPendingValues();
    return;
  }
  if (!flushTimer) {
    flushTimer = setTimeout(() => {
      flushTimer = null;
      flushPendingValues();
    }, REALTIME_INTERVAL_MS);
  }
}

// Keeps the fetched fixture list in step with what has actually been sent.
//
// Widgets that read a channel back need this. The colour wheel places its
// marker from the current values, and the joystick adds its step to them, so
// against a cache that never moved the marker snapped home on every echo and
// the joystick could never get past one step from where it started.
function cacheChannelValue(deviceId, offset, value) {
  const device = devicesCache.find((d) => d.id === deviceId);
  if (!device) return;
  const channel = (device.channels || []).find((c) => c.offset === offset);
  if (channel) channel.value = value;
}

// How long after writing a channel ourselves we stop believing what comes back
// for it. The board echoes every change, including our own, and that echo
// arrives at least one round trip late. While a joystick is held the value has
// already moved on by then, so accepting the echo would put the older value
// back and the fixture would crawl backwards against the stick.
//
// Long enough to cover a round trip on a slow link, short enough that letting go
// hands control back to the other browsers almost at once.
const ECHO_TRUST_DELAY_MS = 500;
let lastLocalWrite = new Map();

function applyRemoteValue(deviceId, offset, value) {
  const key = deviceId + ":" + offset;
  const wroteAt = lastLocalWrite.get(key);
  if (wroteAt !== undefined && Date.now() - wroteAt < ECHO_TRUST_DELAY_MS) return;

  cacheChannelValue(deviceId, offset, value);
  const control = channelControls.get(key);
  // Skip the control currently under the pointer: overwriting it mid-drag would
  // fight the person holding it.
  if (!control || control.dragging) return;
  control.apply(value);
}

function connectWebSocket() {
  if (!boardInfo.websocket_enabled || !apiKey) return;
  const port = boardInfo.websocket_port || 81;
  const url = "ws://" + location.hostname + ":" + port + "/?api_key=" + encodeURIComponent(apiKey);
  try {
    ws = new WebSocket(url);
  } catch (e) {
    ws = null;
    return;
  }
  ws.addEventListener("message", (event) => {
    let frame;
    try {
      frame = JSON.parse(event.data);
    } catch (e) {
      return;
    }
    if (frame.t === "val") applyRemoteValue(frame.d, frame.o, frame.v);
  });
  ws.addEventListener("open", () => {
    wsRetryDelay = WS_RETRY_MIN_MS;
  });
  ws.addEventListener("close", () => {
    ws = null;
    // The board reboots, the venue's AP blinks: keep trying rather than silently
    // degrading to HTTP for the rest of the session. But back off while doing
    // it. A fixed short retry turns a board that is refusing sockets into a
    // connection storm, which is exactly when it can least afford one.
    setTimeout(connectWebSocket, wsRetryDelay);
    wsRetryDelay = Math.min(wsRetryDelay * 2, WS_RETRY_MAX_MS);
  });
  ws.addEventListener("error", () => {
    if (ws) ws.close();
  });
}

// ---- shared state ----

let labelsCache = [];
let categoriesCache = [];
let activeFilters = new Set();
let activeCategories = new Set();
let searchTerm = "";
let sortMode = "az";
let boardInfo = {};

// Saves a fixture as a file the board can take back. The shape is deliberately
// the same object /api/devices returns and /api/devices accepts, so a saved
// fixture is a fragment of a full config backup rather than its own format.
// The live channel values are stripped: this describes a fixture, not a look.
function downloadFixture(device) {
  const copy = JSON.parse(JSON.stringify(device));
  delete copy.id;  // the board mints a fresh one on import
  (copy.channels || []).forEach((c) => delete c.value);
  const blob = new Blob([JSON.stringify(copy, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = el("a", { href: url, download: safeFileName(device.name) + ".json" });
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function safeFileName(name) {
  return (name || "fixture").replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "fixture";
}

function labelById(id) {
  return labelsCache.find((l) => l.id === id);
}

function categoryName(id) {
  const found = categoriesCache.find((c) => c.id === id);
  return found ? found.name : id;
}

// ---- navigation ----

function switchView(name) {
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
  document.getElementById("view-" + name).classList.add("active");
  document.querySelector('.nav-btn[data-view="' + name + '"]').classList.add("active");
  // The add button belongs to the fixtures view alone.
  document.getElementById("add-device-fab").hidden = name !== "devices";
  if (name === "devices") renderDevices();
  if (name === "settings") renderSettings();
}

document.querySelectorAll(".nav-btn").forEach((btn) => {
  btn.addEventListener("click", () => switchView(btn.dataset.view));
});

function switchPanel(name) {
  document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
  document.querySelectorAll(".subnav-btn").forEach((b) => b.classList.remove("active"));
  document.getElementById("panel-" + name).classList.add("active");
  document.querySelector('.subnav-btn[data-panel="' + name + '"]').classList.add("active");
  if (name === "labels") renderLabelList();
  if (name === "info") renderInfo();
}

document.querySelectorAll(".subnav-btn").forEach((btn) => {
  btn.addEventListener("click", () => switchPanel(btn.dataset.panel));
});

// ---- devices view: fixtures plus their live controls ----

function renderFilterChips(devices) {
  const bar = document.getElementById("label-filters");
  bar.innerHTML = "";
  if (labelsCache.length === 0) return;

  const all = el("button", { type: "button", class: "chip" + (activeFilters.size ? "" : " on") }, [
    "All",
  ]);
  all.addEventListener("click", () => {
    activeFilters.clear();
    redrawDevices();
  });
  bar.appendChild(all);

  labelsCache.forEach((label) => {
    const on = activeFilters.has(label.id);
    const count = devices.filter((d) => (d.labels || []).indexOf(label.id) !== -1).length;
    const chip = el("button", { type: "button", class: "chip" + (on ? " on" : "") }, [
      label.name + " (" + count + ")",
    ]);
    chip.style.setProperty("--chip", label.color);
    chip.addEventListener("click", () => {
      if (on) activeFilters.delete(label.id);
      else activeFilters.add(label.id);
      renderDevices();
    });
    bar.appendChild(chip);
  });
}

function renderCategoryChips(devices) {
  const bar = document.getElementById("category-filters");
  bar.innerHTML = "";
  // Only offer categories something is actually filed under, so the bar does not
  // list eleven kinds of machine for a rig of three PARs.
  const present = categoriesCache.filter((c) => devices.some((d) => d.category === c.id));
  if (present.length < 2) return;

  const all = el(
    "button",
    { type: "button", class: "chip cat" + (activeCategories.size ? "" : " on") },
    ["All types"]
  );
  all.addEventListener("click", () => {
    activeCategories.clear();
    redrawDevices();
  });
  bar.appendChild(all);

  present.forEach((cat) => {
    const on = activeCategories.has(cat.id);
    const count = devices.filter((d) => d.category === cat.id).length;
    const chip = el("button", { type: "button", class: "chip cat" + (on ? " on" : "") }, [
      cat.name + " (" + count + ")",
    ]);
    chip.addEventListener("click", () => {
      if (on) activeCategories.delete(cat.id);
      else activeCategories.add(cat.id);
      redrawDevices();
    });
    bar.appendChild(chip);
  });
}

// Categories and labels are independent facets: a fixture must satisfy both
// bars, but within one bar the chips widen the selection rather than
// intersecting. Picking Face and Contre shows both, picking PAR on top of them
// narrows that to the PARs among them. Search narrows further again.
function matchesFilters(device) {
  if (activeCategories.size && !activeCategories.has(device.category)) return false;
  if (activeFilters.size && !(device.labels || []).some((id) => activeFilters.has(id))) return false;
  if (!searchTerm) return true;
  // One box across all three, because looking for "face" should find the label
  // and looking for "lyre" should find the category, without first asking which
  // kind of thing the word is.
  const haystack = [
    device.name,
    categoryName(device.category),
    ...(device.labels || []).map((id) => (labelById(id) || {}).name || ""),
  ]
    .join(" ")
    .toLowerCase();
  return haystack.indexOf(searchTerm) !== -1;
}

function sortDevices(devices) {
  const byName = (a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
  const sorted = devices.slice();
  if (sortMode === "az") sorted.sort(byName);
  else if (sortMode === "za") sorted.sort((a, b) => byName(b, a));
  else if (sortMode === "channel") sorted.sort((a, b) => a.start_channel - b.start_channel);
  else if (sortMode === "category") {
    sorted.sort((a, b) => {
      const byCat = categoryName(a.category).localeCompare(categoryName(b.category));
      return byCat !== 0 ? byCat : byName(a, b);
    });
  }
  return sorted;
}

function channelControl(device, channel) {
  const row = el("div", { class: "channel-control" });
  row.appendChild(el("label", {}, [channel.name]));
  const key = device.id + ":" + channel.offset;
  const send = (value, immediate) => sendValue(device.id, channel.offset, value, immediate);

  const current = typeof channel.value === "number" ? channel.value : 0;

  if (channel.type === "slider") {
    const input = el("input", { type: "range", min: "0", max: "255", value: String(current) });
    const output = el("span", {}, [String(current)]);
    const state = { dragging: false };
    // "input" fires all through the drag, "change" once on release. Sending on
    // both is what makes the fader live, with the release guaranteeing the final
    // value lands even if it fell inside a throttle window.
    input.addEventListener("input", () => {
      state.dragging = true;
      output.textContent = input.value;
      send(parseInt(input.value, 10), false);
    });
    input.addEventListener("change", () => {
      state.dragging = false;
      send(parseInt(input.value, 10), true);
    });
    state.apply = (value) => {
      input.value = String(value);
      output.textContent = String(value);
    };
    channelControls.set(key, state);
    row.appendChild(input);
    row.appendChild(output);
  } else if (channel.type === "button-momentary") {
    const button = el("button", { class: "channel-btn momentary" }, ["Hold"]);
    // Press and release are single events, so they go out immediately rather
    // than waiting on the throttle: a blackout should not be 30 ms late.
    const press = (e) => {
      if (e) e.preventDefault();
      send(255, true);
    };
    const release = (e) => {
      if (e) e.preventDefault();
      send(0, true);
    };
    button.addEventListener("mousedown", press);
    button.addEventListener("mouseup", release);
    button.addEventListener("mouseleave", release);
    button.addEventListener("touchstart", press);
    button.addEventListener("touchend", release);
    button.addEventListener("touchcancel", release);
    row.appendChild(button);
  } else if (channel.type === "button-switch") {
    const button = el("button", { class: "channel-btn switch" }, [current ? "On" : "Off"]);
    let on = current > 0;
    button.classList.toggle("on", on);
    const paint = (value) => {
      on = value > 0;
      button.textContent = on ? "On" : "Off";
      button.classList.toggle("on", on);
    };
    button.addEventListener("click", () => {
      paint(on ? 0 : 255);
      send(on ? 255 : 0, true);
    });
    channelControls.set(key, { apply: paint });
    row.appendChild(button);
  } else {
    const button = el("button", { class: "channel-btn" }, ["Trigger"]);
    button.addEventListener("click", () => send(255, true));
    row.appendChild(button);
  }
  return row;
}

function deviceCard(device) {
  const card = el("div", { class: "device-card" });

  const head = el("div", { class: "card-head" });
  const title = el("div", { class: "card-title" }, [
    el("h3", {}, [device.name]),
    el("span", { class: "card-sub" }, [
      categoryName(device.category) + " · start ch. " + device.start_channel,
    ]),
  ]);
  head.appendChild(title);

  const actions = el("div", { class: "card-actions" });
  actions.appendChild(
    iconButton(ICON_EXPORT, "Save as JSON", () => downloadFixture(device))
  );
  // An EZ fixture edits through the role dialog it was built with; a lite one
  // through the plain channel list.
  actions.appendChild(
    iconButton(ICON_GEAR, "Edit", () =>
      device.card === "ez" ? openEzModal(device, device.start_channel) : openDeviceModal(device, device.id)
    )
  );
  actions.appendChild(
    iconButton(ICON_PLUS, "Duplicate", () => {
      const span = device.channels.reduce((max, c) => Math.max(max, c.offset), 1);
      openDeviceModal(
        {
          name: device.name + " copy",
          category: device.category,
          start_channel: Math.min(device.start_channel + span, 512),
          channels: device.channels,
          labels: device.labels,
        },
        null
      );
    })
  );
  actions.appendChild(
    iconButton(ICON_TRASH, "Delete", async () => {
      if (!confirm('Delete "' + device.name + '"?')) return;
      await api("/api/devices/" + device.id, "DELETE");
      renderDevices();
    })
  );
  head.appendChild(actions);
  card.appendChild(head);

  const tags = (device.labels || []).map(labelById).filter(Boolean);
  if (tags.length) {
    const bar = el("div", { class: "chip-bar tiny" });
    tags.forEach((label) => {
      const chip = el("span", { class: "chip static" }, [label.name]);
      chip.style.setProperty("--chip", label.color);
      bar.appendChild(chip);
    });
    card.appendChild(bar);
  }

  const isEz = device.card === "ez" && device.ez && device.ez.kind;
  const peeking = litePeek.has(device.id);

  if (isEz && !peeking) {
    ezCardBody(device).forEach((part) => card.appendChild(part));
  } else {
    device.channels.forEach((channel) => card.appendChild(channelControl(device, channel)));
  }

  if (isEz) {
    const toggle = el("button", { type: "button", class: "secondary small lite-toggle" }, [
      peeking ? "Back to the widget" : "Show raw channels",
    ]);
    toggle.addEventListener("click", () => {
      if (peeking) litePeek.delete(device.id);
      else litePeek.add(device.id);
      redrawDevices();
    });
    card.appendChild(toggle);
  }
  return card;
}

let devicesCache = [];

// Typing in the search box or changing the order only rearranges what is
// already on screen, so it redraws from the cache. Refetching per keystroke
// would put a request on the board for every letter.
async function renderDevices() {
  labelsCache = await api("/api/labels");
  if (categoriesCache.length === 0) categoriesCache = await api("/api/categories");
  devicesCache = await api("/api/devices");
  redrawDevices();
}

function redrawDevices() {
  const devices = devicesCache;
  renderCategoryChips(devices);
  renderFilterChips(devices);

  const grid = document.getElementById("device-grid");
  grid.innerHTML = "";
  channelControls.clear();  // the old controls just left the DOM
  if (devices.length === 0) {
    grid.appendChild(el("p", { class: "empty" }, ["No fixtures yet. Add one with the + button."]));
    return;
  }
  const shown = sortDevices(devices.filter(matchesFilters));
  if (shown.length === 0) {
    grid.appendChild(el("p", { class: "empty" }, ["No fixture matches the selected filters."]));
    return;
  }
  shown.forEach((device) => grid.appendChild(deviceCard(device)));
}

// ---- sort and filter column ----

document.getElementById("device-search").addEventListener("input", (e) => {
  searchTerm = e.target.value.trim().toLowerCase();
  redrawDevices();
});

document.getElementById("device-sort").addEventListener("change", (e) => {
  sortMode = e.target.value;
  redrawDevices();
});

document.getElementById("filters-reset").addEventListener("click", () => {
  activeFilters.clear();
  activeCategories.clear();
  searchTerm = "";
  document.getElementById("device-search").value = "";
  redrawDevices();
});

// On a phone the column would push the fixtures off the screen, so it folds
// away and this opens it. On a wide screen it is simply always there.
document.getElementById("sidebar-toggle").addEventListener("click", () => {
  document.getElementById("device-sidebar").classList.toggle("open");
});

// ---- EZ control kinds ----
//
// One table describing what each kind asks for and, by consequence, what its
// card can draw. Optional roles left blank at creation stay unbound, and the
// card simply does not grow that part: nothing is ever written to a channel the
// fixture never claimed.

const EZ_KINDS = {
  dimmer: {
    label: "Dimmer",
    category: "dimmer",
    roles: [{ key: "level", label: "Level", required: true }],
  },
  strobe: {
    label: "Strobe",
    category: "strobe",
    roles: [{ key: "strobe", label: "Strobe", required: true }],
  },
  mono: {
    label: "Light, single colour",
    category: "par",
    roles: [
      { key: "level", label: "Light", required: true },
      { key: "strobe", label: "Strobe", required: false },
    ],
  },
  rgb: {
    label: "Light, RGB",
    category: "par",
    roles: [
      { key: "red", label: "Red", required: true },
      { key: "green", label: "Green", required: true },
      { key: "blue", label: "Blue", required: true },
      { key: "dimmer", label: "Master dimmer", required: false },
      { key: "strobe", label: "Strobe", required: false },
    ],
  },
  rgbw: {
    label: "Light, RGBW",
    category: "par",
    roles: [
      { key: "red", label: "Red", required: true },
      { key: "green", label: "Green", required: true },
      { key: "blue", label: "Blue", required: true },
      { key: "white", label: "White", required: true },
      { key: "dimmer", label: "Master dimmer", required: false },
      { key: "strobe", label: "Strobe", required: false },
    ],
  },
  cwww: {
    label: "Light, cold and warm white",
    category: "par",
    roles: [
      { key: "warm", label: "Warm white", required: true },
      { key: "cold", label: "Cold white", required: true },
      { key: "dimmer", label: "Master dimmer", required: false },
      { key: "strobe", label: "Strobe", required: false },
    ],
  },
  smoke: {
    label: "Smoke machine",
    category: "smoke",
    roles: [{ key: "output", label: "Output", required: true }],
    options: [
      {
        key: "mode",
        label: "Control",
        type: "select",
        choices: [
          ["onoff", "On and off only"],
          ["slider", "Variable pump"],
        ],
        default: "onoff",
      },
      {
        key: "auto_off_s",
        label: "Auto-off after (seconds, 0 to disable)",
        type: "number",
        default: "0",
        hint: "Closes a machine left on. Bursts are always capped at 30 s by the board.",
      },
    ],
  },
  motion: {
    label: "Motion, pan and tilt",
    category: "lyre",
    roles: [
      { key: "horizontal", label: "Horizontal", required: true },
      { key: "vertical", label: "Vertical", required: true },
      { key: "horizontal_fine", label: "Horizontal fine", required: false },
      { key: "vertical_fine", label: "Vertical fine", required: false },
      { key: "speed", label: "Movement speed", required: false },
    ],
    options: [
      { key: "invert_h", label: "Invert horizontal", type: "checkbox", default: "" },
      { key: "invert_v", label: "Invert vertical", type: "checkbox", default: "" },
      {
        key: "invert_h_fine",
        label: "Invert horizontal fine",
        type: "checkbox",
        default: "",
        hint: "For a fixture whose fine channel counts the other way from its coarse one.",
      },
      { key: "invert_v_fine", label: "Invert vertical fine", type: "checkbox", default: "" },
      {
        key: "max_step",
        label: "Fastest step at full deflection",
        type: "number",
        default: "10",
        hint: "A small push always steps by one; this is what a full push reaches.",
      },
      {
        key: "arrow_step",
        label: "Keyboard arrow step",
        type: "number",
        default: "5",
        hint: "How far one arrow key press moves. Nothing to do with the stick's speed.",
      },
      {
        key: "fine_mode",
        label: "What the card's Fine position does",
        type: "select",
        choices: [
          ["both", "Movement and fine tune together"],
          ["fine", "Fine tune channels only"],
        ],
        default: "both",
      },
    ],
  },
};

function ezRoleOffset(device, role) {
  const roles = (device.ez && device.ez.roles) || {};
  const offset = roles[role];
  return typeof offset === "number" && offset > 0 ? offset : null;
}

function ezSetting(device, key, fallback) {
  const settings = (device.ez && device.ez.settings) || {};
  const value = settings[key];
  return value === undefined || value === "" ? fallback : value;
}

// ---- EZ widgets ----

const PERCENTS = [0, 25, 50, 75, 100];
const clamp255 = (v) => Math.max(0, Math.min(255, Math.round(v)));

// Fixtures the user has flipped to the raw channel view for now. Deliberately
// not persisted: it is a "show me what is really going on" toggle for one
// awkward evening, not a property of the fixture.
let litePeek = new Set();

function ezChannelValue(device, role) {
  const offset = ezRoleOffset(device, role);
  if (offset === null) return 0;
  const channel = (device.channels || []).find((c) => c.offset === offset);
  return channel && typeof channel.value === "number" ? channel.value : 0;
}

function ezSend(device, role, value, immediate) {
  const offset = ezRoleOffset(device, role);
  if (offset === null) return;
  sendValue(device.id, offset, clamp255(value), immediate);
}

// Lets a remote change repaint this widget, the same way lite controls already
// do, so two browsers watching one rig agree.
function ezRegister(device, role, apply) {
  const offset = ezRoleOffset(device, role);
  if (offset === null) return;
  channelControls.set(device.id + ":" + offset, { apply: apply });
}

function percentRow(onPick) {
  const row = el("div", { class: "pct-row" });
  PERCENTS.forEach((pct) => {
    const btn = el("button", { type: "button", class: "secondary small" }, [pct + "%"]);
    btn.addEventListener("click", () => onPick(Math.round((pct * 255) / 100)));
    row.appendChild(btn);
  });
  return row;
}

// A labelled fader plus its percentage row, bound to one role.
function roleFader(device, role, label) {
  if (ezRoleOffset(device, role) === null) return null;
  const block = el("div", { class: "ez-block" });
  const current = ezChannelValue(device, role);

  const head = el("div", { class: "ez-row" });
  head.appendChild(el("label", {}, [label]));
  const input = el("input", { type: "range", min: "0", max: "255", value: String(current) });
  const out = el("span", { class: "ez-readout" }, [String(current)]);
  head.appendChild(input);
  head.appendChild(out);

  const paint = (value) => {
    input.value = String(value);
    out.textContent = String(value);
  };
  const state = { dragging: false, apply: paint };
  input.addEventListener("input", () => {
    state.dragging = true;
    out.textContent = input.value;
    ezSend(device, role, parseInt(input.value, 10), false);
  });
  input.addEventListener("change", () => {
    state.dragging = false;
    ezSend(device, role, parseInt(input.value, 10), true);
  });
  const offset = ezRoleOffset(device, role);
  channelControls.set(device.id + ":" + offset, state);

  block.appendChild(head);
  block.appendChild(
    percentRow((value) => {
      paint(value);
      ezSend(device, role, value, true);
    })
  );
  return block;
}

// -- colour --

function hsvToRgb(h, s, v) {
  const i = Math.floor(h * 6);
  const f = h * 6 - i;
  const p = v * (1 - s);
  const q = v * (1 - f * s);
  const t = v * (1 - (1 - f) * s);
  const table = [
    [v, t, p],
    [q, v, p],
    [p, v, t],
    [p, q, v],
    [t, p, v],
    [v, p, q],
  ][i % 6];
  return table.map((c) => clamp255(c * 255));
}

function rgbToHsv(r, g, b) {
  r /= 255;
  g /= 255;
  b /= 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const d = max - min;
  let h = 0;
  if (d !== 0) {
    if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
    else if (max === g) h = ((b - r) / d + 2) / 6;
    else h = ((r - g) / d + 4) / 6;
  }
  return [h, max === 0 ? 0 : d / max, max];
}

function drawColourWheel(canvas) {
  const ctx = canvas.getContext("2d");
  const size = canvas.width;
  const r = size / 2;
  ctx.clearRect(0, 0, size, size);
  // One-degree wedges, then a white radial wash for the saturation axis. Cheap
  // and exact enough at this size, and it needs no image data juggling.
  for (let a = 0; a < 360; a++) {
    ctx.beginPath();
    ctx.moveTo(r, r);
    ctx.arc(r, r, r, ((a - 1) * Math.PI) / 180, ((a + 1) * Math.PI) / 180);
    ctx.closePath();
    ctx.fillStyle = "hsl(" + a + ", 100%, 50%)";
    ctx.fill();
  }
  const wash = ctx.createRadialGradient(r, r, 0, r, r, r);
  wash.addColorStop(0, "rgba(255,255,255,1)");
  wash.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = wash;
  ctx.beginPath();
  ctx.arc(r, r, r, 0, Math.PI * 2);
  ctx.fill();
}

function colourWheel(device, hasWhite) {
  const block = el("div", { class: "ez-block wheel-block" });
  const size = 168;
  const canvas = el("canvas", { width: String(size), height: String(size), class: "wheel" });
  const marker = el("div", { class: "wheel-marker" });
  const holder = el("div", { class: "wheel-holder" }, [canvas, marker]);
  drawColourWheel(canvas);

  const placeMarker = (r, g, b, w) => {
    // A white channel carries what the three colours have in common, so add it
    // back before working out where on the wheel this colour sits.
    const hsv = rgbToHsv(Math.min(255, r + w), Math.min(255, g + w), Math.min(255, b + w));
    const angle = hsv[0] * Math.PI * 2;
    const radius = (hsv[1] * size) / 2;
    marker.style.left = size / 2 + Math.cos(angle) * radius + "px";
    marker.style.top = size / 2 + Math.sin(angle) * radius + "px";
  };

  const readBack = () => {
    placeMarker(
      ezChannelValue(device, "red"),
      ezChannelValue(device, "green"),
      ezChannelValue(device, "blue"),
      hasWhite ? ezChannelValue(device, "white") : 0
    );
  };
  readBack();

  const apply = (rgb) => {
    let [r, g, b] = rgb;
    let w = 0;
    if (hasWhite) {
      // Whatever all three share is the white channel's job: it is a cleaner and
      // usually brighter white than mixing one out of the colour emitters.
      w = Math.min(r, g, b);
      r -= w;
      g -= w;
      b -= w;
    }
    ezSend(device, "red", r, false);
    ezSend(device, "green", g, false);
    ezSend(device, "blue", b, false);
    if (hasWhite) ezSend(device, "white", w, false);
    placeMarker(r, g, b, w);
  };

  const pick = (event) => {
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left - size / 2;
    const y = event.clientY - rect.top - size / 2;
    const radius = Math.min(1, Math.sqrt(x * x + y * y) / (size / 2));
    let angle = Math.atan2(y, x) / (Math.PI * 2);
    if (angle < 0) angle += 1;
    apply(hsvToRgb(angle, radius, 1));
  };

  let picking = false;
  canvas.addEventListener("pointerdown", (e) => {
    picking = true;
    canvas.setPointerCapture(e.pointerId);
    pick(e);
  });
  canvas.addEventListener("pointermove", (e) => {
    if (picking) pick(e);
  });
  canvas.addEventListener("pointerup", () => {
    picking = false;
  });

  ["red", "green", "blue"].concat(hasWhite ? ["white"] : []).forEach((role) => {
    ezRegister(device, role, () => readBack());
  });

  block.appendChild(holder);
  return block;
}

// -- warm and cold white --

function whitesSlider(device) {
  const block = el("div", { class: "ez-block whites-block" });
  const warm = ezChannelValue(device, "warm");
  const cold = ezChannelValue(device, "cold");
  // Position is a crossfade: the top is all warm, the bottom all cold.
  const start = warm + cold === 0 ? 128 : Math.round((cold * 255) / (warm + cold));

  const input = el("input", {
    type: "range",
    min: "0",
    max: "255",
    value: String(start),
    class: "whites",
    orient: "vertical",
  });
  const readout = el("span", { class: "ez-readout" }, ["mix"]);

  const apply = (pos) => {
    ezSend(device, "warm", 255 - pos, false);
    ezSend(device, "cold", pos, false);
    readout.textContent = pos < 96 ? "warm" : pos > 160 ? "cold" : "mix";
  };
  input.addEventListener("input", () => apply(parseInt(input.value, 10)));

  block.appendChild(el("label", {}, ["Warm to cold"]));
  block.appendChild(input);
  block.appendChild(readout);
  return block;
}

// -- smoke --

function smokeControls(device) {
  const block = el("div", { class: "ez-block" });
  const sliderMode = ezSetting(device, "mode", "onoff") === "slider";
  const autoOff = parseInt(ezSetting(device, "auto_off_s", "0"), 10) || 0;
  const offset = ezRoleOffset(device, "output");

  const burst = (seconds) => {
    api("/api/devices/" + device.id + "/burst", "POST", {
      offset: offset,
      value: 255,
      ms: Math.round(seconds * 1000),
    });
  };

  if (sliderMode) {
    const fader = roleFader(device, "output", "Pump");
    if (fader) block.appendChild(fader);
  } else {
    const row = el("div", { class: "ez-row" });
    let on = ezChannelValue(device, "output") > 0;
    const button = el("button", { class: "channel-btn" + (on ? " on" : "") }, [on ? "On" : "Off"]);
    const paint = (value) => {
      on = value > 0;
      button.textContent = on ? "On" : "Off";
      button.classList.toggle("on", on);
    };
    button.addEventListener("click", () => {
      const next = on ? 0 : 255;
      paint(next);
      // With an auto-off set, "on" goes through the board's burst timer, so a
      // browser that disappears cannot leave the machine running.
      if (next && autoOff > 0) burst(autoOff);
      else ezSend(device, "output", next, true);
    });
    ezRegister(device, "output", paint);
    row.appendChild(el("label", {}, ["Output"]));
    row.appendChild(button);
    block.appendChild(row);
  }

  const bursts = el("div", { class: "pct-row" });
  [1, 3, 5].forEach((s) => {
    const btn = el("button", { type: "button", class: "secondary small" }, ["Burst " + s + "s"]);
    btn.addEventListener("click", () => burst(s));
    bursts.appendChild(btn);
  });
  const custom = el("input", { type: "number", min: "1", max: "30", value: "10", class: "burst-n" });
  const go = el("button", { type: "button", class: "secondary small" }, ["Burst"]);
  go.addEventListener("click", () => burst(parseInt(custom.value, 10) || 1));
  bursts.appendChild(custom);
  bursts.appendChild(go);
  block.appendChild(bursts);

  block.appendChild(
    el("p", { class: "hint" }, [
      autoOff > 0
        ? "Auto-off after " + autoOff + " s. The board holds the timer, capped at 30 s."
        : "Bursts are timed by the board and capped at 30 s.",
    ])
  );
  return block;
}

// -- motion --

function motionPad(device) {
  const block = el("div", { class: "ez-block" });
  const invertH = ezSetting(device, "invert_h", "") === "1";
  const invertV = ezSetting(device, "invert_v", "") === "1";
  const invertHFine = ezSetting(device, "invert_h_fine", "") === "1";
  const invertVFine = ezSetting(device, "invert_v_fine", "") === "1";
  const maxStep = Math.max(1, parseInt(ezSetting(device, "max_step", "10"), 10) || 10);
  const arrowStep = Math.max(1, parseInt(ezSetting(device, "arrow_step", "5"), 10) || 5);
  const fineOnly = ezSetting(device, "fine_mode", "both") === "fine";
  const hasFineH = ezRoleOffset(device, "horizontal_fine") !== null;
  const hasFineV = ezRoleOffset(device, "vertical_fine") !== null;
  const hasAnyFine = hasFineH || hasFineV;

  // Which channels the stick is on right now. Position "move" is always coarse
  // only; position "fine" does whatever the card was configured to mean by it.
  // Kept in memory rather than saved: it is a way of working during a session,
  // not a property of the fixture.
  let stickMode = "move";

  const modeRow = el("div", { class: "seg-row" });
  const moveBtn = el("button", { type: "button", class: "seg on" }, ["Move"]);
  const fineBtn = el("button", { type: "button", class: "seg" }, ["Fine"]);
  const paintMode = () => {
    moveBtn.classList.toggle("on", stickMode === "move");
    fineBtn.classList.toggle("on", stickMode === "fine");
  };
  moveBtn.addEventListener("click", () => {
    stickMode = "move";
    paintMode();
  });
  fineBtn.addEventListener("click", () => {
    stickMode = "fine";
    paintMode();
  });
  modeRow.appendChild(moveBtn);
  modeRow.appendChild(fineBtn);
  if (!hasAnyFine) {
    fineBtn.disabled = true;
    fineBtn.title = "No fine channels are bound on this fixture";
  }

  const pad = el("div", { class: "joystick", tabindex: "0" });
  const knob = el("div", { class: "joystick-knob" });
  pad.appendChild(knob);

  let vector = { x: 0, y: 0 };
  let timer = null;

  // Deflection sets the rate, not the position: a small push always steps by
  // one, full travel reaches max_step. That is what makes a slow follow
  // possible on the same control that repositions a head quickly.
  const stepFor = (axis) => {
    if (axis === 0) return 0;
    const magnitude = Math.min(1, Math.abs(axis));
    const size = Math.max(1, Math.round(magnitude * maxStep));
    return axis > 0 ? size : -size;
  };

  // A fine channel that counts backwards on this fixture is corrected here, so
  // everything above it can think in one direction.
  const readFine = (role, inverted) => {
    const raw = ezChannelValue(device, role);
    return inverted ? 255 - raw : raw;
  };
  const writeFine = (role, value, inverted) => {
    ezSend(device, role, inverted ? 255 - value : value, false);
  };

  const nudgeAxis = (coarseRole, fineRole, hasFine, fineInverted, delta) => {
    if (delta === 0) return;

    // Position "move": the coarse channel and nothing else, whatever fine
    // channels exist.
    if (stickMode === "move" || !hasFine) {
      ezSend(device, coarseRole, ezChannelValue(device, coarseRole) + delta, false);
      return;
    }

    // Position "fine", card set to fine only.
    if (fineOnly) {
      writeFine(fineRole, Math.max(0, Math.min(255, readFine(fineRole, fineInverted) + delta)), fineInverted);
      return;
    }

    // Position "fine", card set to both: coarse and fine as one 16-bit value,
    // so a step of one is the smallest movement the fixture can make rather
    // than 1/256th of its travel.
    const wide = ezChannelValue(device, coarseRole) * 256 + readFine(fineRole, fineInverted);
    const next = Math.max(0, Math.min(65535, wide + delta));
    ezSend(device, coarseRole, Math.floor(next / 256), false);
    writeFine(fineRole, next % 256, fineInverted);
  };

  const tick = () => {
    const dx = stepFor(invertH ? -vector.x : vector.x);
    const dy = stepFor(invertV ? -vector.y : vector.y);
    nudgeAxis("horizontal", "horizontal_fine", hasFineH, invertHFine, dx);
    nudgeAxis("vertical", "vertical_fine", hasFineV, invertVFine, dy);
  };

  const startTicking = () => {
    if (!timer) timer = setInterval(tick, 60);
  };
  const stopTicking = () => {
    if (timer) clearInterval(timer);
    timer = null;
    vector = { x: 0, y: 0 };
    knob.style.transform = "translate(-50%, -50%)";
  };

  const track = (event) => {
    const rect = pad.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width - 0.5;
    const y = (event.clientY - rect.top) / rect.height - 0.5;
    vector = { x: Math.max(-1, Math.min(1, x * 2)), y: Math.max(-1, Math.min(1, y * 2)) };
    // In pixels, not percent: a percentage inside translate() resolves against
    // the knob's own box, so the knob stopped a fifth of the way out while the
    // rate kept climbing. The control has to show what it is doing.
    const reach = (rect.width - knob.offsetWidth) / 2;
    knob.style.transform =
      "translate(calc(-50% + " + vector.x * reach + "px), calc(-50% + " + vector.y * reach + "px))";
  };

  pad.addEventListener("pointerdown", (e) => {
    pad.setPointerCapture(e.pointerId);
    track(e);
    startTicking();
  });
  pad.addEventListener("pointermove", (e) => {
    if (timer) track(e);
  });
  pad.addEventListener("pointerup", stopTicking);
  pad.addEventListener("pointercancel", stopTicking);
  // No pointerleave handler: the pointer is captured, so dragging past the edge
  // of the pad is a legitimate full deflection rather than a reason to stop.

  // Double-click centres, which is how you find a head that has wandered.
  pad.addEventListener("dblclick", () => {
    stopTicking();
    ["horizontal", "vertical"].forEach((role) => ezSend(device, role, 128, true));
    ["horizontal_fine", "vertical_fine"].forEach((role) => ezSend(device, role, 128, true));
  });

  const KEYS = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
  pad.addEventListener("keydown", (e) => {
    const key = KEYS[e.key];
    if (!key) return;
    e.preventDefault();
    // Arrows are a fixed step, not the stick's rate curve: one press is one
    // increment of whatever the card was told, so a nudge is repeatable rather
    // than depending on how long a finger stayed down. Holding a key repeats
    // through the browser's own key repeat.
    nudgeAxis("horizontal", "horizontal_fine", hasFineH, invertHFine, (invertH ? -1 : 1) * key[0] * arrowStep);
    nudgeAxis("vertical", "vertical_fine", hasFineV, invertVFine, (invertV ? -1 : 1) * key[1] * arrowStep);
  });

  block.appendChild(modeRow);
  block.appendChild(pad);
  block.appendChild(
    el("p", { class: "hint" }, [
      "Drag to move, further is faster. Double-click to centre. Arrow keys step by " +
        arrowStep +
        ". " +
        (hasAnyFine
          ? "Fine drives " + (fineOnly ? "the fine channels alone." : "movement and fine together.")
          : "No fine channels bound, so Fine is unavailable."),
    ])
  );
  return block;
}

// -- presets --

function presetRow(device) {
  const presets = (device.ez && device.ez.presets) || [];
  const row = el("div", { class: "pct-row" });

  const roles = Object.keys((device.ez && device.ez.roles) || {});

  presets.forEach((preset, index) => {
    const btn = el("button", { type: "button", class: "secondary small" }, [preset.name]);
    btn.addEventListener("click", () => {
      Object.keys(preset.values || {}).forEach((role) => {
        ezSend(device, role, preset.values[role], true);
      });
      redrawDevices();
    });
    btn.addEventListener("contextmenu", async (e) => {
      e.preventDefault();
      if (!confirm('Delete the preset "' + preset.name + '"?')) return;
      const next = presets.slice();
      next.splice(index, 1);
      await savePresets(device, next);
    });
    row.appendChild(btn);
  });

  const save = el("button", { type: "button", class: "secondary small" }, ["Save look"]);
  save.addEventListener("click", async () => {
    const name = prompt("Name for this look", "Preset " + (presets.length + 1));
    if (!name) return;
    const values = {};
    roles.forEach((role) => {
      values[role] = ezChannelValue(device, role);
    });
    await savePresets(device, presets.concat([{ name: name, values: values }]));
  });
  row.appendChild(save);

  if (presets.length) {
    row.appendChild(el("span", { class: "hint" }, ["Right-click a look to delete it."]));
  }
  return row;
}

async function savePresets(device, presets) {
  const ez = JSON.parse(JSON.stringify(device.ez || {}));
  ez.presets = presets.slice(0, 12);
  await api("/api/devices/" + device.id, "PUT", { ez: ez });
  renderDevices();
}

// -- assembling a card --

function ezCardBody(device) {
  const kind = (device.ez && device.ez.kind) || "";
  const parts = [];

  if (kind === "dimmer") parts.push(roleFader(device, "level", "Level"));
  else if (kind === "strobe") parts.push(roleFader(device, "strobe", "Strobe"));
  else if (kind === "mono") parts.push(roleFader(device, "level", "Light"));
  else if (kind === "rgb" || kind === "rgbw") parts.push(colourWheel(device, kind === "rgbw"));
  else if (kind === "cwww") parts.push(whitesSlider(device));
  else if (kind === "smoke") parts.push(smokeControls(device));
  else if (kind === "motion") parts.push(motionPad(device));

  // Shared optional roles, drawn only where the fixture claimed them.
  if (kind !== "dimmer") parts.push(roleFader(device, "dimmer", "Master dimmer"));
  if (kind !== "strobe") parts.push(roleFader(device, "strobe", "Strobe"));
  if (kind === "motion") parts.push(roleFader(device, "speed", "Movement speed"));

  if (kind !== "smoke") parts.push(presetRow(device));
  return parts.filter(Boolean);
}

// ---- device modal: create, edit and duplicate ----

let editingDeviceId = null;
let modalLabels = new Set();

function addChannelRow(offset, name, type) {
  const rows = document.getElementById("channel-rows");
  const row = el("div", { class: "channel-row" });
  row.appendChild(
    el("input", { type: "number", placeholder: "Offset", value: String(offset), min: "1", class: "ch-offset" })
  );
  row.appendChild(el("input", { type: "text", placeholder: "Name", value: name || "", class: "ch-name" }));
  const select = el("select", { class: "ch-type" }, [
    el("option", { value: "slider" }, ["Slider"]),
    el("option", { value: "button" }, ["Button (trigger)"]),
    el("option", { value: "button-momentary" }, ["Button (momentary)"]),
    el("option", { value: "button-switch" }, ["Button (switch)"]),
  ]);
  select.value = type || "slider";
  row.appendChild(select);
  const removeBtn = el("button", { type: "button", class: "secondary" }, ["Remove"]);
  removeBtn.addEventListener("click", () => row.remove());
  row.appendChild(removeBtn);
  rows.appendChild(row);
}

document.getElementById("add-channel-row").addEventListener("click", () => {
  const count = document.querySelectorAll("#channel-rows .channel-row").length;
  addChannelRow(count + 1);
});

function renderModalLabelPicker() {
  const picker = document.getElementById("device-labels");
  picker.innerHTML = "";
  if (labelsCache.length === 0) {
    picker.appendChild(el("span", { class: "hint" }, ["No labels yet. Create some in Settings."]));
    return;
  }
  labelsCache.forEach((label) => {
    const on = modalLabels.has(label.id);
    const chip = el("button", { type: "button", class: "chip" + (on ? " on" : "") }, [label.name]);
    chip.style.setProperty("--chip", label.color);
    chip.addEventListener("click", () => {
      if (modalLabels.has(label.id)) modalLabels.delete(label.id);
      else modalLabels.add(label.id);
      renderModalLabelPicker();
    });
    picker.appendChild(chip);
  });
}

// `device` seeds the form, `id` decides the verb: an id edits that fixture in
// place, null creates a new one. Duplicate is simply the second case seeded
// from an existing fixture.
function renderCategorySelect(selected) {
  const select = document.getElementById("device-category");
  select.innerHTML = "";
  categoriesCache.forEach((cat) => {
    select.appendChild(el("option", { value: cat.id }, [cat.name]));
  });
  select.value = selected || "other";
}

function openDeviceModal(device, id) {
  const form = document.getElementById("device-form");
  editingDeviceId = id;
  form.name.value = device ? device.name : "";
  form.start_channel.value = device ? device.start_channel : 1;
  renderCategorySelect(device && device.category);
  modalLabels = new Set((device && device.labels) || []);
  document.getElementById("channel-rows").innerHTML = "";
  if (device) device.channels.forEach((c) => addChannelRow(c.offset, c.name, c.type));
  renderModalLabelPicker();
  document.getElementById("device-form-title").textContent = id ? "Edit device" : "New device";
  document.getElementById("device-submit").textContent = id ? "Save changes" : "Create device";
  document.getElementById("device-modal").hidden = false;
  form.name.focus();
}

function closeDeviceModal() {
  document.getElementById("device-modal").hidden = true;
  editingDeviceId = null;
}

document.querySelectorAll("#device-modal [data-close]").forEach((node) => {
  node.addEventListener("click", closeDeviceModal);
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !document.getElementById("device-modal").hidden) closeDeviceModal();
});

// ---- the three ways to get a fixture ----

function closeChoiceModal() {
  document.getElementById("choice-modal").hidden = true;
  document.getElementById("choice-status").textContent = "";
}

document.querySelectorAll("#choice-modal [data-close-choice]").forEach((node) => {
  node.addEventListener("click", closeChoiceModal);
});

document.getElementById("choice-lite").addEventListener("click", async () => {
  closeChoiceModal();
  openDeviceModal(
    { name: "", category: "other", start_channel: await nextFreeStart(), channels: [], labels: [] },
    null
  );
});

document.getElementById("choice-ez").addEventListener("click", async () => {
  closeChoiceModal();
  openEzModal(null, await nextFreeStart());
});

document.getElementById("choice-restore").addEventListener("click", () => {
  document.getElementById("fixture-file").click();
});

document.getElementById("fixture-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  const status = document.getElementById("choice-status");
  if (!file) return;
  try {
    const fixture = JSON.parse(await file.text());
    if (!fixture || !Array.isArray(fixture.channels)) {
      throw new Error("that file has no channel list, so it is not a fixture");
    }
    delete fixture.id;  // never trust an id from a file; the board mints one
    // Landing it past everything already patched, rather than on whatever
    // address it happened to be saved from, which is very likely taken.
    fixture.start_channel = await nextFreeStart();
    await api("/api/devices", "POST", fixture);
    closeChoiceModal();
    renderDevices();
  } catch (err) {
    status.textContent = "Could not restore that file: " + err.message;
  }
  e.target.value = "";
});

// Past the end of everything already patched, so a new fixture does not
// silently share addresses with an existing one.
async function nextFreeStart() {
  const devices = await api("/api/devices");
  let next = 1;
  devices.forEach((d) => {
    const span = d.channels.reduce((max, c) => Math.max(max, c.offset), 0);
    next = Math.max(next, d.start_channel + span);
  });
  return Math.min(next, 512);
}

document.getElementById("add-device-fab").addEventListener("click", async () => {
  labelsCache = await api("/api/labels");
  if (categoriesCache.length === 0) categoriesCache = await api("/api/categories");
  document.getElementById("choice-modal").hidden = false;
});

// ---- EZ creation and editing ----

let editingEzId = null;
let ezLabels = new Set();

function openEzModal(device, startChannel) {
  const form = document.getElementById("ez-form");
  editingEzId = device ? device.id : null;
  ezLabels = new Set((device && device.labels) || []);

  const kindSelect = document.getElementById("ez-kind");
  kindSelect.innerHTML = "";
  Object.keys(EZ_KINDS).forEach((key) => {
    kindSelect.appendChild(el("option", { value: key }, [EZ_KINDS[key].label]));
  });
  kindSelect.value = (device && device.ez && device.ez.kind) || "rgb";

  const catSelect = document.getElementById("ez-category");
  catSelect.innerHTML = "";
  categoriesCache.forEach((c) => catSelect.appendChild(el("option", { value: c.id }, [c.name])));

  form.name.value = device ? device.name : "";
  form.start_channel.value = device ? device.start_channel : startChannel;
  document.getElementById("ez-title").textContent = device ? "Edit EZ device" : "New EZ device";
  document.getElementById("ez-submit").textContent = device ? "Save changes" : "Create device";

  renderEzKind(device);
  renderEzLabelPicker();
  document.getElementById("ez-error").hidden = true;
  document.getElementById("ez-modal").hidden = false;
  form.name.focus();
}

function renderEzKind(device) {
  const kind = document.getElementById("ez-kind").value;
  const spec = EZ_KINDS[kind];
  const catSelect = document.getElementById("ez-category");
  // Only steer the category on a fresh fixture; an edit keeps what was chosen.
  if (!device) catSelect.value = spec.category;
  else catSelect.value = device.category || spec.category;

  document.getElementById("ez-roles-hint").textContent =
    "Offsets within the fixture, counted from its start channel. Leave an optional one blank to drop it from the card.";

  const rolesBox = document.getElementById("ez-roles");
  rolesBox.innerHTML = "";
  spec.roles.forEach((role) => {
    const row = el("div", { class: "role-row" });
    row.appendChild(
      el("label", { for: "ez-role-" + role.key }, [
        role.label,
        role.required ? "" : el("span", { class: "hint" }, ["optional"]),
      ])
    );
    const existing = device ? ezRoleOffset(device, role.key) : null;
    row.appendChild(
      el("input", {
        type: "number",
        min: "1",
        max: "512",
        id: "ez-role-" + role.key,
        "data-role": role.key,
        "data-required": role.required ? "1" : "",
        value: existing === null ? "" : String(existing),
        class: "ez-role",
      })
    );
    rolesBox.appendChild(row);
  });

  const optionsBox = document.getElementById("ez-options");
  optionsBox.innerHTML = "";
  (spec.options || []).forEach((opt) => {
    const current = device ? ezSetting(device, opt.key, opt.default) : opt.default;
    const field = el("div", { class: opt.type === "checkbox" ? "field field-inline" : "field" });
    let input;
    if (opt.type === "select") {
      input = el("select", { id: "ez-opt-" + opt.key, "data-opt": opt.key });
      opt.choices.forEach((c) => input.appendChild(el("option", { value: c[0] }, [c[1]])));
      input.value = current;
    } else if (opt.type === "checkbox") {
      input = el("input", { type: "checkbox", id: "ez-opt-" + opt.key, "data-opt": opt.key });
      input.checked = current === "1";
    } else {
      input = el("input", {
        type: "number",
        id: "ez-opt-" + opt.key,
        "data-opt": opt.key,
        value: String(current),
      });
    }
    const label = el("label", { for: "ez-opt-" + opt.key }, [opt.label]);
    if (opt.type === "checkbox") {
      field.appendChild(input);
      field.appendChild(label);
    } else {
      field.appendChild(label);
      field.appendChild(input);
      if (opt.hint) field.appendChild(el("span", { class: "hint" }, [opt.hint]));
    }
    optionsBox.appendChild(field);
  });
}

document.getElementById("ez-kind").addEventListener("change", () => renderEzKind(null));

function renderEzLabelPicker() {
  const picker = document.getElementById("ez-labels");
  picker.innerHTML = "";
  if (labelsCache.length === 0) {
    picker.appendChild(el("span", { class: "hint" }, ["No labels yet."]));
    return;
  }
  labelsCache.forEach((label) => {
    const on = ezLabels.has(label.id);
    const chip = el("button", { type: "button", class: "chip" + (on ? " on" : "") }, [label.name]);
    chip.style.setProperty("--chip", label.color);
    chip.addEventListener("click", () => {
      if (ezLabels.has(label.id)) ezLabels.delete(label.id);
      else ezLabels.add(label.id);
      renderEzLabelPicker();
    });
    picker.appendChild(chip);
  });
}

function closeEzModal() {
  document.getElementById("ez-modal").hidden = true;
  editingEzId = null;
}

document.querySelectorAll("#ez-modal [data-close-ez]").forEach((node) => {
  node.addEventListener("click", closeEzModal);
});

// Reads the role inputs and refuses anything a card could not draw. Cancel
// still works: the block is on saving a broken fixture, not on changing your
// mind about making one.
function collectEzRoles() {
  const roles = {};
  const seen = new Map();
  let error = "";
  document.querySelectorAll("#ez-roles .ez-role").forEach((input) => {
    const key = input.dataset.role;
    const raw = input.value.trim();
    if (!raw) {
      if (input.dataset.required) error = error || "Every required channel needs an offset.";
      return;
    }
    const offset = parseInt(raw, 10);
    if (!(offset >= 1 && offset <= 512)) {
      error = error || "Offsets must be between 1 and 512.";
      return;
    }
    if (seen.has(offset)) {
      error =
        error ||
        "Two roles point at offset " + offset + ": " + seen.get(offset) + " and " + key + ".";
      return;
    }
    seen.set(offset, key);
    roles[key] = offset;
  });
  return { roles: roles, error: error };
}

document.getElementById("ez-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const kind = document.getElementById("ez-kind").value;
  const spec = EZ_KINDS[kind];
  const collected = collectEzRoles();
  const errorBox = document.getElementById("ez-error");

  if (collected.error) {
    errorBox.textContent = collected.error;
    errorBox.hidden = false;
    return;
  }
  errorBox.hidden = true;

  const settings = {};
  document.querySelectorAll("#ez-options [data-opt]").forEach((input) => {
    settings[input.dataset.opt] = input.type === "checkbox" ? (input.checked ? "1" : "") : input.value;
  });

  // An EZ fixture is a normal fixture underneath: one plain channel per bound
  // role, so MQTT, the serial console and the lite view all keep working
  // against it without knowing what a colour wheel is.
  const channels = spec.roles
    .filter((role) => collected.roles[role.key])
    .map((role) => ({
      offset: collected.roles[role.key],
      name: role.label,
      type: "slider",
    }));

  const payload = {
    name: form.name.value,
    category: document.getElementById("ez-category").value,
    card: "ez",
    start_channel: parseInt(form.start_channel.value, 10),
    channels: channels,
    labels: Array.from(ezLabels),
    ez: { kind: kind, mode: settings.mode || "", roles: collected.roles, settings: settings },
  };

  if (editingEzId) await api("/api/devices/" + editingEzId, "PUT", payload);
  else await api("/api/devices", "POST", payload);
  closeEzModal();
  renderDevices();
});


document.getElementById("device-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const channels = [];
  document.querySelectorAll("#channel-rows .channel-row").forEach((row) => {
    channels.push({
      offset: parseInt(row.querySelector(".ch-offset").value, 10),
      name: row.querySelector(".ch-name").value || "Channel",
      type: row.querySelector(".ch-type").value,
    });
  });
  const payload = {
    name: form.name.value,
    category: form.category.value,
    start_channel: parseInt(form.start_channel.value, 10),
    channels: channels,
    labels: Array.from(modalLabels),
  };
  if (editingDeviceId) await api("/api/devices/" + editingDeviceId, "PUT", payload);
  else await api("/api/devices", "POST", payload);
  closeDeviceModal();
  renderDevices();
});

// ---- settings ----

async function renderSettings() {
  await renderWifiList();

  const mqtt = await api("/api/mqtt");
  const mqttForm = document.getElementById("mqtt-form");
  mqttForm.enabled.checked = !!mqtt.enabled;
  mqttForm.host.value = mqtt.host || "";
  mqttForm.port.value = mqtt.port || 1883;
  mqttForm.username.value = mqtt.username || "";
  mqttForm.password.value = mqtt.password || "";
  mqttForm.base_topic.value = mqtt.base_topic || "";
  mqttForm.discovery_prefix.value = mqtt.discovery_prefix || "";

  const system = await api("/api/system");
  const pinsForm = document.getElementById("system-pins-form");
  pinsForm.dmx_tx_pin.value = system.dmx_tx_pin || "";
  pinsForm.dmx_dir_pin_enabled.checked = !!system.dmx_dir_pin_enabled;
  pinsForm.dmx_dir_pin.value = system.dmx_dir_pin || "";

  document.getElementById("hostname-form").hostname.value = system.hostname || "";

  const apForm = document.getElementById("ap-form");
  apForm.ap_ssid.value = system.ap_ssid || "";
  apForm.ap_password.value = system.ap_password || "";
  apForm.ap_ip.value = system.ap_ip || "";

  updateDirPinField();

  const modules = await api("/api/modules");
  const modForm = document.getElementById("modules-form");
  modForm.http_api_enabled.checked = !!modules.http_api_enabled;
  modForm.websocket_enabled.checked = !!modules.websocket_enabled;
  modForm.mqtt_enabled.checked = !!modules.mqtt_enabled;
  document.getElementById("api-key").value = modules.api_key || "(hidden)";

  const mesh = await api("/api/mesh");
  const meshForm = document.getElementById("mesh-form");
  meshForm.role.value = mesh.role || "none";
  meshForm.ssid.value = mesh.ssid || "";
  meshForm.password.value = mesh.password || "";

  await renderLabelList();
  await renderEthernet();
}

// -- config backup and restore --

document.getElementById("config-load-btn").addEventListener("click", () => {
  document.getElementById("config-file").click();
});

document.getElementById("config-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  const status = document.getElementById("config-status");
  if (!file) return;
  status.textContent = "Reading " + file.name + "...";
  try {
    const parsed = JSON.parse(await file.text());
    const res = await api("/api/config", "POST", parsed);
    if (res.error) throw new Error(res.error);
    status.textContent = "Applied " + file.name + ". Reboot to pick up pin changes.";
    await renderSettings();
    labelsCache = await api("/api/labels");
  } catch (err) {
    status.textContent = "Could not apply that file: " + err.message;
  }
  e.target.value = "";
});

// -- labels --

async function renderLabelList() {
  labelsCache = await api("/api/labels");
  const list = document.getElementById("label-list");
  list.innerHTML = "";
  if (labelsCache.length === 0) {
    list.appendChild(el("p", { class: "hint" }, ["No labels yet."]));
    return;
  }
  labelsCache.forEach((label) => {
    const item = el("div", { class: "list-item" });

    const swatch = el("input", { type: "color", value: label.color, class: "swatch" });
    const name = el("input", { type: "text", value: label.name, class: "grow" });
    item.appendChild(swatch);
    item.appendChild(name);

    const save = el("button", { class: "secondary" }, ["Save"]);
    save.addEventListener("click", async () => {
      await api("/api/labels/" + label.id, "PUT", { name: name.value, color: swatch.value });
      renderLabelList();
    });

    const del = el("button", { class: "secondary" }, ["Remove"]);
    del.addEventListener("click", async () => {
      if (!confirm('Remove label "' + label.name + '"? Fixtures keep their channels.')) return;
      await api("/api/labels/" + label.id, "DELETE");
      activeFilters.delete(label.id);
      renderLabelList();
    });

    item.appendChild(save);
    item.appendChild(del);
    list.appendChild(item);
  });
}

document.getElementById("label-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  await api("/api/labels", "POST", { name: form.name.value, color: form.color.value });
  form.reset();
  form.color.value = "#3b82f6";
  renderLabelList();
});

// -- wifi --

let wifiCache = [];
let dragIndex = null;

// Posts the list back in its current order. The board turns the order into
// priorities, so there is one source of truth rather than two that can drift.
async function saveWifiOrder() {
  wifiCache = await api("/api/wifi", "PUT", wifiCache);
  renderWifiList();
}

async function renderWifiList(fetchFirst) {
  if (fetchFirst !== false) wifiCache = await api("/api/wifi");
  const list = document.getElementById("wifi-list");
  list.innerHTML = "";
  if (wifiCache.length === 0) {
    list.appendChild(el("p", { class: "hint" }, ["No saved networks."]));
    return;
  }
  wifiCache.forEach((net, index) => {
    const item = el("div", { class: "list-item draggable", draggable: "true" });

    item.appendChild(el("span", { class: "drag-handle", title: "Drag to reorder" }, ["⠿"]));
    item.appendChild(
      el("span", { class: "grow" }, [
        net.ssid,
        el("span", { class: "card-sub" }, [
          net.ip_mode === "static" ? "static " + (net.static_ip || "?") : "DHCP",
        ]),
      ])
    );

    const actions = el("div", { class: "card-actions" });
    actions.appendChild(iconButton(ICON_GEAR, "Edit", () => openWifiModal(index)));
    actions.appendChild(
      iconButton(ICON_TRASH, "Remove", async () => {
        if (!confirm('Remove "' + net.ssid + '"?')) return;
        await api("/api/wifi/" + encodeURIComponent(net.ssid), "DELETE");
        renderWifiList();
      })
    );
    item.appendChild(actions);

    item.addEventListener("dragstart", () => {
      dragIndex = index;
      item.classList.add("dragging");
    });
    item.addEventListener("dragend", () => item.classList.remove("dragging"));
    item.addEventListener("dragover", (e) => {
      e.preventDefault();
      item.classList.add("drop-target");
    });
    item.addEventListener("dragleave", () => item.classList.remove("drop-target"));
    item.addEventListener("drop", (e) => {
      e.preventDefault();
      item.classList.remove("drop-target");
      if (dragIndex === null || dragIndex === index) return;
      const [moved] = wifiCache.splice(dragIndex, 1);
      wifiCache.splice(index, 0, moved);
      dragIndex = null;
      saveWifiOrder();
    });

    list.appendChild(item);
  });
}

// -- per-network editor --

let editingWifiIndex = null;

function updateWifiStaticFields() {
  const form = document.getElementById("wifi-edit-form");
  document.getElementById("wifi-static-fields").hidden = form.ip_mode.value !== "static";
}

function openWifiModal(index) {
  const net = wifiCache[index];
  const form = document.getElementById("wifi-edit-form");
  editingWifiIndex = index;
  form.ssid.value = net.ssid;
  form.password.value = net.password || "";
  form.ip_mode.value = net.ip_mode || "dhcp";
  form.static_ip.value = net.static_ip || "";
  form.static_netmask.value = net.static_netmask || "255.255.255.0";
  form.static_gateway.value = net.static_gateway || "";
  form.static_dns.value = net.static_dns || "1.1.1.1";
  updateWifiStaticFields();
  document.getElementById("wifi-modal").hidden = false;
}

function closeWifiModal() {
  document.getElementById("wifi-modal").hidden = true;
  editingWifiIndex = null;
}

document.querySelectorAll("#wifi-modal [data-close-wifi]").forEach((node) => {
  node.addEventListener("click", closeWifiModal);
});

document.getElementById("wifi-edit-form").ip_mode.addEventListener("change", updateWifiStaticFields);

document.getElementById("wifi-edit-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  wifiCache[editingWifiIndex] = {
    ssid: form.ssid.value,
    password: form.password.value,
    ip_mode: form.ip_mode.value,
    static_ip: form.static_ip.value,
    static_netmask: form.static_netmask.value,
    static_gateway: form.static_gateway.value,
    static_dns: form.static_dns.value,
  };
  closeWifiModal();
  await saveWifiOrder();
});

document.getElementById("wifi-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  // New networks land at the bottom, which is the lowest priority. Drag them up
  // if they should be tried first.
  await api("/api/wifi", "POST", {
    ssid: form.ssid.value,
    password: form.password.value,
    priority: 0,
  });
  form.reset();
  renderWifiList();
});

document.getElementById("wifi-scan-btn").addEventListener("click", async () => {
  const results = await api("/api/wifi/scan");
  const datalist = document.getElementById("wifi-scan-results");
  datalist.innerHTML = "";
  results.forEach((net) => datalist.appendChild(el("option", { value: net.ssid })));
});

document.getElementById("hostname-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  await api("/api/system", "POST", { hostname: e.target.hostname.value });
  document.getElementById("hostname-hint").textContent =
    "Saved. The board answers on the new name after a reboot.";
});

document.getElementById("ap-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  await api("/api/system", "POST", {
    ap_ssid: form.ap_ssid.value,
    ap_password: form.ap_password.value,
    ap_ip: form.ap_ip.value,
  });
});

// -- wired ethernet, W5500 --

const ETH_BETA_WARNING =
  "The W5500 support has never been run against the hardware. It is written to " +
  "fail safely, so a board with no adapter attached still boots and still comes " +
  "up on WiFi, but nothing here has been observed working.\n\nEnable it anyway?";

async function renderEthernet() {
  const eth = await api("/api/ethernet");
  const supported = eth.supported !== false;
  document.getElementById("section-w5500").hidden = !supported;
  document.getElementById("section-eth-address").hidden = !supported;
  if (!supported) return;

  const form = document.getElementById("w5500-form");
  form.enabled.checked = !!eth.enabled;
  form.cs_pin.value = eth.cs_pin;

  const addr = document.getElementById("eth-address-form");
  addr.ip_mode.value = eth.ip_mode || "dhcp";
  addr.static_ip.value = eth.static_ip || "";
  addr.static_netmask.value = eth.static_netmask || "255.255.255.0";
  addr.static_gateway.value = eth.static_gateway || "";
  addr.static_dns.value = eth.static_dns || "1.1.1.1";
  updateEthStaticFields();

  const status = eth.status || {};
  const state = document.getElementById("eth-state");
  if (!eth.enabled) state.textContent = "Disabled. Turn it on under Settings, Config.";
  else if (status.link) state.textContent = "Link up at " + status.ip;
  else state.textContent = "Enabled but no link: " + (status.reason || "no cable, or no adapter");
}

function updateEthStaticFields() {
  const form = document.getElementById("eth-address-form");
  document.getElementById("eth-static-fields").hidden = form.ip_mode.value !== "static";
}

document.getElementById("eth-mode").addEventListener("change", updateEthStaticFields);

document.getElementById("w5500-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  // Only warn on the way in. Turning it back off needs no ceremony.
  if (form.enabled.checked && !confirm(ETH_BETA_WARNING)) {
    form.enabled.checked = false;
    return;
  }
  await api("/api/ethernet", "POST", {
    enabled: form.enabled.checked,
    cs_pin: parseInt(form.cs_pin.value, 10) || 10,
  });
  document.getElementById("w5500-status").textContent =
    "Saved. The interface comes up on the next reboot.";
  renderEthernet();
});

document.getElementById("eth-address-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  await api("/api/ethernet", "POST", {
    ip_mode: form.ip_mode.value,
    static_ip: form.static_ip.value,
    static_netmask: form.static_netmask.value,
    static_gateway: form.static_gateway.value,
    static_dns: form.static_dns.value,
  });
  renderEthernet();
});

// -- modules and the api key --

document.getElementById("modules-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  await api("/api/modules", "POST", {
    http_api_enabled: form.http_api_enabled.checked,
    websocket_enabled: form.websocket_enabled.checked,
    mqtt_enabled: form.mqtt_enabled.checked,
  });
});

document.getElementById("api-key-copy").addEventListener("click", async () => {
  const field = document.getElementById("api-key");
  const status = document.getElementById("api-key-status");
  try {
    await navigator.clipboard.writeText(field.value);
    status.textContent = "Copied.";
  } catch (err) {
    // Clipboard access needs a secure context, which plain http on a LAN is not.
    field.select();
    status.textContent = "Could not reach the clipboard, so the key is selected instead.";
  }
});

document.getElementById("api-key-new").addEventListener("click", async () => {
  if (!confirm("Regenerate the API key? Anything using the old one stops working.")) return;
  const res = await api("/api/modules/key", "POST");
  document.getElementById("api-key").value = res.api_key;
  document.getElementById("api-key-status").textContent = "New key in place, old one revoked.";
});

// -- dmx pins and reboot --

// The pin only means something when the direction line is driven at all.
function updateDirPinField() {
  const form = document.getElementById("system-pins-form");
  document.getElementById("field-dir-pin").hidden = !form.dmx_dir_pin_enabled.checked;
}

document
  .getElementById("system-pins-form")
  .dmx_dir_pin_enabled.addEventListener("change", updateDirPinField);

document.getElementById("reboot-btn").addEventListener("click", async () => {
  if (!confirm("Reboot the board? DMX output stops for a couple of seconds.")) return;
  const status = document.getElementById("reboot-status");
  status.textContent = "Rebooting...";
  try {
    await api("/api/reboot", "POST");
  } catch (err) {
    // The board drops the connection on its way down, which is expected.
  }
  setTimeout(() => {
    status.textContent = "Back up, reloading.";
    location.reload();
  }, 8000);
});

document.getElementById("system-pins-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  await api("/api/system", "POST", {
    dmx_tx_pin: form.dmx_tx_pin.value,
    dmx_dir_pin_enabled: form.dmx_dir_pin_enabled.checked,
    dmx_dir_pin: form.dmx_dir_pin.value,
  });
});

// -- mesh --

document.getElementById("mesh-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  await api("/api/mesh", "POST", {
    role: form.role.value,
    ssid: form.ssid.value,
    password: form.password.value,
  });
});

// -- info --

async function renderInfo() {
  const info = await api("/api/info");
  document.getElementById("info-version").textContent = info.version;
  const board = document.getElementById("info-board");
  board.textContent = info.board || "unknown";
  // The ESP8266 target compiles but has not been run since the C++ rewrite.
  if (info.board === "esp8266") board.appendChild(el("span", { class: "beta-tag" }, ["beta"]));
  document.getElementById("info-hostname").textContent = info.hostname
    ? info.hostname + ".local"
    : "not set";
  document.getElementById("info-transport").textContent =
    transportName() === "websocket"
      ? "WebSocket on port " + (info.websocket_port || 81)
      : "HTTP (the socket is off or unreachable)";
  const author = document.getElementById("info-author");
  author.innerHTML = "";
  author.appendChild(el("a", { href: info.author.url, target: "_blank" }, [info.author.name]));
  const repo = document.getElementById("info-repo");
  repo.innerHTML = "";
  repo.appendChild(el("a", { href: info.repo, target: "_blank" }, [info.repo]));
  const wiki = document.getElementById("info-wiki");
  wiki.innerHTML = "";
  wiki.appendChild(el("a", { href: info.wiki_local, target: "_blank" }, ["Local copy"]));
  wiki.appendChild(document.createTextNode(" | "));
  wiki.appendChild(el("a", { href: info.wiki_online, target: "_blank" }, ["On GitHub"]));
}

// ---- boot ----

(async function start() {
  // One request rather than five. The board serves a single client at a time,
  // so every extra connection in the opening burst is another chance for one to
  // be refused while the browser is still fetching the page's own assets.
  try {
    const boot = await api("/api/bootstrap");
    boardInfo = boot;
    // The UI is exempt from the key on HTTP, but the socket asks every client
    // for it, so it rides along here.
    apiKey = boot.api_key || null;
    categoriesCache = boot.categories || [];
    labelsCache = boot.labels || [];
  } catch (e) {
    boardInfo = {};
    apiKey = null;
  }
  connectWebSocket();
  // The ESP8266 backend is nailed to Serial1/GPIO2, so offering pin fields there
  // would promise something the firmware cannot honour.
  const isEsp8266 = boardInfo.board === "esp8266";
  document.getElementById("section-dmx-pins").hidden = isEsp8266;
  document.getElementById("section-dmx-pins-esp8266").hidden = !isEsp8266;
  switchView("devices");
})();
