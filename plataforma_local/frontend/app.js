/* FireCal Perú: frontend mínimo del MVP (PLAN.md sección 7).
 * API: misma URL que sirve esta página, o ?api=https://otra-api para un backend separado. */
"use strict";

const API = (new URLSearchParams(location.search).get("api") || window.FIRECAL_API || "").replace(/\/$/, "");
const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
const VIRIDIS = ["#440154", "#482878", "#3e4989", "#31688e", "#26828e", "#1f9e89", "#35b779", "#6ece58", "#b5de2b", "#fde725"];
const DIVERGING = [[-2, "#2166ac"], [-1, "#67a9cf"], [0, "#f7f7f7"], [1, "#fdb863"], [2, "#e66101"]];

const state = { mode: "departamento", color: "anomalia", bbox: null, data: null, depLayer: null };
const $ = (id) => document.getElementById(id);

// ------------------------------------------------------------------ utilidades
function hexToRgb(h) { const n = parseInt(h.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255]; }
function rgbToHex(r) { return "#" + r.map((v) => Math.round(v).toString(16).padStart(2, "0")).join(""); }
function mix(a, b, t) { const x = hexToRgb(a), y = hexToRgb(b); return rgbToHex(x.map((v, i) => v + (y[i] - v) * t)); }
function ramp(stops, t) {
  t = Math.min(1, Math.max(0, t)); const p = t * (stops.length - 1), i = Math.floor(p);
  return i >= stops.length - 1 ? stops[stops.length - 1] : mix(stops[i], stops[i + 1], p - i);
}
function divergingColor(v) {
  if (v <= DIVERGING[0][0]) return DIVERGING[0][1];
  for (let i = 1; i < DIVERGING.length; i++) {
    const [x1, c1] = DIVERGING[i]; const [x0, c0] = DIVERGING[i - 1];
    if (v <= x1) return mix(c0, c1, (v - x0) / (x1 - x0));
  }
  return DIVERGING[DIVERGING.length - 1][1];
}
function inkFor(bg) { const [r, g, b] = hexToRgb(bg); return (0.299 * r + 0.587 * g + 0.114 * b) > 150 ? "#1d2330" : "#fff"; }
function setMsg(text, kind = "") { const m = $("msg"); m.textContent = text; m.className = "msg " + kind; }

async function api(path, params) {
  const url = new URL(API + path, location.href);
  Object.entries(params || {}).forEach(([k, v]) => { if (v !== null && v !== undefined && v !== "") url.searchParams.set(k, v); });
  const res = await fetch(url);
  const ms = res.headers.get("X-Process-Time-ms");
  let body = null;
  try { body = await res.json(); } catch { /* respuesta no JSON */ }
  if (!res.ok) {
    const detail = body && body.detail ? (typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail)) : `Error ${res.status}`;
    throw new Error(detail);
  }
  return { body, ms, url };
}

function aoiParams() {
  if (state.mode === "departamento") return { departamento: $("dep").value };
  if (!state.bbox) return {};
  return { bbox: state.bbox.map((v) => v.toFixed(4)).join(",") };
}

// ------------------------------------------------------------------ mapa
const map = L.map("map", { zoomControl: true }).setView([-13.5, -72], 6);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 18, attribution: "© OpenStreetMap",
}).addTo(map);
let rect = null;

function styleDep(code) {
  const sel = state.mode === "departamento" && code === $("dep").value;
  return { color: sel ? "#c2410c" : "#1d2330", weight: sel ? 3 : 1, fillOpacity: sel ? 0.12 : 0.03 };
}
function restyle() { if (state.depLayer) state.depLayer.eachLayer((l) => l.setStyle(styleDep(l.feature.properties.code))); }

async function loadDepartments() {
  const [{ body: deps }, { body: geo }] = await Promise.all([api("/api/departamentos"), api("/api/v1/regions")]);
  const sel = $("dep");
  deps.departamentos.forEach((d) => sel.add(new Option(`${d.name} (${d.code})`, d.code)));
  sel.value = deps.departamentos.some((d) => d.code === "PE-CUS") ? "PE-CUS" : sel.options[0].value;
  if (deps.data_mode === "synthetic") { $("banner").hidden = false; $("banner").textContent = "DATOS SINTÉTICOS · no usar para decisiones"; }
  geo.features = geo.features.filter((f) => f.properties.level === "departamento");
  state.depLayer = L.geoJSON(geo, {
    style: (f) => styleDep(f.properties.code),
    onEachFeature: (f, layer) => {
      layer.bindTooltip(f.properties.name, { sticky: true });
      layer.on("click", () => { if (state.mode !== "departamento") return; sel.value = f.properties.code; restyle(); query(); });
    },
  }).addTo(map);
  map.fitBounds(state.depLayer.getBounds(), { padding: [10, 10] });
}

