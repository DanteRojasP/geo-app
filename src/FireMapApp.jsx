import { createElement, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import {
  Activity, CalendarDays, CircleHelp, CloudSun, Download, Flame, Gauge, Info,
  Layers3, LocateFixed, MapPin, Menu, Pause, Play, Radar, RefreshCw, Satellite,
  Scan, Search, ShieldAlert, SlidersHorizontal, ThermometerSun, Trash2, X,
} from 'lucide-react'
import cuscoBoundaryRaw from './data/cusco-boundary.json'
import { getFireOverview } from './services/fireApi.js'

maplibregl.setWorkerUrl(maplibreWorkerUrl)

const MAP_STYLE = 'https://tiles.openfreemap.org/styles/positron'
const PERU_DEPARTMENTS_URL = 'https://raw.githubusercontent.com/juaneladio/peru-geojson/master/peru_departamental_simple.geojson'
const EMPTY_FEATURE_COLLECTION = { type: 'FeatureCollection', features: [] }
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
const CUSCO_CENTER = [-71.97, -13.53]
const PERU_BOUNDS = new maplibregl.LngLatBounds([-81.45, -18.5], [-68.55, 0.25])
const CUSCO_FEATURE = { ...cuscoBoundaryRaw.features[0], id: 'cusco' }
const CUSCO_BOUNDARY = { type: 'FeatureCollection', features: [CUSCO_FEATURE] }
const CUSCO_RING = CUSCO_FEATURE.geometry.coordinates[0]
const CUSCO_POINTS = CUSCO_FEATURE.geometry.coordinates.flat()
const CUSCO_BOUNDS = CUSCO_POINTS.reduce(
  (bounds, point) => bounds.extend(point),
  new maplibregl.LngLatBounds(CUSCO_POINTS[0], CUSCO_POINTS[0]),
)
const CUSCO_MASK = {
  type: 'FeatureCollection',
  features: [{
    type: 'Feature',
    properties: {},
    geometry: {
      type: 'Polygon',
      coordinates: [
        [[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]],
        [...CUSCO_RING].reverse(),
      ],
    },
  }],
}

function hotspotsToGeoJson(points) {
  return {
    type: 'FeatureCollection',
    features: points.map((point) => ({
      type: 'Feature',
      id: point.id,
      properties: {
        date: point.date,
        sensor: point.sensor,
        source: point.source || point.sensor,
        frp: Number(point.frp) || 0,
        confidence: Number(point.confidence) || 0,
      },
      geometry: { type: 'Point', coordinates: [point.lon, point.lat] },
    })),
  }
}

function pointInRing(lon, lat, ring) {
  let inside = false
  for (let index = 0, previous = ring.length - 1; index < ring.length; previous = index++) {
    const [x1, y1] = ring[index]
    const [x2, y2] = ring[previous]
    if ((y1 > lat) !== (y2 > lat) && lon < ((x2 - x1) * (lat - y1)) / (y2 - y1) + x1) inside = !inside
  }
  return inside
}

function isInsideCusco(point) {
  const rings = CUSCO_FEATURE.geometry.coordinates
  return pointInRing(point.lon, point.lat, rings[0]) && !rings.slice(1).some((ring) => pointInRing(point.lon, point.lat, ring))
}

function isInsideGeometry(point, geometry) {
  if (!geometry) return false
  const polygons = geometry.type === 'MultiPolygon' ? geometry.coordinates : [geometry.coordinates]
  return polygons.some((polygon) => pointInRing(point.lon, point.lat, polygon[0])
    && !polygon.slice(1).some((ring) => pointInRing(point.lon, point.lat, ring)))
}

function isInsidePeru(point, departments) {
  return departments.features.some((feature) => isInsideGeometry(point, feature.geometry))
}

function addActivityToDepartments(departments, points) {
  return {
    ...departments,
    features: departments.features.map((feature) => {
      const matches = points.filter((point) => isInsideGeometry(point, feature.geometry))
      const frp = matches.reduce((sum, point) => sum + point.frp, 0)
      const confidence = matches.length
        ? Math.round(matches.reduce((sum, point) => sum + point.confidence, 0) / matches.length)
        : 0
      return {
        ...feature,
        properties: {
          ...feature.properties,
          fireCount: matches.length,
          frp: Number(frp.toFixed(1)),
          confidence,
        },
      }
    }),
  }
}

function boundsToGeoJson(bounds) {
  if (!bounds) return { type: 'FeatureCollection', features: [] }
  const { west, east, south, north } = bounds
  return {
    type: 'FeatureCollection',
    features: [{
      type: 'Feature',
      properties: {},
      geometry: { type: 'Polygon', coordinates: [[[west, south], [east, south], [east, north], [west, north], [west, south]]] },
    }],
  }
}

function summarizeHotspots(points) {
  const frp = points.reduce((sum, point) => sum + point.frp, 0)
  const confidence = points.length ? Math.round(points.reduce((sum, point) => sum + point.confidence, 0) / points.length) : 0
  const modis = points.filter((point) => point.sensor === 'MODIS').length
  const risk = points.length >= 25 || frp >= 600 ? 'Alto' : points.length >= 10 || frp >= 180 ? 'Moderado' : 'Bajo'
  return { frp, confidence, modis, viirs: points.length - modis, risk }
}

function fitToCusco(map, compact = window.innerWidth < 650) {
  map.fitBounds(CUSCO_BOUNDS, {
    padding: compact
      ? { top: 76, right: 24, bottom: 112, left: 24 }
      : { top: 100, right: 160, bottom: 130, left: 430 },
    duration: 900,
    maxZoom: 8.2,
  })
}

function fitToPeru(map, compact = window.innerWidth < 650) {
  map.fitBounds(PERU_BOUNDS, {
    padding: compact
      ? { top: 76, right: 24, bottom: 112, left: 24 }
      : { top: 100, right: 160, bottom: 130, left: 430 },
    duration: 900,
    maxZoom: 5.7,
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

function RiskBadge({ level }) {
  return <span className={`fw-risk fw-risk--${level.toLowerCase()}`}><i />Riesgo {level}</span>
}

function LayerButton({ active, icon, label, onClick, tone }) {
  return <button className={`fw-layer-button ${active ? 'is-active' : ''}`} onClick={onClick} title={label}><span className={tone}>{createElement(icon, { size: 18 })}</span><b>{label}</b></button>
}

function Metric({ icon, label, value, tone }) {
  return <div className="fw-metric"><span className={tone}>{createElement(icon, { size: 16 })}</span><div><b>{value}</b><small>{label}</small></div></div>
}

function SatelliteSelectionMap({ bounds, hotspots }) {
  const containerRef = useRef(null)
  const previewMapRef = useRef(null)
  const previewReadyRef = useRef(false)
  const hotspotsRef = useRef(hotspots)
  const boundsRef = useRef(bounds)
  hotspotsRef.current = hotspots
  boundsRef.current = bounds

  const fitPreview = useCallback((map, nextBounds) => {
    map.fitBounds([[nextBounds.west, nextBounds.south], [nextBounds.east, nextBounds.north]], { padding: 22, duration: 0, maxZoom: 12 })
  }, [])

  useEffect(() => {
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: SATELLITE_STYLE,
      center: [(boundsRef.current.west + boundsRef.current.east) / 2, (boundsRef.current.south + boundsRef.current.north) / 2],
      zoom: 8,
      minZoom: 5,
      maxZoom: 16,
      attributionControl: false,
      antialias: true,
    })
    previewMapRef.current = map
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-left')
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.on('load', () => {
      map.addSource('preview-hotspots', { type: 'geojson', data: hotspotsToGeoJson(hotspotsRef.current) })
      map.addLayer({
        id: 'preview-heat', type: 'heatmap', source: 'preview-hotspots', maxzoom: 14,
        paint: {
          'heatmap-weight': ['interpolate', ['linear'], ['get', 'frp'], 0, 0.2, 40, 0.6, 100, 1],
          'heatmap-intensity': 1.35,
          'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], 0, 'rgba(255,230,110,0)', 0.25, '#ffe66d', 0.5, '#ff9f32', 0.72, '#ff4c2f', 1, '#9f001f'],
          'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 6, 18, 12, 42],
          'heatmap-opacity': 0.78,
        },
      })
      map.addLayer({
        id: 'preview-points', type: 'circle', source: 'preview-hotspots',
        paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 6, 4, 12, 8], 'circle-color': '#ff5a3d', 'circle-opacity': 0.95, 'circle-stroke-color': '#fff5dc', 'circle-stroke-width': 1.4 },
      })
      previewReadyRef.current = true
      fitPreview(map, boundsRef.current)
    })
    return () => {
      previewReadyRef.current = false
      map.remove()
      previewMapRef.current = null
    }
  }, [fitPreview])

  useEffect(() => {
    const map = previewMapRef.current
    if (!previewReadyRef.current || !map) return
    map.getSource('preview-hotspots').setData(hotspotsToGeoJson(hotspots))
    fitPreview(map, bounds)
  }, [bounds, fitPreview, hotspots])

  return <div className="fw-satellite-preview"><div ref={containerRef} className="fw-satellite-map"/><span className="fw-satellite-badge"><i/>IMAGEN SATELITAL</span><div className="fw-satellite-legend"><span><i className="heat"/>Calor FIRMS</span><span><i className="point"/>Detección</span></div></div>
}

