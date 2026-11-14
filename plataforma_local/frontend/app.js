/* FireCal Cusco: frontend del prototipo (PLAN.md §7 + MAESTRO.md P2/P3).
 * Unidad: "focos armonizados" (eq_hotspots). API: misma URL que sirve esta página, o
 * ?api=https://otra-api para un backend separado. */
"use strict";

const API = (new URLSearchParams(location.search).get("api") || window.FIRECAL_API || "").replace(/\/$/, "");
const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
// YlOrRd (ColorBrewer, apta para daltonismo) para los 5 tramos con fuego; el 0 va en gris neutro.
const YLORRD = ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"];
const ZERO = "#eef0f3";
const DIVERGING = [[-2, "#2166ac"], [-1, "#67a9cf"], [0, "#f7f7f7"], [1, "#fdb863"], [2, "#e66101"]];
const CALIDAD = { extrapolado: "extrapolado (solo Terra × kT)", mixto: "mixto (Terra × kT y MODIS)",
  referencia: "referencia (MODIS)", calibrado: "calibrado (VIIRS × k)" };

const state = { mode: "departamento", color: "valor", bbox: null, data: null, regionLayer: null };
const $ = (id) => document.getElementById(id);
const fmt = (v, d = 0) => (v === null || v === undefined) ? "–" : Number(v).toLocaleString("es-PE", { maximumFractionDigits: d, minimumFractionDigits: d });

// ------------------------------------------------------------------ utilidades
function hexToRgb(h) { const n = parseInt(h.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255]; }
function rgbToHex(r) { return "#" + r.map((v) => Math.round(v).toString(16).padStart(2, "0")).join(""); }
function mix(a, b, t) { const x = hexToRgb(a), y = hexToRgb(b); return rgbToHex(x.map((v, i) => v + (y[i] - v) * t)); }
function divergingColor(v) {
  if (v <= DIVERGING[0][0]) return DIVERGING[0][1];
  for (let i = 1; i < DIVERGING.length; i++) {
    const [x1, c1] = DIVERGING[i]; const [x0, c0] = DIVERGING[i - 1];
    if (v <= x1) return mix(c0, c1, (v - x0) / (x1 - x0));
  }
  return DIVERGING[DIVERGING.length - 1][1];
}
function classColor(v, breaks) {
  if (!v) return ZERO;
  let i = 0;
  while (i < breaks.length && v > breaks[i]) i++;
  return YLORRD[Math.min(i, YLORRD.length - 1)];
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
  return { body, ms };
}

function aoiParams() {
  if (state.mode === "departamento") return { departamento: "PE-CUS" };
  if (!state.bbox) return {};
  return { bbox: state.bbox.map((v) => v.toFixed(4)).join(",") };
}

// ------------------------------------------------------------------ mapa
const map = L.map("map", { zoomControl: true }).setView([-13.3, -72], 7);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: "© OpenStreetMap" }).addTo(map);
let rect = null;

async function loadRegion() {
  const { body } = await api("/api/departamentos");
  state.regionLayer = L.geoJSON(body.geojson, {
    style: () => ({ color: "#c2410c", weight: 2.5, fillOpacity: 0.08 }),
    onEachFeature: (f, layer) => {
      layer.bindTooltip("Cusco (datos armonizados)", { sticky: true });
      layer.on("click", () => { if (state.mode === "departamento") query(); });
    },
  }).addTo(map);
  map.fitBounds(state.regionLayer.getBounds(), { padding: [10, 10] });
}

// Dibujo de rectángulo sin dependencias: arrastrar con el mapa en modo bbox.
let dragStart = null;
map.on("mousedown", (e) => {
  if (state.mode !== "bbox") return;
  map.dragging.disable(); dragStart = e.latlng;
  if (rect) map.removeLayer(rect);
  rect = L.rectangle([dragStart, dragStart], { color: "#1d2330", weight: 2 }).addTo(map);
});
map.on("mousemove", (e) => { if (dragStart && rect) rect.setBounds([dragStart, e.latlng]); });
map.on("mouseup", () => {
  if (!dragStart) return;
  map.dragging.enable(); dragStart = null;
  const b = rect.getBounds();
  state.bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
  $("bbox-text").textContent = state.bbox.map((v) => v.toFixed(3)).join(", ");
  query();
});

