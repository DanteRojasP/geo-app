// Cliente de la API de FireCal (backend FastAPI de plataforma_local).
// Por defecto usa la misma dirección que sirve la página. Para un frontend publicado aparte
// (p. ej. Vercel), define VITE_API_BASE_URL con la URL del backend.
import { getLang } from '../i18n.js'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export const CUSCO = 'PE-CUS'

function buildUrl(path, params = {}) {
  const url = new URL(`${API_BASE_URL}${path}`, window.location.href)
  Object.entries(params).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== '') url.searchParams.set(key, value)
  })
  url.searchParams.set('lang', getLang())          // textos de la API en el idioma de la interfaz
  return url
}

async function request(path, params) {
  const response = await fetch(buildUrl(path, params))
  let body = null
  try { body = await response.json() } catch { /* respuesta sin JSON */ }
  if (!response.ok) {
    const detail = body?.detail
    const error = new Error(typeof detail === 'string' ? detail : `La API respondió con estado ${response.status}`)
    error.status = response.status
    error.retryAfter = response.headers.get('Retry-After')
    throw error
  }
  return { body, ms: response.headers.get('X-Process-Time-ms') }
}

// AOI: { departamento: 'PE-CUS' } o { bbox: 'oeste,sur,este,norte' }
export const getRegion = () => request('/api/departamentos.geojson')
export const getMetadata = () => request('/api/metadatos')
export const getCalendar = (aoi, fechaInicio, fechaFin) =>
  request('/api/calendario', { ...aoi, fecha_inicio: fechaInicio, fecha_fin: fechaFin })
export const getMonth = (aoi, mes) => request('/api/anomalias', { ...aoi, mes })
// Analíticas "en simple": cada respuesta trae titulo, en_simple, como_leerlo y los datos.
export const getResumen = (aoi) => request('/api/resumen', aoi)
export const getAnalitica = (nombre, aoi, extra = {}) => request(`/api/analitica/${nombre}`, { ...aoi, ...extra })
export const getFocos = (aoi, fechaInicio, fechaFin) =>
  request('/api/focos.geojson', { ...aoi, fecha_inicio: fechaInicio, fecha_fin: fechaFin })

// Descarga del CSV de focos (18 columnas del contrato). Se usa fetch para mostrar los errores.
export async function downloadCsv(aoi, fechaInicio, fechaFin) {
  const response = await fetch(buildUrl('/api/hotspots.csv', { ...aoi, fecha_inicio: fechaInicio, fecha_fin: fechaFin }))
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `La API respondió con estado ${response.status}`)
  }
  const blob = await response.blob()
  const name = (response.headers.get('Content-Disposition') || '').match(/filename="(.+)"/)?.[1] || 'focos_cusco.csv'
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = name
  link.click()
  URL.revokeObjectURL(link.href)
  return { rows: Number(response.headers.get('X-Row-Count')), total: Number(response.headers.get('X-Total-Eq-Foco')) }
}
