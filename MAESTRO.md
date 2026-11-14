# MAESTRO · Armonización de focos FIRMS (MODIS + VIIRS) — Reto NASA

> Versión 1.2 · 2026-11-14 · Región validada: **Cusco (Perú)** · Datos: 2000-11-04 a 2025-12-31

**Para el asistente que mantiene este repo:** lee este archivo completo antes de cualquier tarea. Es la fuente de verdad del contexto. Si el repo ya tiene un `CLAUDE.md`, **no lo reemplaces**: añade una línea que diga "Antes de tocar datos o armonización, lee MAESTRO.md". Al terminar cada tarea, añade una línea al registro de cambios (§11).

## 0. Arranque de sesión (pega esto al empezar un chat nuevo)
```
Lee MAESTRO.md completo y los contratos de harmonizacion/docs/. No cambies nada todavía.
Respóndeme en menos de 12 líneas: (1) qué producto de datos hay y qué región y fechas cubre,
(2) las reglas de oro que más fácil se rompen, (3) filas y sumas de control de los dos CSV,
(4) los límites conocidos que afectan a lo que voy a pedir, (5) el vocabulario y las decisiones del equipo (§12).
Después espera mi orden.
```

## 1. Reglas de oro (no negociables)
1. **El conteo armonizado es la suma de `eq_hotspots` (celda-día) o `eq_foco` (foco).** Nunca `n_modis + n_viirs` ni contar filas: son sensores distintos con ~×4 de diferencia.
2. **Unidad definida en la interfaz y en la descarga:** "celdas-día con fuego (equivalentes MODIS)". Nombre en la interfaz: **"Focos armonizados"** (inglés: *Harmonized hotspots*), con la definición completa a un clic (leyenda o *tooltip*). No llamar "incendio", "evento", "hectáreas" ni "área quemada" a esta unidad. Usa siempre el vocabulario de §12.
3. **No calcular ni mostrar área quemada.** Está fuera del reto y un foco es un píxel con anomalía térmica, no una superficie.
4. **FRP no está armonizado** (VIIRS/MODIS ≈ ×1.2–2.0 según ambiente). No sumarlo entre sensores; si se muestra, por sensor y con aviso.
5. **`calidad = extrapolado`** (2000-11 a 2002-07-03, solo Terra) se dibuja atenuado y con aviso: error mensual ~41–45 %. Un solo foco ahí pesa hasta 7.7.
6. **Cobertura armonizada y validada: solo Cusco.** Un departamento sin factores validados no puede mostrarse como armonizado: si la app lo incluye, se rotula "sin armonizar" (conteos crudos separados por sensor, sin sumarlos) o muestra "sin datos". Nunca ceros que parezcan "sin fuego".
7. **Fechas en hora local de Perú (UTC−5).** `hora_utc` y `confianza` se leen como texto (`hora_utc` tiene ceros a la izquierda; `confianza` mezcla números y `n`/`h`).
8. **Los factores `k` y `kT` son de Cusco.** No reutilizarlos en otra región sin recalibrar y validar (§8, P7).
9. **No presentar la relación sequía-fuego como hallazgo.** Fue un piloto exploratorio y débil (ver `harmonizacion/sequia_fuego/PROTOCOLO.md`). Solo capa descriptiva.
10. **No inventar datos ni rellenar huecos.** Si un cálculo necesita datos que no están, dilo y detente.
11. **No subir** `data/raw/`, CSV crudos de FIRMS, credenciales (Earth Engine, MAP_KEY de FIRMS) ni claves.
12. **Cada cambio de datos o del código de armonización:** correr `verificar_datos.py`, comparar con las sumas de control (§6) y registrarlo en §11.

## 2. El reto (texto esencial, del usuario)
Desarrollar un **calendario armonizado de actividad de quema** basado en focos activos, en una aplicación web, combinando la serie histórica de MODIS con la continuidad y el mayor detalle de VIIRS, para obtener una serie consistente.
- **Parte 1 (armonización):** que, al terminar, "el sensor de origen ya no importe".
- **Parte 2 (app web):** el usuario elige región y rango de fechas, descarga analíticas y visualizaciones, y ve un calendario de conteos de focos "desde principios de los 2000 hasta hoy" con rampas de color. Se exige un **CSV descargable de los focos** de la búsqueda.
- Productos: focos activos / FRP de NASA FIRMS. Dominio elegido: según el registro de incendios más grandes; validado en Cusco.

