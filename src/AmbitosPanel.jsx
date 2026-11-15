// Panel "Ámbitos": nivel de peligro por focos de calor (formato CENEPRED) por provincia, distrito
// o cuenca Pfafstetter, con el mapa pintado por nivel, la lista ordenada, el informe de cada unidad
// y la tabla CSV del nivel. Datos: /api/ambitos/* del backend.
import { useEffect, useMemo, useRef, useState } from 'react'
import { CalendarDays, Download, Eye, FileText, LoaderCircle, X } from 'lucide-react'
import { ambitoUrl, getAmbitoGeojson, getAmbitoNivel, getAmbitos, informeUrl } from './services/api.js'
import { tr } from './i18n.js'

const LEVELS = ['muy_alto', 'alto', 'medio', 'bajo', 'sin_clasificar']
const COLORS = { muy_alto: '#c0392b', alto: '#e67e22', medio: '#f1c40f', bajo: '#27ae60', sin_clasificar: '#98a2b3' }
const MAX_ROWS = 80

function paint(map, geojson) {
  if (!map) return
  // Si el mapa todavía carga su estilo, se pinta apenas termine (si no, la capa no aparecería).
  if (!map.isStyleLoaded()) { map.once('idle', () => paint(map, geojson)); return }
  if (!map.getSource('ambitos')) {
    map.addSource('ambitos', { type: 'geojson', data: geojson })
    const before = map.getLayer('fire-heat') ? 'fire-heat' : undefined
    map.addLayer({ id: 'ambitos-fill', type: 'fill', source: 'ambitos', paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.5 } }, before)
    map.addLayer({ id: 'ambitos-line', type: 'line', source: 'ambitos', paint: { 'line-color': '#1d2330', 'line-width': 0.7, 'line-opacity': 0.75 } }, before)
  } else {
    map.getSource('ambitos').setData(geojson)
  }
  map.setLayoutProperty('ambitos-fill', 'visibility', 'visible')
  map.setLayoutProperty('ambitos-line', 'visibility', 'visible')
}

function hide(map) {
  if (map?.getLayer?.('ambitos-fill')) {
    map.setLayoutProperty('ambitos-fill', 'visibility', 'none')
    map.setLayoutProperty('ambitos-line', 'visibility', 'none')
  }
}

