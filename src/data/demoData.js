export const departments = {
  cusco: {
    name: 'Cusco',
    center: [-13.53, -71.97],
    zoom: 7,
    base: 82,
    polygon: [[-11.9,-72.7],[-12.4,-70.9],[-13.4,-70.6],[-15.2,-71.1],[-15.4,-72.6],[-14.0,-73.8],[-12.5,-73.6]],
  },
  ucayali: {
    name: 'Ucayali',
    center: [-9.7, -73.2],
    zoom: 6,
    base: 96,
    polygon: [[-7.2,-75.0],[-7.6,-71.9],[-10.1,-71.0],[-11.4,-72.5],[-10.9,-74.3],[-9.2,-75.2]],
  },
  huanuco: {
    name: 'Huánuco',
    center: [-9.93, -76.24],
    zoom: 7,
    base: 68,
    polygon: [[-8.2,-77.1],[-8.4,-75.2],[-10.5,-74.9],[-10.8,-76.4],[-9.7,-77.5]],
  },
  cajamarca: {
    name: 'Cajamarca',
    center: [-6.8, -78.1],
    zoom: 7,
    base: 61,
    polygon: [[-4.6,-79.3],[-5.2,-78.0],[-7.0,-77.5],[-7.7,-78.7],[-6.7,-79.6]],
  },
  'madre-de-dios': {
    name: 'Madre de Dios',
    center: [-11.9, -70.1],
    zoom: 7,
    base: 89,
    polygon: [[-10.1,-71.6],[-10.3,-68.7],[-12.4,-68.5],[-13.2,-70.0],[-12.4,-71.6]],
  },
}

const seeded = (seed) => {
  const value = Math.sin(seed) * 10000
  return value - Math.floor(value)
}

export function makeHotspots(key, year = 2026) {
  const department = departments[key]
  const [lat, lon] = department.center
  return Array.from({ length: 28 }, (_, index) => ({
    id: `${key}-${year}-${index}`,
    lat: lat + (seeded(index * 11 + department.base) - 0.5) * 2.8,
    lon: lon + (seeded(index * 17 + department.base) - 0.5) * 3.2,
    frp: Math.round(8 + seeded(index * 23 + department.base) * 96),
    confidence: Math.round(62 + seeded(index * 31 + department.base) * 37),
    sensor: index % 3 === 0 ? 'MODIS' : 'VIIRS',
    date: `${year}-${String(7 + (index % 4)).padStart(2, '0')}-${String(1 + (index % 27)).padStart(2, '0')}`,
  })).filter((point) => point.confidence >= 70)
}

export function makeCalendar(key, startYear, endYear) {
  const base = departments[key].base
  const rows = []
  for (let year = startYear; year <= endYear; year += 1) {
    rows.push({
      year,
      months: Array.from({ length: 12 }, (_, month) => {
        const drySeason = month >= 6 && month <= 9 ? 1.85 : 0.55
        return Math.round((seeded(year * 19 + month * 37 + base) * 46 + base / 3) * drySeason)
      }),
    })
  }
  return rows
}
