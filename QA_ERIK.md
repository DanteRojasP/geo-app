# QA de usuario y control de errores — Erik

NASA Space Apps Challenge 2026 · FireCal Cusco
Fuente: [PLAN.md](PLAN.md) (rol de Erik: Q/A de usuario, propuesta y control de errores)

> **Versión probada:** `main` @ `f53ad18` (la publicada en Cloud Run, según [AVISO_EQUIPO.md](AVISO_EQUIPO.md)) ·
> sábado 14-nov-2026, 19:30 (hora de Colombia). La primera ronda de QA se hizo sobre `antonio/analitica` @ `e14c7f4`.

## Resumen

Los **datos y los cálculos están bien**: los números del calendario, el CSV, el mapa, las anomalías y las analíticas
coinciden entre sí en 94 combinaciones al azar de áreas y fechas, y las sumas de control de `MAESTRO.md` §6 dan
iguales. Los errores están en la **interfaz** (sobre todo en el celular), en **cómo la API acepta algunas fechas** y
en los **textos** del panel "En simple".

| # | Error | Gravedad | Responsable |
|---|---|---|---|
| 1 | En el celular no se puede cambiar de año, abrir "En simple" ni dibujar un área | Alta | Dante |
| 2 | Área dibujada + ▶: "Demasiadas solicitudes" en 5 de cada 12 meses | Alta | Dante y Julio |
| 3 | La API acepta fechas como `9999-12` y responde 4,7 MB en 2 s | Alta | Julio |
| 4 | El cero se pinta casi negro en el calendario | Media | Dante |
| 5 | "En simple" se contradice en áreas con poco fuego | Media | Antonio y Julio |
| 6 | "El año más tranquilo" puede ser un año extrapolado (2001, 2002) | Media | Antonio y Julio |
| 7 | Año 2000 + ▶: aviso rojo "Sin datos" en meses deshabilitados | Media | Dante |
| 8 | En pantalla grande, el calendario tapa el panel de Capas | Media | Dante |
| 9 | Jerga técnica a la vista ("Σ eq_foco", "peso eq_foco", "218.4 ms") | Baja | Dante |
| 10 | Plurales: "1 focos armonizados", "1 lugares" | Baja | Julio |
| 11 | Mensajes de validación en inglés ("Field required") | Baja | Julio |
| 12 | Mensajes con detalles a corregir (radio 0, "mes inválida", fecha con día) | Baja | Julio |
| 13 | Área en Cusco sin fuego dice "Sin datos" | Baja | Julio y Dante |
| 14 | Un botón sin nombre para lectores de pantalla | Baja | Dante |

## Detalle de cada error

### 1. En el celular no se puede cambiar de año (Alta)

- **Cómo reproducirlo:** abrir la URL en un celular (o en el navegador con ancho de 375 px).
- **Qué pasa:** no aparecen las flechas de año ni la barra lateral (Calendario, Seleccionar área, En simple, Capas,
  Información): miden 0 × 0 px. El usuario se queda en 2025. El calendario solo se abre con el botón del panel, y si
  cierra el panel no hay otro botón para volver a abrirlo.
- **Esperado:** en el celular se puede cambiar de año, abrir el calendario, "En simple" y dibujar un área.
- Confirmado en la URL publicada con vista de celular.

### 2. Área dibujada + ▶ falla (Alta)

- **Cómo reproducirlo:** dibujar un área, elegir cualquier año de 2001 a 2025 y pulsar ▶.
- **Qué pasa:** en todos los años, 5 de los 12 meses muestran "Demasiadas solicitudes desde tu conexión". En la
  temporada de fuego (julio a octubre) fallan 3 de los 4 meses. En 2023 fallan junio, agosto, septiembre, octubre y
  diciembre. Si se deja correr una segunda vuelta, solo se ven 3 de 12 meses.
- **Causa:** el ▶ pide `/api/calendario?bbox=…` cada 1,6 s y esa consulta cuenta como "pesada": la API admite 5
  seguidas y luego 1 cada 6 s (`heavy_burst: 5`, `heavy_per_minute: 10`). No depende de los datos: si el ▶ empieza en
  julio, fallan enero a marzo.
- **Propuesta (Dante):** durante el ▶, leer el mes del calendario del año que ya se pidió al elegir el año, en vez
  de pedirlo otra vez. Ante un 429, conservar lo que se ve y reintentar después del `Retry-After`. No juntar en un
  mismo `Promise.all` el calendario y los focos del área.
- **Propuesta (Julio):** no contar como pesado el calendario de un solo mes de un área (responde en ~40 ms), o
  subir el límite a más de 38 por minuto.
- **Verificación:** `qa/play_por_anio.py` debe dar los 12 meses en OK de 2001 a 2025.

### 3. Fechas absurdas hacen lenta la API (Alta)

- **Cómo reproducirlo:** `GET /api/calendario?departamento=PE-CUS&fecha_inicio=2020-01&fecha_fin=9999-12`.
- **Qué pasa:** responde 200 con 4,7 MB (7 980 años y 95 760 celdas vacías) y tarda 2,1 s. Con `fecha_inicio=0000-01`
  arma 2 002 años. Con el departamento la consulta no cuenta como pesada, así que se puede repetir 120 veces por
  minuto y cargar el servidor de Cloud Run.
- **Propuesta:** recortar `fecha_inicio` y `fecha_fin` a la cobertura (2000-11 a 2025-12) antes de armar la matriz,
  o rechazar años fuera de 2000–2025 con un 422.

### 4. El cero se pinta casi negro (Media)

- **Qué pasa:** en el calendario, los meses con 0 focos son el color más oscuro de todos y resaltan más que los
  meses de más fuego.
- **Esperado:** `MAESTRO.md` P2 pide el cero en gris claro neutro.

