# Auditoría de FireCal Cusco (Q/A de lógica)

*Sábado 14-nov-2026 · Gabriel · rama `gabriel2` (= `main` en `f53ad18`, PR #8)*

**Resumen:** los datos y los cálculos están correctos (todas las pruebas pasan). Lo que hay que mejorar es
cómo la interfaz llama al API y cómo se ven los números. Hay **2 fallos altos** en la interfaz.

Evidencia en [`auditoria/`](auditoria/): capturas, scripts para repetir cada prueba y resultados.

## 1. Pruebas

| Prueba | Resultado |
|---|---|
| Suite del equipo (`pytest`), ruff, ESLint y build | ✅ 153 pruebas pasan |
| `harmonizacion/verificar_datos.py` y sumas de control de MAESTRO §6 | ✅ TODO OK |
| Q/A de lógica independiente (conteos, deduplicación, mediana, anomalía, CSV) | ✅ 57 de 57 |
| Q/A de analíticas (estacionalidad, ranking, curva, altitud, recurrencia) | ✅ 26 de 26 |
| URL publicada en Cloud Run (10 consultas de lectura) | ✅ Mismo total: 15.732 |
| Recorrido de la interfaz con navegador automático | ⚠️ 2 fallos altos, varios medios |

El Q/A de lógica recalcula todo con pandas directamente desde los dos CSV, sin usar código del backend, y lo
compara con el API. Casos de control: MAESTRO §12 (total 15.732; 2005 = 1.355; 2012 = 678; 2013 = 424;
2020 = 1.206; 2025 = 385), agosto de 2020 (anomalía +3,04), febrero de 2010 y agosto de 2001 (extrapolado,
rango 98,6–253,4). El foco VIIRS repetido del 25-ago-2022 queda como aviso, igual que en `verificar_datos.py`.

## 2. Funcionalidades

| Gravedad | Hallazgo | Evidencia |
|---|---|---|
| **Alta** | **"Reproducir" con un área dibujada termina en "Demasiadas solicitudes"** a los ~8 s. Cada mes dispara 2 consultas del área y el cupo de pesadas es de 5 seguidas; la interfaz no reintenta aunque el 429 trae `Retry-After`. | `capturas/09_reproducir_con_area.png` |
| **Alta** | **El panel muestra números de otro mes bajo la etiqueta del mes actual.** Mientras carga o tras un error conserva los datos anteriores: decía "Ago 2020" con 32 focos (valor de mayo); el real es 508. | `capturas/09_reproducir_con_area.png` |
| Media | La capa **"Límite"** apaga la densidad y los puntos (las capas son excluyentes). | `capturas/05_capa_limite.png` |
| Media | **En celular** no hay acceso a "En simple" ni a "Info", el calendario corta de octubre a diciembre y el panel tapa el mapa. | `capturas/10_movil.png`, `10b_movil_calendario.png` |
| Media | A 1440×900 el **calendario tapa Cusco** y parte del panel de capas; 2021–2025 quedan bajo el pliegue. | `capturas/01_carga.png` |
| Baja | El botón "Focos" del menú lateral no hace nada; la leyenda de puntos muestra un degradado de densidad; el título de "En simple" para un área muestra las coordenadas crudas; la tarjeta del área tapa parte de "En simple". | `capturas/08_en_simple_area.png` |

Funciones que el API ya tiene y la interfaz no usa: rangos de varios meses o años, punto + radio, detalle diario
del mes (`dias` en `/api/anomalias`) y el mapa de recurrencia (`/api/analitica/recurrencia`).

## 3. Flujo de datos

- La cadena está verificada de punta a punta: CSV de Antonio → validación con SHA-256 → Parquet → API →
  pantalla → descarga CSV. El total de la descarga coincide con el de la pantalla en todos los casos probados.
- La serie es estática hasta 2025-12; la ingesta casi en tiempo real (`firecal/etl/nrt_fetch.py`) es solo un
  esqueleto.
- El panel muestra dos cifras de "focos" (p. ej. 2.984 en el mapa y 508 armonizados) sin explicar la diferencia.
- GitHub Pages (`pages.yml`) sigue publicando el `dist/` viejo de la raíz, no FireCal.

## 4. Interfaz del API

**Bien:** errores claros en español, códigos 422/404 coherentes, consultas parametrizadas (probé inyección en
`departamento` y `bbox`), CORS cerrado a orígenes externos y límites 429/503 funcionando.

| Hallazgo | Detalle |
|---|---|
| **Sin compresión ni caché** (también en producción) | `focos.geojson` de un año pesa 1,65 MB y tarda ~1 s; ninguna respuesta lleva `gzip`, `Cache-Control` ni `ETag`. Los datos son históricos: se pueden cachear. |
| **"En simple" calcula de más** | 5 llamadas en paralelo; `/api/resumen` recalcula las mismas 4 analíticas (~1,7 s). Con 6 consultas de área simultáneas, 4 dieron 503. |
| **Cupo de pesadas incoherente** | Solo cuenta `calendario` y `anomalias` con área ([`api/limits.py:37`](plataforma_local/backend/api/limits.py#L37)); `focos.geojson` y las analíticas con área no, aunque `ACTIVIDADES_JULIO.md` dice que "cualquier llamada con bbox" es pesada. |
| **Sin esquemas de respuesta** | Ninguna de las 15 rutas declara su esquema en `/docs`; el frontend depende de nombres de campo no documentados en OpenAPI. |
| **Validación laxa** | Acepta `2020-01-15` y `2020-8` sin avisar; un parámetro mal escrito (`departmento`) responde "AOI vacío". |
| Latencia (servidor local) | calendario 26–46 ms · metadatos 3 ms · anomalías ~390 ms · focos.geojson ~0,9–1 s · resumen ~1,7 s. |

Detalle completo: [`auditoria/resultados/auditoria_api.txt`](auditoria/resultados/auditoria_api.txt).

## 5. Simplificación de módulos

- **El 66 % del backend no lo usa la app publicada:** 46 de 57 módulos (4.404 de 6.674 líneas) son del backend
  sintético apagado (`/api/v1`): `harmonization`, `synth`, `etl`, `climatology`, `pipeline`, `api/services`,
  `api/db`… También 83 de las 128 funciones de prueba.
- **Dependencias que solo usa ese código:** `lightgbm`, `scikit-learn`, `matplotlib`, `h3`. La imagen Docker pesa
  1,33 GB.
- [`api/routers/plan.py`](plataforma_local/backend/api/routers/plan.py) repite los 5 parámetros del área en 11 rutas:
  cabe en una sola dependencia.
- [`FireMapApp.jsx`](plataforma_local/frontend/src/FireMapApp.jsx) es un único componente de 563 líneas; conviene
  separar mapa, calendario, panel y línea de tiempo.
- Restos en la raíz: `hola.txt`, el `dist/` viejo y `.openai/`.

**Propuesta:** mover el backend sintético a una rama de archivo (`archivo/backend-sintetico`) y dejar en
`plataforma_local/backend` solo `firecal/plan`, `settings`, `regions`, `concurrency`, `api/main`, `api/limits` y
`api/routers/plan`.

## 6. Paleta y legibilidad (design thinking)

- **Tres sistemas de color mezclados:** barra oscura, paneles blancos y un calendario con colores pensados para
  tema oscuro. 135 colores distintos y solo 5 variables CSS.
- **El cero es la celda más oscura del calendario:** lo que más resalta es "sin fuego".
- **Modo Anomalía casi ilegible:** texto blanco sobre celdas pálidas, contraste 1,2–2,5 (mínimo WCAG: 4,5).
  Con texto oscuro sube a 6–12. Ver `capturas/03_modo_anomalia.png`.
- **Contraste bajo sobre blanco:** leyenda 2,3 · años 2,8 · créditos 3,2 · aviso de CSV 1,3 · celdas
  extrapoladas 2,2–3,0.
- **Letra muy pequeña:** 412 de 433 textos visibles miden menos de 11 px (mínimo 6 px).
- **Daltonismo:** calendario (YlOrRd), anomalía (rojo/azul) y gráficos se distinguen bien. Las insignias
  rojo/ámbar/verde no (deuteranopía/protanopía).
- **Teclado:** ninguna de las 312 celdas del calendario es alcanzable; no hay estilos de foco visibles.
- **Aciertos:** cortes por cuantiles, rayado para "sin dato", borde punteado para "incierta", leyenda de calidad.

## 7. Mejoras sugeridas

**Rápidas (pocas horas):**
1. Reintentar tras un 429 usando `Retry-After`, y pausar "Reproducir" cuando hay un área dibujada.
2. Vaciar el panel mientras carga, para no mostrar números de otro mes.
3. Modo Anomalía con texto oscuro; cero en gris claro; subir el contraste de leyenda, notas y créditos.
4. Activar `GZipMiddleware` y `Cache-Control` en el API.
5. Convertir "Límite" en un interruptor independiente de las capas.
6. Mostrar primero los años recientes en el calendario.
7. Dar acceso a "En simple" e "Info" en celular.

**Siguientes:**
1. Acoplar el calendario abajo o al costado, sin tapar el mapa.
2. Selector de rango de fechas (el API ya lo admite).
3. Unificar la paleta en variables CSS (tokens) y fijar un mínimo de 12 px.
4. Servir "En simple" con una sola llamada.
5. Retirar el backend sintético a una rama de archivo.

## 8. Nichos de innovación para el analista-operador ambiental/forestal

1. **Informe de temporada en un clic:** PDF por área con las frases, los gráficos y el mapa. Las piezas ya existen.
2. **Áreas propias:** subir un polígono (área protegida, concesión, comunidad, distrito), guardarlo y comparar
   áreas entre sí.
3. **Mapa de recurrencia:** el API ya devuelve 12.830 lugares y los 1.476 que arden 4 o más años de 13. Sirve
   para priorizar patrullaje y cortafuegos.
4. **Seguimiento de la temporada en curso:** ingerir datos recientes de FIRMS, marcados como provisionales, sobre
   la curva del año frente a lo normal (ya hecha). Rotularlo "seguimiento", no "alerta" (regla del equipo).
5. **Cruce con capas de gestión:** áreas protegidas, cobertura de bosque, provincias y pisos de altitud (el 50 %
   del fuego ocurre bajo 1.500 m).
6. **Vista compartible y citable:** URL que conserve área, mes y capa; descargas con versión de datos y fecha.
7. **Contexto de sequía:** el análisis sequía–fuego de `harmonizacion/sequia_fuego/` como capa exploratoria.

## 9. Cómo repetir las pruebas

Con el servidor corriendo (`firecal plan-events` y `firecal serve` en `plataforma_local/backend`):

```powershell
$py = "plataforma_local\backend\.venv\Scripts\python"
& $py -I -X utf8 auditoria\scripts\qa_logica.py data\harmonized            # Q/A de lógica
& $py -I -X utf8 auditoria\scripts\qa_analitica.py data\harmonized         # Q/A de analíticas
& $py -I -X utf8 auditoria\scripts\auditoria_api.py                        # API (~8 min por las pausas)
& $py -I -X utf8 auditoria\scripts\auditoria_estatica.py plataforma_local  # paleta, tipografía, módulos
& $py -I -X utf8 auditoria\scripts\ui_recorrido.py "C:\Program Files\Google\Chrome\Application\chrome.exe" salida_ui
```

Los scripts usan `http://127.0.0.1:8000` por defecto; se puede pasar otra URL como último argumento.
