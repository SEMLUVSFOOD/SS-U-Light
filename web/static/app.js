// U-Light bridge front-end. No framework, no build step — edit and reload.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const ui = { color: "pink", rgb: "#ff5fc8", fx: "solid", speed: 5, plan: "timing", confirmed: [] };

async function api(path, data) {
  const opts = data instanceof FormData ? { method: "POST", body: data }
    : data !== undefined ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }
    : {};
  try {
    const r = await fetch(path, opts);
    return await r.json();
  } catch (e) {
    toast("Can't reach the Pi — is it on the same Wi-Fi?");
    return { ok: false };
  }
}

let toastTimer;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 2600);
}

// ---------- hero preview ----------
function darken(hex, f = 0.55) {
  const n = parseInt(hex.slice(1), 16);
  const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map(v => Math.round(v * f));
  return "#" + c.map(v => v.toString(16).padStart(2, "0")).join("");
}
function preview() {
  const root = document.documentElement.style;
  const off = ui.color === "off";
  const glow = off ? "#3a3340" : ui.rgb;
  root.setProperty("--glow", glow);
  root.setProperty("--glow-deep", darken(glow));
  const orb = $("#orb");
  orb.className = "orb" + (off ? " off" : "") + (ui.fx !== "solid" && !off ? " fx-" + ui.fx : "");
  // speed 1 (slow) … 10 (fast) — mirrors web/engine.py roughly
  const base = { strobe: 0.9, rainbow: 2.2, pulse: 3.0 }[ui.fx] || 1;
  orb.style.setProperty("--fx-dur", Math.max(0.25, (base / ui.speed) * 2) * (ui.fx === "strobe" ? 2 : 1) + "s");
  $("#now-color").textContent = ui.fx === "rainbow" ? "rainbow" : ui.color;
  const mapped = ui.fx === "rainbow" || ui.confirmed.includes(ui.color);
  $("#now-mode").textContent = (ui.fx !== "solid" && ui.fx !== "rainbow" ? " · " + ui.fx : "") + (mapped ? "" : " · preview only — no code yet");
  $$(".sw").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.color === ui.color)));
  $$(".seg button").forEach(b => b.setAttribute("aria-checked", String(b.dataset.fx === ui.fx)));
  $("#speed").value = ui.speed;
  $("#speed-out").textContent = ui.speed;
}

async function sendCurrent() {
  const r = ui.fx === "solid" && ui.color !== "off"
    ? await api("/api/color", { id: ui.color })
    : ui.color === "off" ? await api("/api/color", { id: "off" })
    : await api("/api/effect", { mode: ui.fx, color: ui.color, speed: ui.speed });
  if (r.unmapped) toast(r.error);
  else if (r.ok) toast(r.tx && r.tx.mock ? "Sent (mock — nothing transmitted)" : "Sent ✨");
  else if (r.error) toast(r.error);
  refresh();
}

// ---------- control tab ----------
$$(".sw").forEach(b => b.addEventListener("click", () => {
  ui.color = b.dataset.color; ui.rgb = b.dataset.rgb;
  if (ui.fx === "rainbow") ui.fx = "solid";
  preview(); sendCurrent();
}));
$("#picker").addEventListener("input", e => { ui.rgb = e.target.value; preview(); });
$("#picker").addEventListener("change", async e => {
  // snap to the nearest colour the stick actually knows
  const r = await api("/api/color", { hex: e.target.value });
  const sw = $(`.sw[data-color="${r.id}"]`);
  if (sw) { ui.color = r.id; ui.rgb = sw.dataset.rgb; preview(); }
  toast(r.unmapped ? r.error : `Closest stick colour: ${r.id}`);
});
$$(".seg button").forEach(b => b.addEventListener("click", () => { ui.fx = b.dataset.fx; preview(); }));
$("#speed").addEventListener("input", e => { ui.speed = +e.target.value; preview(); });
$("#go").addEventListener("click", sendCurrent);
$("#stop").addEventListener("click", async () => { await api("/api/stop", {}); toast("Stopped"); });
$$(".preset").forEach(b => b.addEventListener("click", () => {
  const p = JSON.parse(b.dataset.preset);
  ui.color = p.color; ui.fx = p.fx; ui.speed = p.speed;
  ui.rgb = $(`.sw[data-color="${p.color}"]`).dataset.rgb;
  preview(); sendCurrent();
}));

// ---------- tabs ----------
function showTab(id) {
  $$(".tabs [role=tab]").forEach(t => {
    const on = t.id === id;
    t.setAttribute("aria-selected", String(on));
    $("#" + t.getAttribute("aria-controls")).hidden = !on;
  });
  document.body.dataset.tab = id;
  try { localStorage.setItem("ulight-tab", id); } catch (e) { /* private mode */ }
}
$$(".tabs [role=tab]").forEach(t => t.addEventListener("click", () => showTab(t.id)));

// ---------- discovery ----------
$$(".plan").forEach(b => b.addEventListener("click", () => {
  ui.plan = b.dataset.plan;
  $$(".plan").forEach(x => x.setAttribute("aria-checked", String(x === b)));
}));
$("#dwell").addEventListener("input", e => { $("#dwell-out").textContent = (e.target.value / 1000).toFixed(1) + " s"; });
$("#d-start").addEventListener("click", async () => {
  if (ui.plan === "learn") toast("Now switch the stick ON!");
  await api("/api/discovery/start", { plan: ui.plan, dwell_ms: +$("#dwell").value, start: Math.max(0, (+$("#d-from").value || 1) - 1) });
  refresh();
});
$("#d-pause").addEventListener("click", () => api("/api/discovery/pause", {}).then(refresh));
$("#d-prev").addEventListener("click", () => api("/api/discovery/step", { dir: -1 }).then(refresh));
$("#d-next").addEventListener("click", () => api("/api/discovery/step", { dir: 1 }).then(refresh));
$("#d-replay").addEventListener("click", () => api("/api/discovery/replay", {}).then(refresh));
$("#d-hit").addEventListener("click", async () => {
  const r = await api("/api/discovery/hit", {});
  if (r.ok) { navigator.vibrate?.(60); toast("Logged to codes.json — paused. Bracket it with ◀︎ ▶︎"); }
  refresh();
});

