// FireCal Cusco: interfaz de Dante (rama `dante`, "Firewatch Perú") adaptada a la plataforma.
// Cambios respecto al original: datos reales de Cusco desde nuestra API (sin datos demo ni FIRMS
// en vivo), solo Cusco, unidad "focos armonizados", sin FRP, y la línea de tiempo de 5 días pasa a
// ser el calendario histórico mes x año del PLAN (2000-11 a 2025-12).
import { createElement, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import {
  CalendarDays, ChevronLeft, ChevronRight, Download, Flame, Gauge, Info,
  Layers3, Map as MapIcon, MapPin, MessageCircleQuestion, Mountain, Pause, Play, Satellite, Scan, ShieldAlert,
  SlidersHorizontal,
  ThermometerSun, Trash2, X,
} from 'lucide-react'
import SimplePanel from './SimplePanel.jsx'
import { LANGS, getLang, locale, months, setLang, tr } from './i18n.js'
import { CUSCO, downloadCsv, getCalendar, getFocos, getMetadata, getMonth, getRegion } from './services/api.js'

maplibregl.setWorkerUrl(maplibreWorkerUrl)

const MAP_STYLE = 'https://tiles.openfreemap.org/styles/positron'
const SATELLITE_STYLE = {
  version: 8,
  sources: {
    imagery: {
      type: 'raster',
      tiles: ['https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
      tileSize: 256,
      attribution: 'Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community',
    },
  },
  layers: [{ id: 'satellite-imagery', type: 'raster', source: 'imagery', paint: { 'raster-saturation': 0.08, 'raster-contrast': 0.08 } }],
}
const EMPTY = { type: 'FeatureCollection', features: [] }
const FIRST_YEAR = 2000
const LAST_YEAR = 2025
const YEARS = Array.from({ length: LAST_YEAR - FIRST_YEAR + 1 }, (_, i) => FIRST_YEAR + i)
// YlOrRd (ColorBrewer, apta para daltonismo) para los tramos con fuego; el 0 va en gris neutro.
const YLORRD = ['#ffffb2', '#fecc5c', '#fd8d3c', '#f03b20', '#bd0026']
const ZERO = '#e4e7ec'               // 0 focos: gris claro (no debe resaltar)
const calidadLabel = (q) => tr(`calidad.${q}`)
const catLabel = (c) => (c ? tr(`cat.${c}`) : tr('noData'))
const CATEGORIA = {
  'muy por debajo': 'bajo', 'por debajo': 'bajo', normal: 'moderado',
  'por encima': 'alto', 'muy por encima': 'alto', incierta: 'incierto',
}
const fmt = (v, d = 0) => (v === null || v === undefined || Number.isNaN(v)) ? '–'
  : Number(v).toLocaleString(locale(), { minimumFractionDigits: d, maximumFractionDigits: d })
const fmtFocos = (v) => (v > 0 && v < 1 ? fmt(v, 1) : fmt(v))
const ym = (y, m) => `${y}-${String(m).padStart(2, '0')}`

function classColor(value, breaks) {
  if (!value) return ZERO
  let i = 0
  while (i < breaks.length && value > breaks[i]) i++
  return YLORRD[Math.min(i, YLORRD.length - 1)]
}

// Anomalía: azul (por debajo) - blanco - rojo (por encima), de -2 a +2 (apta para daltonismo).
const DIVERGING = [[-2, '#2166ac'], [-1, '#67a9cf'], [0, '#f7f7f7'], [1, '#ef8a62'], [2, '#b2182b']]
function mixHex(a, b, t) {
  const pa = parseInt(a.slice(1), 16), pb = parseInt(b.slice(1), 16)
  const ch = (s) => Math.round(((pa >> s) & 255) + (((pb >> s) & 255) - ((pa >> s) & 255)) * t)
  return `#${[16, 8, 0].map((s) => ch(s).toString(16).padStart(2, '0')).join('')}`
}
function divergingColor(v) {
  if (v <= DIVERGING[0][0]) return DIVERGING[0][1]
  for (let i = 1; i < DIVERGING.length; i++) {
    const [x1, c1] = DIVERGING[i], [x0, c0] = DIVERGING[i - 1]
    if (v <= x1) return mixHex(c0, c1, (v - x0) / (x1 - x0))
  }
  return DIVERGING[DIVERGING.length - 1][1]
}

// Texto oscuro sobre colores claros (amarillos) y claro sobre oscuros.
function inkFor(color) {
  if (!color.startsWith('#')) return '#f7fbf8'
  const n = parseInt(color.slice(1), 16)
  const lum = 0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)
  return lum > 150 ? '#1d2330' : '#f7fbf8'
}

function boundsOf(geojson) {
  const coords = geojson.features.flatMap((f) => (f.geometry.type === 'MultiPolygon'
    ? f.geometry.coordinates.flatMap((p) => p[0]) : f.geometry.coordinates[0]))
  return coords.reduce((b, c) => b.extend(c), new maplibregl.LngLatBounds(coords[0], coords[0]))
}

// Máscara: oscurece todo lo que está fuera de Cusco (los anillos de Cusco son agujeros).
function maskOf(geojson) {
  const holes = geojson.features.flatMap((f) => (f.geometry.type === 'MultiPolygon'
    ? f.geometry.coordinates.map((p) => [...p[0]].reverse()) : [[...f.geometry.coordinates[0]].reverse()]))
  return {
    type: 'FeatureCollection',
    features: [{ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]], ...holes] } }],
  }
}

function boundsToGeoJson(bounds) {
  if (!bounds) return EMPTY
  const { west, east, south, north } = bounds
  return { type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[[west, south], [east, south], [east, north], [west, north], [west, south]]] } }] }
}

function fitTo(map, bounds, compact = window.innerWidth < 650) {
  map.fitBounds(bounds, {
    padding: compact ? { top: 76, right: 24, bottom: 112, left: 24 } : { top: 100, right: 160, bottom: 300, left: 430 },
    duration: 900, maxZoom: 8.6,
  })
}

