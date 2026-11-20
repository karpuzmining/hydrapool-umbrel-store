const PALETTES = {
  neon: ["#3df0ff", "#ff3dbe", "#ffe14a", "#5dff8a", "#ff9a2e", "#b388ff", "#7dffa0"],
  hashdash: ["#3ba7ff", "#8b6cff", "#f2c14e", "#3dd68c", "#ff8a5b", "#d46bff", "#5eead4"],
};

function isHashdash() {
  return document.documentElement.dataset.theme === "hashdash";
}

function palette() {
  return isHashdash() ? PALETTES.hashdash : PALETTES.neon;
}

const CHART_RANGES = [
  { seconds: 3600, label: "Last 1h" },
  { seconds: 21600, label: "Last 6h" },
  { seconds: 86400, label: "Last 24h" },
  { seconds: 604800, label: "Last 7d" },
];

function readPref(key, fallback) {
  try {
    const value = localStorage.getItem(key);
    return value == null || value === "" ? fallback : value;
  } catch (error) {
    return fallback;
  }
}

function writePref(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch (error) {
    /* private mode can reject storage */
  }
}

let chartRange = Number(readPref("hydrapool-chart-range", "21600"));
let avgWindow = Number(readPref("hydrapool-avg-window", "300"));

const state = {
  meta: null,
  live: { users: [], history: [] },
  tab: "setup",
  tables: {
    overview: { query: "", group: true, idle: false },
    miners: { query: "", group: false, idle: true },
  },
};

const $ = (id) => document.getElementById(id);

function formatHashrate(value) {
  if (value == null || !Number.isFinite(value)) return "—";
  const units = ["H/s", "kH/s", "MH/s", "GH/s", "TH/s", "PH/s", "EH/s"];
  let amount = value;
  let index = 0;
  while (amount >= 1000 && index < units.length - 1) {
    amount /= 1000;
    index += 1;
  }
  const digits = amount >= 100 ? 0 : amount >= 10 ? 1 : 2;
  return `${amount.toFixed(digits)} ${units[index]}`;
}

