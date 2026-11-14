import { createElement, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import {
  Activity, CalendarDays, CircleHelp, CloudSun, Download, Flame, Gauge, Info,
  Layers3, LocateFixed, MapPin, Menu, Pause, Play, Radar, RefreshCw, Satellite,
  Search, ShieldAlert, SlidersHorizontal, ThermometerSun, X,
} from 'lucide-react'
import cuscoBoundaryRaw from './data/cusco-boundary.json'
import { getFireOverview } from './services/fireApi.js'

maplibregl.setWorkerUrl(maplibreWorkerUrl)

const MAP_STYLE = 'https://tiles.openfreemap.org/styles/positron'
const CUSCO_CENTER = [-71.97, -13.53]
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

function fitToCusco(map, compact = window.innerWidth < 650) {
  map.fitBounds(CUSCO_BOUNDS, {
    padding: compact
      ? { top: 76, right: 24, bottom: 112, left: 24 }
      : { top: 100, right: 160, bottom: 130, left: 430 },
    duration: 900,
    maxZoom: 8.2,
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

function FireMapApp() {
  const mapContainerRef = useRef(null)
  const mapRef = useRef(null)
  const mapReadyRef = useRef(false)
  const hotspotsRef = useRef([])
  const [result, setResult] = useState({ hotspots: [], mode: 'demo', metadata: {} })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [activeLayer, setActiveLayer] = useState('heat')
  const [selectedDate, setSelectedDate] = useState('all')
  const [playing, setPlaying] = useState(false)
  const [detailsOpen, setDetailsOpen] = useState(true)
  const [layersOpen, setLayersOpen] = useState(true)
  const [studySelected, setStudySelected] = useState(false)

  const loadData = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await getFireOverview({ department: 'cusco', startYear: 2021, endYear: 2026 })
      setResult(data)
    } catch (caught) {
      setError(caught.message || 'No se pudieron consultar las detecciones.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const dates = useMemo(() => [...new Set(result.hotspots.map((point) => point.date).filter(Boolean))].sort().slice(-5), [result.hotspots])
  const visibleHotspots = useMemo(() => selectedDate === 'all' ? result.hotspots : result.hotspots.filter((point) => point.date === selectedDate), [result.hotspots, selectedDate])
  hotspotsRef.current = visibleHotspots

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
      center: CUSCO_CENTER,
      zoom: 6.4,
      minZoom: 5,
      maxZoom: 14,
      attributionControl: false,
      antialias: true,
    })
    mapRef.current = map
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right')
    map.addControl(new maplibregl.NavigationControl({ showCompass: false, visualizePitch: false }), 'bottom-right')

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
      map.addSource('cusco-mask', { type: 'geojson', data: CUSCO_MASK })
      map.addSource('cusco-area', { type: 'geojson', data: CUSCO_BOUNDARY })
      map.addSource('fire-hotspots', { type: 'geojson', data: hotspotsToGeoJson([]) })

      map.addLayer({ id: 'outside-mask', type: 'fill', source: 'cusco-mask', paint: { 'fill-color': '#07130f', 'fill-opacity': 0.3 } })
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

      map.on('mouseenter', 'study-area-fill', () => {
        map.getCanvas().style.cursor = 'pointer'
        map.setFeatureState({ source: 'cusco-area', id: 'cusco' }, { hover: true })
      })
      map.on('mouseleave', 'study-area-fill', () => {
        map.getCanvas().style.cursor = ''
        map.setFeatureState({ source: 'cusco-area', id: 'cusco' }, { hover: false })
      })
      map.on('click', 'study-area-fill', (event) => {
        map.setFeatureState({ source: 'cusco-area', id: 'cusco' }, { selected: true })
        setStudySelected(true)
        fitToCusco(map)
        showAreaPopup(event.lngLat)
      })
      map.on('mouseenter', 'fire-points', () => { map.getCanvas().style.cursor = 'pointer' })
      map.on('mouseleave', 'fire-points', () => { map.getCanvas().style.cursor = '' })
      map.on('click', 'fire-points', (event) => {
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
      fitToCusco(map)
    })

    return () => {
      mapReadyRef.current = false
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
    if (!mapReadyRef.current) return
    map.setLayoutProperty('fire-heat', 'visibility', activeLayer === 'heat' ? 'visible' : 'none')
    map.setLayoutProperty('fire-points', 'visibility', activeLayer === 'aoi' ? 'none' : 'visible')
    map.setPaintProperty('study-area-fill', 'fill-opacity', activeLayer === 'aoi'
      ? ['case', ['boolean', ['feature-state', 'selected'], false], 0.3, ['boolean', ['feature-state', 'hover'], false], 0.22, 0.12]
      : ['case', ['boolean', ['feature-state', 'selected'], false], 0.22, ['boolean', ['feature-state', 'hover'], false], 0.16, 0.035])
  }, [activeLayer])

  const focusStudyArea = () => {
    const map = mapRef.current
    if (!mapReadyRef.current || !map) return
    const nextSelected = !studySelected
    setStudySelected(nextSelected)
    map.setFeatureState({ source: 'cusco-area', id: 'cusco' }, { selected: nextSelected })
    fitToCusco(map)
  }

  const stats = useMemo(() => {
    const frp = visibleHotspots.reduce((sum, point) => sum + point.frp, 0)
    const confidence = visibleHotspots.length ? Math.round(visibleHotspots.reduce((sum, point) => sum + point.confidence, 0) / visibleHotspots.length) : 0
    const modis = visibleHotspots.filter((point) => point.sensor === 'MODIS').length
    const viirs = visibleHotspots.length - modis
    const risk = visibleHotspots.length >= 25 || frp >= 600 ? 'Alto' : visibleHotspots.length >= 10 || frp >= 180 ? 'Moderado' : 'Bajo'
    return { frp, confidence, modis, viirs, risk }
  }, [visibleHotspots])

  const downloadCsv = () => {
    const rows = ['fecha,sensor,fuente,latitud,longitud,frp_mw,confianza']
    visibleHotspots.forEach((point) => rows.push([point.date, point.sensor, point.source || point.sensor, point.lat, point.lon, point.frp, point.confidence].join(',')))
    const blob = new Blob([rows.join('\n')], { type: 'text/csv;charset=utf-8' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `cusco-posibles-incendios-${selectedDate}.csv`
    link.click()
    URL.revokeObjectURL(link.href)
  }

  const formatDay = (date) => new Intl.DateTimeFormat('es-PE', { weekday: 'short', day: '2-digit' }).format(new Date(`${date}T12:00:00`)).replace('.', '')
  const formatDate = (date) => date ? new Intl.DateTimeFormat('es-PE', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(`${date}T12:00:00`)) : 'Últimos 5 días'

  return (
    <div className="fw-app">
      <div ref={mapContainerRef} className="fw-map" aria-label="Mapa interactivo de posibles incendios en Cusco" />
      <header className="fw-topbar">
        <div className="fw-brand"><span><Radar size={21}/></span><div><b>FIREWATCH</b><small>CUSCO · PERÚ</small></div></div>
        <button className="fw-search" onClick={focusStudyArea}><Search size={18}/><div><b>Cusco, Perú</b><small>{studySelected ? 'Zona de estudio seleccionada' : 'Seleccionar zona de estudio'}</small></div><LocateFixed size={18}/></button>
        <div className="fw-top-actions"><span className="fw-live"><i/>{result.mode === 'api' ? 'NASA FIRMS EN VIVO' : 'VISTA DE DEMOSTRACIÓN'}</span><button title="Ayuda"><CircleHelp size={19}/></button><button title="Menú"><Menu size={20}/></button></div>
      </header>
      <nav className="fw-rail" aria-label="Herramientas del mapa">
        <button className="is-active" title="Monitoreo"><Flame size={20}/><span>Fuego</span></button>
        <button title="Capas" onClick={() => setLayersOpen((value) => !value)}><Layers3 size={20}/><span>Capas</span></button>
        <button title="Alertas"><ShieldAlert size={20}/><span>Alertas</span></button>
        <button title="Información" onClick={() => setDetailsOpen((value) => !value)}><Info size={20}/><span>Info</span></button>
      </nav>
      {detailsOpen && <aside className="fw-summary">
        <div className="fw-summary-head"><div><p>MONITOREO ACTIVO</p><h1>Posibles incendios</h1><span>Cusco · {formatDate(selectedDate === 'all' ? null : selectedDate)}</span></div><button onClick={() => setDetailsOpen(false)}><X size={17}/></button></div>
        <div className="fw-summary-status"><RiskBadge level={stats.risk}/><span>{loading ? 'Actualizando satélites…' : `${visibleHotspots.length} detecciones visibles`}</span></div>
        {error && <div className="fw-error"><ShieldAlert size={16}/>{error}</div>}
        <div className="fw-metrics">
          <Metric icon={Flame} label="Detecciones" value={visibleHotspots.length} tone="red"/>
          <Metric icon={Gauge} label="FRP acumulado" value={`${stats.frp.toFixed(1)} MW`} tone="orange"/>
          <Metric icon={Activity} label="Confianza media" value={`${stats.confidence}%`} tone="green"/>
          <Metric icon={Satellite} label="MODIS / VIIRS" value={`${stats.modis} / ${stats.viirs}`} tone="blue"/>
        </div>
        <div className="fw-sensor-row"><span><i className="modis"/>MODIS · 1 km</span><span><i className="viirs"/>VIIRS · 375 m</span></div>
        <div className="fw-summary-actions"><button onClick={loadData} disabled={loading}><RefreshCw className={loading ? 'spin' : ''} size={16}/>Actualizar</button><button onClick={downloadCsv}><Download size={16}/>CSV</button></div>
        <p className="fw-disclaimer">Anomalías térmicas para verificación en campo. Límite oficial: INEI vía IGN.</p>
      </aside>}
      {layersOpen && <aside className="fw-layers">
        <div className="fw-layers-title"><span>CAPAS DEL MAPA</span><SlidersHorizontal size={15}/></div>
        <LayerButton active={activeLayer === 'heat'} icon={ThermometerSun} label="Calor" tone="heat" onClick={() => setActiveLayer('heat')}/>
        <LayerButton active={activeLayer === 'points'} icon={MapPin} label="Puntos" tone="points" onClick={() => setActiveLayer('points')}/>
        <LayerButton active={activeLayer === 'aoi'} icon={Layers3} label="Límite" tone="boundary" onClick={() => setActiveLayer('aoi')}/>
        <div className="fw-scale"><span>INTENSIDAD FRP</span><div/><section><small>Baja</small><small>Media</small><small>Alta</small></section></div>
      </aside>}
      <div className="fw-map-meta"><button onClick={focusStudyArea} className={studySelected ? 'is-active' : ''}><MapPin size={13}/>Zona de estudio · Cusco</button><span><Satellite size={13}/>MODIS + VIIRS</span><span><CloudSun size={13}/>Actualización cada 15 min</span></div>
      <section className="fw-timeline">
        <button className="fw-play" onClick={() => setPlaying((value) => !value)} title={playing ? 'Pausar' : 'Reproducir'}>{playing ? <Pause size={20}/> : <Play size={20}/>}</button>
        <div className="fw-time-info"><CalendarDays size={15}/><div><b>{selectedDate === 'all' ? 'Últimos 5 días' : formatDate(selectedDate)}</b><small>{visibleHotspots.length} detecciones</small></div></div>
        <div className="fw-days"><button className={selectedDate === 'all' ? 'is-active' : ''} onClick={() => { setSelectedDate('all'); setPlaying(false) }}><span>Todos</span><b>5 días</b></button>{dates.map((date) => <button className={selectedDate === date ? 'is-active' : ''} key={date} onClick={() => { setSelectedDate(date); setPlaying(false) }}><span>{formatDay(date).split(' ')[0]}</span><b>{formatDay(date).split(' ')[1]}</b><i style={{ '--events': Math.min(100, result.hotspots.filter((point) => point.date === date).length * 12) }}/></button>)}</div>
        <div className="fw-timeline-note"><span>UTC−5</span><b>{result.mode === 'api' ? 'DATOS EN VIVO' : 'MODO DEMO'}</b></div>
      </section>
    </div>
  )
}

export default FireMapApp