### 5. "En simple" se contradice en áreas con poco fuego (Media)

- **Cómo reproducirlo:** `GET /api/resumen?lat=-13.52&lon=-71.97&radio_km=3`.
- **Qué pasa:** "La temporada de fuego se concentra en septiembre: esos meses reúnen el 100 %… El mes más activo es
  enero, con unos 0 focos armonizados". Cuando todas las medianas son 0, el mes pico sale enero.
- **Propuesta:** si la mediana del mes pico es 0, decir que el área tiene muy poco fuego para describir una
  temporada; y "ese mes" en singular.

### 6. "El año más tranquilo" puede ser un año extrapolado (Media)

- **Cómo reproducirlo:** `GET /api/analitica/ranking?bbox=-73.2,-12.2,-72.4,-11.4` → "El más tranquilo fue 2001,
  con 0". Con `bbox=-72.2,-13.7,-71.8,-13.4` → "2002, con 0".
- **Qué pasa:** 2001 y la primera mitad de 2002 son solo Terra (ve unas 5 veces menos). Con 0 focos la
  incertidumbre también da 0 y el año pasa como "ok". En Cusco completo sí se excluyen.
- **Propuesta:** excluir de "más tranquilo" los años con `calidad = extrapolado`, aunque su valor sea 0.

### 7. Año 2000 + ▶ (Media)

- **Qué pasa:** enero a octubre de 2000 ya aparecen deshabilitados, pero el ▶ pasa por ellos y muestra el aviso rojo
  "Sin datos" en cada uno.
- **Propuesta:** que el ▶ salte los meses sin dato.

### 8. El calendario tapa el panel de Capas (Media)

- **Qué pasa:** con la pantalla a 1440 × 900, el calendario abierto queda encima del panel de Capas y corta la
  leyenda de densidad.

### 9 a 14. Textos y detalles (Baja)

- **9.** Jerga técnica en pantalla: el aviso del CSV dice "Σ eq_foco = 603.21" (y no se borra después), la capa de
  densidad dice "(peso eq_foco)" y abajo a la derecha se ve un contador "218.4 ms".
- **10.** Plurales: "con 1 focos armonizados", "1 lugares ardieron".
- **11.** Los errores de validación de FastAPI salen en inglés: "Field required", "Input should be a valid number".
- **12.** Radio 0: el mensaje dice "entre 0 y 100.0 km" pero rechaza el 0. "mes inválida" debería ser "mes inválido".
  Una fecha con día (`2020-05-01`) o con espacios se acepta sin avisar que se usa el mes completo.
- **13.** Un área de Cusco donde nunca hubo fuego responde "Sin datos: no hay focos en bbox [-71.36, …]". Mejor:
  "No se detectaron focos en esta área entre 2000 y 2025", sin coordenadas crudas.
- **14.** Hay un botón sin texto, `title` ni `aria-label`.

## Lo que pasó las pruebas

- **Pruebas del equipo:** 153 pruebas de `pytest` (incluida la de la interfaz compilada), `ruff` y `eslint` sin
  errores; `npm run build` compila.
- **Coherencia de números** (`qa/coherencia.py`): 94 combinaciones al azar de departamento, rectángulos y puntos con
  rangos de fechas. Calendario = suma de sus meses = CSV (`X-Total-Eq-Foco` y suma de `eq_foco`) = mapa
  (`focos.geojson`). La anomalía de cada mes coincide con la celda del calendario. Todos los focos del CSV caen dentro
  del área y del rango.
- **Analíticas** (`qa/analiticas.py`): el ranking, la curva acumulada, las franjas de altitud y la recurrencia
  cuadran con el calendario.
- **Entradas raras** (`qa/limites.py`): inyección SQL, `NaN`, `inf`, rectángulos de área cero o invertidos,
  parámetros de 5 000 caracteres, rutas y métodos que no existen: todos se rechazan bien.
- **Descargas:** 6 descargas simultáneas del CSV completo (7,3 MB) responden bien. El CSV y el PNG del panel se
  descargan con buen nombre.
- **Créditos:** el crédito de NASA FIRMS aparece en la interfaz y en `/api/metadatos`.
- **Errores que ya están bien resueltos:** AOI vacío, rango invertido, otro departamento, área fuera de Cusco, área
  demasiado grande, fechas fuera de cobertura y demasiados focos para el mapa responden con mensajes claros en
  español, y nunca con ceros donde no hay datos.

## Pendiente

- Probar en un teléfono real (no solo en vista de celular), como pide `AVISO_EQUIPO.md`.
- Dibujar un área en la interfaz real: en mi entorno de prueba el mapa base no carga, así que ese flujo se verificó
  contra la API.
- Formulario de evaluación de usuario (25 ítems, alfa de Cronbach): pendiente de aplicar a participantes.

## Cómo repetir las pruebas

Los scripts están en [`qa/`](qa/). Necesitan la API corriendo en local (`firecal serve` o Docker) y Python con
`httpx` (y `playwright` para `ui_test.py`).

| Script | Qué prueba | Puerto que usa |
|---|---|---|
| `play_por_anio.py` | Área + ▶ en cada año de 2000 a 2025 (error 2) | 8001–8005, con límites activos |
| `play_controles.py` | ▶ desde julio y dos vueltas seguidas | 8006, con límites activos |
| `coherencia.py` | Números entre calendario, CSV, mapa y anomalías | 8100, con `rate_limit.enabled: false` |
| `analiticas.py` | Analíticas de "En simple" contra el calendario | 8100, sin límites |
| `limites.py` | Entradas raras y casos límite | 8100, sin límites |
| `ui_test.py` | Interfaz en Chrome sin pantalla, escritorio y celular | 8200, con límites activos |

Para cambiar el puerto, editar la constante al inicio de cada script.
