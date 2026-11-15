import { useEffect, useMemo, useState } from 'react'
import { ArrowRight, Database, Layers3, MapPinned, Satellite, ShieldCheck } from 'lucide-react'
import { LANGS, tr } from './i18n.js'
import { CUSCO, getResumen } from './services/api.js'

function IntroScreen({ lang, onLanguage, onEnter }) {
  const [summary, setSummary] = useState(null)

  useEffect(() => {
    let active = true
    getResumen({ departamento: CUSCO }, { graficos: 'false' })
      .then(({ body }) => active && setSummary(body))
      .catch(() => {})
    return () => { active = false }
  }, [lang])

  const fallback = useMemo(() => [
    { pregunta: tr('intro.q1'), respuesta: tr('intro.a1') },
    { pregunta: tr('intro.q2'), respuesta: tr('intro.a2') },
    { pregunta: tr('intro.q3'), respuesta: tr('intro.a3') },
  ], [lang]) // eslint-disable-line react-hooks/exhaustive-deps
  const findings = summary?.frases?.slice(0, 3) || fallback

  return <div className="fc-intro">
    <div className="fc-intro-frame">
      <main className="fc-intro-sheet">
        <header className="fc-intro-top"><img src="./nubel-team-logo.png" alt="Nubel Team"/><div role="group" aria-label={tr('lang.title')}>{LANGS.map((code) => <button key={code} className={code === lang ? 'is-active' : ''} onClick={() => onLanguage(code)}>{code.toUpperCase()}</button>)}</div></header>
        <section className="fc-intro-copy">
          <p>{tr('intro.kicker')}</p>
          <h1>{tr('intro.title')}</h1>
          <span>{tr('intro.lead')}</span>
        </section>
        <div className="fc-intro-facts">
          <div><Satellite/><span>{tr('intro.source')}</span><b>MODIS + VIIRS</b></div>
          <div><MapPinned/><span>{tr('intro.area')}</span><b>Cusco, Perú</b></div>
          <div><ShieldCheck/><span>{tr('intro.coverage')}</span><b>2000–2025</b></div>
        </div>
        <section className="fc-intro-plain">
          <header><div><span>01</span><p>{tr('intro.plainKicker')}</p></div><h2>{tr('intro.plainTitle')}</h2></header>
          <dl>{findings.map((finding) => <div key={finding.pregunta}><dt>{finding.pregunta}</dt><dd>{finding.respuesta}</dd></div>)}</dl>
        </section>
        <footer className="fc-intro-action"><div><Database/><span><b>{tr('intro.ready')}</b><small>{tr('intro.readyNote')}</small></span></div><button onClick={onEnter}>{tr('intro.cta')}<ArrowRight/></button></footer>
      </main>
      <aside className="fc-intro-map" aria-hidden="true">
        <div className="fc-intro-map-card"><span>{tr('intro.mapKicker')}</span><b>{tr('intro.mapTitle')}</b><small>{tr('intro.mapNote')}</small></div>
        <div className="fc-intro-map-index"><Layers3/><span>NASA FIRMS</span><i/>MODIS<i/>VIIRS</div>
      </aside>
    </div>
  </div>
}

export default IntroScreen