// ------------------------------------------------------------------ calendario
function renderCalendar(d) {
  state.data = d;
  const byKey = new Map(d.celdas.map((c) => [`${c.anio}-${c.mes}`, c]));
  const useAnom = state.color === "anomalia";
  const breaks = d.cortes_color || [];
  let html = "<table><thead><tr><th></th>" + MESES.map((m) => `<th>${m}</th>`).join("") + "</tr></thead><tbody>";
  d.anios.forEach((y) => {
    html += `<tr><th class="y">${y}</th>`;
    for (let m = 1; m <= 12; m++) {
      const c = byKey.get(`${y}-${m}`);
      if (!c) { html += '<td class="empty"></td>'; continue; }
      if (c.sin_dato) { html += `<td class="nodata" title="${MESES[m - 1]} ${y}: sin dato (fuera de la serie 2000-11-04 a 2025-12-31)"></td>`; continue; }
      const bg = useAnom ? (c.anomalia === null ? "#d0d5dd" : divergingColor(c.anomalia)) : classColor(c.eq_hotspots, breaks);
      // Un valor entre 0 y 1 (p. ej. 0,33 = una celda-día VIIRS) no se muestra como "0".
      const val = c.eq_hotspots > 0 && c.eq_hotspots < 1 ? fmt(c.eq_hotspots, 1) : fmt(c.eq_hotspots);
      const txt = useAnom ? (c.anomalia === null ? "–" : (c.anomalia > 0 ? "+" : "") + c.anomalia.toFixed(1)) : val;
      const cls = [c.parcial ? "partial" : "", (c.calidad === "extrapolado" || c.calidad === "mixto") ? "extrap" : "",
        y === 2013 && m === 1 ? "viirs-start" : ""].join(" ");
      const tip = `${MESES[m - 1]} ${y}: ${fmt(c.eq_hotspots, 2)} focos armonizados · ${c.celdas_dia} celdas-día con fuego · ` +
        `focos detectados: MODIS ${c.focos_modis}, VIIRS ${c.focos_viirs} (sensores distintos, no se suman) · ` +
        `calidad ${CALIDAD[c.calidad] || c.calidad} · mediana del mes ${fmt(c.mediana_hist, 1)} · anomalía ${c.anomalia ?? "–"}` +
        (c.parcial ? " · mes parcial (desde el 04-nov)" : "");
      html += `<td class="${cls}" style="background-color:${bg};color:${inkFor(bg)}" title="${tip}" data-y="${y}" data-m="${m}">${txt}</td>`;
    }
    html += "</tr>";
  });
  $("cal").innerHTML = html + "</tbody></table>";
  $("cal").querySelectorAll("td[data-y]").forEach((td) => td.addEventListener("click", () => detail(td.dataset.y, td.dataset.m)));
  $("cal-title").textContent = `Focos armonizados por mes · ${d.aoi.descripcion} · ${d.fecha_inicio} a ${d.fecha_fin}`;
  renderLegend(useAnom, breaks);
  $("notes").innerHTML = d.notes.length ? "<ul>" + d.notes.map((n) => `<li>${n}</li>`).join("") + "</ul>" : "";
  $("total").hidden = false;
  $("total").innerHTML = `Total del área y rango: <b>${fmt(d.total_eq_hotspots)}</b> focos armonizados` +
    `<br><span class="hint">Igual a la suma de <span class="mono">eq_foco</span> del CSV descargado.</span>`;
}

