// Animación de entrada (≈ 4 s, estilo "apertura de marca"): la llama del logo se arma píxel a píxel de abajo
// hacia arriba, aparece la palabra Nikal y todo hace zoom hacia la llama antes de dar paso al mapa.
// Se salta con un clic o una tecla; con "reducir movimiento" solo se muestra el logo un instante.
// ?intro=0 la omite (presentaciones, pruebas automáticas).
import { useEffect, useState } from 'react'
import { LOGO_VB, PIXELES } from './logoPixeles.js'
import { tr } from './i18n.js'

const DURACION = 4100
const orden = [...PIXELES].map((p, i) => ({ p, i })).sort((a, b) => b.p[1] - a.p[1] || a.p[0] - b.p[0])

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
            left: `${((x - LOGO_VB.x) / LOGO_VB.w) * 100}%`, top: `${((y - LOGO_VB.y) / LOGO_VB.h) * 100}%`,
            width: `${(20 / LOGO_VB.w) * 100}%`, height: `${(20 / LOGO_VB.h) * 100}%`,
            background: c, animationDelay: `${0.15 + k * 0.045}s`,
          }}/>
        ))}
        <img src="./nikal-icono.svg" alt="" className="nk-intro-texto"/>
      </div>
      <p className="nk-intro-lema">{tr('intro.tagline')}</p>
      <span className="nk-intro-saltar">{tr('intro.skip')}</span>
    </div>
  )
}

export default IntroNikal