## 3. Estado actual (v1, congelado)
| Qué | Valor |
|---|---|
| Región / periodo | Cusco, 2000-11-04 a 2025-12-31 (último día con focos: 2025-12-28) |
| Unidad de la serie | celda de 0.01° (~1.1 km) × día local; presencia de fuego |
| Sensores | MODIS Terra y Aqua (2000-) y VIIRS S-NPP (2012-); NOAA-20 no incluido |
| Filtros | `type = 0` (vegetación); MODIS `confidence ≥ 30`; VIIRS `n` o `h` |
| Datos de origen | archivos anuales por país de FIRMS, hasta 2025-12-31 |
| Datos de 2026 | **no incluidos** y no verificada su disponibilidad |

**Método en 7 líneas**
1. Fecha local = UTC − 5; celda = 0.01°.
2. Se cuenta *presencia por celda-día*, no detecciones.
3. Aun así VIIRS/MODIS en celda-día es ×3.0 (≥2500 m) a ×4.1 (<1500 m), no ×1: es **sensibilidad**, no solo resolución; por eso se calibra.
4. `k` (VIIRS→MODIS) por estrato de altitud, 2013-2019: **0.330** (≥2500 m), **0.247** (<2500 m). Validación 2020-24: VIIRS×k / MODIS real = 0.90–1.09 por año. En 2013-19 el error anual llega a ±20 %.
5. 2025 sale ×1.50: MODIS cae más que VIIRS (compatible con deriva orbital; no verificado). La serie armonizada no lo sufre porque desde 2013 usa VIIRS.
6. Terra ve ~5× menos que Aqua (10:30 vs 13:30). `kT` (Terra→Terra+Aqua), 2003-2012: **2.62** / **7.74**.
7. Serie: antes de 2002-07-04 `Terra*kT`; 2002-07-04 a 2012 `MODIS` (peso 1.0); desde 2013 `VIIRS*k`.

## 4. Mapa de archivos (propuesto; adáptalo a la estructura real del repo)
```
MAESTRO.md                                   este archivo
data/harmonized/harmonizado_cusco_celda_dia.csv   36,260 filas, 2.7 MB   -> calendario
data/harmonized/focos_cusco_individuales.csv      58,779 filas, 7.4 MB   -> descarga de focos
harmonizacion/
  firms_csv.py            genera el CSV de celda-día (calibra k y kT)
  focos_individuales.py   genera el CSV de focos con peso por foco
  firms_armoniza.py       SOLO diagnóstico (razones, deriva, error); no escribe CSV
  cusco_referencia.py     límite de Cusco (FAO GAUL) y altitud SRTM (Earth Engine)
  verificar_datos.py      validación de integridad de ambos CSV (exit 1 si falla)
  cusco_ref/              limite.json, elev.npy, meta.json
  docs/                   CONTRATO.md (celda-día), CONTRATO_focos.md (focos)
  sequia_fuego/           análisis exploratorio + PROTOCOLO.md + figura
  ci/verificar-datos.yml.sugerido
```

## 5. Contratos de datos (resumen; el detalle está en `harmonizacion/docs/`)
**Celda-día:** `fecha_local, cell_lat, cell_lon, alt_m, n_modis, n_viirs, frp_modis, frp_viirs, eq_hotspots, fuente_serie, calidad`.
**Focos:** `fecha_local, fecha_utc, hora_utc, latitude, longitude, cell_lat, cell_lon, alt_m, sensor, satelite, frp, brillo_k, confianza, diurno_nocturno, fuente_serie, calidad, en_serie, eq_foco`.

| `fuente_serie` | Cuándo | `calidad` | Peso |
|---|---|---|---|
| `Terra*kT` | < 2002-07-04 | `extrapolado` | `kT` repartido entre los focos Terra de la celda-día |
| `MODIS` | 2002-07-04 a 2012-12-31 | `referencia` | 1.0 repartido entre los focos MODIS |
| `VIIRS*k` | ≥ 2013-01-01 | `calibrado` | `k` repartido entre los focos VIIRS |
| `fuera_de_serie` (solo focos) | focos conservados sin peso | vacío | 0 (`en_serie` = 0) |

Sumar `eq_foco` en cualquier región y fechas reproduce `eq_hotspots` del otro archivo (diferencia máxima por celda-día 0.0006, por redondeo).

