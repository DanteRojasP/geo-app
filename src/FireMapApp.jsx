import { createElement, useEffect, useMemo, useState } from 'react'
import { CircleMarker, MapContainer, Polygon, Popup, TileLayer, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet.heat'
import {
  Activity, CalendarDays, ChevronDown, CircleHelp, CloudSun, Download, Flame,
  Gauge, Info, Layers3, LocateFixed, MapPin, Menu, Pause, Play, Radar,
  RefreshCw, Satellite, Search, ShieldAlert, SlidersHorizontal, ThermometerSun,
  X,
} from 'lucide-react'
import { departments } from './data/demoData.js'
import { getFireOverview } from './services/fireApi.js'

const CUSCO = departments.cusco

function MapFocus() {
  const map = useMap()
  useEffect(() => {
    map.invalidateSize({ pan: false })
    map.setView(CUSCO.center, CUSCO.zoom, { animate: false })
  }, [map])
  return null
}

function HeatLayer({ points, visible }) {
  const map = useMap()
  useEffect(() => {
    if (!visible || !points.length) return undefined
    const values = points.map((point) => [point.lat, point.lon, Math.min(1, Math.max(.22, point.frp / 90))])
    const layer = L.heatLayer(values, {
      radius: 38,
      blur: 28,
      maxZoom: 11,
      minOpacity: .28,
      gradient: { .18: '#ffe57a', .42: '#ffb13b', .68: '#ff6534', .88: '#eb2d2d', 1: '#9f001f' },
    }).addTo(map)
    return () => map.removeLayer(layer)
  }, [map, points, visible])
  return null
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
  const [result, setResult] = useState({ hotspots: [], mode: 'demo', metadata: {} })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [activeLayer, setActiveLayer] = useState('heat')
  const [selectedDate, setSelectedDate] = useState('all')
  const [playing, setPlaying] = useState(false)
  const [detailsOpen, setDetailsOpen] = useState(true)
  const [layersOpen, setLayersOpen] = useState(true)

  const loadData = async () => {
    setLoading(true); setError('')
    try {
      const data = await getFireOverview({ department: 'cusco', startYear: 2021, endYear: 2026 })
      setResult(data)
    } catch (caught) {
      setError(caught.message || 'No se pudieron consultar las detecciones.')
    } finally { setLoading(false) }
  }

  useEffect(() => { loadData() }, [])

  const dates = useMemo(() => [...new Set(result.hotspots.map((point) => point.date).filter(Boolean))].sort().slice(-5), [result.hotspots])
  const visibleHotspots = useMemo(() => selectedDate === 'all' ? result.hotspots : result.hotspots.filter((point) => point.date === selectedDate), [result.hotspots, selectedDate])

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
    link.href = URL.createObjectURL(blob); link.download = `cusco-posibles-incendios-${selectedDate}.csv`; link.click(); URL.revokeObjectURL(link.href)
  }

  const formatDay = (date) => new Intl.DateTimeFormat('es-PE', { weekday: 'short', day: '2-digit' }).format(new Date(`${date}T12:00:00`)).replace('.', '')
  const formatDate = (date) => date ? new Intl.DateTimeFormat('es-PE', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(`${date}T12:00:00`)) : 'Últimos 5 días'

  return (
    <div className="fw-app">
      <MapContainer center={CUSCO.center} zoom={CUSCO.zoom} minZoom={6} maxZoom={13} zoomControl={false} className="fw-map">
        <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" />
        <MapFocus />
        <HeatLayer points={visibleHotspots} visible={activeLayer === 'heat'} />
        <Polygon positions={CUSCO.polygon} pathOptions={{ color: '#b7f36b', fillColor: '#a6e663', fillOpacity: activeLayer === 'aoi' ? .22 : .035, weight: 2, dashArray: '7 6' }} />
        {(activeLayer === 'points' || activeLayer === 'heat') && visibleHotspots.map((point) => (
          <CircleMarker key={point.id} center={[point.lat, point.lon]} radius={activeLayer === 'heat' ? 3.5 : Math.max(5, Math.min(12, point.frp / 7))} pathOptions={{ color: '#fff4df', fillColor: point.sensor === 'MODIS' ? '#ff9b3f' : '#f33932', fillOpacity: activeLayer === 'heat' ? .88 : .78, weight: activeLayer === 'heat' ? .8 : 1.3 }}>
            <Popup><div className="fw-popup"><b><Flame size={13}/> Posible incendio</b><span>{point.sensor} · {point.date}</span><strong>{point.frp.toFixed(1)} MW</strong><small>Confianza {point.confidence}%</small></div></Popup>
          </CircleMarker>
        ))}
      </MapContainer>

      <header className="fw-topbar">
        <div className="fw-brand"><span><Radar size={21}/></span><div><b>FIREWATCH</b><small>CUSCO · PERÚ</small></div></div>
        <div className="fw-search"><Search size={18}/><div><b>Cusco, Perú</b><small>Monitoreo satelital de posibles incendios</small></div><LocateFixed size={18}/></div>
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
        <p className="fw-disclaimer">Las detecciones satelitales indican anomalías térmicas y deben verificarse en campo.</p>
      </aside>}

      {layersOpen && <aside className="fw-layers">
        <div className="fw-layers-title"><span>CAPAS DEL MAPA</span><SlidersHorizontal size={15}/></div>
        <LayerButton active={activeLayer === 'heat'} icon={ThermometerSun} label="Calor" tone="heat" onClick={() => setActiveLayer('heat')}/>
        <LayerButton active={activeLayer === 'points'} icon={MapPin} label="Puntos" tone="points" onClick={() => setActiveLayer('points')}/>
        <LayerButton active={activeLayer === 'aoi'} icon={Layers3} label="Límite" tone="boundary" onClick={() => setActiveLayer('aoi')}/>
        <div className="fw-scale"><span>INTENSIDAD FRP</span><div/><section><small>Baja</small><small>Media</small><small>Alta</small></section></div>
      </aside>}

      <div className="fw-map-meta"><span><MapPin size={13}/>Región Cusco</span><span><Satellite size={13}/>MODIS + VIIRS</span><span><CloudSun size={13}/>Actualización cada 15 min</span></div>

      <section className="fw-timeline">
        <button className="fw-play" onClick={() => setPlaying((value) => !value)} title={playing ? 'Pausar' : 'Reproducir'}>{playing ? <Pause size={20}/> : <Play size={20}/>}</button>
        <div className="fw-time-info"><CalendarDays size={15}/><div><b>{selectedDate === 'all' ? 'Últimos 5 días' : formatDate(selectedDate)}</b><small>{visibleHotspots.length} detecciones</small></div></div>
        <div className="fw-days"><button className={selectedDate === 'all' ? 'is-active' : ''} onClick={() => {setSelectedDate('all');setPlaying(false)}}><span>Todos</span><b>5 días</b></button>{dates.map((date) => <button className={selectedDate === date ? 'is-active' : ''} key={date} onClick={() => {setSelectedDate(date);setPlaying(false)}}><span>{formatDay(date).split(' ')[0]}</span><b>{formatDay(date).split(' ')[1]}</b><i style={{'--events': Math.min(100, result.hotspots.filter((point) => point.date === date).length * 12)}}/></button>)}</div>
        <div className="fw-timeline-note"><span>UTC−5</span><b>{result.mode === 'api' ? 'DATOS EN VIVO' : 'MODO DEMO'}</b></div>
      </section>
    </div>
  )
}

export default FireMapApp