function renderLegend(useAnom, breaks) {
  if (useAnom) {
    $("legend").innerHTML = `<span>Muy por debajo</span><div class="bar" style="background:linear-gradient(90deg,${DIVERGING.map((s) => s[1]).join(",")})"></div><span>Muy por encima</span>` +
      `<span>· (valor − mediana del mismo mes) / IQR, de −2 a +2 · gris = sin anomalía</span>`;
    return;
  }
  const edges = [0, ...breaks];
  const items = [`<span class="cls"><span class="sw" style="background:${ZERO}"></span>0</span>`];
  for (let i = 0; i < YLORRD.length && i < edges.length; i++) {
    const lo = edges[i], hi = edges[i + 1];
    const label = hi === undefined ? `> ${fmt(lo, lo < 10 ? 1 : 0)}` : `${fmt(lo, lo < 10 && lo % 1 ? 1 : 0)}–${fmt(hi, hi < 10 && hi % 1 ? 1 : 0)}`;
    items.push(`<span class="cls"><span class="sw" style="background:${YLORRD[i]}"></span>${label}</span>`);
  }
  items.push(`<span class="cls"><span class="sw nodata-sw" style="background:#c9ced6;background-image:repeating-linear-gradient(-45deg,rgba(255,255,255,.7) 0 2px,transparent 2px 6px)"></span>sin dato</span>`);
  items.push(`<span class="cls"><span class="sw" style="background:${YLORRD[1]};opacity:.55;background-image:repeating-linear-gradient(45deg,rgba(255,255,255,.55) 0 3px,transparent 3px 7px)"></span>extrapolado</span>`);
  $("legend").innerHTML = `<b>Focos armonizados por mes</b> (cortes = cuantiles 50/75/90/99 de los meses con fuego de esta selección): ` +
    items.join("") + `<span>· línea negra = desde 2013 la serie usa VIIRS × k</span>`;
}

function bars(points, color, highlight, refLine) {
  const w = Math.max(160, points.length * 12), h = 70;
  const max = Math.max(1, ...points.map((p) => p.v), refLine || 0);
  const bw = Math.max(3, Math.floor(w / Math.max(points.length, 1)) - 2);
  const rects = points.map((p, i) => {
    const hh = 64 * p.v / max, x = i * (bw + 2);
    return `<rect x="${x}" y="${66 - hh}" width="${bw}" height="${hh}" fill="${p.key === highlight ? "#c2410c" : color}"><title>${p.label}: ${fmt(p.v, 2)}</title></rect>`;
  }).join("");
  const ref = refLine ? `<line x1="0" x2="${points.length * (bw + 2)}" y1="${66 - 64 * refLine / max}" y2="${66 - 64 * refLine / max}" stroke="#1d2330" stroke-dasharray="3 2"/>` : "";
  return `<svg width="${points.length * (bw + 2)}" height="${h}" role="img">${rects}${ref}</svg>`;
}