function createPopupContent(title, lines) {
  const root = document.createElement('div')
  root.className = 'fw-popup'
  const heading = document.createElement('b')
  heading.textContent = title
  root.appendChild(heading)
  lines.forEach(({ value, strong = false }) => {
    const element = document.createElement(strong ? 'strong' : 'span')
    element.textContent = value
    root.appendChild(element)
  })
  return root
}

function CategoryBadge({ categoria }) {
  if (!categoria) return <span className="fw-risk fw-risk--bajo"><i />{tr('badge.noAnomaly')}</span>
  const tone = CATEGORIA[categoria] || 'bajo'
  return <span className={`fw-risk fw-risk--${tone}`}><i />{categoria === 'incierta' ? tr('badge.uncertain') : tr('badge.activity', { cat: catLabel(categoria) })}</span>
}

function LayerButton({ active, icon, label, onClick, tone }) {
  return <button className={`fw-layer-button ${active ? 'is-active' : ''}`} onClick={onClick} title={label}><span className={tone}>{createElement(icon, { size: 18 })}</span><b>{label}</b></button>
}

function Metric({ icon, label, value, tone }) {
  return <div className="fw-metric"><span className={tone}>{createElement(icon, { size: 16 })}</span><div><b>{value}</b><small>{label}</small></div></div>
}

function SatelliteSelectionMap({ bounds, focos }) {
  const containerRef = useRef(null)
  const previewMapRef = useRef(null)
  const previewReadyRef = useRef(false)
  const focosRef = useRef(focos)
  const boundsRef = useRef(bounds)
  focosRef.current = focos
  boundsRef.current = bounds

  const fitPreview = useCallback((map, b) => {
    map.fitBounds([[b.west, b.south], [b.east, b.north]], { padding: 22, duration: 0, maxZoom: 12 })
  }, [])

  useEffect(() => {
    const map = new maplibregl.Map({
      container: containerRef.current, style: SATELLITE_STYLE,
      center: [(boundsRef.current.west + boundsRef.current.east) / 2, (boundsRef.current.south + boundsRef.current.north) / 2],
      zoom: 8, minZoom: 5, maxZoom: 16, attributionControl: false, antialias: true,
    })
    previewMapRef.current = map
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-left')
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.on('load', () => {
      map.addSource('preview-focos', { type: 'geojson', data: focosRef.current })
      map.addLayer({
        id: 'preview-heat', type: 'heatmap', source: 'preview-focos', maxzoom: 14,
        paint: {
          'heatmap-weight': ['interpolate', ['linear'], ['get', 'eq_foco'], 0, 0.15, 0.5, 0.6, 1, 1],
          'heatmap-intensity': 1.35,
          'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], 0, 'rgba(255,230,110,0)', 0.25, '#ffe66d', 0.5, '#ff9f32', 0.72, '#ff4c2f', 1, '#9f001f'],
          'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 6, 18, 12, 42],
          'heatmap-opacity': 0.78,
        },
      })
      map.addLayer({
        id: 'preview-points', type: 'circle', source: 'preview-focos',
        paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 6, 3, 12, 7], 'circle-color': '#ff5a3d', 'circle-opacity': 0.95, 'circle-stroke-color': '#fff5dc', 'circle-stroke-width': 1.2 },
      })
      previewReadyRef.current = true
      fitPreview(map, boundsRef.current)
    })
    return () => { previewReadyRef.current = false; map.remove(); previewMapRef.current = null }
  }, [fitPreview])

  useEffect(() => {
    const map = previewMapRef.current
    if (!previewReadyRef.current || !map) return
    map.getSource('preview-focos').setData(focos)
    fitPreview(map, bounds)
  }, [bounds, fitPreview, focos])

  return <div className="fw-satellite-preview"><div ref={containerRef} className="fw-satellite-map"/><span className="fw-satellite-badge"><i/>{tr('sat.badge')}</span><div className="fw-satellite-legend"><span><i className="heat"/>{tr('sat.density')}</span><span><i className="point"/>{tr('sat.point')}</span></div></div>
}

