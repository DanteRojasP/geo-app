// Focos de calor por día del año según el nivel de peligro (CENEPRED) de la unidad donde ocurren.
// Datos: GET /api/ambitos/{nivel}/dias, que se calcula al pedirlo con los años y la ventana de suavizado.
// Áreas apiladas por nivel (colores de datos de CENEPRED, los mismos del mapa y la lista); modo "focos por
// año" o "parte del día" (100 %); al pasar el cursor se ve el día con el valor de cada nivel.
import { useEffect, useMemo, useState } from 'react'
import { getAmbitoDias } from './services/api.js'
import { locale, monthLetters, tr } from './i18n.js'

const ANIOS = Array.from({ length: 2025 - 2003 + 1 }, (_, i) => 2003 + i)
const W = 380, H = 170, M = { l: 30, r: 8, t: 8, b: 20 }
const INICIO_MES = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
const n1 = (v) => (v >= 10 ? Math.round(v) : Math.round(v * 10) / 10).toLocaleString(locale())

function AmbitosDias({ nivel }) {
  const [desde, setDesde] = useState(2003)
  const [hasta, setHasta] = useState(2025)
  const [ventana, setVentana] = useState(7)
  const [modo, setModo] = useState('focos')
  const [estado, setEstado] = useState({ cargando: true })
  const [dia, setDia] = useState(null)

  useEffect(() => {
    let activo = true
    setEstado((s) => ({ ...s, cargando: true, error: '' }))
    getAmbitoDias(nivel, { desde, hasta, ventana })
      .then(({ body }) => activo && setEstado({ d: body }))
      .catch((e) => activo && setEstado({ error: e.message }))
    return () => { activo = false }
  }, [nivel, desde, hasta, ventana])

  const { d, error, cargando } = estado
  const niveles = useMemo(() => (d?.niveles || []).filter((n) => n.focos_por_anio > 0), [d])
  const capas = useMemo(() => {
    if (!d) return []
    const valor = (f, k) => (modo === 'parte' ? (f.total > 0 ? f[k] / f.total : 0) : f[k])
    const max = modo === 'parte' ? 1 : Math.max(1e-9, ...d.dias.map((f) => f.total))
    const x = (i) => M.l + (i / 364) * (W - M.l - M.r)
    const y = (v) => M.t + (1 - v / max) * (H - M.t - M.b)
    let base = d.dias.map(() => 0)
    return { max, x, y, areas: niveles.map((n) => {
      const top = d.dias.map((f, i) => base[i] + valor(f, n.nivel_peligro))
      const path = `${top.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('')}`
        + `${base.map((v, i) => [i, v]).reverse().map(([i, v]) => `L${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('')}Z`
      base = top
      return { n, path }
    }) }
  }, [d, niveles, modo])

  const mover = (e) => {
    const r = e.currentTarget.getBoundingClientRect()
    const fx = ((e.clientX - r.left) / r.width) * W
    setDia(Math.min(365, Math.max(1, Math.round(((fx - M.l) / (W - M.l - M.r)) * 364) + 1)))
  }
  const fila = d && dia ? d.dias[dia - 1] : null
  const letras = monthLetters()

  return (
    <section className="fa-dias" aria-label={tr('amb.days.title')}>
      <header><h3>{tr('amb.days.title')}</h3></header>
      <div className="fa-dias-ctrl">
        <label>{tr('amb.days.from')}<select value={desde} onChange={(e) => { const v = Number(e.target.value); setDesde(v); if (v > hasta) setHasta(v) }}>{ANIOS.map((a) => <option key={a}>{a}</option>)}</select></label>
        <label>{tr('amb.days.to')}<select value={hasta} onChange={(e) => { const v = Number(e.target.value); setHasta(v); if (v < desde) setDesde(v) }}>{ANIOS.map((a) => <option key={a}>{a}</option>)}</select></label>
        <label>{tr('amb.days.window')}<select value={ventana} onChange={(e) => setVentana(Number(e.target.value))}>{(d?.ventanas || [1, 7, 15, 31]).map((v) => <option key={v} value={v}>{tr(v === 1 ? 'amb.days.day1' : 'amb.days.dayN', { n: v })}</option>)}</select></label>
        <span className="fa-dias-modo" role="group" aria-label={tr('amb.days.mode')}>
          {['focos', 'parte'].map((m) => <button key={m} className={modo === m ? 'is-active' : ''} aria-pressed={modo === m} onClick={() => setModo(m)}>{tr(`amb.days.${m}`)}</button>)}
        </span>
      </div>
      {error && <p className="fa-error">{error}</p>}
      {d && <>
        <p className="fa-dias-lead">{d.en_simple}</p>
        <div className={`fa-dias-chart ${cargando ? 'is-loading' : ''}`}>
          <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${d.titulo}. ${d.en_simple}`} onMouseMove={mover} onMouseLeave={() => setDia(null)}>
            {[0.5, 1].map((f) => <g key={f}><line x1={M.l} x2={W - M.r} y1={capas.y(capas.max * f)} y2={capas.y(capas.max * f)} className="fa-dias-grid"/>
              <text x={M.l - 4} y={capas.y(capas.max * f) + 3} textAnchor="end" className="fa-dias-eje">{modo === 'parte' ? `${Math.round(100 * f)} %` : n1(capas.max * f)}</text></g>)}
            {capas.areas.map(({ n, path }) => <path key={n.nivel_peligro} d={path} fill={n.color} fillOpacity=".88"><title>{n.etiqueta}</title></path>)}
            <line x1={M.l} x2={W - M.r} y1={capas.y(0)} y2={capas.y(0)} className="fa-dias-grid"/>
            {INICIO_MES.map((dd, i) => <text key={i} x={capas.x(dd - 1 + 15)} y={H - 6} textAnchor="middle" className="fa-dias-eje">{letras[i]}</text>)}
            {fila && <line x1={capas.x(dia - 1)} x2={capas.x(dia - 1)} y1={M.t} y2={capas.y(0)} className="fa-dias-cursor"/>}
          </svg>
          {fila && <div className="fa-dias-tip" style={{ left: `${(100 * capas.x(dia - 1)) / W}%` }}>
            <b>{new Date(2001, 0, dia).toLocaleDateString(locale(), { day: 'numeric', month: 'long' })}</b>
            {niveles.map((n) => <span key={n.nivel_peligro}><i style={{ background: n.color }}/>{n.etiqueta}: {modo === 'parte' ? `${Math.round(100 * (fila.total ? fila[n.nivel_peligro] / fila.total : 0))} %` : n1(fila[n.nivel_peligro])}</span>)}
          </div>}
        </div>
        <ul className="fa-dias-niveles">
          {niveles.map((n) => <li key={n.nivel_peligro}>
            <i style={{ background: n.color }}/><b>{n.etiqueta}</b>
            <span>{tr('amb.days.share', { p: Math.round(100 * n.parte), u: n.unidades })}</span>
            <span>{tr('amb.days.peak', { f: n.fecha_pico })}</span>
            <span>{tr('amb.days.central', { r: n.temporada_central })}</span>
          </li>)}
        </ul>
        <p className="fa-note">{d.como_leerlo} {tr('amb.days.unit', { u: d.unidad })}</p>
      </>}
    </section>
  )
}

export default AmbitosDias
