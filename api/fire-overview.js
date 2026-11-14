const DEPARTMENTS = {
  cusco: [-73.9, -15.5, -70.3, -11.8],
  ucayali: [-75.3, -11.6, -70.8, -7.1],
  huanuco: [-77.7, -10.9, -74.7, -8.1],
  cajamarca: [-79.8, -7.8, -77.3, -4.5],
  'madre-de-dios': [-71.8, -13.3, -68.3, -10.0],
}

const SOURCES = ['MODIS_NRT', 'VIIRS_SNPP_NRT', 'VIIRS_NOAA20_NRT']

function parseCsv(text, source) {
  const lines = text.trim().split(/\r?\n/)
  if (lines.length < 2) return []
  const headers = lines[0].split(',').map((header) => header.trim())
  return lines.slice(1).map((line, index) => {
    const values = line.split(',')
    const row = Object.fromEntries(headers.map((header, position) => [header, values[position]]))
    const rawConfidence = String(row.confidence ?? '').toLowerCase()
    const confidence = Number.isFinite(Number(rawConfidence))
      ? Number(rawConfidence)
      : ({ h: 95, n: 80, l: 60 }[rawConfidence] ?? 70)
    return {
      id: `${source}-${row.acq_date}-${row.latitude}-${row.longitude}-${index}`,
      lat: Number(row.latitude),
      lon: Number(row.longitude),
      frp: Number(row.frp || 0),
      confidence,
      sensor: source.startsWith('MODIS') ? 'MODIS' : 'VIIRS',
      source,
      date: row.acq_date,
      daynight: row.daynight,
    }
  }).filter((point) => Number.isFinite(point.lat) && Number.isFinite(point.lon))
}

function deduplicate(points) {
  const cells = new Map()
  points.forEach((point) => {
    const key = `${point.date}:${point.lat.toFixed(2)}:${point.lon.toFixed(2)}`
    const previous = cells.get(key)
    if (!previous || point.frp > previous.frp) cells.set(key, point)
  })
  return [...cells.values()].filter((point) => point.confidence >= 70)
}

export default async function handler(request, response) {
  if (request.method !== 'GET') return response.status(405).json({ error: 'Método no permitido' })
  const mapKey = process.env.FIRMS_MAP_KEY
  if (!mapKey) return response.status(503).json({ error: 'FIRMS_MAP_KEY no está configurada' })

  const department = String(request.query.department || 'cusco')
  const bbox = DEPARTMENTS[department]
  if (!bbox) return response.status(400).json({ error: 'Departamento no soportado' })

  try {
    const results = await Promise.all(SOURCES.map(async (source) => {
      const url = `https://firms.modaps.eosdis.nasa.gov/api/area/csv/${mapKey}/${source}/${bbox.join(',')}/5`
      const nasaResponse = await fetch(url, { headers: { 'User-Agent': 'Firewatch-Peru/0.1' } })
      if (!nasaResponse.ok) throw new Error(`FIRMS ${source}: ${nasaResponse.status}`)
      return parseCsv(await nasaResponse.text(), source)
    }))

    const hotspots = deduplicate(results.flat())
    response.setHeader('Cache-Control', 's-maxage=900, stale-while-revalidate=3600')
    return response.status(200).json({
      department,
      hotspots,
      eventCount: hotspots.length,
      sources: SOURCES,
      dayRange: 5,
      generatedAt: new Date().toISOString(),
      harmonizer: 'grid-1km-dedup-v0.1',
    })
  } catch (error) {
    return response.status(502).json({ error: 'No se pudieron consultar los datos de FIRMS', detail: error.message })
  }
}