function CalendarPanel({ calendar, mode, setMode, selected, onSelect, onClose }) {
  const byKey = useMemo(() => new Map((calendar?.celdas || []).map((c) => [`${c.anio}-${c.mes}`, c])), [calendar])
  if (!calendar) return null
  const MESES = months()
  const breaks = calendar.cortes_color || []
  const edges = [0, ...breaks]
  return (
    <aside className="fc-calendar" aria-label={tr('cal.aria')}>
      <div className="fc-calendar-head">
        <div><p>{tr('cal.kicker')}</p><h2>{tr('cal.title', { aoi: calendar.aoi.descripcion })}</h2></div>
        <div className="fc-toggle">
          <button className={mode === 'valor' ? 'is-active' : ''} onClick={() => setMode('valor')}>{tr('cal.hotspots')}</button>
          <button className={mode === 'anomalia' ? 'is-active' : ''} onClick={() => setMode('anomalia')}>{tr('cal.anomaly')}</button>
          <button onClick={onClose} title={tr('cal.close')}><X size={15}/></button>
        </div>
      </div>
      <div className="fc-calendar-grid">
        <table>
          <thead><tr><th/>{MESES.map((m) => <th key={m}>{m}</th>)}</tr></thead>
          <tbody>
            {[...calendar.anios].reverse().map((y) => (
              <tr key={y}>
                <th>{y}</th>
                {MESES.map((_, idx) => {
                  const m = idx + 1
                  const c = byKey.get(`${y}-${m}`)
                  if (!c) return <td key={m} className="is-empty"/>
                  if (c.sin_dato) return <td key={m} className="is-nodata" title={tr('cal.nodataTip', { m: MESES[idx], y })}/>
                  const anomColor = c.anomalia === null ? '#d0d5dd' : divergingColor(c.anomalia)
                  const bg = mode === 'anomalia' ? anomColor : classColor(c.focos_armonizados, breaks)
                  const extrap = c.calidad === 'extrapolado' || c.calidad === 'mixto'
                  const isSel = selected.year === y && selected.month === m
                  const rango = c.incertidumbre ? tr('cal.range', { a: fmt(c.rango[0], 1), b: fmt(c.rango[1], 1) }) : ''
                  const tip = tr('cal.tip', { m: MESES[idx], y, v: fmt(c.focos_armonizados, 2), range: rango, q: calidadLabel(c.calidad), med: fmt(c.mediana_hist, 1), a: c.anomalia ?? '–', cat: catLabel(c.categoria) })
                  return (
                    <td key={m} title={tip} aria-label={tip} role="button" tabIndex={0} onClick={() => onSelect(y, m)}
                      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(y, m) } }}
                      className={[extrap ? 'is-extrap' : '', c.categoria === 'incierta' ? 'is-uncertain' : '', isSel ? 'is-selected' : '', y === 2013 && m === 1 ? 'is-viirs' : ''].join(' ')}
                      style={{ background: bg, color: inkFor(bg) }}>
                      {mode === 'anomalia' ? (c.anomalia === null ? '–' : `${c.anomalia > 0 ? '+' : ''}${c.anomalia.toFixed(1)}`) : fmtFocos(c.focos_armonizados)}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="fc-legend">
        {mode === 'valor' ? <>
          <span className="sw" style={{ background: ZERO }}/>0
          {YLORRD.map((color, i) => i < edges.length && <span key={color} className="fc-cls"><span className="sw" style={{ background: color }}/>{edges[i + 1] === undefined ? `> ${fmt(edges[i])}` : `${fmt(edges[i])}–${fmt(edges[i + 1])}`}</span>)}
        </> : <span>{tr('cal.anomLegend')}</span>}
        <span className="fc-cls"><span className="sw is-nodata"/>{tr('legend.nodata')}</span>
        <span className="fc-cls"><span className="sw is-extrap" style={{ background: YLORRD[2] }}/>{tr('legend.extrap')}</span>
        <span className="fc-cls"><span className="sw is-uncertain"/>{tr('legend.uncertain')}</span>
        <span>{tr('legend.note')}</span>
      </div>
    </aside>
  )
}

function FireMapApp() {
  const mapContainerRef = useRef(null)
  const mapRef = useRef(null)
  const mapReadyRef = useRef(false)
  const focosRef = useRef(EMPTY)
  const regionRef = useRef(null)
  const selectionModeRef = useRef(false)

  const [region, setRegion] = useState(null)
  const [metadata, setMetadata] = useState(null)
  const [calendar, setCalendar] = useState(null)
  const [selected, setSelected] = useState({ year: LAST_YEAR, month: null })
  const [month, setMonth] = useState(null)
  const [focos, setFocos] = useState(EMPTY)
  const [latency, setLatency] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [activeLayer, setActiveLayer] = useState('surface')
  const [showBoundary, setShowBoundary] = useState(false)
  const [baseMap, setBaseMap] = useState('relief')      // Dante (450cc43): relieve por defecto
  const [calendarMode, setCalendarMode] = useState('valor')
  // ?calendario=0 abre la página sin el calendario (p. ej. para incrustarla en una presentación).
  // Abierto solo en pantallas anchas: en 1440x900 tapaba Cusco (auditoría de Gabriel).
  const [calendarOpen, setCalendarOpen] = useState(window.innerWidth >= 1600
    && new URLSearchParams(window.location.search).get('calendario') !== '0')
  const [playing, setPlaying] = useState(false)
  const playableRef = useRef(new Set())
  const yearsRef = useRef(null)
  const [simpleOpen, setSimpleOpen] = useState(false)
  const [detailsOpen, setDetailsOpen] = useState(true)
  const [layersOpen, setLayersOpen] = useState(true)
  const [toolsOpen, setToolsOpen] = useState(false)
  const [selectionMode, setSelectionMode] = useState(false)
  const [selectionBounds, setSelectionBounds] = useState(null)
  const [selection, setSelection] = useState(null)
  const [lang, setLangState] = useState(getLang())
  const changeLang = (l) => { setLang(l); setLangState(l) }
  const MESES = months()

  const periodo = useMemo(() => (selected.month
    ? { inicio: ym(selected.year, selected.month), fin: ym(selected.year, selected.month), label: `${months()[selected.month - 1]} ${selected.year}` }
    : { inicio: ym(selected.year, selected.year === FIRST_YEAR ? 11 : 1), fin: ym(selected.year, 12), label: tr('period.year', { y: selected.year }) }), [selected, lang]) // eslint-disable-line react-hooks/exhaustive-deps
  const aoi = { departamento: CUSCO }
  const yearCells = useMemo(() => (calendar?.celdas || []).filter((c) => c.anio === selected.year), [calendar, selected.year])
  const yearTotal = useMemo(() => yearCells.reduce((s, c) => s + (c.focos_armonizados || 0), 0), [yearCells])
  const yearMax = useMemo(() => Math.max(1, ...yearCells.map((c) => c.focos_armonizados || 0)), [yearCells])
  playableRef.current = new Set(yearCells.filter((c) => !c.sin_dato).map((c) => c.mes))
  selectionModeRef.current = selectionMode
  focosRef.current = focos

  // Datos base: contorno, metadatos y calendario completo de Cusco.
  useEffect(() => {
    let active = true
    Promise.all([getRegion(), getMetadata(), getCalendar({ departamento: CUSCO })])
      .then(([r, m, c]) => {
        if (!active) return
        setRegion(r.body); setMetadata(m.body); setCalendar(c.body); setLatency(c.ms)
      })
      .catch((e) => active && setError(e.message))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [lang])          // en otro idioma, la API devuelve notas y unidad traducidas

  // Focos del periodo seleccionado (mapa) y detalle del mes.
  useEffect(() => {
    let active = true
    setLoading(true)
    setMonth(null)                 // vaciar el detalle: no mostrar números de otro mes mientras carga
    setError('')
    const tasks = [getFocos({ departamento: CUSCO }, periodo.inicio, periodo.fin)]
    if (selected.month) tasks.push(getMonth({ departamento: CUSCO }, periodo.inicio))
    Promise.all(tasks)
      .then(([f, mo]) => {
        if (!active) return
        setFocos(f.body); setLatency(f.ms); setMonth(mo ? mo.body : null); setError('')
      })
      .catch((e) => active && setError(e.message))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [periodo, selected.month])

  // Área dibujada: calendario del área en el periodo y sus focos.
  useEffect(() => {
    if (!selectionBounds) { setSelection(null); return undefined }
    const b = selectionBounds
    const bbox = { bbox: [b.west, b.south, b.east, b.north].map((v) => v.toFixed(4)).join(',') }
    // Las consultas de un área son "pesadas" (cupo de 5 seguidas): durante la reproducción se pausan.
    if (playing) { setSelection({ bbox, paused: true }); return undefined }
    let active = true
    setSelection({ loading: true, bbox })
    Promise.all([getCalendar(bbox, periodo.inicio, periodo.fin), getFocos(bbox, periodo.inicio, periodo.fin)])
      .then(([c, f]) => active && setSelection({ bbox, calendar: c.body, focos: f.body }))
      .catch((e) => active && setSelection({ bbox, error: e.message }))
    return () => { active = false }
  }, [selectionBounds, periodo, playing])

  // Mantener visible el año elegido en la escala de años (se desplaza si no cabe).
  useEffect(() => {
    const center = () => {
      const el = yearsRef.current
      const a = el?.querySelector('.is-active')
      if (el && a) el.scrollTo({ left: a.offsetLeft - (el.clientWidth - a.offsetWidth) / 2 })
    }
    const t = window.setTimeout(center, 250)          // tras cargar fuentes y diseño
    window.addEventListener('resize', center)
    return () => { window.clearTimeout(t); window.removeEventListener('resize', center) }
  }, [selected.year])

  // Reproducir: recorre los meses del año seleccionado.
  useEffect(() => {
    if (!playing) return undefined
    const timer = window.setInterval(() => {
      // QA de Erik (7): saltar los meses sin dato (ene-oct de 2000) en vez de mostrar "Sin datos".
      const ok = playableRef.current
      setSelected((s) => {
        let m = s.month || 0
        for (let k = 0; k < 12; k += 1) { m = (m % 12) + 1; if (!ok.size || ok.has(m)) break }
        return { year: s.year, month: m }
      })
    }, 1600)
    return () => window.clearInterval(timer)
  }, [playing])

  useEffect(() => {
    const map = new maplibregl.Map({
      container: mapContainerRef.current, style: MAP_STYLE, center: [-71.97, -13.53], zoom: 6.2,
      minZoom: 4, maxZoom: 14, attributionControl: false, antialias: true,
      // Conserva el dibujo del lienzo: permite guardar el mapa como imagen (MAESTRO P4).
      canvasContextAttributes: { preserveDrawingBuffer: true },
    })
    mapRef.current = map
    map.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: 'NASA FIRMS · FAO GAUL' }), 'bottom-right')
    map.addControl(new maplibregl.NavigationControl({ showCompass: false, visualizePitch: false }), 'bottom-right')
    const canvas = map.getCanvas()
    const canvasContainer = map.getCanvasContainer()
    let dragStart = null
    let drawBox = null
    let suppressNextClick = false

    const pointerPosition = (event) => {
      const rect = canvas.getBoundingClientRect()
      return { x: event.clientX - rect.left, y: event.clientY - rect.top }
    }
    const removeDrawBox = () => { drawBox?.remove(); drawBox = null; dragStart = null }
    const onPointerDown = (event) => {
      if (!selectionModeRef.current || event.button !== 0) return
      event.preventDefault(); event.stopPropagation()
      dragStart = pointerPosition(event)
      drawBox = document.createElement('div')
      drawBox.className = 'fw-selection-box'
      canvasContainer.appendChild(drawBox)
      canvas.setPointerCapture?.(event.pointerId)
    }
    const onPointerMove = (event) => {
      if (!dragStart || !drawBox) return
      event.preventDefault(); event.stopPropagation()
      const current = pointerPosition(event)
      drawBox.style.left = `${Math.min(dragStart.x, current.x)}px`
      drawBox.style.top = `${Math.min(dragStart.y, current.y)}px`
      drawBox.style.width = `${Math.abs(current.x - dragStart.x)}px`
      drawBox.style.height = `${Math.abs(current.y - dragStart.y)}px`
    }
    const onPointerUp = (event) => {
      if (!dragStart || !drawBox) return
      event.preventDefault(); event.stopPropagation()
      const end = pointerPosition(event)
      if (Math.abs(end.x - dragStart.x) >= 8 && Math.abs(end.y - dragStart.y) >= 8) {
        suppressNextClick = true
        window.setTimeout(() => { suppressNextClick = false }, 0)
        const first = map.unproject([Math.min(dragStart.x, end.x), Math.max(dragStart.y, end.y)])
        const second = map.unproject([Math.max(dragStart.x, end.x), Math.min(dragStart.y, end.y)])
        setSelectionBounds({ west: first.lng, south: first.lat, east: second.lng, north: second.lat })
        if (window.innerWidth < 650) setDetailsOpen(false)
        setSelectionMode(false)
      }
      removeDrawBox()
      canvas.releasePointerCapture?.(event.pointerId)
    }
    canvas.addEventListener('pointerdown', onPointerDown, true)
    canvas.addEventListener('pointermove', onPointerMove, true)
    canvas.addEventListener('pointerup', onPointerUp, true)
    canvas.addEventListener('pointercancel', removeDrawBox, true)

    map.on('load', () => {
      map.addSource('relief-imagery', { type: 'raster', tileSize: 256, attribution: 'Esri, Vantor, Earthstar Geographics, and the GIS User Community', tiles: ['https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'] })
      map.addSource('relief-reference', { type: 'raster', tileSize: 256, tiles: ['https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}'] })
      map.addLayer({ id: 'relief-imagery-layer', type: 'raster', source: 'relief-imagery', layout: { visibility: 'visible' }, paint: { 'raster-saturation': -0.12, 'raster-contrast': 0.08, 'raster-brightness-min': 0.08, 'raster-brightness-max': 0.92 } })
      map.addLayer({ id: 'relief-reference-layer', type: 'raster', source: 'relief-reference', layout: { visibility: 'visible' }, paint: { 'raster-opacity': 0.82 } })
      map.addSource('cusco-mask', { type: 'geojson', data: EMPTY })
      map.addSource('cusco-area', { type: 'geojson', data: EMPTY })
      map.addSource('focos', { type: 'geojson', data: EMPTY })
      map.addSource('selection-area', { type: 'geojson', data: EMPTY })
      map.addLayer({ id: 'cusco-mask', type: 'fill', source: 'cusco-mask', paint: { 'fill-color': '#0b1712', 'fill-opacity': 0.38 } })
      map.addLayer({ id: 'study-area-fill', type: 'fill', source: 'cusco-area', paint: { 'fill-color': '#0f766e', 'fill-opacity': 0.035 } })
      map.addLayer({ id: 'study-area-glow', type: 'line', source: 'cusco-area', paint: { 'line-color': '#0f766e', 'line-width': 4, 'line-opacity': 0.18, 'line-blur': 4 } })
      map.addLayer({ id: 'study-area-border', type: 'line', source: 'cusco-area', paint: { 'line-color': '#0f766e', 'line-width': 1.8, 'line-opacity': 0.9, 'line-dasharray': [2, 1.6] } })
      map.addLayer({
        id: 'fire-heat', type: 'heatmap', source: 'focos', maxzoom: 12, layout: { visibility: 'visible' },
        paint: {
          // Peso = aporte del foco a la serie armonizada (eq_foco); sin FRP.
          'heatmap-weight': ['interpolate', ['linear'], ['get', 'eq_foco'], 0, 0.04, 0.25, 0.3, 1, 0.75, 3, 1],
          'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 5, 0.5, 8, 0.9, 11, 1.3],
          'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'],
            0, 'rgba(245,158,11,0)', 0.16, 'rgba(245,158,11,0)', 0.24, 'rgba(245,158,11,.22)',
            0.36, '#fde68a', 0.52, '#f59e0b', 0.68, '#ea580c', 0.84, '#dc2626', 1, '#7f1d1d'],
          'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 5, 10, 7, 18, 10, 34],
          'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 5, 0.8, 11, 0.5],
        },
      })
      map.addLayer({
        id: 'fire-points', type: 'circle', source: 'focos', layout: { visibility: 'none' },
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 5, 2.5, 10, 6],
          'circle-color': ['match', ['get', 'sensor'], 'MODIS', '#ff9b3f', '#f33932'],
          'circle-opacity': ['case', ['==', ['get', 'en_serie'], 1], 0.92, 0.35],
          'circle-stroke-color': '#fff4df', 'circle-stroke-width': 1,
        },
      })
      map.addLayer({ id: 'selection-area-fill', type: 'fill', source: 'selection-area', paint: { 'fill-color': '#5ee7d7', 'fill-opacity': 0.12 } })
      map.addLayer({ id: 'selection-area-line', type: 'line', source: 'selection-area', paint: { 'line-color': '#5ee7d7', 'line-width': 2.5, 'line-dasharray': [2, 1.4] } })

      map.on('mouseenter', 'fire-points', () => { map.getCanvas().style.cursor = 'pointer' })
      map.on('mouseleave', 'fire-points', () => { map.getCanvas().style.cursor = '' })
      map.on('click', 'fire-points', (event) => {
        if (suppressNextClick) return
        const p = event.features?.[0]?.properties
        if (!p) return
        new maplibregl.Popup({ offset: 12, className: 'fw-map-popup' })
          .setLngLat(event.features[0].geometry.coordinates)
          .setDOMContent(createPopupContent(tr('popup.title', { sensor: p.sensor, sat: p.satelite }), [
            { value: `${p.fecha_local} · ${String(p.hora_utc).slice(0, 2)}:${String(p.hora_utc).slice(2)} UTC` },
            { value: Number(p.en_serie) === 1 ? tr('popup.weight', { v: fmt(Number(p.eq_foco), 3) }) : tr('popup.out'), strong: true },
            { value: p.calidad ? tr('popup.quality', { q: calidadLabel(p.calidad) }) : tr('popup.noweight') },
          ]))
          .addTo(map)
      })
      mapReadyRef.current = true
      map.getSource('focos').setData(focosRef.current)
      if (regionRef.current) {
        map.getSource('cusco-area').setData(regionRef.current)
        map.getSource('cusco-mask').setData(maskOf(regionRef.current))
        fitTo(map, boundsOf(regionRef.current))
      }
    })
    return () => {
      mapReadyRef.current = false
      canvas.removeEventListener('pointerdown', onPointerDown, true)
      canvas.removeEventListener('pointermove', onPointerMove, true)
      canvas.removeEventListener('pointerup', onPointerUp, true)
      canvas.removeEventListener('pointercancel', removeDrawBox, true)
      removeDrawBox()
      map.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    regionRef.current = region
    const map = mapRef.current
    if (!region || !mapReadyRef.current || !map) return
    map.getSource('cusco-area').setData(region)
    map.getSource('cusco-mask').setData(maskOf(region))
    fitTo(map, boundsOf(region))
  }, [region])

  useEffect(() => {
    const map = mapRef.current
    if (mapReadyRef.current && map?.getSource('focos')) map.getSource('focos').setData(focos)
  }, [focos])

  useEffect(() => {
    const map = mapRef.current
    if (mapReadyRef.current && map?.getSource('selection-area')) map.getSource('selection-area').setData(boundsToGeoJson(selectionBounds))
  }, [selectionBounds])

  useEffect(() => {
    const map = mapRef.current
    if (!mapReadyRef.current || !map) return
    map.getContainer().classList.toggle('is-selecting', selectionMode)
    const handlers = [map.dragPan, map.touchZoomRotate, map.doubleClickZoom]
    handlers.forEach((h) => (selectionMode ? h.disable() : h.enable()))
  }, [selectionMode])

  useEffect(() => {
    const cancel = (event) => { if (event.key === 'Escape') setSelectionMode(false) }
    window.addEventListener('keydown', cancel)
    return () => window.removeEventListener('keydown', cancel)
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!mapReadyRef.current || !map) return
    map.setLayoutProperty('fire-heat', 'visibility', activeLayer === 'surface' ? 'visible' : 'none')
    map.setLayoutProperty('fire-points', 'visibility', activeLayer === 'points' ? 'visible' : 'none')
  }, [activeLayer])

  useEffect(() => {
    const map = mapRef.current
    if (!mapReadyRef.current || !map?.getLayer('relief-imagery-layer')) return
    const visibility = baseMap === 'relief' ? 'visible' : 'none'
    map.setLayoutProperty('relief-imagery-layer', 'visibility', visibility)
    map.setLayoutProperty('relief-reference-layer', 'visibility', visibility)
  }, [baseMap])

  // "Límite" resalta Cusco sin apagar la densidad ni los puntos.
  useEffect(() => {
    const map = mapRef.current
    if (!mapReadyRef.current || !map) return
    map.setPaintProperty('study-area-fill', 'fill-opacity', showBoundary ? 0.22 : 0.035)
    map.setPaintProperty('study-area-border', 'line-width', showBoundary ? 3 : 1.8)
  }, [showBoundary])

  const selectMonth = (year, m) => { setPlaying(false); setSelected({ year, month: m }) }
  const shiftYear = (delta) => setSelected((s) => ({ year: Math.min(LAST_YEAR, Math.max(FIRST_YEAR, s.year + delta)), month: null }))
  const toggleSelectionMode = () => {
    setPlaying(false)
    setSelectionMode((active) => { if (!active) setSelectionBounds(null); return !active })
  }
  const clearSelection = () => { setSelectionMode(false); setSelectionBounds(null) }
  const focusCusco = () => { if (mapReadyRef.current && region) fitTo(mapRef.current, boundsOf(region)) }

  const runDownload = async (aoiParams, label) => {
    setNotice(tr('csv.preparing'))
    try {
      const r = await downloadCsv(aoiParams, periodo.inicio, periodo.fin)
      setNotice(tr('csv.done', { label, n: fmt(r.rows), total: fmt(r.total, 0) }))
      window.setTimeout(() => setNotice(''), 8000)
    } catch (e) { setNotice(e.message) }
  }

  const selectionArea = useMemo(() => {
    if (!selectionBounds) return 0
    const mid = (selectionBounds.north + selectionBounds.south) / 2 * Math.PI / 180
    return Math.abs(selectionBounds.east - selectionBounds.west) * 111.32 * Math.cos(mid) * Math.abs(selectionBounds.north - selectionBounds.south) * 110.57
  }, [selectionBounds])

  const summaryValue = selected.month ? month?.focos_armonizados : yearTotal
  const unidad = metadata?.unidad
  const notes = [...new Set([...(selected.month ? month?.notes || [] : []), ...(calendar?.notes || [])])]

  return (
    <div className="fw-app">
      <div ref={mapContainerRef} className="fw-map" aria-label={tr('map.aria')} />
      <div className="fw-nubel-brand" aria-label="Nubel Team · FireCal Cusco"><img src="./nubel-team-logo.png" alt="Nubel Team"/></div>
      <div className="fc-map-menu">
        <div className="fc-lang" role="group" aria-label={tr('lang.title')}>{LANGS.map((l) => <button key={l} className={l === lang ? 'is-active' : ''} aria-pressed={l === lang} onClick={() => changeLang(l)}>{l.toUpperCase()}</button>)}</div>
        <button className={`fc-menu-toggle ${toolsOpen ? 'is-open' : ''}`} aria-label={tr('rail.label')} aria-expanded={toolsOpen} onClick={() => setToolsOpen((v) => !v)}><Layers3 size={21}/></button>
        {toolsOpen && <nav className="fw-rail" aria-label={tr('rail.label')}>
          <button className="is-active" title={tr('rail.hotspotsTitle')} onClick={() => { focusCusco(); setDetailsOpen(true); setActiveLayer('surface') }}><Flame size={19}/><span>{tr('rail.hotspots')}</span></button>
          <button className={calendarOpen ? 'is-active' : ''} title={tr('rail.calendar')} onClick={() => setCalendarOpen((v) => !v)}><CalendarDays size={19}/><span>{tr('rail.calendar')}</span></button>
          <button className={selectionMode ? 'is-active select' : ''} title={tr('rail.areaTitle')} onClick={toggleSelectionMode}><Scan size={19}/><span>{tr('rail.area')}</span></button>
          <button className={simpleOpen ? 'is-active' : ''} title={tr('rail.simpleTitle')} onClick={() => setSimpleOpen((v) => !v)}><MessageCircleQuestion size={19}/><span>{tr('rail.simple')}</span></button>
          <button className={layersOpen ? 'is-active' : ''} title={tr('rail.layers')} onClick={() => setLayersOpen((v) => !v)}><SlidersHorizontal size={19}/><span>{tr('rail.layers')}</span></button>
          <button className={detailsOpen ? 'is-active' : ''} title={tr('rail.infoTitle')} onClick={() => setDetailsOpen((v) => !v)}><Info size={19}/><span>{tr('rail.info')}</span></button>
        </nav>}
      </div>
      {detailsOpen && <aside className="fw-summary">
        <div className="fw-summary-head"><div><p>{tr('summary.kicker')}</p><h1>{unidad?.nombre || tr('unit.name')}</h1><span>{periodo.label}{month?.calidad ? ` · ${calidadLabel(month.calidad)}` : ''}</span></div><button onClick={() => setDetailsOpen(false)} title={tr('btn.close')} aria-label={tr('btn.close')}><X size={17}/></button></div>
        <div className="fw-summary-status">{selected.month ? <CategoryBadge categoria={month?.categoria}/> : <span className="fw-risk fw-risk--bajo"><i/>{tr('summary.yearTotal')}</span>}<span>{loading ? tr('summary.loading') : tr('summary.onMap', { n: fmt(focos.n_focos || 0) })}</span></div>
        {error && <div className="fw-error"><ShieldAlert size={16}/>{error}</div>}
        <div className="fw-metrics">
          <Metric icon={Flame} label={tr('metric.hotspots')} value={fmtFocos(summaryValue)} tone="red"/>
          <Metric icon={Gauge} label={selected.month ? tr('metric.monthMedian') : tr('metric.monthsFire')} value={selected.month ? fmt(month?.mediana_hist, 1) : yearCells.filter((c) => c.focos_armonizados > 0).length} tone="orange"/>
          <Metric icon={CalendarDays} label={selected.month ? tr('metric.anomaly') : tr('metric.cellDays')} value={selected.month ? (month?.anomalia ?? '–') : fmt(yearCells.reduce((s, c) => s + (c.celdas_dia || 0), 0))} tone="green"/>
          <Metric icon={Satellite} label={tr('metric.modisViirs')} value={selected.month ? `${fmt(month?.focos_modis)} / ${fmt(month?.focos_viirs)}` : `${fmt(yearCells.reduce((s, c) => s + (c.focos_modis || 0), 0))} / ${fmt(yearCells.reduce((s, c) => s + (c.focos_viirs || 0), 0))}`} tone="blue"/>
        </div>
        {selected.month && month?.incertidumbre > 0 && <p className="fc-margin">{tr('summary.margin', { a: fmt(month.rango[0], 1), b: fmt(month.rango[1], 1) })}</p>}
        <div className="fw-sensor-row"><span><i className="modis"/>MODIS · 1 km</span><span><i className="viirs"/>VIIRS · 375 m</span></div>
        <div className="fw-summary-actions"><button onClick={() => setCalendarOpen(true)}><CalendarDays size={16}/>{tr('rail.calendar')}</button><button onClick={() => runDownload(aoi, tr('csv.cusco'))}><Download size={16}/>CSV</button></div>
        {notice && <p className="fc-notice">{notice}</p>}
        <p className="fw-disclaimer">{unidad?.definicion} {tr('disclaimer')}</p>
        {notes.length > 0 && <ul className="fc-notes">{notes.map((n) => <li key={n}>{n}</li>)}</ul>}
        {metadata && <p className="fc-credits">{metadata.creditos?.[0]}</p>}
      </aside>}
      {layersOpen && !selectionBounds && <aside className="fw-layers">
        <div className="fw-layers-title"><span>{tr('layers.title')}</span><SlidersHorizontal size={15}/></div>
        <LayerButton active={activeLayer === 'surface'} icon={ThermometerSun} label={tr('layers.density')} tone="heat" onClick={() => setActiveLayer('surface')}/>
        <LayerButton active={activeLayer === 'points'} icon={MapPin} label={tr('layers.points')} tone="points" onClick={() => setActiveLayer('points')}/>
        <LayerButton active={showBoundary} icon={Layers3} label={tr('layers.boundary')} tone="boundary" onClick={() => setShowBoundary((v) => !v)}/>
        <LayerButton active={selectionMode} icon={Scan} label={tr('layers.area')} tone="select" onClick={toggleSelectionMode}/>
      </aside>}
      {layersOpen && !selectionBounds && <aside className="fw-display-dock" aria-label={tr('basemap.dock')}>
        <div className="fw-display-modes" role="group" aria-label={tr('basemap.title')}>
          <button className={baseMap === 'standard' ? 'is-active' : ''} aria-pressed={baseMap === 'standard'} title={tr('basemap.standard')} onClick={() => setBaseMap('standard')}><MapIcon size={14}/><span>{tr('basemap.standard')}</span></button>
          <button className={baseMap === 'relief' ? 'is-active' : ''} aria-pressed={baseMap === 'relief'} title={tr('basemap.relief')} onClick={() => setBaseMap('relief')}><Mountain size={14}/><span>{tr('basemap.relief')}</span></button>
        </div>
        {activeLayer === 'points'
          ? <div className="fw-heat-legend fc-dock-points"><header><span>{tr('layers.pointsLegend')}</span></header><p><i className="modis"/>MODIS</p><p><i className="viirs"/>VIIRS</p><p><i className="outside"/>{tr('layers.outside')}</p></div>
          : <div className="fw-heat-legend"><header><span>{tr('layers.scaleDensity')}</span></header><i/><div><span>{tr('scale.low')}</span><span>{tr('scale.mid')}</span><span>{tr('scale.high')}</span></div></div>}
      </aside>}
      <div className="fw-map-meta"><button onClick={focusCusco}><MapPin size={13}/>Cusco</button><span><Satellite size={13}/>MODIS + VIIRS</span><span><CalendarDays size={13}/>{periodo.label}</span></div>
      {selectionMode && <div className="fw-draw-hint"><Scan size={20}/><div><b>{tr('draw.title')}</b><span>{tr('draw.hint')}</span></div><button onClick={() => setSelectionMode(false)} title={tr('btn.cancel')}><X size={16}/></button></div>}
      {selectionBounds && !simpleOpen && <aside className="fw-selection-card">
        <div className="fw-selection-head"><div><p>{tr('sel.kicker')}</p><h2>{tr('sel.title')}</h2><span>{periodo.label} · {tr('sel.within')}</span></div><button onClick={clearSelection} title={tr('sel.clear')}><Trash2 size={17}/></button></div>
        <SatelliteSelectionMap bounds={selectionBounds} focos={selection?.focos || EMPTY}/>
        <div className="fw-selection-source"><span>{tr('sel.source')}</span><b>Esri World Imagery · NASA FIRMS</b></div>
        {selection?.paused && <p className="fc-notice">{tr('sel.paused')}</p>}
        {selection?.error ? <div className="fw-error"><ShieldAlert size={16}/>{selection.error}</div> : <div className="fw-selection-grid">
          <article><span>{tr('metric.hotspots')}</span><b>{selection?.calendar ? fmtFocos(selection.calendar.total_focos_armonizados) : '…'}</b></article>
          <article><span>{tr('metric.cellDays')}</span><b>{selection?.calendar ? fmt(selection.calendar.celdas.reduce((s, c) => s + (c.celdas_dia || 0), 0)) : '…'}</b></article>
          <article><span>{tr('metric.modisViirs')}</span><b>{selection?.calendar ? `${fmt(selection.calendar.celdas.reduce((s, c) => s + (c.focos_modis || 0), 0))} / ${fmt(selection.calendar.celdas.reduce((s, c) => s + (c.focos_viirs || 0), 0))}` : '…'}</b></article>
          <article><span>{tr('sel.onMap')}</span><b>{selection?.focos ? fmt(selection.focos.n_focos) : '…'}</b></article>
          <article><span>{tr('sel.boxArea')}</span><b>{selectionArea >= 1000 ? tr('sel.thousandKm2', { v: fmt(selectionArea / 1000, 1) }) : `${fmt(selectionArea)} km²`}</b></article>
          <article><span>{tr('sel.monthAnomaly')}</span><b>{selected.month && selection?.calendar ? (selection.calendar.celdas[0]?.categoria ? catLabel(selection.calendar.celdas[0].categoria) : '–') : tr('sel.pickMonth')}</b></article>
        </div>}
        <div className="fw-selection-actions"><button onClick={toggleSelectionMode}><Scan size={15}/>{tr('sel.redraw')}</button><button onClick={() => selection?.bbox && runDownload(selection.bbox, tr('csv.area'))} disabled={!selection?.calendar}><Download size={15}/>CSV</button></div>
      </aside>}
      {simpleOpen && <SimplePanel key={lang} aoi={selection?.bbox || aoi} etiqueta={selection?.bbox ? 'area' : 'cusco'} onClose={() => setSimpleOpen(false)}/>}
      {calendarOpen && <CalendarPanel calendar={calendar} mode={calendarMode} setMode={setCalendarMode} selected={selected} onSelect={selectMonth} onClose={() => setCalendarOpen(false)}/>}
      <section className="fw-timeline fc-timeline">
        <button className="fw-play" onClick={() => setPlaying((v) => !v)} title={playing ? tr('timeline.pause') : tr('timeline.play')}>{playing ? <Pause size={19}/> : <Play size={19}/>}</button>
        <div className="fw-timeline-panel" style={{ '--progress': `${selected.month ? ((selected.month - 1) / 11) * 100 : 100}%` }}>
          <div className={`fw-time-callout ${selected.month === 1 ? 'is-start' : !selected.month || selected.month === 12 ? 'is-end' : ''}`}><b>{periodo.label}</b><span>{tr('timeline.yearSum', { n: fmtFocos(selected.month ? (month?.focos_armonizados ?? 0) : yearTotal) })}</span></div>
          <div className="fw-days">
            {MESES.map((label, idx) => {
              const c = yearCells.find((x) => x.mes === idx + 1)
              const noData = !c || c.sin_dato
              return <button key={label} disabled={noData} className={[selected.month === idx + 1 ? 'is-active' : '', c?.calidad === 'extrapolado' ? 'is-extrap' : ''].join(' ')} onClick={() => selectMonth(selected.year, idx + 1)} title={noData ? tr('noData') : tr('popup.weight', { v: fmt(c.focos_armonizados, 2) })}><span>{label}</span><small>{noData ? '–' : fmtFocos(c.focos_armonizados)}</small><i style={{ width: `${noData ? 0 : Math.round(100 * c.focos_armonizados / yearMax)}%` }}/></button>
            })}
          </div>
          <div className="fw-timeline-options">
            <button className={selected.month === null ? 'is-active' : ''} title={tr('timeline.allYear')} aria-label={tr('timeline.allYear')} onClick={() => { setSelected((s) => ({ year: s.year, month: null })); setPlaying(false) }}><Layers3 size={13}/><span>{tr('timeline.allYear')}</span></button>
            <div className="fw-year-scale" aria-label={tr('timeline.years')}>
              <button className="fc-year" onClick={() => shiftYear(-1)} title={tr('timeline.prevYear')} disabled={selected.year <= FIRST_YEAR}><ChevronLeft size={13}/></button>
              <div className="fc-years" ref={yearsRef}>
                {YEARS.map((y) => <button key={y} aria-label={String(y)} title={String(y)} className={selected.year === y ? 'is-active' : ''} onClick={() => { setPlaying(false); setSelected({ year: y, month: null }) }}>{String(y).slice(2)}</button>)}
              </div>
              <button className="fc-year" onClick={() => shiftYear(1)} title={tr('timeline.nextYear')} disabled={selected.year >= LAST_YEAR}><ChevronRight size={13}/></button>
            </div>
            <div className="fw-timeline-source"><span>NASA FIRMS · UTC−5</span><b title={latency ? `${latency} ms` : undefined}>{tr('timeline.historic')}</b></div>
          </div>
        </div>
      </section>
    </div>
  )
}

export default FireMapApp
