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

function applyRemoteValue(deviceId, offset, value) {
  const control = channelControls.get(deviceId + ":" + offset);
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
  ws.addEventListener("close", () => {
    ws = null;
    // The board reboots, the venue's AP blinks: keep trying rather than silently
    // degrading to HTTP for the rest of the session.
    setTimeout(connectWebSocket, 3000);
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
let boardInfo = {};

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
    renderDevices();
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
    renderDevices();
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
      renderDevices();
    });
    bar.appendChild(chip);
  });
}

// Categories and labels are independent facets: a fixture must satisfy both
// bars, but within one bar the chips widen the selection rather than
// intersecting. Picking Face and Contre shows both, picking PAR on top of them
// narrows that to the PARs among them.
function matchesFilters(device) {
  if (activeCategories.size && !activeCategories.has(device.category)) return false;
  if (activeFilters.size === 0) return true;
  return (device.labels || []).some((id) => activeFilters.has(id));
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
  actions.appendChild(iconButton(ICON_GEAR, "Edit", () => openDeviceModal(device, device.id)));
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

  device.channels.forEach((channel) => card.appendChild(channelControl(device, channel)));
  return card;
}

async function renderDevices() {
  labelsCache = await api("/api/labels");
  if (categoriesCache.length === 0) categoriesCache = await api("/api/categories");
  const devices = await api("/api/devices");
  renderCategoryChips(devices);
  renderFilterChips(devices);

  const grid = document.getElementById("device-grid");
  grid.innerHTML = "";
  channelControls.clear();  // the old controls just left the DOM
  if (devices.length === 0) {
    grid.appendChild(el("p", { class: "empty" }, ["No fixtures yet. Add one with the + button."]));
    return;
  }
  const shown = devices.filter(matchesFilters);
  if (shown.length === 0) {
    grid.appendChild(el("p", { class: "empty" }, ["No fixture matches the selected filters."]));
    return;
  }
  shown.forEach((device) => grid.appendChild(deviceCard(device)));
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

document.getElementById("add-device-fab").addEventListener("click", async () => {
  labelsCache = await api("/api/labels");
  if (categoriesCache.length === 0) categoriesCache = await api("/api/categories");
  const devices = await api("/api/devices");
  // Land past the end of everything already patched, so a new fixture does not
  // silently share addresses with an existing one.
  let next = 1;
  devices.forEach((d) => {
    const span = d.channels.reduce((max, c) => Math.max(max, c.offset), 0);
    next = Math.max(next, d.start_channel + span);
  });
  openDeviceModal(
    { name: "", category: "other", start_channel: Math.min(next, 512), channels: [], labels: [] },
    null
  );
  document.getElementById("device-form").name.value = "";
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
  document.getElementById("info-board").textContent = info.board || "unknown";
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
  try {
    boardInfo = await api("/api/info");
  } catch (e) {
    boardInfo = {};
  }
  try {
    // The UI is exempt from the key on HTTP, but the socket asks every client
    // for it, so fetch it here and hand it over on connect.
    apiKey = (await api("/api/modules")).api_key || null;
  } catch (e) {
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