// Dibujo de rectángulo sin dependencias: arrastrar con el mapa en modo bbox.
let dragStart = null;
map.on("mousedown", (e) => {
  if (state.mode !== "bbox") return;
  map.dragging.disable(); dragStart = e.latlng;
  if (rect) map.removeLayer(rect);
  rect = L.rectangle([dragStart, dragStart], { color: "#c2410c", weight: 2 }).addTo(map);
});
map.on("mousemove", (e) => { if (dragStart && rect) rect.setBounds([dragStart, e.latlng]); });
map.on("mouseup", () => {
  if (!dragStart) return;
  map.dragging.enable(); dragStart = null;
  const b = rect.getBounds();
  state.bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
  $("bbox-text").textContent = state.bbox.map((v) => v.toFixed(3)).join(", ");
});

// ------------------------------------------------------------------ calendario
function renderCalendar(d) {
  state.data = d;
  const byKey = new Map(d.celdas.map((c) => [`${c.anio}-${c.mes}`, c]));
  const vals = d.celdas.map((c) => c.n_eventos);
  const maxN = Math.max(1, ...vals);
  const useAnom = state.color === "anomalia";
  let html = "<table><thead><tr><th></th>" + MESES.map((m) => `<th>${m}</th>`).join("") + "</tr></thead><tbody>";
  d.anios.forEach((y) => {
    html += `<tr><th class="y">${y}</th>`;
    for (let m = 1; m <= 12; m++) {
      const c = byKey.get(`${y}-${m}`);
      if (!c) { html += '<td class="empty"></td>'; continue; }
      const bg = useAnom ? (c.anomalia === null ? "#d0d5dd" : divergingColor(c.anomalia))
                         : ramp(VIRIDIS, Math.sqrt(c.n_eventos / maxN));
      const txt = useAnom ? (c.anomalia === null ? "–" : (c.anomalia > 0 ? "+" : "") + c.anomalia.toFixed(1)) : c.n_eventos;
      const cls = [c.parcial ? "partial" : "", y === 2012 && m === 2 ? "era-start" : ""].join(" ");
      const tip = `${MESES[m - 1]} ${y}: ${c.n_eventos} eventos · mediana ${c.mediana_hist ?? "–"} · anomalía ${c.anomalia ?? "–"} (${c.categoria ?? "sin dato"}) · era ${c.era}${c.parcial ? " · parcial" : ""}`;
      html += `<td class="${cls}" style="background:${bg};color:${inkFor(bg)}" title="${tip}" data-y="${y}" data-m="${m}">${txt}</td>`;
    }
    html += "</tr>";
  });
  $("cal").innerHTML = html + "</tbody></table>";
  $("cal").querySelectorAll("td[data-y]").forEach((td) => td.addEventListener("click", () => detail(td.dataset.y, td.dataset.m)));
  $("cal-title").textContent = `Calendario · ${d.aoi.descripcion} · ${d.fecha_inicio} a ${d.fecha_fin}`;
  if (useAnom) {
    $("legend").innerHTML = `<span>Muy por debajo</span><div class="bar" style="background:linear-gradient(90deg,${DIVERGING.map((s) => s[1]).join(",")})"></div><span>Muy por encima</span><span>· escala: (n − mediana) / IQR, de −2 a +2 · gris = sin historia suficiente · línea negra = inicio de VIIRS (feb-2012)</span>`;
  } else {
    $("legend").innerHTML = `<span>0</span><div class="bar" style="background:linear-gradient(90deg,${VIRIDIS.join(",")})"></div><span>${maxN} eventos (escala raíz)</span><span>· ojo: el conteo sube con VIIRS desde 2012; para comparar eras usa «Anomalía»</span>`;
  }
  $("notes").innerHTML = d.notes.length ? "<ul>" + d.notes.map((n) => `<li>${n}</li>`).join("") + "</ul>" : "";
}

async function detail(y, m) {
  const mes = `${y}-${String(m).padStart(2, "0")}`;
  try {
    const { body: a } = await api("/api/anomalias", { ...aoiParams(), mes });
    const maxH = Math.max(1, ...a.historial.map((h) => h.n_eventos));
    const bars = a.historial.map((h, i) => {
      const hgt = 60 * h.n_eventos / maxH, x = i * 14;
      const fill = String(h.anio) === String(y) ? "#c2410c" : "#98a2b3";
      return `<rect x="${x}" y="${62 - hgt}" width="11" height="${hgt}" fill="${fill}"><title>${h.anio}: ${h.n_eventos}</title></rect>`;
    }).join("");
    const med = a.mediana_hist !== null ? `<line x1="0" x2="${a.historial.length * 14}" y1="${62 - 60 * a.mediana_hist / maxH}" y2="${62 - 60 * a.mediana_hist / maxH}" stroke="#1d2330" stroke-dasharray="3 2"/>` : "";
    $("detail").hidden = false;
    $("detail").innerHTML = `<h3>${MESES[m - 1]} ${y} · ${a.aoi.descripcion}</h3>
      <div class="kv">
        <div><span>Eventos</span>${a.n_eventos}</div><div><span>Mediana histórica</span>${a.mediana_hist ?? "–"}</div>
        <div><span>Rango intercuartil</span>${a.p25 ?? "–"} – ${a.p75 ?? "–"}</div><div><span>Anomalía</span>${a.anomalia ?? "–"} (${a.categoria ?? "sin dato"})</div>
        <div><span>Era de sensores</span>${a.era}</div><div><span>FRP total</span>${a.frp_total} MW</div>
      </div>
      <p class="hint">Mismo mes en otros años de la era ${a.era} (línea = mediana):</p>
      <svg width="${Math.max(140, a.historial.length * 14)}" height="66" role="img" aria-label="Historial">${bars}${med}</svg>
      ${a.notes.length ? "<ul class='notes'>" + a.notes.map((n) => `<li>${n}</li>`).join("") + "</ul>" : ""}`;
  } catch (e) { setMsg(e.message, "err"); }
}

