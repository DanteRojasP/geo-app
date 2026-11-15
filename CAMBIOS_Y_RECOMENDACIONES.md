# Cambios, recomendaciones, seguridad y costos (14-nov-2026)

*Julio · revisión de Cloud Run `firecal-00008` · https://firecal-316891526626.southamerica-east1.run.app*

## 1. Qué cambió

| Área | Cambio | Origen |
| --- | --- | --- |
| Backend | Se retiró el backend sintético (simulador, H3, `/api/v1`, LightGBM): 66 % del código. Está archivado en la rama `archivo/backend-sintetico`. | Auditoría de Gabriel |
| Backend | `resumen?graficos=true` hace el panel "En simple" en una llamada (antes 5). | Auditoría |
| Backend | Parámetros desconocidos → 422. Fechas solo `AAAA-MM`. Área dibujada con título legible. | Auditoría |
| Backend | Una consulta con área dibujada cuenta como pesada en todas las rutas que recalculan. | Auditoría |
| Backend | GZip, caché de 1 h en `/api`, `nosniff` y `Referrer-Policy` (mejora 4). | Auditoría |
| Imagen | Pasa de 1,33 GB a 917 MB y de 60 a 47 dependencias. Sin `libgomp`. | Auditoría |
| Interfaz | Rama de Dante (b4dbf8c): relieve, logo, barra superior, nueva línea de tiempo, CSS. | Dante |
| Interfaz | Botón "Hotspots" útil, leyenda de puntos, años recientes primero, teclado, calendario cerrado en < 1600 px, riel en el celular, sin solapes, los dos conteos rotulados. | Auditoría |
| Interfaz | Mejoras 1-3 y 5 de la auditoría (publicadas antes, revisión 3): pausa de consultas durante la reproducción, paleta divergente sólida, borde de Cusco opcional. | Auditoría |

Pruebas: 83 del backend en verde, `ruff` limpio, ESLint sin errores, build de Vite correcta.

Comprobado en la URL pública:
- Casos de MAESTRO §12: 2005 = 1355 y 2020 = 1206 focos armonizados.
- PE-PUN responde 404 con mensaje en inglés.
- Parámetro mal escrito → 422.
- Gzip activo.
- Una IP falsificada en `X-Forwarded-For` no crea clientes nuevos.

### Revisión 8: QA de Erik

Corregidos los 14 errores de `QA_ERIK.md` (detalle al final de ese archivo) y la escala de años, que se cortaba en
2021 en pantallas de 1440 px. 90 pruebas en verde.

## 2. Recomendaciones (no implementadas)

1. **Alerta de presupuesto** de US$10-20 en Facturación → Presupuestos. Es lo más importante antes de compartir la URL.
2. **`--max-instances 1`** mientras dure la evaluación: reduce a la mitad el gasto máximo. Una instancia atiende
   ~40 visitantes a la vez.
3. **Formulario de comentarios** (Google Forms) para la evaluación de impacto, con el enlace en el grupo o en la app.
4. **Borrar `.github/workflows/pages.yml`**: falla en cada push porque Pages no está habilitado. Borrar también los
   restos de la raíz (`dist/`, `hola.txt`, `.openai/`). Hay que confirmarlo con el equipo.
5. **Esquemas de respuesta en OpenAPI** (`response_model`) para que `/docs` muestre los campos.
6. **Dividir `FireMapApp.jsx`** (~1500 líneas) en componentes: mapa, calendario, línea de tiempo y paneles.
7. **Optimizar el logo** (408 KB en PNG). En WebP quedaría por debajo de 50 KB.
8. **Mover `credenciales_meteo.txt`** fuera de las carpetas de trabajo y del repositorio (está ignorado por
   `.gitignore`, pero es mejor fuera).
9. **Prueba con 2 personas en redes distintas** del límite por IP (ver `AVISO_EQUIPO.md`).
10. Limpiar en `settings.yaml` los bloques que solo usaba el backend sintético.
11. Al terminar la evaluación: `--min-instances 0` o borrar el servicio.

## 3. Seguridad

- **Sin secretos** en el repositorio ni en la imagen. El contenedor corre sin privilegios (uid 10001). Solo acepta
  `GET` y `OPTIONS`. El SQL usa parámetros.
- `npm audit` y `pip-audit` sin vulnerabilidades conocidas.
- Abuso: 120 solicitudes/min por IP y 10 consultas pesadas/min. Hay 2 pesadas a la vez como máximo: si hay más,
  responde 503 en vez de saturarse. El CSV tiene un tope de 200 000 filas. La IP se toma del último salto de Cloud Run,
  así que no se puede falsificar.
- **Riesgo restante:** una red de bots con muchas IP puede generar tráfico de salida (egress), que es lo único sin
  tope. Con la alerta de presupuesto se detecta a tiempo; si hace falta, se pone Cloud Armor o se baja el servicio.
- Las cifras son de focos de calor, no de incendios. La interfaz lo aclara y da los créditos de FIRMS.

## 4. Costos (Cloud Run, São Paulo)

| Escenario | Estimación |
| --- | --- |
| En reposo (1 instancia mínima, 1 vCPU, 1 GiB) | ~US$0,6 por día |
| Uso normal de la evaluación | ~US$1 por día |
| Peor caso de cómputo (2 instancias al 100 % todo el día) | ~US$6 por día |
| Tráfico de salida | ~US$0,12 por GB; cada visita usa ~1-2 MB (el mapa base viene de Esri, no de nuestro servidor) |

Con el crédito de prueba de Google Cloud, un mes de evaluación cuesta menos de US$30.