function formatAgo(stamp) {
  if (!stamp) return "no shares";
  const delta = Math.max(0, Math.floor(Date.now() / 1000 - stamp));
  if (delta < 5) return "just now";
  if (delta < 60) return `${delta}s ago`;
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`;
  return `${Math.floor(delta / 86400)}d ago`;
}

function shortAddress(address) {
  if (!address || address.length <= 20) return address || "";
  return `${address.slice(0, 10)}…${address.slice(-6)}`;
}

function copyButton(text) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "copy-btn";
  button.textContent = "Copy";
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch (_error) {
      const area = document.createElement("textarea");
      area.value = text;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    button.textContent = "Copied";
    setTimeout(() => {
      button.textContent = "Copy";
    }, 1200);
  });
  return button;
}

function copyRow(label, value) {
  const row = document.createElement("div");
  row.className = "copy-row";
  const name = document.createElement("span");
  name.textContent = label;
  const code = document.createElement("code");
  code.textContent = value || "—";
  row.append(name, code, copyButton(value || ""));
  return row;
}

function showTab(name) {
  state.tab = name;
  document.querySelectorAll(".tab").forEach((button) => {
    button.setAttribute("aria-pressed", button.dataset.tab === name ? "true" : "false");
  });
  document.querySelectorAll(".view").forEach((view) => {
    view.hidden = view.id !== `view-${name}`;
  });
  if (name === "overview") drawCharts();
}

function setupMode() {
  const selected = document.querySelector('input[name="mode"]:checked');
  return selected ? selected.value : "solo";
}

function syncSetupVisibility() {
  const pplns = setupMode() === "pplns";
  $("pplns-fields").hidden = !pplns;
  $("address-label").textContent = pplns ? "Your operator address" : "Your payout address";
  const network = state.meta && state.meta.network_label ? state.meta.network_label : "this node";
  $("address-hint").textContent = pplns
    ? `This address receives a block only when no miner shares are in the window yet, plus any fee you set. Friends enter their own ${network} address as the miner username.`
    : `Every miner should use this ${network} address. Hydrapool pays the address in the username straight from the coinbase.`;
}

function fillForm(setup) {
  if (!setup) return;
  const mode = document.querySelector(`input[name="mode"][value="${setup.mode}"]`);
  if (mode) mode.checked = true;
  $("payout-address").value = setup.payout_address || "";
  $("fee-bps").value = setup.fee_bps ?? 0;
  $("fee-address").value = setup.fee_address || "";
  $("tailscale-host").value = setup.tailscale_host || "";
  $("difficulty-multiplier").value = setup.difficulty_multiplier ?? 1;
  $("pplns-ttl").value = setup.pplns_ttl_days ?? 7;
  $("start-difficulty").value = setup.start_difficulty ?? 1024;
  $("minimum-difficulty").value = setup.minimum_difficulty ?? 1;
  syncSetupVisibility();
}

function connectionCard() {
  const meta = state.meta || {};
  const setup = meta.setup;
  const lan = meta.lan_url || "stratum+tcp://umbrel.local:34533";
  const tail = setup && setup.tailscale_url ? setup.tailscale_url : "";
  const mode = setup ? setup.mode : "solo";
  const primaryUrl = mode === "pplns" && tail ? tail : lan;
  const user = setup ? `${setup.payout_address}.worker` : "your-bitcoin-address.worker";
  return { lan, tail, primaryUrl, user, password: "x", mode };
}

function renderStratum(target) {
  const card = connectionCard();
  target.replaceChildren();
  if (card.mode === "pplns") {
    target.append(
      copyRow("Tailnet", card.tail || "Add a Tailscale name in Setup"),
      copyRow("LAN", card.lan),
      copyRow("Your user", card.user),
      copyRow("Friend user", "their-bitcoin-address.worker"),
      copyRow("Password", card.password),
    );
  } else {
    target.append(
      copyRow("URL", card.lan),
      copyRow("Username", card.user),
      copyRow("Password", card.password),
    );
  }
}

function renderStatus() {
  const pill = $("pool-status");
  const text = $("pool-status-text");
  const configured = state.meta && state.meta.configured;
  const chain = state.live && state.live.bitcoin;
  const up = state.live && state.live.pool_up;
  const dash = isHashdash();
  pill.classList.remove("down", "wait");
  if (chain && chain.syncing) {
    pill.classList.add("wait");
    text.textContent = dash ? "Syncing" : "Node syncing";
  } else if (!configured) {
    pill.classList.add("wait");
    text.textContent = "Setup needed";
  } else if (!up) {
    pill.classList.add("down");
    text.textContent = dash ? "Offline" : "Pool offline";
  } else {
    text.textContent = dash ? "Online" : "Pool online";
  }
  const updated = $("last-update");
  if (updated) {
    const stamp = new Date().toLocaleString([], {
      year: "numeric",
      month: "numeric",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      second: "2-digit",
    });
    updated.textContent = `Last Update: ${stamp}`;
  }
}

function renderBanner() {
  const banner = $("bitcoin-banner");
  const bitcoin = state.meta && state.meta.bitcoin_problem;
  const chain = state.live && state.live.bitcoin;
  const arch = (state.meta && state.meta.cpu_arch) || "";
  const poolDown = state.live && state.live.pool_up === false;
  let text = "";
  if (chain && chain.syncing) {
    let percent = "";
    if (typeof chain.verification_progress === "number") {
      percent = ` (${(chain.verification_progress * 100).toFixed(1)}%)`;
    }
    text = `Bitcoin node syncing${percent}. The pool waits for a block template until the node finishes.`;
  } else {
    text = bitcoin || "";
  }
  if (!text && poolDown && /aarch64|arm64/i.test(arch)) {
    text = "This Umbrel is arm64. The pool image is 64-bit Intel/AMD only, so stratum stays down. The dashboard is still available.";
  }
  banner.hidden = !text;
  banner.textContent = text;
}

function setRate(id, value) {
  const node = $(id);
  node.replaceChildren();
  const formatted = formatHashrate(value);
  const split = formatted.lastIndexOf(" ");
  if (split <= 0) {
    node.textContent = formatted;
    return;
  }
  const amount = document.createElement("span");
  amount.className = "rate";
  amount.textContent = formatted.slice(0, split);
  const unit = document.createElement("span");
  unit.className = "unit";
  unit.textContent = formatted.slice(split + 1);
  node.append(amount, unit);
}

function renderTiles() {
  const live = state.live || {};
  setRate("hash-5m", live.hashrate_5m);
  setRate("hash-1h", live.hashrate_1h);
  $("hash-5m-note").textContent = live.warming_up ? "Warming up" : "Trailing five minutes";
  $("active-users").textContent = String(live.active_users || 0);
  $("active-workers").textContent = String(live.active_workers || 0);
  $("share-note").textContent = `Accepted ${live.accepted || 0} · rejected ${live.rejected || 0}`;
}

function filteredRows(which) {
  const prefs = state.tables[which];
  const query = prefs.query.trim().toLowerCase();
  const users = (state.live && state.live.users) || [];
  const payout = state.meta && state.meta.setup ? state.meta.setup.payout_address : "";
  const solo = state.meta && state.meta.setup && state.meta.setup.mode === "solo";
  const flat = [];
  users.forEach((user) => {
    user.workers.forEach((worker) => {
      if (!prefs.idle && worker.idle) return;
      const haystack = `${worker.address} ${worker.worker}`.toLowerCase();
      if (query && !haystack.includes(query)) return;
      flat.push({
        ...worker,
        foreign: solo && payout && worker.address !== payout,
      });
    });
  });
  return flat;
}

function statusLabel(worker) {
  if (worker.foreign) return { text: "Other address", className: "status-foreign" };
  if (worker.idle || !worker.active) return { text: "Idle", className: "status-idle" };
  return { text: "Active", className: "status-on" };
}

function renderTable(which) {
  const body = $(`table-${which}`);
  const prefs = state.tables[which];
  const rows = filteredRows(which);
  body.replaceChildren();
  if (!rows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 7;
    td.className = "empty";
    td.textContent = state.meta && state.meta.configured
      ? "No workers match. Point a miner at the stratum URL, or turn on Show idle."
      : "Finish setup, then point a miner at this Umbrel.";
    tr.append(td);
    body.append(tr);
    return;
  }
  if (!prefs.group) {
    rows.forEach((worker, index) => body.append(workerRow(worker, index + 1)));
    return;
  }
  const groups = [];
  rows.forEach((worker) => {
    let group = groups.find((item) => item.address === worker.address);
    if (!group) {
      group = { address: worker.address, workers: [] };
      groups.push(group);
    }
    group.workers.push(worker);
  });
  let rank = 1;
  groups.forEach((group) => {
    const header = document.createElement("tr");
    header.className = "user-row";
    const cell = document.createElement("td");
    cell.colSpan = 7;
    const rate = group.workers.reduce((sum, worker) => sum + (worker.hashrate_5m || 0), 0);
    cell.textContent = `${shortAddress(group.address)} · ${formatHashrate(rate)} · ${group.workers.length} worker${group.workers.length === 1 ? "" : "s"}`;
    cell.title = group.address;
    header.append(cell);
    body.append(header);
    group.workers.forEach((worker) => {
      body.append(workerRow(worker, rank));
      rank += 1;
    });
  });
}

function workerRow(worker, rank) {
  const tr = document.createElement("tr");
  const status = statusLabel(worker);
  const values = [
    String(rank),
    worker.worker,
    shortAddress(worker.address),
    formatHashrate(worker.hashrate_5m),
    worker.best_share ? String(worker.best_share) : "—",
    formatAgo(worker.last_share),
    status.text,
  ];
  values.forEach((value, index) => {
    const td = document.createElement("td");
    td.textContent = value;
    if (index === 2) td.title = worker.address;
    if (index === 0 || index === 3 || index === 4) td.classList.add("num");
    if (index === 6) td.classList.add(status.className);
    tr.append(td);
  });
  return tr;
}

function drawCharts() {
  drawHistory($("history-chart"));
  drawDonut($("share-donut"), $("share-legend"));
}

function canvasSize(canvas) {
  const width = canvas.clientWidth || 320;
  const height = canvas.id === "share-donut" ? 180 : canvas.id === "history-chart" ? 280 : 220;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.floor(width * ratio);
  canvas.height = Math.floor(height * ratio);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { ctx, width, height };
}

function historySpan() {
  return Number((state.live && state.live.history_span) || 0);
}

function windowReady(seconds) {
  return historySpan() >= seconds * 0.9;
}

function chosenChartRange() {
  const ready = CHART_RANGES.filter((item) => windowReady(item.seconds));
  const wanted = CHART_RANGES.find((item) => item.seconds === chartRange);
  if (wanted && windowReady(wanted.seconds)) return wanted;
  return ready.length ? ready[ready.length - 1] : null;
}

function formatCovered(seconds) {
  if (seconds >= 86400) return `Last ${Math.max(1, Math.round(seconds / 86400))}d`;
  if (seconds >= 3600) return `Last ${Math.max(1, Math.round(seconds / 3600))}h`;
  if (seconds >= 60) return `Last ${Math.max(1, Math.round(seconds / 60))}m`;
  return "Last few seconds";
}

function chartPoints() {
  const all = (state.live && state.live.history) || [];
  if (all.length < 2) return all;
  const chosen = chosenChartRange();
  if (!chosen) return all;
  const end = all[all.length - 1].t;
  const visible = all.filter((point) => point.t >= end - chosen.seconds);
  return visible.length >= 2 ? visible : all;
}

function smoothPoints(points) {
  if (points.length < 5) return points;
  const radius = 2;
  return points.map((point, index) => {
    let sum = 0;
    let count = 0;
    for (let offset = Math.max(0, index - radius); offset <= Math.min(points.length - 1, index + radius); offset += 1) {
      sum += points[offset].hashrate;
      count += 1;
    }
    return { t: point.t, hashrate: sum / count };
  });
}

function renderHistory() {
  const span = historySpan();
  const chosen = chosenChartRange();
  const label = $("history-range-label");
  if (label) label.textContent = chosen ? chosen.label : formatCovered(span);
  document.querySelectorAll("#chart-range button").forEach((button) => {
    const seconds = Number(button.dataset.range);
    button.disabled = !windowReady(seconds);
    button.setAttribute("aria-pressed", chosen && chosen.seconds === seconds ? "true" : "false");
  });
  document.querySelectorAll("#avg-window button").forEach((button) => {
    const seconds = Number(button.dataset.avg);
    const ready = windowReady(seconds);
    button.disabled = !ready;
    button.setAttribute("aria-pressed", ready && seconds === avgWindow ? "true" : "false");
  });
  const rates = (state.live && state.live.hashrates) || {};
  const rate = windowReady(avgWindow) ? rates[String(avgWindow)] : null;
  setRate("actual-hashrate", typeof rate === "number" ? rate : null);
}

function bindHistory() {
  document.querySelectorAll("#avg-window button").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.disabled) return;
      avgWindow = Number(button.dataset.avg);
      writePref("hydrapool-avg-window", String(avgWindow));
      renderHistory();
    });
  });
  document.querySelectorAll("#chart-range button").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.disabled) return;
      chartRange = Number(button.dataset.range);
      writePref("hydrapool-chart-range", String(chartRange));
      renderHistory();
      if (state.tab === "overview") drawCharts();
    });
  });
}

function drawHistory(canvas) {
  const dash = isHashdash();
  const { ctx, width, height } = canvasSize(canvas);
  ctx.clearRect(0, 0, width, height);
  const padL = 52;
  const padR = 12;
  const padT = 22;
  const padB = 26;
  const plotW = Math.max(10, width - padL - padR);
  const plotH = Math.max(10, height - padT - padB);
  const points = smoothPoints(chartPoints());
  const max = points.length ? Math.max(...points.map((point) => point.hashrate), 1) : 1;
  const units = ["H/s", "kH/s", "MH/s", "GH/s", "TH/s", "PH/s", "EH/s"];
  let unitIndex = 0;
  let scaledMax = max;
  while (scaledMax >= 1000 && unitIndex < units.length - 1) {
    scaledMax /= 1000;
    unitIndex += 1;
  }
  const scale = 1000 ** unitIndex;
  const grid = dash ? "rgba(255, 255, 255, 0.08)" : "rgba(61, 240, 255, 0.16)";
  const ink = dash ? "rgba(226, 232, 240, 0.7)" : "#8ea4bc";
  const line = "#3ba7ff";
  const lime = "#c6ff4a";
  ctx.strokeStyle = grid;
  ctx.fillStyle = ink;
  ctx.lineWidth = 1;
  ctx.font = dash ? "11px Segoe UI, Helvetica Neue, sans-serif" : "11px Share Tech Mono, monospace";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (let i = 0; i < 5; i += 1) {
    const y = padT + (plotH / 4) * i;
    ctx.beginPath();
    ctx.moveTo(padL, y);
    ctx.lineTo(width - padR, y);
    ctx.stroke();
    const value = (max * (1 - i / 4)) / scale;
    const digits = value >= 100 || value === 0 ? 0 : value >= 10 ? 1 : 2;
    ctx.fillText(value.toFixed(digits), padL - 6, y);
  }
  ctx.fillStyle = dash ? line : ink;
  ctx.textAlign = "left";
  ctx.fillText(`Hashrate (${units[unitIndex]})`, padL, 12);
  if (points.length < 2) {
    ctx.fillStyle = ink;
    ctx.font = dash ? "13px Segoe UI, Helvetica Neue, sans-serif" : "13px Share Tech Mono, monospace";
    ctx.fillText("Waiting for shares", padL + 8, padT + plotH / 2);
    return;
  }
  const minT = points[0].t;
  const maxT = points[points.length - 1].t || minT + 1;
  const coords = points.map((point) => {
    const x = padL + ((point.t - minT) / (maxT - minT)) * plotW;
    const y = padT + plotH - (point.hashrate / max) * plotH;
    return [x, y];
  });
  const traceLine = () => {
    ctx.beginPath();
    coords.forEach(([x, y], index) => {
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
  };
  if (!dash) {
    ctx.save();
    traceLine();
    ctx.lineTo(coords[coords.length - 1][0], padT + plotH);
    ctx.lineTo(coords[0][0], padT + plotH);
    ctx.closePath();
    ctx.clip();
    const fill = ctx.createLinearGradient(padL, 0, padL + plotW, 0);
    fill.addColorStop(0, "rgba(255, 176, 71, 0.34)");
    fill.addColorStop(0.58, "rgba(255, 61, 190, 0.34)");
    fill.addColorStop(1, "rgba(61, 240, 255, 0.34)");
    ctx.fillStyle = fill;
    ctx.fillRect(padL, padT, plotW, plotH);
    const fade = ctx.createLinearGradient(0, padT, 0, padT + plotH);
    fade.addColorStop(0, "rgba(0, 0, 0, 1)");
    fade.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.globalCompositeOperation = "destination-in";
    ctx.fillStyle = fade;
    ctx.fillRect(padL, padT, plotW, plotH);
    ctx.restore();
  }
  traceLine();
  ctx.shadowBlur = 0;
  ctx.shadowColor = "transparent";
  if (!dash) {
    ctx.strokeStyle = lime;
    ctx.lineWidth = 6;
    ctx.shadowColor = lime;
    ctx.shadowBlur = 8;
    ctx.stroke();
    ctx.shadowBlur = 0;
    const stroke = ctx.createLinearGradient(padL, 0, padL + plotW, 0);
    stroke.addColorStop(0, "#ffb047");
    stroke.addColorStop(0.58, "#ff3dbe");
    stroke.addColorStop(1, "#3df0ff");
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 3.5;
  } else {
    ctx.strokeStyle = line;
    ctx.lineWidth = 2;
  }
  ctx.stroke();
  if (dash) {
    ctx.lineTo(coords[coords.length - 1][0], padT + plotH);
    ctx.lineTo(coords[0][0], padT + plotH);
    ctx.closePath();
    const fill = ctx.createLinearGradient(0, padT, 0, padT + plotH);
    fill.addColorStop(0, "rgba(59, 167, 255, 0.38)");
    fill.addColorStop(1, "rgba(59, 167, 255, 0.02)");
    ctx.fillStyle = fill;
    ctx.shadowBlur = 0;
    ctx.fill();
  }
  ctx.fillStyle = ink;
  ctx.font = dash ? "11px Segoe UI, Helvetica Neue, sans-serif" : "11px Share Tech Mono, monospace";
  ctx.textAlign = "center";
  ctx.textBaseline = "alphabetic";
  const marks = [0, Math.floor(points.length / 2), points.length - 1];
  marks.forEach((index, mark) => {
    if (mark > 0 && marks[mark] === marks[mark - 1]) return;
    const point = points[index];
    const label = new Date(point.t * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    ctx.fillText(label, coords[index][0], height - 6);
  });
}

function drawDonut(canvas, legend) {
  const { ctx, width, height } = canvasSize(canvas);
  ctx.clearRect(0, 0, width, height);
  const users = ((state.live && state.live.users) || [])
    .filter((user) => user.hashrate_5m > 0 && user.active)
    .slice()
    .sort((a, b) => b.hashrate_5m - a.hashrate_5m);
  const colors = palette();
  const dash = isHashdash();
  const total = users.reduce((sum, user) => sum + user.hashrate_5m, 0);
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) / 2 - (dash ? 14 : 8);
  ctx.lineWidth = dash ? 28 : 18;
  ctx.lineCap = "butt";
  ctx.strokeStyle = dash ? "rgba(255, 255, 255, 0.06)" : "rgba(61, 240, 255, 0.12)";
  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI * 2);
  ctx.stroke();
  legend.replaceChildren();
  if (total <= 0) {
    const item = document.createElement("li");
    item.textContent = "No share yet";
    legend.append(item);
    return;
  }
  let angle = -Math.PI / 2;
  users.slice(0, 6).forEach((user, index) => {
    const slice = (user.hashrate_5m / total) * Math.PI * 2;
    ctx.beginPath();
    ctx.strokeStyle = colors[index % colors.length];
    ctx.shadowColor = dash ? "transparent" : ctx.strokeStyle;
    ctx.shadowBlur = dash ? 0 : 8;
    ctx.arc(cx, cy, radius, angle, angle + slice);
    ctx.stroke();
    angle += slice;
    const item = document.createElement("li");
    const label = document.createElement("span");
    const swatch = document.createElement("i");
    swatch.className = "swatch";
    swatch.style.background = colors[index % colors.length];
    label.append(swatch, document.createTextNode(shortAddress(user.address)));
    const value = document.createElement("span");
    value.textContent = `${Math.round((user.hashrate_5m / total) * 100)}%`;
    item.append(label, value);
    legend.append(item);
  });
}

function renderConnect() {
  const card = connectionCard();
  const network = state.meta && state.meta.network_label ? state.meta.network_label : "the node network";
  const modeLabel = card.mode === "pplns" ? "PPLNS" : "Solo";
  $("connect-network").textContent = `${network} · ${modeLabel}`;
  $("connect-title").textContent = card.mode === "pplns" ? "Share the pool" : "Point a miner";
  renderStratum($("connect-stratum"));
  const steps = $("connect-steps");
  steps.replaceChildren();
  const port = (state.meta && state.meta.stratum_port) || 34533;
  const lines = card.mode === "pplns"
    ? [
        `Install Umbrel's Tailscale app and sign this Umbrel into your tailnet. That app uses the host network, and Hydrapool publishes port ${port} on the host, so tailnet peers can reach the pool without extra port forwarding.`,
        "Copy this Umbrel's MagicDNS name from the Tailscale app and paste it into Setup. It looks like umbrel.tailnet-name.ts.net.",
        `Send friends ${card.tail || "the tailnet URL from Setup"}. Miners on the same LAN can keep using ${card.lan}.`,
        `Each friend sets the username to their own ${network} Bitcoin address, a dot, and a worker name. The password is x.`,
        "A found block pays those addresses from the coinbase. You never hold their bitcoin. Your address receives the optional fee and any reward that arrives before the first shares.",
      ]
    : [
        `On the same LAN, use ${card.lan}. If a miner cannot resolve ${state.meta ? state.meta.device_domain : "umbrel.local"}, use this Umbrel's LAN IP with port ${port}.`,
        "Set the username to your payout address, a dot, and a worker name, for example the value copied above.",
        "Set the password to x. Hydrapool does not use the password for payouts.",
        "Every machine should use your address. A different address is paid directly, and the miners table marks it as another address.",
      ];
  lines.forEach((line) => {
    const item = document.createElement("li");
    item.textContent = line;
    steps.append(item);
  });
  const payout = $("payout-copy");
  payout.replaceChildren();
  const paragraphs = card.mode === "pplns"
    ? [
        "PPLNS means pay per last N shares. Hydrapool weights recent accepted shares by difficulty and writes one coinbase output per address.",
        "The window multiplier and share retention on the setup tab are the defaults from Hydrapool: multiplier 1 and 7 days. Raise the multiplier only if you know you want a longer share window.",
        "Switching back to solo does not delete old shares. It changes who you tell miners to use, and it drops the pool fee.",
      ]
    : [
        "Solo on this app is a private pool with one payout address. It still runs Hydrapool's standalone pool mode, so the coinbase is built by the pool and paid to the username address.",
        "There is no pool fee in solo mode. Nothing is sent to a developer or operator address unless you later switch to PPLNS and set one.",
        "You can switch to a shared PPLNS pool later without reinstalling. The pool restarts when you save.",
      ];
  paragraphs.forEach((text) => {
    const p = document.createElement("p");
    p.textContent = text;
    payout.append(p);
  });
}

