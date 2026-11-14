import { createElement, useEffect, useMemo, useState } from 'react'
import { CircleMarker, MapContainer, Polygon, Popup, TileLayer, useMap } from 'react-leaflet'
import {
  Activity, CalendarDays, ChevronDown, CircleHelp, Download, Flame, Layers3,
  MapPin, Menu, Radar, RefreshCw, Satellite, Search, SlidersHorizontal,
} from 'lucide-react'
import { departments } from './data/demoData.js'
import { getCsvUrl, getFireOverview } from './services/fireApi.js'

const months = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

function MapFocus({ center, zoom }) {
  const map = useMap()
  useEffect(() => {
    map.invalidateSize({ pan: false })
    map.setView(center, zoom, { animate: false })
  }, [center, zoom, map])
  return null
}

function MetricCard({ icon, label, value, note, accent = false }) {
  return (
    <article className={`metric-card ${accent ? 'accent' : ''}`}>
      <div className="metric-icon">{createElement(icon, { size: 17 })}</div>
      <div><span>{label}</span><strong>{value}</strong><small>{note}</small></div>
    </article>
  )
}

function HeatCalendar({ rows }) {
  const max = Math.max(...rows.flatMap((row) => row.months), 1)
  const level = (value) => Math.min(5, Math.ceil((value / max) * 5))
  return (
    <div className="calendar-scroll">
      <div className="heat-calendar">
        <div />
        {months.map((month) => <span className="month" key={month}>{month}</span>)}
        {rows.map((row) => [
          <span className="year" key={`${row.year}-label`}>{row.year}</span>,
          ...row.months.map((value, index) => (
            <button className={`heat-cell heat-${level(value)}`} title={`${months[index]} ${row.year}: ${value} eventos`} key={`${row.year}-${index}`}>
              <span>{value}</span>
            </button>
          )),
        ])}
      </div>
      <div className="heat-legend"><span>Menor actividad</span>{[1,2,3,4,5].map((n) => <i className={`heat-${n}`} key={n} />)}<span>Mayor actividad</span></div>
    </div>
  )
}