## 6. Sumas de control (si no coinciden, algo cambió: investiga antes de seguir)
| Archivo | Filas | Suma de pesos | SHA-256 |
|---|---|---|---|
| `harmonizado_cusco_celda_dia.csv` | 36,260 | `eq_hotspots` = 15,732.03 | `6F33CAEC736AF9718E559DA1143B93CF0886093E0C0DFAB9B5667BAA42A257CC` |
| `focos_cusco_individuales.csv` | 58,779 (MODIS 15,693; VIIRS 43,086; `en_serie` 47,464) | `eq_foco` = 15,732.01 | `C8D15200BF17DA15807F48972C8A4DCA76D274DE1B872EFF82DE59444DE7F36B` |

Un cambio **intencional** de datos cambia estos valores: actualízalos aquí y anótalo en §11.
Comando de verificación (desde la raíz del repo):
`python -I harmonizacion/verificar_datos.py data/harmonized/harmonizado_cusco_celda_dia.csv data/harmonized/focos_cusco_individuales.csv`

## 7. Defectos conocidos y límites
**Corregidos en v1 (auditoría):** `firms_armoniza.py` sobrescribía el CSV con una versión obsoleta (factor por mes, sin `calidad`) → ahora solo diagnostica. El proyecto de Earth Engine estaba fijo en el código → variable `EE_PROJECT`. Si el polígono de Cusco no se leía, los scripts producían salida vacía en silencio → ahora abortan con error. Tras la revisión del equipo (v1.1): `requirements.txt` omitía matplotlib en los scripts de generación (lo importan para decidir qué puntos caen dentro de Cusco), y los scripts no encontraban los nombres que entrega FIRMS (`viirs-snpp_AAAA_Peru.csv`); ahora los aceptan.
**Abiertos:**
- El límite de Cusco es FAO GAUL simplificado a ~500 m: focos junto al borde pueden asignarse mal. Se ignoran huecos interiores y solo se leen polígonos (un `MultiPolygon` se ignoraría).
- `Aqua` se fija en 2002-07-04, pero su primer foco en Cusco es de 2002-07-19: ~15 días de julio de 2002 pesan 1.0 en lugar de `kT` (efecto pequeño, temporada baja).
- Celdas sin altitud SRTM se tratan como estrato "bajo".
- Un par de focos VIIRS (2022-08-25 18:06 UTC) repite posición y hora con FRP distinto: artefacto del propio FIRMS; se conserva.
- Los archivos terminan el 2025-12-31 UTC: el último día local puede estar incompleto.
- `kT` es impreciso (error mensual 41–45 %; anual de −32 % a +45 % en el estrato bajo).
- Solo S-NPP; sin NOAA-20/21 (no estaban en los archivos públicos por país).
- Los scripts se probaron solo en Windows con Python 3.11.9 (numpy 2.4.4, pandas 2.3.3, scipy 1.17.1, matplotlib 3.10.8, earthengine-api 1.7.22). No probados en Linux ni en CI, salvo `verificar_datos.py`, que solo necesita numpy y pandas.
- `sequia_fuego/` es exploratorio: decenas de pruebas sobre los mismos datos, SPI con base 1981-2010 mal calibrado para 2003-25 (quiebre de CHIRPS en 1999-2000). **No citar ningún p-valor de ahí como resultado.**

## 8. Biblioteca de órdenes (copiar, completar lo que está entre `[ ]` y pegar)
Formato de cada orden: **Contexto → Tarea → Entradas → Criterios de aceptación → No hacer.**

### P1 · Cargar los datos en la app
- **Contexto:** lee §1, §5 y el contrato de celda-día.
- **Tarea:** haz llegar a la interfaz `harmonizado_cusco_celda_dia.csv` (calendario) y `focos_cusco_individuales.csv` (descarga y detalle) **a través del backend** (decisión del equipo, §12): el backend carga los dos CSV y los sirve filtrados por región y fechas, con las mismas columnas del contrato y los mismos totales. La app no lee CSV estáticos. Antes de dar la tarea por terminada, pasa los casos de prueba de §12.
- **Entradas:** los dos CSV. Lee `hora_utc` y `confianza` como texto.
- **Criterios:** la suma de `eq_hotspots` cargada es 15,732.03 y el recuento de filas es 36,260; la pantalla no se congela en móvil.
- **No hacer:** convertir a enteros los pesos; descartar filas `extrapolado`; ocultar el aviso de cobertura.