async function detail(y, m) {
  const mes = `${y}-${String(m).padStart(2, "0")}`;
  try {
    const { body: a } = await api("/api/anomalias", { ...aoiParams(), mes });
    const hist = a.historial.map((h) => ({ key: String(h.anio), label: h.anio, v: h.eq_hotspots }));
    const days = a.dias.map((d) => ({ key: d.fecha_local, label: d.fecha_local, v: d.eq_hotspots }));
    $("detail").hidden = false;
    $("detail").innerHTML = `<h3>${MESES[m - 1]} ${y} · ${a.aoi.descripcion}</h3>
      <div class="kv">
        <div><span>Focos armonizados</span>${fmt(a.eq_hotspots, 2)}</div>
        <div><span>Celdas-día con fuego</span>${a.celdas_dia}</div>
        <div><span>Mediana del mes (histórica)</span>${fmt(a.mediana_hist, 1)}</div>
        <div><span>Anomalía</span>${a.anomalia ?? "–"} (${a.categoria ?? "sin dato"})</div>
        <div><span>Calidad</span>${CALIDAD[a.calidad] || a.calidad}</div>
        <div><span>Focos detectados (sin armonizar)</span>MODIS ${a.focos_modis} · VIIRS ${a.focos_viirs}</div>
      </div>
      <p class="hint">Por día del mes (focos armonizados):</p>${days.length ? bars(days, "#fd8d3c") : "<p class='hint'>Sin focos este mes.</p>"}
      <p class="hint">Mismo mes en otros años (línea = mediana):</p>${bars(hist, "#98a2b3", String(y), a.mediana_hist)}
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
    $("total").hidden = true;
  } finally { btn.disabled = false; }
}

function downloadCsv() {
  const ini = $("ini").value || "2000-11", fin = $("fin").value || "2025-12";
  const url = new URL(API + "/api/hotspots.csv", location.href);
  Object.entries({ ...aoiParams(), fecha_inicio: ini, fecha_fin: fin }).forEach(([k, v]) => v && url.searchParams.set(k, v));
  setMsg("Preparando CSV…");
  // Se descarga con fetch (no con un enlace directo) para mostrar los errores en el panel.
  fetch(url).then(async (res) => {
    if (!res.ok) { const b = await res.json().catch(() => ({})); throw new Error(b.detail || `Error ${res.status}`); }
    const total = res.headers.get("X-Total-Eq-Foco"), n = res.headers.get("X-Row-Count");
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = (res.headers.get("Content-Disposition") || "").match(/filename="(.+)"/)?.[1] || "focos_cusco.csv";
    a.click(); URL.revokeObjectURL(a.href);
    setMsg(`CSV descargado: ${fmt(Number(n))} focos, Σ eq_foco = ${fmt(Number(total), 2)}.`, "ok");
  }).catch((e) => setMsg(e.message, "err"));
}

async function loadMethod() {
  try {
    const { body: m } = await api("/api/metadatos");
    const h = m.armonizacion;
    const serie = h.serie.map((s) => `<li><b>${s.periodo}</b>: ${s.fuente_serie} (${s.calidad})` +
      (s.k ? ` · k alto ${s.k.alto}, bajo ${s.k.bajo}` : "") + (s.kT ? ` · kT alto ${s.kT.alto}, bajo ${s.kT.bajo}` : "") + "</li>").join("");
    const ctl = Object.entries(m.controles_maestro).map(([k, v]) => `${k}: ${fmt(v.filas)} filas, suma ${fmt(v.suma, 2)} (${v.coincide ? "coincide con MAESTRO §6" : "NO coincide"})`).join(" · ");
    $("unit-def").textContent = m.unidad.definicion;
    $("method").innerHTML = `<p><b>Unidad:</b> ${m.unidad.definicion}</p>
      <p><b>Armonización (${h.version_datos}):</b> ${h.grilla}. ${h.filtros}. Estratos: ${h.estratos}.</p>
      <ul>${serie}</ul>
      <p><b>Validación:</b> ${h.validacion}. <b>Anomalía:</b> ${h.anomalia} (mínimo ${h.min_anios_para_anomalia} años).</p>
      <p><b>Cobertura:</b> ${m.cobertura.region.name}, ${m.cobertura.desde} a ${m.cobertura.hasta}. ${m.cobertura.nota}</p>
      <p><b>Sumas de control:</b> ${ctl}.</p>
      <ul>${m.notes.map((n) => `<li>${n}</li>`).join("")}</ul>`;
  } catch { /* opcional */ }
}

// ------------------------------------------------------------------ eventos de la UI
document.querySelectorAll(".tab[data-mode]").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll(".tab[data-mode]").forEach((x) => x.classList.toggle("active", x === b));
  state.mode = b.dataset.mode;
  $("mode-departamento").hidden = state.mode !== "departamento";
  $("mode-bbox").hidden = state.mode !== "bbox";
  if (state.mode === "departamento") {
    if (rect) { map.removeLayer(rect); rect = null; }
    state.bbox = null; $("bbox-text").textContent = "Sin rectángulo";
    query();
  }
}));
document.querySelectorAll(".tab[data-color]").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll(".tab[data-color]").forEach((x) => x.classList.toggle("active", x === b));
  state.color = b.dataset.color;
  if (state.data) renderCalendar(state.data);
}));
$("go").addEventListener("click", query);
$("csv").addEventListener("click", downloadCsv);

loadRegion().then(query).catch((e) => setMsg("No se pudo conectar con la API: " + e.message, "err"));
loadMethod();