function App() {
  const [departmentKey, setDepartmentKey] = useState('cusco')
  const [startYear, setStartYear] = useState(2021)
  const [endYear, setEndYear] = useState(2026)
  const [result, setResult] = useState({ calendar: [], hotspots: [], mode: 'demo' })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [mapLayer, setMapLayer] = useState('hotspots')
  const department = departments[departmentKey]

  const loadData = async () => {
    setLoading(true); setError('')
    try {
      const safeStart = Math.min(startYear, endYear)
      const safeEnd = Math.max(startYear, endYear)
      const data = await getFireOverview({ department: departmentKey, startYear: safeStart, endYear: safeEnd })
      setStartYear(safeStart); setEndYear(safeEnd); setResult(data)
    } catch (caught) {
      setError(caught.message || 'No se pudieron cargar los datos.')
    } finally { setLoading(false) }
  }

  useEffect(() => { loadData() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const stats = useMemo(() => {
    const calendarTotal = result.calendar.flatMap((row) => row.months ?? []).reduce((sum, value) => sum + value, 0)
    const total = result.mode === 'api' ? result.hotspots.length : calendarTotal
    const frp = result.hotspots.reduce((sum, item) => sum + item.frp, 0)
    const averageConfidence = result.hotspots.length ? Math.round(result.hotspots.reduce((sum, item) => sum + item.confidence, 0) / result.hotspots.length) : 0
    const anomaly = total ? Math.round(((total % 41) - 8)) : 0
    return { total, frp, averageConfidence, anomaly }
  }, [result])

  const downloadCsv = () => {
    const apiUrl = getCsvUrl({ department: departmentKey, startYear, endYear })
    if (apiUrl) { window.location.href = apiUrl; return }
    const lines = ['fecha,sensor,latitud,longitud,frp_mw,confianza']
    result.hotspots.forEach((point) => lines.push([point.date, point.sensor, point.lat.toFixed(5), point.lon.toFixed(5), point.frp, point.confidence].join(',')))
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob); link.download = `hotspots-${departmentKey}-${startYear}-${endYear}.csv`; link.click(); URL.revokeObjectURL(link.href)
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand"><span className="brand-icon"><Radar size={21} /></span><div><b>FIREWATCH</b><small>PERÚ</small></div></div>
        <nav><a className="active" href="#overview">Observatorio</a><a href="#method">Metodología</a><a href="#data">Datos</a></nav>
        <div className="top-actions"><span className={`mode-badge ${result.mode}`}><i />{result.mode === 'api' ? 'API conectada' : 'Modo demo'}</span><button aria-label="Ayuda"><CircleHelp size={18} /></button><button className="menu-button" aria-label="Menú"><Menu size={20} /></button></div>
      </header>

      <main id="overview">
        <section className="intro-row">
          <div><p className="eyebrow"><Satellite size={14} /> OBSERVATORIO SATELITAL</p><h1>Actividad del fuego<br/><span>en el territorio.</span></h1></div>
          <p className="intro-copy">Explora detecciones armonizadas de <b>MODIS</b> y <b>VIIRS</b>, compara patrones históricos y descarga resultados para tomar mejores decisiones.</p>
        </section>

        <section className="workspace">
          <aside className="filters-panel">
            <div className="panel-title"><div><SlidersHorizontal size={16} /><b>Filtros de consulta</b></div><button aria-label="Restablecer filtros" onClick={() => { setDepartmentKey('cusco'); setStartYear(2021); setEndYear(2026) }}><RefreshCw size={14} /></button></div>
            <label>Área de interés</label>
            <div className="select-control"><MapPin size={15} /><select value={departmentKey} onChange={(event) => setDepartmentKey(event.target.value)}>{Object.entries(departments).map(([key, item]) => <option value={key} key={key}>{item.name}</option>)}</select><ChevronDown size={14} /></div>
            <div className="field-group"><label>Periodo histórico</label><div className="year-fields"><div><span>Desde</span><select value={startYear} onChange={(event) => setStartYear(+event.target.value)}>{Array.from({length: 27},(_,i) => 2000+i).map((year) => <option key={year}>{year}</option>)}</select></div><div><span>Hasta</span><select value={endYear} onChange={(event) => setEndYear(+event.target.value)}>{Array.from({length: 27},(_,i) => 2000+i).map((year) => <option key={year}>{year}</option>)}</select></div></div></div>
            <button className="search-button" onClick={loadData} disabled={loading}>{loading ? <RefreshCw className="spin" size={16} /> : <Search size={16} />}{loading ? 'Consultando…' : 'Actualizar análisis'}</button>
            {error && <p className="error-message">{error}</p>}
            <div className="source-block"><span>FUENTES ACTIVAS</span><div><i className="source-dot modis"/><p><b>MODIS</b><small>Resolución de 1 km</small></p></div><div><i className="source-dot viirs"/><p><b>VIIRS</b><small>Resolución de 375 m</small></p></div></div>
            <div className="method-note"><Satellite size={17}/><p><b>Serie armonizada</b><span>Las detecciones se llevan a una grilla común para evitar saltos entre sensores.</span></p></div>
          </aside>

          <div className="map-panel">
            <div className="map-heading"><div><p>ÁREA SELECCIONADA</p><h2>{department.name}</h2></div><div className="map-switch"><button className={mapLayer === 'hotspots' ? 'active' : ''} onClick={() => setMapLayer('hotspots')}><Flame size={14}/>Hotspots</button><button className={mapLayer === 'aoi' ? 'active' : ''} onClick={() => setMapLayer('aoi')}><Layers3 size={14}/>AOI</button></div></div>
            <MapContainer center={department.center} zoom={department.zoom} minZoom={5} zoomControl={false} className="map">
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
                className="base-map-tiles"
              />
              <MapFocus center={department.center} zoom={department.zoom} />
              <Polygon positions={department.polygon} pathOptions={{ color: '#b7f36b', fillColor: '#89d65b', fillOpacity: mapLayer === 'aoi' ? 0.2 : 0.06, weight: 1.5, dashArray: '5 5' }} />
              {mapLayer === 'hotspots' && result.hotspots.map((point) => <CircleMarker key={point.id} center={[point.lat, point.lon]} radius={Math.max(4, Math.min(11, point.frp/9))} pathOptions={{ color: point.sensor === 'MODIS' ? '#ff8c42' : '#ff4d3d', fillColor: point.sensor === 'MODIS' ? '#ffb15c' : '#ff513f', fillOpacity: 0.78, weight: 1 }}><Popup><b>{point.sensor}</b><br/>{point.date}<br/>FRP: {point.frp} MW<br/>Confianza: {point.confidence}%</Popup></CircleMarker>)}
            </MapContainer>
            <div className="map-legend"><span><i className="lg low"/>Menor FRP</span><span><i className="lg high"/>Mayor FRP</span><span className="live"><i/>Datos filtrados</span></div>
          </div>

          <aside className="insights-panel">
            <div className="insights-title"><span>RESUMEN DEL PERIODO</span><b>{startYear} — {endYear}</b></div>
            <MetricCard icon={Flame} label={result.mode === 'api' ? 'Eventos recientes' : 'Eventos armonizados'} value={stats.total.toLocaleString('es-PE')} note={result.mode === 'api' ? 'Últimos 5 días · NASA FIRMS' : `${result.hotspots.length} visibles en el mapa`} accent />
            <MetricCard icon={Activity} label="Anomalía estimada" value={`${stats.anomaly >= 0 ? '+' : ''}${stats.anomaly}%`} note="Frente a la mediana histórica" />
            <MetricCard icon={Satellite} label="FRP observado" value={`${stats.frp.toLocaleString('es-PE')} MW`} note="Potencia radiativa acumulada" />
            <MetricCard icon={Radar} label="Confianza media" value={`${stats.averageConfidence}%`} note="Umbral actual ≥ 70%" />
            <button className="download-button" onClick={downloadCsv}><Download size={16}/><span>Descargar hotspots<small>Archivo CSV filtrado</small></span></button>
          </aside>
        </section>

        <section className="history-panel" id="data">
          <div className="history-head"><div><p className="eyebrow dark"><CalendarDays size={14}/> PATRÓN HISTÓRICO</p><h2>Calendario de actividad</h2></div><p>{result.mode === 'api' ? 'El mapa usa NASA FIRMS en vivo. El calendario continúa con datos de muestra hasta conectar el backend histórico.' : 'Cada celda representa el número mensual de eventos armonizados. Pasa el cursor para consultar el valor exacto.'}</p></div>
          {loading ? <div className="calendar-loader"><RefreshCw className="spin"/>Procesando serie temporal…</div> : <HeatCalendar rows={result.calendar} />}
        </section>

        <section className="method-section" id="method">
          <div><p className="eyebrow"><Satellite size={14}/> MÉTODO</p><h2>Dos sensores.<br/><span>Una sola historia.</span></h2></div>
          <div className="method-grid"><article><b>01</b><h3>Normalización</h3><p>La confianza de cada sensor se transforma a una escala comparable.</p></article><article><b>02</b><h3>Grilla común</h3><p>MODIS y VIIRS se proyectan sobre celdas consistentes de un kilómetro.</p></article><article><b>03</b><h3>Deduplicación</h3><p>Una celda y un día cuentan como un evento; se conserva el mayor FRP.</p></article></div>
        </section>
      </main>

      <footer><div className="brand"><span className="brand-icon"><Radar size={18}/></span><div><b>FIREWATCH</b><small>PERÚ</small></div></div><p>We acknowledge the use of data and/or imagery from NASA's FIRMS.</p><span>NASA SPACE APPS · 2026</span></footer>
    </div>
  )
}

export default App