### P2 · Calendario con rampa de color
- **Contexto:** reglas 1, 2, 5 y 6.
- **Tarea:** calendario diario (una celda por día, agrupado por año y mes) con el valor = Σ `eq_hotspots` de la región y fechas elegidas.
- **Color:** rampa secuencial YlOrRd de 6 clases (apta para daltonismo; inferno o viridis si el tema es oscuro). Cortes = cuantiles 50/75/90/99 de los días con fuego **de la selección actual**, redondeados, con leyenda que los muestra. Referencia para Cusco entero: 0 / 0–2 / 2–5 / 5–11 / 11–34 / >34 (mediana 2.0, p90 11, p99 34, máximo 62 por día).
- **Cero y sin dato:** días con 0 en gris claro neutro; antes de 2000-11-04 o fuera de la cobertura, gris distinto con rayado. Años `extrapolado`: rayado o menor opacidad, no otro color.
- **Criterios:** al cambiar la región se recalculan los cortes y la leyenda; el calendario se ve continuo en 2012–2013; el 2025 más bajo tiene una nota explicativa.
- **No hacer:** cortes lineales (casi todo quedaría en el color más claro); usar color para distinguir sensores.

### P3 · Selección de región y fechas, y descarga de focos
- **Tarea:** el usuario dibuja un rectángulo o elige el departamento y un rango de fechas. Filtra celda-día por `cell_lat/cell_lon` y focos por `latitude/longitude`. Botón "Descargar CSV de focos" con las **mismas 18 columnas** del contrato.
- **Criterios:** el nombre del archivo incluye región y fechas; el total mostrado en pantalla es Σ `eq_foco` de las filas descargadas; fuera de Cusco aparece "sin datos".
- **No hacer:** cambiar nombres u orden de columnas; omitir `en_serie`/`eq_foco`.

### P4 · Analíticas y visualizaciones descargables
- **Tarea:** (a) serie anual apilada por `fuente_serie`, (b) perfil estacional por mes, (c) barras por banda de altitud (<1500, 1500–2500, 2500–3500, >3500 m). Cada gráfico se descarga como PNG y sus datos como CSV.
- **Criterios:** ejes con unidades ("celdas-día eq. MODIS"); años extrapolados marcados; nota sobre 2025.
- **No hacer:** gráficos de FRP combinado, de hectáreas o de "incendios".

### P5 · Verificación antes de cada commit
- **Tarea:** ejecuta el comando de §6. Si falla, no hagas commit: explica qué falló. Si pasa, compara filas y sumas con §6.
- **Criterios:** salida `TODO OK` y código 0; cualquier diferencia queda explicada.
- **No hacer:** relajar una comprobación para que pase sin entender por qué falló.

### P6 · Actualizar con datos nuevos (por ejemplo 2026)
- **Contexto:** los archivos por país de FIRMS llegan hasta 2025-12-31; la disponibilidad de 2026 **no está verificada**. Puede requerir la API de FIRMS con una MAP_KEY del usuario (pídela; no la guardes en el repo).
- **Tarea:** descargar los focos nuevos a `firms_raw/` (no versionado), regenerar con `firms_csv.py` y `focos_individuales.py`, y verificar. Nombres aceptados: `modis_AAAA*.csv` y `snpp_AAAA*.csv` o `viirs-snpp_AAAA*.csv` (el nombre que da FIRMS, p. ej. `viirs-snpp_2023_Peru.csv`); un archivo por sensor y año, y si hay dos del mismo año los scripts abortan.
- **Criterios:** los factores `k` no se recalibran con los años nuevos; se comprueba que VIIRS×k / MODIS real de los años nuevos queda en 0.8–1.2 y se informa si no (2025 dio 1.5); `verificar_datos.py` en verde; sumas de control de §6 actualizadas.
- **No hacer:** recalibrar `k` con datos de validación; borrar el historial de cambios.

