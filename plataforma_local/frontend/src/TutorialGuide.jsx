import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, ArrowRight, Check, Compass, X } from 'lucide-react'
import { tr } from './i18n.js'

const STEP_SELECTORS = [
  '.fw-nubel-brand',
  '.fc-data-launcher:not(.fc-simple-launcher):not(.fc-compare-launcher):not(.fc-ambitos-launcher):not(.fc-tutorial-launcher)',
  '.fc-simple-launcher',
  '.fc-compare-launcher',
  '.fc-ambitos-launcher',
  '.fc-map-menu',
  '.fc-timeline',
  '.fw-layers, .fc-map-menu',
]

const clamp = (value, min, max) => Math.max(min, Math.min(value, max))

function TutorialPrompt({ onStart, onSkip }) {
  return <div className="ft-prompt-layer" role="dialog" aria-modal="true" aria-labelledby="ft-prompt-title">
    <article className="ft-prompt-card">
      <span className="ft-prompt-icon"><Compass/></span>
      <p>{tr('tutorial.welcomeKicker')}</p>
      <h2 id="ft-prompt-title">{tr('tutorial.welcomeTitle')}</h2>
      <span>{tr('tutorial.welcomeBody')}</span>
      <div><button type="button" className="is-secondary" onClick={onSkip}>{tr('tutorial.skip')}</button><button type="button" className="is-primary" onClick={onStart}>{tr('tutorial.start')}<ArrowRight/></button></div>
    </article>
  </div>
}

function TutorialTour({ onClose }) {
  const [step, setStep] = useState(0)
  const [rect, setRect] = useState(null)
  const total = STEP_SELECTORS.length
  const copy = useMemo(() => ({ title: tr(`tutorial.step${step + 1}.title`), body: tr(`tutorial.step${step + 1}.body`) }), [step])

  useEffect(() => {
    const update = () => {
      const element = document.querySelector(STEP_SELECTORS[step])
      if (!element) { setRect(null); return }
      const box = element.getBoundingClientRect()
      setRect({ left: box.left, top: box.top, right: box.right, bottom: box.bottom, width: box.width, height: box.height })
    }
    update()
    const timer = window.setTimeout(update, 220)
    window.addEventListener('resize', update)
    return () => { window.clearTimeout(timer); window.removeEventListener('resize', update) }
  }, [step])

  const cardPosition = useMemo(() => {
    const width = Math.min(340, window.innerWidth - 32)
    const height = 230
    if (!rect || window.innerWidth <= 650) return { left: 16, top: window.innerHeight - height - 16, width }
    const gap = 18
    if (rect.right + gap + width < window.innerWidth) return { left: rect.right + gap, top: clamp(rect.top, 16, window.innerHeight - height - 16), width }
    if (rect.left - gap - width > 0) return { left: rect.left - gap - width, top: clamp(rect.top, 16, window.innerHeight - height - 16), width }
    const above = rect.top - height - gap
    return { left: clamp(rect.left + rect.width / 2 - width / 2, 16, window.innerWidth - width - 16), top: above > 16 ? above : clamp(rect.bottom + gap, 16, window.innerHeight - height - 16), width }
  }, [rect])

  const finish = () => onClose(true)
  return <div className="ft-tour-layer" role="dialog" aria-modal="true" aria-label={tr('tutorial.label')}>
    {rect && <div className="ft-spotlight" style={{ left: rect.left - 7, top: rect.top - 7, width: rect.width + 14, height: rect.height + 14 }}/>}
    <article className="ft-tour-card" style={cardPosition}>
      <header><span>{tr('tutorial.progress', { n: step + 1, total })}</span><button type="button" onClick={() => onClose(false)} aria-label={tr('tutorial.close')}><X/></button></header>
      <div className="ft-step-number">{String(step + 1).padStart(2, '0')}</div>
      <h2>{copy.title}</h2>
      <p>{copy.body}</p>
      <div className="ft-dots" aria-hidden="true">{STEP_SELECTORS.map((_, index) => <i key={index} className={index === step ? 'is-active' : index < step ? 'is-done' : ''}/>)}</div>
      <footer>
        <button type="button" className="is-back" disabled={step === 0} onClick={() => setStep((value) => value - 1)}><ArrowLeft/>{tr('tutorial.back')}</button>
        {step < total - 1
          ? <button type="button" className="is-next" onClick={() => setStep((value) => value + 1)}>{tr('tutorial.next')}<ArrowRight/></button>
          : <button type="button" className="is-next" onClick={finish}>{tr('tutorial.finish')}<Check/></button>}
      </footer>
    </article>
  </div>
}

export default function TutorialGuide({ prompt, open, onStart, onSkip, onClose }) {
  if (prompt) return <TutorialPrompt onStart={onStart} onSkip={onSkip}/>
  if (open) return <TutorialTour onClose={onClose}/>
  return null
}