function AmbitosPanel({ map, onClose }) {
  const [niveles, setNiveles] = useState([])
  const [nivel, setNivel] = useState('provincia')
  const [datos, setDatos] = useState(null)
  const [error, setError] = useState('')
  const [filtro, setFiltro] = useState('')
  const [elegido, setElegido] = useState(null)
  const [fechaInicio, setFechaInicio] = useState('2000-11-01')
  const [fechaFin, setFechaFin] = useState('2025-12-31')
  const [reportLoading, setReportLoading] = useState('')
  const listRef = useRef(null)

  useEffect(() => {
    getAmbitos().then(({ body }) => setNiveles(body.niveles)).catch((e) => setError(e.message))
  }, [])

  useEffect(() => {
    let activo = true
    setDatos(null)
    setError('')
    setElegido(null)
    Promise.all([getAmbitoNivel(nivel), getAmbitoGeojson(nivel)])
      .then(([a, g]) => {
        if (!activo) return
        setDatos(a.body)
        paint(map, g.body)
      })
      .catch((e) => activo && setError(e.message))
    return () => { activo = false }
  }, [nivel, map])

  // Clic en una unidad del mapa: se elige en la lista.
  useEffect(() => {
    if (!map) return undefined
    const onClick = (ev) => {
      const p = ev.features?.[0]?.properties
      if (p?.codigo) setElegido(String(p.codigo))
    }
    const enter = () => { map.getCanvas().style.cursor = 'pointer' }
    const leave = () => { map.getCanvas().style.cursor = '' }
    map.on('click', 'ambitos-fill', onClick)
    map.on('mouseenter', 'ambitos-fill', enter)
    map.on('mouseleave', 'ambitos-fill', leave)
    return () => {
      map.off('click', 'ambitos-fill', onClick)
      map.off('mouseenter', 'ambitos-fill', enter)
      map.off('mouseleave', 'ambitos-fill', leave)
      hide(map)
    }
  }, [map])

  useEffect(() => {
    if (elegido) listRef.current?.querySelector(`[data-codigo="${elegido}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [elegido])

  const filas = useMemo(() => {
    const us = datos?.unidades || []
    const q = filtro.trim().toLowerCase()
    const sel = q ? us.filter((u) => u.nombre.toLowerCase().includes(q) || u.codigo.includes(q)) : us
    if (elegido && !sel.slice(0, MAX_ROWS).some((u) => u.codigo === elegido)) {
      const u = us.find((x) => x.codigo === elegido)
      if (u) return [u, ...sel.slice(0, MAX_ROWS - 1)]
    }
    return sel.slice(0, MAX_ROWS)
  }, [datos, filtro, elegido])

  const politicos = niveles.filter((n) => n.grupo === 'politico')
  const hidro = niveles.filter((n) => n.grupo === 'hidrografico')
  const conteo = datos?.conteo || {}
  const periodoValido = Boolean(fechaInicio && fechaFin && fechaInicio <= fechaFin)
  const inicioMes = fechaInicio.slice(0, 7)
  const finMes = fechaFin.slice(0, 7)
  const unidadElegida = datos?.unidades?.find((u) => u.codigo === elegido)
  const reportUrl = (codigo = elegido) => codigo && periodoValido
    ? informeUrl({ ambito: `${nivel}:${codigo}` }, { fecha_inicio: inicioMes, fecha_fin: finMes })
    : ''

  const openGeneratedReport = async (mode, codigo = elegido) => {
    const url = reportUrl(codigo)
    if (!url || reportLoading) return
    const popup = window.open('', '_blank')
    if (!popup) { setError(tr('amb.popupBlocked')); return }
    const loadingText = tr(mode === 'pdf' ? 'amb.preparingPdf' : 'amb.preparingReport')
    setReportLoading(mode)
    popup.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${loadingText}</title><style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f5f8fa;color:#29404d;font:14px system-ui}.loader{text-align:center}.spin{width:34px;height:34px;margin:0 auto 16px;border:3px solid #d5e2e9;border-top-color:#2c86ad;border-radius:50%;animation:s .8s linear infinite}@keyframes s{to{transform:rotate(360deg)}}small{display:block;margin-top:7px;color:#71838d}</style></head><body><div class="loader"><div class="spin"></div><b>${loadingText}</b><small>${tr('amb.loadingWait')}</small></div></body></html>`)
    popup.document.close()
    try {
      const response = await fetch(url)
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
      let html = await response.text()
      html = html.replace('<head>', `<head><base href="${window.location.origin}/">`)
      if (mode === 'pdf') html = html.replace('</body>', `<script>window.addEventListener('load',()=>setTimeout(()=>window.print(),450))</script></body>`)
      popup.document.open()
      popup.document.write(html)
      popup.document.close()
    } catch (e) {
      popup.document.open()
      popup.document.write(`<p style="font:14px system-ui;padding:24px;color:#9f2424">${tr('amb.reportError')}: ${e.message}</p>`)
      popup.document.close()
    } finally {
      setReportLoading('')
    }
  }

  return (
    <aside className="fa-panel" aria-label={tr('amb.title')}>
      <div className="fa-head">
        <div><p>{tr('amb.kicker')}</p><h2>{tr('amb.title')}</h2></div>
        <button onClick={onClose} title={tr('amb.close')} aria-label={tr('amb.close')}><X size={16}/></button>
      </div>
      <div className="fa-controls">
        <label>{tr('amb.scope')}
          <select value={nivel} onChange={(e) => setNivel(e.target.value)}>
            <optgroup label={tr('amb.political')}>{politicos.map((n) => <option key={n.nivel} value={n.nivel}>{n.titulo} ({n.n_unidades})</option>)}</optgroup>
            <optgroup label={tr('amb.hydro')}>{hidro.map((n) => <option key={n.nivel} value={n.nivel}>{n.titulo} ({n.n_unidades})</option>)}</optgroup>
          </select>
        </label>
        <label>{tr('amb.unit')}
          <select value={elegido || ''} disabled={!datos} onChange={(e) => setElegido(e.target.value || null)}>
            <option value="">{tr('amb.chooseUnit')}</option>
            {(datos?.unidades || []).map((u) => <option key={u.codigo} value={u.codigo}>{u.nombre} · {u.codigo}</option>)}
          </select>
        </label>
        <div className="fa-period">
          <strong><CalendarDays size={14}/>{tr('amb.reportPeriod')}</strong>
          <div>
            <label>{tr('filter.from')}<input type="date" min="2000-11-01" max="2025-12-31" value={fechaInicio} onChange={(e) => setFechaInicio(e.target.value)}/></label>
            <label>{tr('filter.to')}<input type="date" min="2000-11-01" max="2025-12-31" value={fechaFin} onChange={(e) => setFechaFin(e.target.value)}/></label>
          </div>
          {!periodoValido && <small className="fa-period-error">{tr('filter.invalid')}</small>}
          <small>{tr('amb.monthResolution')}</small>
          {reportUrl()
            ? <div className="fa-report-buttons">
              <button type="button" className="fa-btn" disabled={Boolean(reportLoading)} onClick={() => openGeneratedReport('view')}><Eye size={15}/>{tr('amb.viewReport')}</button>
              <button type="button" className="fa-btn fa-report-primary" disabled={Boolean(reportLoading)} onClick={() => openGeneratedReport('pdf')}><Download size={15}/>{tr('amb.downloadPdf')}</button>
            </div>
            : <small>{tr('amb.chooseReportUnit')}</small>}
          {reportLoading && <div className="fa-report-loading" role="status" aria-live="polite"><LoaderCircle size={16}/><span>{tr(reportLoading === 'pdf' ? 'amb.preparingPdf' : 'amb.preparingReport')}</span></div>}
        </div>
        <input type="search" value={filtro} onChange={(e) => setFiltro(e.target.value)} placeholder={tr('amb.filter')} aria-label={tr('amb.filter')}/>
      </div>
      {error && <p className="fa-error">{error}</p>}
      {!datos && !error && <p className="fa-note">{tr('amb.loading')}</p>}
      {datos && <>
        <div className="fa-legend">
          {LEVELS.filter((l) => l !== 'sin_clasificar' || Object.keys(conteo).length > 4).map((l) => (
            <span key={l}><i style={{ background: COLORS[l] }}/>{tr(`amb.level.${l}`)}</span>
          ))}
        </div>
        <p className="fa-note">{tr('amb.coverage', { p: Math.round((datos.cobertura || 0) * 1000) / 10 })}</p>
        <ol className="fa-list" ref={listRef}>
          {filas.map((u) => (
            <li key={u.codigo} data-codigo={u.codigo} className={u.codigo === elegido ? 'is-picked' : ''} onClick={() => setElegido(u.codigo)} aria-current={u.codigo === elegido ? 'true' : undefined}>
              <span className="fa-rank">{u.puesto ?? '–'}</span>
              <span className="fa-badge" style={{ background: u.color }}>{u.etiqueta}</span>
              <span className="fa-name"><b>{u.nombre}</b><small>{u.provincia ? `${u.provincia} · ` : ''}{u.codigo} · {tr('amb.density', { v: u.densidad ?? 0 })}</small></span>
              <button type="button" className="fa-btn" disabled={Boolean(reportLoading)} title={tr('amb.reportRange', { a: fechaInicio, b: fechaFin })} onClick={(e) => { e.stopPropagation(); setElegido(u.codigo); openGeneratedReport('view', u.codigo) }}><FileText size={14}/>{tr('amb.reportShort')}</button>
            </li>
          ))}
        </ol>
        {(datos.unidades.length > filas.length) && <p className="fa-note">{tr('amb.more', { n: datos.unidades.length - filas.length })}</p>}
        <div className="fa-actions">
          <a className="fa-btn" href={ambitoUrl(`/api/ambitos/${nivel}.csv`)}><Download size={14}/>{tr('amb.csv')}</a>
          {unidadElegida && <span>{unidadElegida.nombre} · {inicioMes}–{finMes}</span>}
        </div>
        <p className="fa-note">{datos.metodo.notas[0]} {datos.metodo.notas[1]}</p>
        <p className="fa-note">{datos.fuente}</p>
      </>}
    </aside>
  )
}

export default AmbitosPanel