async function query() {
  const btn = $("go"); btn.disabled = true; setMsg("Consultando…");
  try {
    const { body, ms } = await api("/api/calendario", { ...aoiParams(), fecha_inicio: $("ini").value, fecha_fin: $("fin").value });
    renderCalendar(body);
    $("detail").hidden = true;
    $("latency").textContent = ms ? `respuesta del servidor: ${ms} ms` : "";
    setMsg(`Listo: ${body.celdas.length} meses.`, "ok");
  } catch (e) {
    setMsg(e.message, "err");
  } finally { btn.disabled = false; }
}

function downloadCsv() {
  const ini = $("ini").value, fin = $("fin").value;
  if (!ini || !fin) { setMsg("Para descargar el CSV elige «Desde» y «Hasta» (máx. 5 años).", "err"); return; }
  const url = new URL(API + "/api/hotspots.csv", location.href);
  Object.entries({ ...aoiParams(), fecha_inicio: ini, fecha_fin: fin }).forEach(([k, v]) => v && url.searchParams.set(k, v));
  // Se descarga con fetch (no con un enlace directo) para mostrar los errores 422 en el panel.
  fetch(url).then(async (res) => {
    if (!res.ok) { const b = await res.json().catch(() => ({})); throw new Error(b.detail || `Error ${res.status}`); }
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = (res.headers.get("Content-Disposition") || "").match(/filename="(.+)"/)?.[1] || "focos.csv";
    a.click(); URL.revokeObjectURL(a.href);
    setMsg("CSV descargado.", "ok");
  }).catch((e) => setMsg(e.message, "err"));
}

async function loadMethod() {
  try {
    const { body: m } = await api("/api/metadatos");
    const h = m.armonizador;
    $("method").innerHTML = `<p><b>Versión:</b> ${h.version} · <b>Datos:</b> ${m.data_mode} · cobertura ${m.cobertura.primer_mes} a ${m.cobertura.ultima_fecha}</p>
      <p><b>Armonización (${h.alternativas.join(" + ")}).</b> ${h.deduplicacion} ${h.constelacion}.</p>
      <p><b>Anomalía:</b> ${h.anomalia}; se necesita un mínimo de ${h.min_anios_para_anomalia} años en la era. Eras: ${Object.entries(h.eras).map(([k, v]) => `${k}: ${v}`).join("; ")}.</p>
      <p><b>Confianza mínima:</b> ${m.umbral_confianza.minimo} (MODIS ${m.umbral_confianza.modis_conf_norm}; VIIRS l/n/h = ${Object.values(m.umbral_confianza.viirs_conf_norm).join("/")}).</p>
      <p><b>Conteos:</b> ${m.conteos.detecciones_limpias.toLocaleString()} detecciones limpias → ${m.conteos.eventos.toLocaleString()} eventos tras deduplicar.</p>
      <ul>${m.notes.map((n) => `<li>${n}</li>`).join("")}</ul>`;
  } catch { /* opcional */ }
}

// ------------------------------------------------------------------ eventos de la UI
document.querySelectorAll(".tab[data-mode]").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll(".tab[data-mode]").forEach((x) => x.classList.toggle("active", x === b));
  state.mode = b.dataset.mode;
  $("mode-departamento").hidden = state.mode !== "departamento";
  $("mode-bbox").hidden = state.mode !== "bbox";
  if (state.mode === "departamento" && rect) { map.removeLayer(rect); rect = null; state.bbox = null; $("bbox-text").textContent = "Sin rectángulo"; }
  restyle();
}));
document.querySelectorAll(".tab[data-color]").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll(".tab[data-color]").forEach((x) => x.classList.toggle("active", x === b));
  state.color = b.dataset.color;
  if (state.data) renderCalendar(state.data);
}));
$("dep").addEventListener("change", () => { restyle(); query(); });
$("go").addEventListener("click", query);
$("csv").addEventListener("click", downloadCsv);

loadDepartments().then(query).catch((e) => setMsg("No se pudo conectar con la API: " + e.message, "err"));
loadMethod();
