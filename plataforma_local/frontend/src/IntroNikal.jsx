// Animación de entrada (≈ 6 s, estilo "apertura de marca"): la llama del logo se arma píxel a píxel de abajo
// hacia arriba, aparece la palabra Nikal, la llama "vive" (sus píxeles laten y se iluminan en oleadas, más
// arriba que abajo, y suben chispas) y al final todo hace zoom hacia la llama antes de dar paso al mapa.
// Se salta con un clic o una tecla; con "reducir movimiento" solo se muestra el logo un instante.
// ?intro=0 la omite (presentaciones, pruebas automáticas).
import { useEffect, useState } from 'react'
import { LOGO_VB, PIXELES } from './logoPixeles.js'
import { tr } from './i18n.js'

const DURACION = 6000
const orden = [...PIXELES].map((p, i) => ({ p, i })).sort((a, b) => b.p[1] - a.p[1] || a.p[0] - b.p[0])
// Chispas que se desprenden de la punta: posición horizontal (unidades del SVG), retraso y color.
const CHISPAS = [[57, 2.0, '#fcffa4'], [33, 2.45, '#fca50a'], [83, 2.8, '#fcffa4'], [60, 3.25, '#fca50a'], [45, 3.6, '#fcffa4'], [72, 3.95, '#dd513a']]
const pct = (v, total) => `${(v / total) * 100}%`

function IntroNikal({ onDone }) {
  const [saliendo, setSaliendo] = useState(false)
  const reducido = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

  useEffect(() => {
    const total = reducido ? 1200 : DURACION
    const fin = setTimeout(onDone, total)
    const saltar = () => { setSaliendo(true); setTimeout(onDone, 350) }
    window.addEventListener('keydown', saltar, { once: true })
    return () => { clearTimeout(fin); window.removeEventListener('keydown', saltar) }
  }, [onDone, reducido])

  return (
    <div className={`nk-intro ${reducido ? 'is-reducido' : ''} ${saliendo ? 'is-saliendo' : ''}`} role="presentation"
      onClick={() => { setSaliendo(true); setTimeout(onDone, 350) }}>
      <div className="nk-intro-bloom" aria-hidden="true"/>
      <div className="nk-intro-logo" aria-label="Nikal">
        {orden.map(({ p: [x, y, c] }, k) => (
          <i key={`${x}-${y}`} style={{
            left: pct(x - LOGO_VB.x, LOGO_VB.w), top: pct(y - LOGO_VB.y, LOGO_VB.h),
            width: pct(20, LOGO_VB.w), height: pct(20, LOGO_VB.h), background: c,
            // 1) aparecer (de abajo hacia arriba)  2) latir como fuego: más amplitud cuanto más arriba
            animationDelay: `${0.15 + k * 0.045}s, ${1.75 + ((x / 25 + y / 25) % 5) * 0.12}s`,
            '--amp': `${4 + ((170 - y) / 170) * 14}%`,
          }}/>
        ))}
        {CHISPAS.map(([x, d, c], k) => (
          <b key={k} className="nk-intro-chispa" style={{ left: pct(x - LOGO_VB.x, LOGO_VB.w), top: pct(-4 - LOGO_VB.y, LOGO_VB.h), background: c, animationDelay: `${d}s` }}/>
        ))}
        <img src="./nikal-icono.svg" alt="" className="nk-intro-texto"/>
      </div>
      <p className="nk-intro-lema">{tr('intro.tagline')}</p>
      <span className="nk-intro-saltar">{tr('intro.skip')}</span>
    </div>
  )
}

export default IntroNikal