function render() {
  renderBanner();
  renderStatus();
  renderTiles();
  renderTable("overview");
  renderTable("miners");
  renderConnect();
  renderHistory();
  if (!document.getElementById("view-overview").hidden) drawCharts();
}

async function refreshMeta() {
  const response = await fetch("/api/meta", { cache: "no-store" });
  state.meta = await response.json();
  if (!state.formDirty) fillForm(state.meta.setup);
  if (!state.tabChosen) showTab(state.meta.configured ? "overview" : "setup");
  render();
}

async function refreshLive() {
  const response = await fetch("/api/live", { cache: "no-store" });
  state.live = await response.json();
  render();
}

function bindTable(which) {
  $(`search-${which}`).addEventListener("input", (event) => {
    state.tables[which].query = event.target.value;
    renderTable(which);
  });
  $(`group-${which}`).addEventListener("click", (event) => {
    state.tables[which].group = !state.tables[which].group;
    event.currentTarget.setAttribute("aria-pressed", state.tables[which].group ? "true" : "false");
    renderTable(which);
  });
  $(`idle-${which}`).addEventListener("click", (event) => {
    state.tables[which].idle = !state.tables[which].idle;
    event.currentTarget.setAttribute("aria-pressed", state.tables[which].idle ? "true" : "false");
    renderTable(which);
  });
}

