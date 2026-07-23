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

// ---- navigation ----

function switchView(name) {
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
  document.getElementById("view-" + name).classList.add("active");
  document.querySelector('.nav-btn[data-view="' + name + '"]').classList.add("active");
  if (name === "home") renderHome();
  if (name === "settings") renderSettings();
  if (name === "devices") renderDevices();
  if (name === "info") renderInfo();
}

document.querySelectorAll(".nav-btn").forEach((btn) => {
  btn.addEventListener("click", () => switchView(btn.dataset.view));
});

// ---- home view: live channel control ----

async function renderHome() {
  const container = document.getElementById("view-home");
  container.innerHTML = "";
  const devices = await api("/api/devices");
  if (devices.length === 0) {
    container.appendChild(el("p", {}, ["No devices yet. Add one from Device Manager."]));
    return;
  }
  devices.forEach((device) => {
    const card = el("div", { class: "device-card" }, [el("h3", {}, [device.name])]);
    device.channels.forEach((channel) => {
      const row = el("div", { class: "channel-control" });
      row.appendChild(el("label", {}, [channel.name]));
      const send = (value) =>
        api("/api/devices/" + device.id + "/channel/" + channel.offset, "POST", {
          value: value,
        });

      if (channel.type === "slider") {
        const input = el("input", { type: "range", min: "0", max: "255", value: "0" });
        const output = el("span", {}, ["0"]);
        input.addEventListener("input", () => {
          output.textContent = input.value;
        });
        input.addEventListener("change", () => send(parseInt(input.value, 10)));
        row.appendChild(input);
        row.appendChild(output);
      } else if (channel.type === "button-momentary") {
        const button = el("button", { class: "channel-btn momentary" }, ["Hold"]);
        const press = (e) => {
          if (e) e.preventDefault();
          send(255);
        };
        const release = (e) => {
          if (e) e.preventDefault();
          send(0);
        };
        button.addEventListener("mousedown", press);
        button.addEventListener("mouseup", release);
        button.addEventListener("mouseleave", release);
        button.addEventListener("touchstart", press);
        button.addEventListener("touchend", release);
        button.addEventListener("touchcancel", release);
        row.appendChild(button);
      } else if (channel.type === "button-switch") {
        const button = el("button", { class: "channel-btn switch" }, ["Off"]);
        let on = false;
        const apply = () => {
          on = !on;
          button.textContent = on ? "On" : "Off";
          button.classList.toggle("on", on);
          send(on ? 255 : 0);
        };
        button.addEventListener("click", apply);
        row.appendChild(button);
      } else {
        // legacy "button" = fire-and-forget trigger
        const button = el("button", { class: "channel-btn" }, ["Trigger"]);
        button.addEventListener("click", () => send(255));
        row.appendChild(button);
      }
      card.appendChild(row);
    });
    container.appendChild(card);
  });
}

// ---- settings view ----

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
  const systemForm = document.getElementById("system-form");
  systemForm.dmx_tx_pin.value = system.dmx_tx_pin || "";
  systemForm.dmx_dir_pin_enabled.checked = !!system.dmx_dir_pin_enabled;
  systemForm.dmx_dir_pin.value = system.dmx_dir_pin || "";
  systemForm.hostname.value = system.hostname || "";
  systemForm.ap_ssid.value = system.ap_ssid || "";
  systemForm.ap_password.value = system.ap_password || "";
  systemForm.ap_ip.value = system.ap_ip || "";

  const staticForm = document.getElementById("staticip-form");
  staticForm.sta_ip_mode.value = system.sta_ip_mode || "dhcp";
  staticForm.sta_static_ip.value = system.sta_static_ip || "";
  staticForm.sta_static_netmask.value = system.sta_static_netmask || "";
  staticForm.sta_static_gateway.value = system.sta_static_gateway || "";
  staticForm.sta_static_dns.value = system.sta_static_dns || "";
  updateStaticIpFields();

  const mesh = await api("/api/mesh");
  const meshForm = document.getElementById("mesh-form");
  meshForm.role.value = mesh.role || "none";
  meshForm.ssid.value = mesh.ssid || "";
  meshForm.password.value = mesh.password || "";
}

async function renderWifiList() {
  const networks = await api("/api/wifi");
  const list = document.getElementById("wifi-list");
  list.innerHTML = "";
  networks.forEach((net) => {
    const item = el("div", { class: "list-item" }, [
      el("span", {}, [net.ssid + " (priority " + net.priority + ")"]),
    ]);
    const del = el("button", { class: "secondary" }, ["Remove"]);
    del.addEventListener("click", async () => {
      await api("/api/wifi/" + encodeURIComponent(net.ssid), "DELETE");
      renderWifiList();
    });
    item.appendChild(del);
    list.appendChild(item);
  });
}

document.getElementById("wifi-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  await api("/api/wifi", "POST", {
    ssid: form.ssid.value,
    password: form.password.value,
    priority: parseInt(form.priority.value, 10) || 0,
  });
  form.reset();
  renderWifiList();
});