### P7 · Ampliar a otra región o a todo Perú
- **Contexto:** Cusco es el 4.5 % de los focos de Perú (58,779 de 1,295,299 filtrados). Estimación de tamaño para Perú: focos ≈ 163 MB y celda-día ≈ 62 MB (~833 mil filas), medida por filas × bytes/fila de Cusco.
- **Límites de GitHub** (según su documentación; verifícalos): archivo > 50 MB genera aviso y > 100 MB se bloquea. El hosting del sitio (hoy Vercel, según el equipo) tiene sus propios límites por archivo y por despliegue: verifícalos. Un solo CSV de focos de Perú **no cabe**.
- **Tarea:** (1) obtener el límite de la región (FAO GAUL) y la altitud SRTM **por teselas** (la lectura de `sampleRectangle` está limitada a 262,144 píxeles por llamada; Perú ≈ 2.3 M de píxeles a 0.01°); (2) recalibrar `k` y `kT` **por región/estrato**, y para todo Perú probablemente por mes: con un factor fijo el error mensual fue 31–33 % en Perú frente a 10–12 % en Cusco, y 14 % con factor por mes; (3) validar con 2020–2025 reservado; (4) dividir la salida por departamento y/o año (cada archivo < 50 MB).
- **Criterios:** `verificar_datos.py` adaptado y en verde por región; error mensual de validación reportado por región.
- **No hacer:** aplicar `k` de Cusco a otra región; subir un CSV único de Perú.

### P8 · Capa descriptiva de sequía (opcional)
- **Tarea:** mostrar dónde y cuándo hubo sequía junto al fuego, como mapa de contexto, sin afirmar causalidad ni correlación.
- **Entradas:** `harmonizacion/sequia_fuego/` (`PROTOCOLO.md`, figura). Si hay que recalcular, el SPI debe usar base 2000-2026 (CHIRPS tiene un quiebre en 1999-2000).
- **No hacer:** copiar resultados estadísticos de las pruebas exploratorias.

### P9 · Texto del método para la entrega del reto
- **Tarea:** redacta ≤ 1 página (español e inglés) del método y sus límites, con los números de §3 y §7. Incluir la sección "Qué no hace": área quemada, FRP armonizado, otras regiones.
- **Criterios:** cada cifra aparece en este MAESTRO; los límites quedan explícitos; no promete más de lo validado.

### P10 · Revisión senior periódica
- **Tarea:** revisa los scripts y los CSV buscando: rutas absolutas, dependencias no declaradas, fallos silenciosos (salidas vacías), cambios de formato de FIRMS, columnas que cambian de tipo, y diferencias contra §6. Entrega una lista priorizada (grave / medio / menor) con evidencia, **sin corregir** hasta que se apruebe.

## 9. Plantilla para órdenes nuevas
```
Contexto: lee MAESTRO.md (§1 reglas, §5 contratos, §7 límites).
Tarea: [qué se quiere, en una frase].
Entradas: [archivos exactos y rutas].
Criterios de aceptación: [qué debe cumplirse y cómo se comprueba].
No hacer: [límites de alcance].
Al terminar: corre verificar_datos.py si tocaste datos o armonización, y añade una línea al registro de cambios.
```

## 10. Convenciones de trabajo
- Commits pequeños, un propósito cada uno. Prefijos: `datos:`, `app:`, `docs:`, `scripts:`. Sin `push --force`.
- Ningún dato crudo ni credencial en el repo (§1.11). El archivo `gitignore.sugerido` del paquete lista lo que conviene ignorar: **combínalo con el `.gitignore` existente**, no lo sobrescribas.
- Si el workflow de verificación (`ci/verificar-datos.yml.sugerido`) se va a activar, pide confirmación al usuario antes de añadirlo a `.github/workflows/`.
- Las rutas de §4 son una propuesta: si la app ya tiene otra estructura, adáptala y anota el cambio en §4.
- Contexto del repo según el equipo (no verificado aquí): `HowlO/NASA_CLAUDE_TEAM`; el sitio se publica ahora con Vercel (el workflow de Pages falla); `data/raw/` está excluido de git; ya existen apps de Julio y Dante, con un backend FastAPI de Julio y cinco departamentos en pantalla. Este MAESTRO debe integrarse con ese trabajo, no reemplazarlo (§12).