function bind() {
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => {
      state.tabChosen = true;
      showTab(button.dataset.tab);
      render();
    });
  });
  document.querySelectorAll('input[name="mode"]').forEach((input) => {
    input.addEventListener("change", () => {
      state.formDirty = true;
      syncSetupVisibility();
    });
  });
  ["payout-address", "fee-bps", "fee-address", "tailscale-host"].forEach((id) => {
    $(id).addEventListener("input", () => {
      state.formDirty = true;
    });
  });
  bindTable("overview");
  bindTable("miners");
  $("setup-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const error = $("setup-error");
    const ok = $("setup-ok");
    error.hidden = true;
    ok.hidden = true;
    const payload = {
      mode: setupMode(),
      payout_address: $("payout-address").value.trim(),
      fee_bps: Number($("fee-bps").value || 0),
      fee_address: $("fee-address").value.trim(),
      tailscale_host: $("tailscale-host").value.trim(),
      difficulty_multiplier: Number($("difficulty-multiplier").value || 1),
      pplns_ttl_days: Number($("pplns-ttl").value || 7),
      start_difficulty: Number($("start-difficulty").value || 1024),
      minimum_difficulty: Number($("minimum-difficulty").value || 1),
    };
    const response = await fetch("/api/setup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    if (!response.ok) {
      error.hidden = false;
      error.textContent = body.error || "Could not save setup.";
      return;
    }
    state.formDirty = false;
    ok.hidden = false;
    ok.textContent = payload.mode === "pplns"
      ? "PPLNS pool saved. Hydrapool is restarting with the new payout rules."
      : "Solo pool saved. Hydrapool is restarting. Point miners at the LAN URL.";
    await refreshMeta();
    state.tabChosen = true;
    showTab("connect");
    render();
  });
  window.addEventListener("resize", () => {
    if (state.tab === "overview") drawCharts();
  });
}

