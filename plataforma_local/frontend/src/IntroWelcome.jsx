import { ArrowRight, Database, MapPinned, Satellite, ShieldCheck } from 'lucide-react'

const COPY = {
  es: {
    kicker: 'ACTIVIDAD TÉRMICA · CUSCO, PERÚ',
    title: 'Lee el territorio antes de explorar el mapa.',
    lead: 'Nikal convierte los registros MODIS y VIIRS en una lectura histórica armonizada para explorar, comparar y comunicar la actividad térmica de Cusco.',
    source: 'Fuentes satelitales', area: 'Área validada', coverage: 'Cobertura histórica',
    section: 'LO QUE LOS DATOS YA NOS CUENTAN',
    findings: [
      ['¿Cuándo hay más focos?', 'La temporada más activa se concentra entre julio y octubre, con su mayor intensidad habitual en septiembre.'],
      ['¿Qué permite analizar?', 'Periodos, provincias, distritos y cuencas, con comparaciones, mapas e informes descargables.'],
      ['¿Qué representa el mapa?', 'Densidad de focos térmicos armonizados; no equivale directamente a superficie quemada.'],
    ],
    ready: 'Vista interactiva preparada', note: 'Fechas, capas, selección de área, comparación e informes', cta: 'Explorar el mapa',
  },
  en: {
    kicker: 'THERMAL ACTIVITY · CUSCO, PERU',
    title: 'Read the territory before exploring the map.',
    lead: 'Nikal turns MODIS and VIIRS records into one harmonized historical view for exploring, comparing and communicating thermal activity in Cusco.',
    source: 'Satellite sources', area: 'Validated area', coverage: 'Historical coverage',
    section: 'WHAT THE DATA ALREADY TELLS US',
    findings: [
      ['When are there more hotspots?', 'The most active season is concentrated between July and October, usually peaking in September.'],
      ['What can be analyzed?', 'Periods, provinces, districts and basins, with comparisons, maps and downloadable reports.'],
      ['What does the map represent?', 'Density of harmonized thermal hotspots; it is not a direct measurement of burned area.'],
    ],
    ready: 'Interactive view ready', note: 'Dates, layers, area selection, comparison and reports', cta: 'Explore the map',
  },
}

export default function IntroWelcome({ lang, onLanguage }) {
  const c = COPY[lang] || COPY.es
  const params = new URLSearchParams(window.location.search)
  params.set('welcome', '0'); params.set('intro', '0'); params.set('tutorialPrompt', '1'); params.set('lang', lang); params.delete('tutorial')
  const mapHref = `${window.location.pathname}?${params.toString()}`
  return <div className="nk-welcome">
    <article>
      <header><img src="./nikal-icono.svg" alt="Nikal"/><div><button className={lang === 'en' ? 'is-active' : ''} onClick={() => onLanguage('en')}>EN</button><button className={lang === 'es' ? 'is-active' : ''} onClick={() => onLanguage('es')}>ES</button></div></header>
      <section className="nk-welcome-copy"><small>{c.kicker}</small><h1>{c.title}</h1><p>{c.lead}</p></section>
      <section className="nk-welcome-facts"><div><Satellite/><span>{c.source}</span><b>MODIS + VIIRS</b></div><div><MapPinned/><span>{c.area}</span><b>Cusco, Perú</b></div><div><ShieldCheck/><span>{c.coverage}</span><b>2000–2025</b></div></section>
      <section className="nk-welcome-findings"><h2>{c.section}</h2>{c.findings.map(([q, a]) => <div key={q}><b>{q}</b><p>{a}</p></div>)}</section>
      <footer><div><Database/><span><b>{c.ready}</b><small>{c.note}</small></span></div><a href={mapHref}>{c.cta}<ArrowRight/></a></footer>
    </article>
    <aside><div><small>CUSCO · MODIS + VIIRS</small><h2>25 años de actividad térmica, en una sola lectura.</h2><p>Explora el territorio. Entiende la temporada. Actúa con evidencia.</p></div></aside>
  </div>
}