## 11. Registro de cambios
| Fecha | Cambio | Quién |
|---|---|---|
| 2026-11-14 | v1: CSV de celda-día y de focos de Cusco, contratos, verificación, protocolo sequía-fuego, auditoría de scripts | sesión de ciencia de datos |
| 2026-11-14 | v1.1: `requirements.txt` con matplotlib en todos los scripts de generación; los scripts aceptan los nombres de archivo de FIRMS y abortan si hay dos del mismo año; reglas 2 y 6 y órdenes P1/P7 adaptadas al trabajo del equipo (Vercel, FastAPI, cinco departamentos); nueva §12 | sesión de ciencia de datos |
| 2026-11-14 | v1.2: decisiones del equipo cerradas (solo Cusco es real, backend FastAPI, sin estáticos); vocabulario único con "Focos armonizados" como unidad; casos de prueba del backend | sesión de ciencia de datos |
| | *(añade aquí una línea por cada tarea terminada)* | |

## 12. Decisiones del equipo y vocabulario (resueltas el 2026-11-14; no reabrir sin el usuario)
**Decisiones**
1. **Cobertura:** solo Cusco es real. Los otros cuatro departamentos de las apps son datos de prueba: deben rotularse "datos de prueba" o retirarse, y nunca mezclarse en totales ni comparaciones con Cusco.
2. **Unidad:** se adopta el vocabulario de abajo. La palabra "evento" deja de usarse para conteos.
3. **Arquitectura:** backend (FastAPI). No se usan archivos estáticos. Las pruebas se hacen con los dos CSV reales de este paquete.

**Vocabulario único (úsalo en código, interfaz, API y documentos)**
| Término | Significado | Campo | ¿Comparable entre sensores? |
|---|---|---|---|
| **Foco** (*hotspot*) | Una detección de un satélite: una fila del CSV de focos | fila; `n_modis`, `n_viirs` | No (VIIRS detecta ~×4–5 más) |
| **Celda-día activa** | Celda de ~1 km con al menos un foco en un día local | fila del CSV de celda-día | No directamente |
| **Foco armonizado** (*harmonized hotspot*) | Celda-día activa expresada en la escala de MODIS. **Es la unidad del calendario y de todos los totales** | `eq_hotspots`, `eq_foco` | **Sí** |
| **Evento** | Reservado para una agrupación de celdas-día vecinas en espacio y tiempo. **No está calculado en esta versión**: no usar la palabra | — | — |

- Texto de la leyenda: "Focos armonizados: celdas de ~1 km con fuego por día, en escala equivalente a MODIS. Combina MODIS (2000–2012) y VIIRS (2013 en adelante)."
- Los valores son fraccionarios (un foco armonizado de VIIRS vale 0.330 o 0.247). En pantalla se pueden redondear a entero; en la descarga y en la API van sin redondear.
- En la API los nombres de campo no cambian (`eq_hotspots`, `eq_foco`); "Focos armonizados" es solo la etiqueta visible.

**Casos de prueba del backend (Cusco entero, Σ `eq_hotspots`; tolerancia ±1)**
| Consulta | Resultado esperado |
|---|---|
| Todo el periodo | 15,732 (36,260 celdas-día; 58,779 focos en la descarga) |
| Año 2005 | 1,355 |
| Año 2012 (último solo MODIS) | 678 |
| Año 2013 (primero con VIIRS) | 424 |
| Año 2020 | 1,206 |
| Año 2025 | 385 |
| Antes de 2000-11-04, o región fuera de Cusco | "sin datos" (no cero) |
| Σ `eq_foco` de la descarga de cualquier consulta | igual al total mostrado en pantalla |

### Preguntas originales (ya resueltas arriba; solo como referencia)
1. **Cobertura.** Las apps existentes muestran cinco departamentos; los datos armonizados validados son solo de Cusco. ¿Qué se muestra en los demás? Mientras no haya factores validados: "sin armonizar" (conteos crudos por sensor, sin sumar) o "sin datos" (§1.6).
2. **Nombre de la unidad.** El equipo usa "eventos". Una celda-día no es un evento. Definir qué es un "evento" (¿una agrupación de focos?) y no mezclarlo con la unidad armonizada, o acordar un nombre corto (§1.2).
3. **Arquitectura.** ¿Archivos estáticos en el navegador (los CSV de Cusco pesan 2.7 + 7.4 MB) o el backend FastAPI? El contrato de datos es el mismo en ambos casos; con backend, los totales deben coincidir con §6.
4. **Fuente de los otros departamentos y de `data/raw/`.** Qué datos usan hoy para los demás departamentos (p. ej. FIRMS crudo de 2023) y cómo se relacionan con la serie armonizada.
