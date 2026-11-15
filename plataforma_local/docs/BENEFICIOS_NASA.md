# Beneficios de NASA Space Apps: ¿cuáles sirven a Nikal Perú?

Evaluación de cada oferta para este proyecto: un geovisor web con API Python, datos FIRMS MODIS + VIIRS y un
calendario por departamento. Los montos de crédito y las condiciones de cada oferta hay que confirmarlos al
canjearla: el texto recibido no los detalla.

## Resumen

| Beneficio | ¿Sirve? | Para qué, en concreto | Prioridad |
| --- | --- | --- | --- |
| **Microsoft Azure** | **Sí, mucho** | Hospedar la imagen Docker (Container Apps), guardar datos (Blob Storage), actualización diaria (Container Apps Jobs), mapa base (Azure Maps), monitoreo (Application Insights) | **Alta** (despliegue) |
| **Google Cloud** | **Sí** (alternativa a Azure) | Cloud Run para la misma imagen, Cloud Storage, Google Maps API para el mapa base, Firebase Hosting para un frontend separado | Alta si no se usa Azure |
| **GoDaddy Registry** (dominio + hosting + SSL) | **Sí** | Dominio propio para la demo (p. ej. `firecal-peru.<tld>`) apuntando a Azure o Cloud Run. El hosting incluido sirve, como mucho, para una página estática | **Alta** (presentación) |
| **Microsoft Planetary Computer** | **Sí, como extra** | Validación y contexto: área quemada MODIS (MCD64A1), anomalías térmicas MODIS diarias, cobertura del suelo y elevación | Media (después del MVP) |
| **Meteomatics Weather API** (1000 consultas/día) | **Sí, para la Fase 7** | Precipitación, humedad y viento por departamento y mes para el modelo de "perspectiva del mes siguiente" y para explicar anomalías | Media-baja |
| **GitHub Copilot** | Sí (productividad) | Escribir y revisar código, tests y documentación del equipo | Media |
| **Microsoft Teams Free** | Sí (coordinación) | Reuniones de los hitos H1 a H4 (≤ 60 min, ≤ 100 personas), compartir pantalla y archivos (5 GB) | Media |
| **Miro** (Business 14 días + plantillas) | Sí (gestión) | Tablero de los hitos, riesgos y la historia de usuario para la presentación | Baja-media |
| **Microsoft Copilot** | Marginal | Lluvia de ideas y textos de la presentación | Baja |

## Detalle por beneficio

### Microsoft Azure: recomendado para publicar la web
- **Azure Container Apps:** corre el mismo `Dockerfile`, con HTTPS administrado, dominio personalizado y escalado de
  1 a N réplicas. Configuración sugerida: 0,5 vCPU, 1 GiB y mínimo 1 réplica (ver `DESPLIEGUE_Y_FALENCIAS.md`).
- **Blob Storage:** guardar `data/processed` (eventos Parquet de ~10 MB y DuckDB). Cuando haya datos reales NRT, la
  API se actualiza sin reconstruir la imagen.
- **Container Apps Jobs:** tarea diaria que descargue FIRMS NRT y corra `firecal all` (Fase R).
- **Azure Maps:** mapa base con clave propia, en lugar de los mosaicos de OpenStreetMap (falencia n.º 5).
- **Application Insights:** saber si la web cae durante la evaluación.
- Cuidado: configurar alertas de presupuesto; los créditos tienen límite y vencen.

### Google Cloud: alternativa equivalente
- **Cloud Run** despliega desde el código fuente (`gcloud run deploy --source .`); el `Dockerfile` ya usa `PORT`.
- **Google Maps Platform** para el mapa base (también requiere clave y tiene cuotas).
- Elegir **una sola** nube (Azure o GCP) para no dividir esfuerzos. Azure ofrece además Azure Maps y el Planetary
  Computer en el mismo ecosistema.

### GoDaddy Registry: dominio gratis por 1 año
- Útil para que el jurado tenga una URL limpia con HTTPS.
- El registro se completa con Porkbun (socio del registrador). Solo dominios no premium.
- El "website hosting" incluido no está pensado para una API Python con DuckDB: usar el dominio para apuntar a la
  nube (CNAME), no para hospedar el backend.

### Microsoft Planetary Computer: valor científico extra
- El catálogo de datos y la API STAC son públicos y no necesitan cuenta (el Hub de notebooks ya no está disponible;
  se trabaja desde Python local con `pystac-client` y `planetary-computer`).
- **No reemplaza a FIRMS** para los focos: FIRMS sigue siendo la fuente del calendario.
- Usos concretos:
  1. **Validación independiente:** comparar el calendario con el **área quemada mensual MODIS (MCD64A1)** por
     departamento. Si los meses con anomalía alta coinciden con más área quemada, es un buen argumento para el jurado.
  2. **Contexto:** cobertura del suelo (p. ej. ESA WorldCover) para separar quemas agrícolas de incendios forestales,
     y elevación (Copernicus DEM) para cuantificar la nota sobre la omisión de fuegos pequeños altoandinos.
- Antes de usar cada colección, confirmar en el catálogo su nombre exacto y su cobertura temporal.

### Meteomatics Weather API: para el modelo predictivo (Fase 7)
- 1000 consultas/día alcanzan para series mensuales por departamento (5 departamentos × pocas variables), siempre
  que se guarden en caché local (`data/raw/covariates/`). No hay que consultar en cada visita a la web.
- Variables útiles: precipitación acumulada, humedad relativa, temperatura máxima y viento.
- La clave va como variable de entorno o secreto, nunca en el repositorio.

### GitHub Copilot, Teams, Miro y Copilot
- No cambian la arquitectura, pero ayudan a cumplir el cronograma: Copilot para tests y revisión, Teams para los
  hitos H1 a H4 y Miro para preparar la presentación (problema → usuarios → demo → método → limitaciones).

## Recomendación final

1. **Azure Container Apps + dominio de GoDaddy** para publicar la demo (o Cloud Run si el equipo ya conoce GCP).
2. **Azure Maps** (o Google Maps) como mapa base si el tráfico esperado es alto.
3. **Planetary Computer (MCD64A1)** como validación extra si sobra tiempo después de H3.
4. **Meteomatics** solo cuando se aborde la Fase 7.