function drawWave(pulses) {
  const svg = $("#d-wave");
  if (!pulses || !pulses.length) { svg.innerHTML = ""; return; }
  // compress long sync gaps so the bits stay readable
  const w = pulses.map(([, us]) => Math.min(us, 2500));
  const total = w.reduce((a, b) => a + b, 0);
  let x = 0, d = "M0 34";
  pulses.forEach(([lvl], i) => {
    const y = lvl ? 6 : 34;
    d += ` L${x.toFixed(1)} ${y}`;
    x += (w[i] / total) * 300;
    d += ` L${x.toFixed(1)} ${y}`;
  });
  svg.innerHTML = `<path d="${d}" fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke"/>`;
}

// ---------- codes tab ----------
function candLine(c) { return c ? `<b>${esc(c.label)}</b>` : "—"; }
function esc(s) { return String(s).replace(/[&<>"]/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch])); }
const options = $("#action-options").innerHTML;

function codeItem(c, extra = "") {
  const li = document.createElement("li");
  li.innerHTML = `${extra}${candLine(c)}
    <div class="acts"><button class="btn" data-act="send">Send</button>
    <select aria-label="Map to button">${options}</select></div>`;
  $("[data-act=send]", li).addEventListener("click", () => api("/api/codes/send", { candidate: c }).then(r => toast(r.ok ? "Sent" : r.error)));
  $("select", li).addEventListener("change", async e => {
    if (!e.target.value) return;
    await api("/api/codes/confirm", { action: e.target.value, candidate: c });
    toast(`Mapped to ${e.target.value}`); refresh();
  });
  return li;
}

let lastHitsKey = "", lastImportsKey = "";
function renderCodes(s) {
  const hitsKey = JSON.stringify(s.hits.map(h => h.ts + h.candidate.id));
  if (hitsKey !== lastHitsKey) {           // don't rebuild while someone's using a <select>
    lastHitsKey = hitsKey;
    const ul = $("#hits"); ul.innerHTML = "";
    if (!s.hits.length) ul.innerHTML = '<li class="muted">No hits yet. Go to Discover.</li>';
    s.hits.forEach(h => {
      ul.append(codeItem(h.candidate, `<div class="muted">${esc(h.ts)}</div>`));
      if (h.previous) ul.append(codeItem(h.previous, '<div class="muted">↳ the guess just before</div>'));
    });
  }
  const importsKey = JSON.stringify(s.imports.map(c => c.id));
  if (importsKey !== lastImportsKey) {
    lastImportsKey = importsKey;
    const ul = $("#imports"); ul.innerHTML = "";
    s.imports.forEach(c => ul.append(codeItem(c)));
  }
  $("#confirmed").innerHTML = s.actions.map(a =>
    `<span class="chip ${s.confirmed.includes(a) ? "on" : ""}">${esc(a.replace("fx_", "fx: "))}</span>`).join("");
  $("#txlog").innerHTML = s.tx.map(t =>
    `<li>${t.ok ? "✓" : "✗"} ${t.mock ? "[mock] " : ""}${esc(t.summary)}${t.error ? "<br>" + esc(t.error) : ""}</li>`).join("")
    || '<li class="muted">Nothing sent yet.</li>';
}

$("#import").addEventListener("submit", async e => {
  e.preventDefault();
  const r = await api("/api/import", new FormData(e.target));
  toast(r.ok ? `Imported ${r.imported} candidate(s)` : r.error);
  refresh();
});
$("#tone").addEventListener("click", async () => {
  const r = await api("/api/tone", { seconds: 1 });
  toast(r.ok ? (r.tx.mock ? "Tone (mock)" : "Tone sent — check your receiver") : (r.tx?.error || "Tone failed"));
  refresh();
});

// ---------- polling ----------
async function refresh() {
  const s = await api("/api/state");
  if (!s.radio) return;
  const pill = $("#radio");
  pill.textContent = s.radio.mock ? "MOCK radio" : "LIVE 433.92";
  pill.className = "pill " + (s.radio.mock ? "mock" : "live");
  ui.confirmed = s.confirmed;
  $$(".sw").forEach(b => b.classList.toggle("unmapped", !s.confirmed.includes(b.dataset.color)));
  const n = s.confirmed.filter(a => !a.startsWith("fx_")).length;
  $("#fx-note").textContent = n ? `${n} colour code${n > 1 ? "s" : ""} found` : "no codes found yet";

  const d = s.discovery;
  $("#d-live").hidden = !d;
  if (d) {
    $("#d-count").textContent = `${Math.min(d.index + 1, d.total)} / ${d.total}`;
    $("#d-bar").style.width = (100 * (d.index + 1) / d.total) + "%";
    $("#d-label").textContent = d.current ? d.current.label : "warming up…";
    $("#d-pause").textContent = d.paused ? "Resume" : "Pause";
    drawWave(d.pulses);
  }
  renderCodes(s);
  preview();
}

try { const t = localStorage.getItem("ulight-tab"); if (t && $("#" + t)) showTab(t); } catch (e) { /* ignore */ }
if (!document.body.dataset.tab) document.body.dataset.tab = "t-control";
preview();
refresh();
setInterval(refresh, 900);