function applyTheme(theme, persist) {
  const next = theme === "hashdash" ? "hashdash" : "neon";
  document.documentElement.dataset.theme = next;
  const neon = $("theme-neon");
  const dash = $("theme-hashdash");
  if (neon) neon.setAttribute("aria-pressed", next === "neon" ? "true" : "false");
  if (dash) dash.setAttribute("aria-pressed", next === "hashdash" ? "true" : "false");
  if (persist) {
    try {
      localStorage.setItem("hydrapool-theme", next);
    } catch (error) {
      /* private mode can reject storage */
    }
  }
  renderStatus();
  if (state.tab === "overview") drawCharts();
}

function bindTheme() {
  document.querySelectorAll("[data-theme-choice]").forEach((button) => {
    button.addEventListener("click", () => applyTheme(button.dataset.themeChoice, true));
  });
  applyTheme(document.documentElement.dataset.theme, false);
}

function bindExperimental() {
  const note = $("experimental-note");
  const button = $("experimental-dismiss");
  if (!note || !button) return;
  button.addEventListener("click", () => {
    document.documentElement.dataset.experimental = "hidden";
    try {
      localStorage.setItem("hydrapool-experimental-dismissed", "1");
    } catch (error) {
      /* private mode can reject storage */
    }
  });
}

bindHistory();
bindExperimental();
bindTheme();
bind();
syncSetupVisibility();
const requestedTab = new URLSearchParams(location.search).get("tab");
if (requestedTab && document.getElementById(`view-${requestedTab}`)) {
  state.tabChosen = true;
  showTab(requestedTab);
}
refreshMeta().catch((error) => {
  $("bitcoin-banner").hidden = false;
  $("bitcoin-banner").textContent = `Dashboard could not load: ${error.message}`;
});
refreshLive().catch(() => {});
setInterval(() => {
  refreshLive().catch(() => {});
}, 5000);
setInterval(() => {
  refreshMeta().catch(() => {});
}, 20000);