document.getElementById("wifi-scan-btn").addEventListener("click", async () => {
  const results = await api("/api/wifi/scan");
  const datalist = document.getElementById("wifi-scan-results");
  datalist.innerHTML = "";
  results.forEach((net) => {
    datalist.appendChild(el("option", { value: net.ssid }));
  });
});

document.getElementById("mqtt-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  await api("/api/mqtt", "POST", {
    enabled: form.enabled.checked,
    host: form.host.value,
    port: parseInt(form.port.value, 10) || 1883,
    username: form.username.value,
    password: form.password.value,
    base_topic: form.base_topic.value,
    discovery_prefix: form.discovery_prefix.value,
  });
});

document.getElementById("system-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  await api("/api/system", "POST", {
    dmx_tx_pin: form.dmx_tx_pin.value,
    dmx_dir_pin_enabled: form.dmx_dir_pin_enabled.checked,
    dmx_dir_pin: form.dmx_dir_pin.value,
    hostname: form.hostname.value,
    ap_ssid: form.ap_ssid.value,
    ap_password: form.ap_password.value,
    ap_ip: form.ap_ip.value,
  });
});

function updateStaticIpFields() {
  const form = document.getElementById("staticip-form");
  const dhcp = form.sta_ip_mode.value === "dhcp";
  ["sta_static_ip", "sta_static_netmask", "sta_static_gateway", "sta_static_dns"].forEach((n) => {
    form[n].disabled = dhcp;
  });
}

document.getElementById("staticip-form").sta_ip_mode.addEventListener(
  "change",
  updateStaticIpFields
);

document.getElementById("staticip-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  await api("/api/system", "POST", {
    sta_ip_mode: form.sta_ip_mode.value,
    sta_static_ip: form.sta_static_ip.value,
    sta_static_netmask: form.sta_static_netmask.value,
    sta_static_gateway: form.sta_static_gateway.value,
    sta_static_dns: form.sta_static_dns.value,
  });
});

document.getElementById("mesh-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  await api("/api/mesh", "POST", {
    role: form.role.value,
    ssid: form.ssid.value,
    password: form.password.value,
  });
});

// ---- device manager view ----

function addChannelRow(offset) {
  const rows = document.getElementById("channel-rows");
  const row = el("div", { class: "channel-row" });
  row.appendChild(
    el("input", { type: "number", placeholder: "Offset", value: String(offset), min: "1", class: "ch-offset" })
  );
  row.appendChild(el("input", { type: "text", placeholder: "Name", class: "ch-name" }));
  const select = el("select", { class: "ch-type" }, [
    el("option", { value: "slider" }, ["Slider"]),
    el("option", { value: "button" }, ["Button (trigger)"]),
    el("option", { value: "button-momentary" }, ["Button (momentary)"]),
    el("option", { value: "button-switch" }, ["Button (switch)"]),
  ]);
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
  await api("/api/devices", "POST", {
    name: form.name.value,
    start_channel: parseInt(form.start_channel.value, 10),
    channels: channels,
  });
  form.reset();
  document.getElementById("channel-rows").innerHTML = "";
  renderDevices();
});

async function renderDevices() {
  const devices = await api("/api/devices");
  const list = document.getElementById("device-list");
  list.innerHTML = "";
  devices.forEach((device) => {
    const card = el("div", { class: "device-card" }, [
      el("h3", {}, [device.name + " (start ch. " + device.start_channel + ")"]),
    ]);
    device.channels.forEach((channel) => {
      card.appendChild(
        el("div", { class: "list-item" }, [
          el("span", {}, [channel.offset + ": " + channel.name + " (" + channel.type + ")"]),
        ])
      );
    });
    const del = el("button", { class: "secondary" }, ["Delete device"]);
    del.addEventListener("click", async () => {
      await api("/api/devices/" + device.id, "DELETE");
      renderDevices();
    });
    card.appendChild(del);
    list.appendChild(card);
  });
}

// ---- info view ----

async function renderInfo() {
  const info = await api("/api/info");
  document.getElementById("info-version").textContent = info.version;

  const authorLink = el(
    "a",
    { href: info.author.url, target: "_blank", rel: "noopener" },
    [info.author.name]
  );
  const authorDd = document.getElementById("info-author");
  authorDd.innerHTML = "";
  authorDd.appendChild(authorLink);

  const repoLink = el(
    "a",
    { href: info.repo, target: "_blank", rel: "noopener" },
    ["GitHub"]
  );
  const repoDd = document.getElementById("info-repo");
  repoDd.innerHTML = "";
  repoDd.appendChild(repoLink);

  const wikiDd = document.getElementById("info-wiki");
  wikiDd.innerHTML = "";
  wikiDd.appendChild(
    el("a", { href: info.wiki_online, target: "_blank", rel: "noopener" }, ["Online (GitHub)"])
  );
  wikiDd.appendChild(document.createTextNode(" · "));
  wikiDd.appendChild(el("a", { href: info.wiki_local, target: "_blank" }, ["Local copy"]));
}

switchView("home");
