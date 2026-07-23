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
  if (name === "index") renderIndex();
  if (name === "settings") renderSettings();
  if (name === "devices") renderDevices();
}

document.querySelectorAll(".nav-btn").forEach((btn) => {
  btn.addEventListener("click", () => switchView(btn.dataset.view));
});

// ---- index view: live channel control ----

async function renderIndex() {
  const container = document.getElementById("view-index");
  container.innerHTML = "";
  const devices = await api("/api/devices");
  if (devices.length === 0) {
    container.appendChild(el("p", {}, ["Aucun device. Ajoute-en un depuis Device manager."]));
    return;
  }
  devices.forEach((device) => {
    const card = el("div", { class: "device-card" }, [el("h3", {}, [device.name])]);
    device.channels.forEach((channel) => {
      const row = el("div", { class: "channel-control" });
      row.appendChild(el("label", {}, [channel.name]));
      if (channel.type === "slider") {
        const input = el("input", {
          type: "range",
          min: "0",
          max: "255",
          value: "0",
        });
        const output = el("span", {}, ["0"]);
        input.addEventListener("input", () => {
          output.textContent = input.value;
        });
        input.addEventListener("change", () => {
          api("/api/devices/" + device.id + "/channel/" + channel.offset, "POST", {
            value: parseInt(input.value, 10),
          });
        });
        row.appendChild(input);
        row.appendChild(output);
      } else {
        const button = el("button", {}, ["Trigger"]);
        button.addEventListener("click", () => {
          api("/api/devices/" + device.id + "/channel/" + channel.offset, "POST", {
            value: 255,
          });
        });
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
  systemForm.dmx_dir_pin.value = system.dmx_dir_pin || "";
  systemForm.hostname.value = system.hostname || "";
  systemForm.ap_ssid.value = system.ap_ssid || "";
  systemForm.ap_password.value = system.ap_password || "";
  systemForm.ap_ip.value = system.ap_ip || "";
}

async function renderWifiList() {
  const networks = await api("/api/wifi");
  const list = document.getElementById("wifi-list");
  list.innerHTML = "";
  networks.forEach((net) => {
    const item = el("div", { class: "list-item" }, [
      el("span", {}, [net.ssid + " (priorité " + net.priority + ")"]),
    ]);
    const del = el("button", { class: "secondary" }, ["Supprimer"]);
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
    dmx_dir_pin: form.dmx_dir_pin.value,
    hostname: form.hostname.value,
    ap_ssid: form.ap_ssid.value,
    ap_password: form.ap_password.value,
    ap_ip: form.ap_ip.value,
  });
});

// ---- device manager view ----

function addChannelRow(offset) {
  const rows = document.getElementById("channel-rows");
  const row = el("div", { class: "channel-row" });
  row.appendChild(
    el("input", { type: "number", placeholder: "Offset", value: String(offset), min: "1", class: "ch-offset" })
  );
  row.appendChild(el("input", { type: "text", placeholder: "Nom", class: "ch-name" }));
  const select = el("select", { class: "ch-type" }, [
    el("option", { value: "slider" }, ["Slider"]),
    el("option", { value: "button" }, ["Button"]),
  ]);
  row.appendChild(select);
  const removeBtn = el("button", { type: "button", class: "secondary" }, ["Retirer"]);
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
    const del = el("button", { class: "secondary" }, ["Supprimer le device"]);
    del.addEventListener("click", async () => {
      await api("/api/devices/" + device.id, "DELETE");
      renderDevices();
    });
    card.appendChild(del);
    list.appendChild(card);
  });
}

switchView("index");
