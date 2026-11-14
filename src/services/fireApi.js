import { makeCalendar, makeHotspots } from '../data/demoData.js'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '')
const USE_VERCEL_API = import.meta.env.VITE_USE_LIVE_API === 'true'
  || (typeof window !== 'undefined' && window.location.hostname.endsWith('.vercel.app'))

async function request(path, params = {}) {
  const query = new URLSearchParams(params)
  const response = await fetch(`${API_BASE_URL}${path}?${query}`)
  if (!response.ok) throw new Error(`La API respondió con estado ${response.status}`)
  return response.json()
}

export async function getFireOverview({ department, startYear, endYear }) {
  if (USE_VERCEL_API && !API_BASE_URL) {
    const live = await fetch(`/api/fire-overview?department=${encodeURIComponent(department)}`)
    if (!live.ok) {
      const body = await live.json().catch(() => ({}))
      throw new Error(body.error || `La API respondió con estado ${live.status}`)
    }
    const data = await live.json()
    return {
      mode: 'api',
      calendar: makeCalendar(department, startYear, endYear),
      hotspots: data.hotspots,
      metadata: {
        harmonizer: data.harmonizer,
        confidenceThreshold: 70,
        generatedAt: data.generatedAt,
        dayRange: data.dayRange,
        calendarMode: 'demo',
      },
    }
  }

  if (!API_BASE_URL) {
    await new Promise((resolve) => setTimeout(resolve, 260))
    return {
      mode: 'demo',
      calendar: makeCalendar(department, startYear, endYear),
      hotspots: makeHotspots(department, endYear),
      metadata: { harmonizer: 'demo-0.1', confidenceThreshold: 70 },
    }
  }

  const common = { departamento: department, fecha_inicio: `${startYear}-01-01`, fecha_fin: `${endYear}-12-31` }
  const [calendar, anomalies, metadata] = await Promise.all([
    request('/api/calendario', common),
    request('/api/anomalias', common),
    request('/api/metadatos'),
  ])

  return { mode: 'api', calendar, anomalies, metadata, hotspots: calendar.hotspots ?? [] }
}

export function getCsvUrl({ department, startYear, endYear }) {
  if (!API_BASE_URL) return null
  const query = new URLSearchParams({ departamento: department, fecha_inicio: `${startYear}-01-01`, fecha_fin: `${endYear}-12-31` })
  return `${API_BASE_URL}/api/hotspots.csv?${query}`
}