function FireMapApp() {
  const mapContainerRef = useRef(null)
  const mapRef = useRef(null)
  const mapReadyRef = useRef(false)
  const hotspotsRef = useRef([])
  const departmentsRef = useRef(EMPTY_FEATURE_COLLECTION)
  const selectionModeRef = useRef(false)
  const [result, setResult] = useState({ hotspots: [], mode: 'demo', metadata: {} })
  const [departments, setDepartments] = useState(EMPTY_FEATURE_COLLECTION)
  const [activeScope, setActiveScope] = useState('peru')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [activeLayer, setActiveLayer] = useState('activity')
  const [selectedDate, setSelectedDate] = useState('all')
  const [playing, setPlaying] = useState(false)
  const [detailsOpen, setDetailsOpen] = useState(true)
  const [layersOpen, setLayersOpen] = useState(true)
  const [studySelected, setStudySelected] = useState(false)
  const [selectionMode, setSelectionMode] = useState(false)
  const [selectionBounds, setSelectionBounds] = useState(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await getFireOverview({ department: 'peru', startYear: 2021, endYear: 2026 })
      setResult(data)
    } catch (caught) {
      setError(caught.message || 'No se pudieron consultar las detecciones.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  useEffect(() => {
    let active = true
    fetch(PERU_DEPARTMENTS_URL)
      .then((response) => {
        if (!response.ok) throw new Error(`Límites: ${response.status}`)
        return response.json()
      })
      .then((data) => { if (active) setDepartments(data) })
      .catch(() => { if (active) setError('El mapa funciona, pero no se pudieron cargar los límites departamentales.') })
    return () => { active = false }
  }, [])

  const peruHotspots = useMemo(() => departments.features.length
    ? result.hotspots.filter((point) => isInsidePeru(point, departments))
    : result.hotspots, [departments, result.hotspots])
  const scopedHotspots = useMemo(() => activeScope === 'cusco'
    ? peruHotspots.filter(isInsideCusco)
    : peruHotspots, [activeScope, peruHotspots])
  const dates = useMemo(() => [...new Set(scopedHotspots.map((point) => point.date).filter(Boolean))].sort().slice(-5), [scopedHotspots])
  const visibleHotspots = useMemo(() => selectedDate === 'all' ? scopedHotspots : scopedHotspots.filter((point) => point.date === selectedDate), [scopedHotspots, selectedDate])
  const mappedDepartments = useMemo(() => addActivityToDepartments(departments, visibleHotspots), [departments, visibleHotspots])
  const selectedHotspots = useMemo(() => selectionBounds ? visibleHotspots.filter((point) => point.lon >= selectionBounds.west && point.lon <= selectionBounds.east && point.lat >= selectionBounds.south && point.lat <= selectionBounds.north) : [], [selectionBounds, visibleHotspots])
  hotspotsRef.current = visibleHotspots
  departmentsRef.current = mappedDepartments
  selectionModeRef.current = selectionMode

  useEffect(() => {
    if (!playing || !dates.length) return undefined
    const timer = window.setInterval(() => {
      setSelectedDate((current) => {
        const index = current === 'all' ? -1 : dates.indexOf(current)
        return dates[(index + 1) % dates.length]
      })
    }, 1400)
    return () => window.clearInterval(timer)
  }, [dates, playing])

  useEffect(() => {
    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: MAP_STYLE,
      center: [-75.1, -9.2],
      zoom: 4.2,
      minZoom: 3.4,
      maxZoom: 14,
      attributionControl: false,
      antialias: true,
    })
    mapRef.current = map
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right')
    map.addControl(new maplibregl.NavigationControl({ showCompass: false, visualizePitch: false }), 'bottom-right')
    const canvas = map.getCanvas()
    const canvasContainer = map.getCanvasContainer()
    let dragStart = null
    let drawBox = null
    let suppressNextClick = false
    let hoveredDepartmentId = null

    const pointerPosition = (event) => {
      const rect = canvas.getBoundingClientRect()
      return { x: event.clientX - rect.left, y: event.clientY - rect.top }
    }

    const removeDrawBox = () => {
      drawBox?.remove()
      drawBox = null
      dragStart = null
    }

    const onPointerDown = (event) => {
      if (!selectionModeRef.current || event.button !== 0) return
      event.preventDefault()
      event.stopPropagation()
      dragStart = pointerPosition(event)
      drawBox = document.createElement('div')
      drawBox.className = 'fw-selection-box'
      canvasContainer.appendChild(drawBox)
      canvas.setPointerCapture?.(event.pointerId)
    }

    const onPointerMove = (event) => {
      if (!dragStart || !drawBox) return
      event.preventDefault()
      event.stopPropagation()
      const current = pointerPosition(event)
      drawBox.style.left = `${Math.min(dragStart.x, current.x)}px`
      drawBox.style.top = `${Math.min(dragStart.y, current.y)}px`
      drawBox.style.width = `${Math.abs(current.x - dragStart.x)}px`
      drawBox.style.height = `${Math.abs(current.y - dragStart.y)}px`
    }

    const onPointerUp = (event) => {
      if (!dragStart || !drawBox) return
      event.preventDefault()
      event.stopPropagation()
      const end = pointerPosition(event)
      const width = Math.abs(end.x - dragStart.x)
      const height = Math.abs(end.y - dragStart.y)
      if (width >= 8 && height >= 8) {
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

    const showAreaPopup = (lngLat) => {
      new maplibregl.Popup({ closeButton: false, offset: 12, className: 'fw-map-popup' })
        .setLngLat(lngLat)
        .setDOMContent(createPopupContent('Zona de estudio · Cusco', [
          { value: 'Límite departamental oficial' },
          { value: 'Fuente: INEI vía IGN', strong: true },
        ]))
        .addTo(map)
    }

    map.on('load', () => {
      map.addSource('peru-departments', { type: 'geojson', data: departmentsRef.current, generateId: true })
      map.addSource('cusco-area', { type: 'geojson', data: CUSCO_BOUNDARY })
      map.addSource('fire-hotspots', { type: 'geojson', data: hotspotsToGeoJson([]) })
      map.addSource('selection-area', { type: 'geojson', data: boundsToGeoJson(null) })
      map.addSource('selected-hotspots', { type: 'geojson', data: hotspotsToGeoJson([]) })

      map.addLayer({
        id: 'department-fill', type: 'fill', source: 'peru-departments',
        paint: {
          'fill-color': ['interpolate', ['linear'], ['coalesce', ['get', 'fireCount'], 0],
            0, '#17362c', 1, '#d9ef8b', 5, '#fee08b', 15, '#fdae61', 35, '#f46d43', 70, '#a50026'],
          'fill-opacity': ['case', ['boolean', ['feature-state', 'hover'], false], 0.9, 0.72],
        },
      })
      map.addLayer({
        id: 'department-lines', type: 'line', source: 'peru-departments',
        paint: { 'line-color': '#9eb3a8', 'line-width': ['interpolate', ['linear'], ['zoom'], 4, 0.7, 8, 1.5], 'line-opacity': 0.58 },
      })
      map.addLayer({
        id: 'study-area-fill', type: 'fill', source: 'cusco-area',
        paint: { 'fill-color': '#b8f36b', 'fill-opacity': ['case', ['boolean', ['feature-state', 'selected'], false], 0.22, ['boolean', ['feature-state', 'hover'], false], 0.16, 0.035] },
      })
      map.addLayer({
        id: 'study-area-glow', type: 'line', source: 'cusco-area',
        paint: { 'line-color': '#b8f36b', 'line-width': ['case', ['boolean', ['feature-state', 'hover'], false], 8, 5], 'line-opacity': 0.25, 'line-blur': 5 },
      })
      map.addLayer({
        id: 'study-area-border', type: 'line', source: 'cusco-area',
        paint: { 'line-color': '#b8f36b', 'line-width': ['case', ['boolean', ['feature-state', 'selected'], false], 3, ['boolean', ['feature-state', 'hover'], false], 2.8, 1.8], 'line-opacity': 0.95, 'line-dasharray': [2, 1.6] },
      })
      map.addLayer({
        id: 'fire-heat', type: 'heatmap', source: 'fire-hotspots', maxzoom: 12,
        paint: {
          'heatmap-weight': ['interpolate', ['linear'], ['get', 'frp'], 0, 0.18, 40, 0.55, 100, 1],
          'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 5, 0.75, 10, 1.75],
          'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], 0, 'rgba(255,229,122,0)', 0.2, '#ffe57a', 0.42, '#ffb13b', 0.65, '#ff6534', 0.82, '#eb2d2d', 1, '#9f001f'],
          'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 5, 20, 8, 38, 11, 58],
          'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 5, 0.72, 11, 0.35],
        },
      })
      map.addLayer({
        id: 'fire-points', type: 'circle', source: 'fire-hotspots',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 5, 4, 10, 8],
          'circle-color': ['match', ['get', 'sensor'], 'MODIS', '#ff9b3f', '#f33932'],
          'circle-opacity': 0.92,
          'circle-stroke-color': '#fff4df',
          'circle-stroke-width': 1.2,
        },
      })
      map.addLayer({ id: 'selection-area-fill', type: 'fill', source: 'selection-area', paint: { 'fill-color': '#5ee7d7', 'fill-opacity': 0.12 } })
      map.addLayer({ id: 'selection-area-line', type: 'line', source: 'selection-area', paint: { 'line-color': '#5ee7d7', 'line-width': 2.5, 'line-dasharray': [2, 1.4] } })
      map.addLayer({
        id: 'selected-fire-points', type: 'circle', source: 'selected-hotspots',
        paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 5, 7, 10, 11], 'circle-color': '#5ee7d7', 'circle-opacity': 0.95, 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2 },
      })

      map.on('mousemove', 'department-fill', (event) => {
        if (selectionModeRef.current) return
        const feature = event.features?.[0]
        if (!feature) return
        if (hoveredDepartmentId !== null) map.setFeatureState({ source: 'peru-departments', id: hoveredDepartmentId }, { hover: false })
        hoveredDepartmentId = feature.id
        map.setFeatureState({ source: 'peru-departments', id: hoveredDepartmentId }, { hover: true })
        map.getCanvas().style.cursor = 'pointer'
      })
      map.on('mouseleave', 'department-fill', () => {
        if (hoveredDepartmentId !== null) map.setFeatureState({ source: 'peru-departments', id: hoveredDepartmentId }, { hover: false })
        hoveredDepartmentId = null
        map.getCanvas().style.cursor = ''
      })
      map.on('click', 'department-fill', (event) => {
        if (selectionModeRef.current || suppressNextClick) return
        const feature = event.features?.[0]
        if (!feature || feature.properties?.NOMBDEP === 'CUSCO') return
        const properties = feature.properties
        new maplibregl.Popup({ offset: 10, className: 'fw-map-popup' })
          .setLngLat(event.lngLat)
          .setDOMContent(createPopupContent(properties.NOMBDEP || 'Departamento', [
            { value: `${properties.fireCount || 0} detecciones recientes` },
            { value: `${Number(properties.frp || 0).toFixed(1)} MW FRP`, strong: true },
            { value: properties.fireCount ? `Confianza media ${properties.confidence}%` : 'Sin actividad térmica visible' },
          ]))
          .addTo(map)
      })

      map.on('mouseenter', 'study-area-fill', () => {
        map.getCanvas().style.cursor = 'pointer'
        map.setFeatureState({ source: 'cusco-area', id: 'cusco' }, { hover: true })
      })
      map.on('mouseleave', 'study-area-fill', () => {
        map.getCanvas().style.cursor = ''
        map.setFeatureState({ source: 'cusco-area', id: 'cusco' }, { hover: false })
      })
      map.on('click', 'study-area-fill', (event) => {
        if (suppressNextClick) return
        map.setFeatureState({ source: 'cusco-area', id: 'cusco' }, { selected: true })
        setStudySelected(true)
        setActiveScope('cusco')
        setSelectedDate('all')
        setSelectionBounds(null)
        fitToCusco(map)
        showAreaPopup(event.lngLat)
      })
      map.on('mouseenter', 'fire-points', () => { map.getCanvas().style.cursor = 'pointer' })
      map.on('mouseleave', 'fire-points', () => { map.getCanvas().style.cursor = '' })
      map.on('click', 'fire-points', (event) => {
        if (suppressNextClick) return
        const feature = event.features?.[0]
        if (!feature) return
        const properties = feature.properties
        new maplibregl.Popup({ offset: 12, className: 'fw-map-popup' })
          .setLngLat(feature.geometry.coordinates)
          .setDOMContent(createPopupContent('Posible incendio', [
            { value: `${properties.sensor} · ${properties.date}` },
            { value: `${Number(properties.frp).toFixed(1)} MW`, strong: true },
            { value: `Confianza ${properties.confidence}%` },
          ]))
          .addTo(map)
      })

      mapReadyRef.current = true
      map.getSource('fire-hotspots').setData(hotspotsToGeoJson(hotspotsRef.current))
      fitToPeru(map)
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
    const map = mapRef.current
    if (!mapReadyRef.current || !map?.getSource('fire-hotspots')) return
    map.getSource('fire-hotspots').setData(hotspotsToGeoJson(visibleHotspots))
  }, [visibleHotspots])

  useEffect(() => {
    const map = mapRef.current
    if (!mapReadyRef.current || !map?.getSource('peru-departments')) return
    map.getSource('peru-departments').setData(mappedDepartments)
  }, [mappedDepartments])

  useEffect(() => {
    const map = mapRef.current
    if (!mapReadyRef.current || !map) return
    map.getContainer().classList.toggle('is-selecting', selectionMode)
    if (selectionMode) {
      map.dragPan.disable()
      map.touchZoomRotate.disable()
      map.doubleClickZoom.disable()
    } else {
      map.dragPan.enable()
      map.touchZoomRotate.enable()
      map.doubleClickZoom.enable()
    }
  }, [selectionMode])

  useEffect(() => {
    const map = mapRef.current
    if (!mapReadyRef.current || !map?.getSource('selection-area')) return
    map.getSource('selection-area').setData(boundsToGeoJson(selectionBounds))
    map.getSource('selected-hotspots').setData(hotspotsToGeoJson(selectedHotspots))
  }, [selectedHotspots, selectionBounds])

  useEffect(() => {
    const cancelSelection = (event) => {
      if (event.key === 'Escape') setSelectionMode(false)
    }
    window.addEventListener('keydown', cancelSelection)
    return () => window.removeEventListener('keydown', cancelSelection)
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!mapReadyRef.current) return
    map.setLayoutProperty('fire-heat', 'visibility', activeLayer === 'heat' ? 'visible' : 'none')
    map.setLayoutProperty('fire-points', 'visibility', activeLayer === 'points' ? 'visible' : 'none')
    map.setPaintProperty('department-fill', 'fill-opacity', activeLayer === 'activity'
      ? ['case', ['boolean', ['feature-state', 'hover'], false], 0.9, 0.72]
      : ['case', ['boolean', ['feature-state', 'hover'], false], 0.18, 0.045])
    map.setPaintProperty('study-area-fill', 'fill-opacity', activeLayer === 'aoi'
      ? ['case', ['boolean', ['feature-state', 'selected'], false], 0.3, ['boolean', ['feature-state', 'hover'], false], 0.22, 0.12]
      : ['case', ['boolean', ['feature-state', 'selected'], false], 0.22, ['boolean', ['feature-state', 'hover'], false], 0.16, 0.035])
  }, [activeLayer])

  const focusStudyArea = () => {
    const map = mapRef.current
    if (!mapReadyRef.current || !map) return
    const nextScope = activeScope === 'peru' ? 'cusco' : 'peru'
    const nextSelected = nextScope === 'cusco'
    setActiveScope(nextScope)
    setStudySelected(nextSelected)
    setSelectedDate('all')
    setSelectionBounds(null)
    map.setFeatureState({ source: 'cusco-area', id: 'cusco' }, { selected: nextSelected })
    if (nextSelected) fitToCusco(map)
    else fitToPeru(map)
  }

  const toggleSelectionMode = () => {
    setPlaying(false)
    setSelectionMode((active) => {
      if (!active) setSelectionBounds(null)
      return !active
    })
  }

  const clearSelection = () => {
    setSelectionMode(false)
    setSelectionBounds(null)
  }

  const stats = useMemo(() => summarizeHotspots(visibleHotspots), [visibleHotspots])
  const selectionStats = useMemo(() => summarizeHotspots(selectedHotspots), [selectedHotspots])
  const selectionArea = useMemo(() => {
    if (!selectionBounds) return 0
    const middleLatitude = (selectionBounds.north + selectionBounds.south) / 2 * Math.PI / 180
    const width = Math.abs(selectionBounds.east - selectionBounds.west) * 111.32 * Math.cos(middleLatitude)
    const height = Math.abs(selectionBounds.north - selectionBounds.south) * 110.57
    return width * height
  }, [selectionBounds])

  const downloadCsv = (points, suffix) => {
    const rows = ['fecha,sensor,fuente,latitud,longitud,frp_mw,confianza']
    points.forEach((point) => rows.push([point.date, point.sensor, point.source || point.sensor, point.lat, point.lon, point.frp, point.confidence].join(',')))
    const blob = new Blob([rows.join('\n')], { type: 'text/csv;charset=utf-8' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `${activeScope}-posibles-incendios-${suffix}.csv`
    link.click()
    URL.revokeObjectURL(link.href)
  }

  const formatDay = (date) => new Intl.DateTimeFormat('es-PE', { weekday: 'short', day: '2-digit' }).format(new Date(`${date}T12:00:00`)).replace('.', '')
  const formatDate = (date) => date ? new Intl.DateTimeFormat('es-PE', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(`${date}T12:00:00`)) : 'Últimos 5 días'

  return (
    <div className="fw-app">
      <div ref={mapContainerRef} className="fw-map" aria-label="Mapa nacional interactivo de focos térmicos en Perú" />
      <header className="fw-topbar">
        <div className="fw-brand"><span><Radar size={21}/></span><div><b>FIREWATCH</b><small>PERÚ · MONITOREO</small></div></div>
        <button className="fw-search" onClick={focusStudyArea}><Search size={18}/><div><b>{activeScope === 'peru' ? 'Perú nacional' : 'Cusco, Perú'}</b><small>{activeScope === 'peru' ? 'Abrir zona piloto de Cusco' : 'Volver a la vista nacional'}</small></div><LocateFixed size={18}/></button>
        <div className="fw-top-actions"><span className="fw-live"><i/>{result.mode === 'api' ? 'NASA FIRMS EN VIVO' : 'VISTA DE DEMOSTRACIÓN'}</span><button title="Ayuda"><CircleHelp size={19}/></button><button title="Menú"><Menu size={20}/></button></div>
      </header>
      <nav className="fw-rail" aria-label="Herramientas del mapa">
        <button className="is-active" title="Monitoreo"><Flame size={20}/><span>Fuego</span></button>
        <button className={selectionMode ? 'is-active select' : ''} title="Seleccionar área" onClick={toggleSelectionMode}><Scan size={20}/><span>Área</span></button>
        <button title="Capas" onClick={() => setLayersOpen((value) => !value)}><Layers3 size={20}/><span>Capas</span></button>
        <button title="Alertas"><ShieldAlert size={20}/><span>Alertas</span></button>
        <button title="Información" onClick={() => setDetailsOpen((value) => !value)}><Info size={20}/><span>Info</span></button>
      </nav>
      {detailsOpen && <aside className="fw-summary">
        <div className="fw-summary-head"><div><p>{activeScope === 'peru' ? 'MONITOREO NACIONAL' : 'ZONA PILOTO'}</p><h1>Posibles incendios</h1><span>{activeScope === 'peru' ? 'Perú' : 'Cusco'} · {formatDate(selectedDate === 'all' ? null : selectedDate)}</span></div><button onClick={() => setDetailsOpen(false)}><X size={17}/></button></div>
        <div className="fw-summary-status"><RiskBadge level={stats.risk}/><span>{loading ? 'Actualizando satélites…' : `${visibleHotspots.length} detecciones visibles`}</span></div>
        {error && <div className="fw-error"><ShieldAlert size={16}/>{error}</div>}
        <div className="fw-metrics">
          <Metric icon={Flame} label="Detecciones" value={visibleHotspots.length} tone="red"/>
          <Metric icon={Gauge} label="FRP acumulado" value={`${stats.frp.toFixed(1)} MW`} tone="orange"/>
          <Metric icon={Activity} label="Confianza media" value={`${stats.confidence}%`} tone="green"/>
          <Metric icon={Satellite} label="MODIS / VIIRS" value={`${stats.modis} / ${stats.viirs}`} tone="blue"/>
        </div>
        <div className="fw-sensor-row"><span><i className="modis"/>MODIS · 1 km</span><span><i className="viirs"/>VIIRS · 375 m</span></div>
        <div className="fw-summary-actions"><button onClick={loadData} disabled={loading}><RefreshCw className={loading ? 'spin' : ''} size={16}/>Actualizar</button><button onClick={() => downloadCsv(visibleHotspots, selectedDate)}><Download size={16}/>CSV</button></div>
        <p className="fw-disclaimer">Anomalías térmicas para verificación en campo. No representan por sí solas incendios confirmados.</p>
      </aside>}
      {layersOpen && !selectionBounds && <aside className="fw-layers">
        <div className="fw-layers-title"><span>CAPAS DEL MAPA</span><SlidersHorizontal size={15}/></div>
        <LayerButton active={activeLayer === 'activity'} icon={Gauge} label="Actividad" tone="activity" onClick={() => setActiveLayer('activity')}/>
        <LayerButton active={activeLayer === 'heat'} icon={ThermometerSun} label="Calor" tone="heat" onClick={() => setActiveLayer('heat')}/>
        <LayerButton active={activeLayer === 'points'} icon={MapPin} label="Puntos" tone="points" onClick={() => setActiveLayer('points')}/>
        <LayerButton active={activeLayer === 'aoi'} icon={Layers3} label="Límite" tone="boundary" onClick={() => setActiveLayer('aoi')}/>
        <LayerButton active={selectionMode} icon={Scan} label="Área" tone="select" onClick={toggleSelectionMode}/>
        <div className="fw-scale"><span>{activeLayer === 'activity' ? 'ACTIVIDAD TÉRMICA' : 'INTENSIDAD FRP'}</span><div/><section><small>Baja</small><small>Media</small><small>Alta</small></section></div>
      </aside>}
      <div className="fw-map-meta"><button onClick={focusStudyArea} className={studySelected ? 'is-active' : ''}><MapPin size={13}/>{activeScope === 'peru' ? 'Abrir piloto · Cusco' : 'Volver a Perú'}</button><span><Satellite size={13}/>MODIS + VIIRS</span><span><CloudSun size={13}/>Últimos 5 días</span></div>
      {selectionMode && <div className="fw-draw-hint"><Scan size={20}/><div><b>Selecciona un área</b><span>Arrastra sobre el mapa para dibujar el cuadro</span></div><button onClick={() => setSelectionMode(false)} title="Cancelar"><X size={16}/></button></div>}
      {selectionBounds && <aside className="fw-selection-card">
        <div className="fw-selection-head"><div><p>ANÁLISIS DEL CUADRO</p><h2>Área seleccionada</h2><span>Resultados dentro de {activeScope === 'peru' ? 'Perú' : 'Cusco'}</span></div><button onClick={clearSelection} title="Limpiar selección"><Trash2 size={17}/></button></div>
        <SatelliteSelectionMap bounds={selectionBounds} hotspots={selectedHotspots}/>
        <div className="fw-selection-source"><span>Vista satelital de referencia</span><b>Esri World Imagery · NASA FIRMS</b></div>
        <div className="fw-selection-grid">
          <article><span>Detecciones</span><b>{selectedHotspots.length}</b></article>
          <article><span>FRP acumulado</span><b>{selectionStats.frp.toFixed(1)} MW</b></article>
          <article><span>Confianza</span><b>{selectionStats.confidence}%</b></article>
          <article><span>MODIS / VIIRS</span><b>{selectionStats.modis} / {selectionStats.viirs}</b></article>
          <article><span>Superficie del cuadro</span><b>{selectionArea >= 1000 ? `${(selectionArea / 1000).toFixed(1)} mil km²` : `${selectionArea.toFixed(0)} km²`}</b></article>
          <article><span>Nivel estimado</span><b className={`risk-${selectionStats.risk.toLowerCase()}`}>{selectionStats.risk}</b></article>
        </div>
        <div className="fw-selection-actions"><button onClick={toggleSelectionMode}><Scan size={15}/>Redibujar</button><button onClick={() => downloadCsv(selectedHotspots, 'area-seleccionada')} disabled={!selectedHotspots.length}><Download size={15}/>CSV</button></div>
      </aside>}
      <section className="fw-timeline">
        <button className="fw-play" onClick={() => setPlaying((value) => !value)} title={playing ? 'Pausar' : 'Reproducir'}>{playing ? <Pause size={20}/> : <Play size={20}/>}</button>
        <div className="fw-time-info"><CalendarDays size={15}/><div><b>{selectedDate === 'all' ? 'Últimos 5 días' : formatDate(selectedDate)}</b><small>{visibleHotspots.length} detecciones</small></div></div>
        <div className="fw-days"><button className={selectedDate === 'all' ? 'is-active' : ''} onClick={() => { setSelectedDate('all'); setPlaying(false) }}><span>Todos</span><b>5 días</b></button>{dates.map((date) => <button className={selectedDate === date ? 'is-active' : ''} key={date} onClick={() => { setSelectedDate(date); setPlaying(false) }}><span>{formatDay(date).split(' ')[0]}</span><b>{formatDay(date).split(' ')[1]}</b><i style={{ '--events': Math.min(100, scopedHotspots.filter((point) => point.date === date).length * (activeScope === 'peru' ? 2 : 12)) }}/></button>)}</div>
        <div className="fw-timeline-note"><span>UTC−5</span><b>{result.mode === 'api' ? 'DATOS EN VIVO' : 'MODO DEMO'}</b></div>
      </section>
    </div>
  )
}

export default FireMapApp
