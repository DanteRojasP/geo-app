# Protocolo de comparación sequía-fuego (piloto Cusco, 2003-2025)

**Estado:** todo lo hecho en Cusco es **exploratorio**. Esos datos ya se vieron en decenas de pruebas, así que no pueden confirmar nada. Este protocolo fija el análisis antes de ejecutarlo en datos nuevos (otras regiones o años reservados).

## 1. Pregunta y hipótesis (fijadas antes de mirar)
- **Primaria (H1, unilateral):** una temporada de lluvias previa más seca (SPI-6 de junio más bajo) se asocia con más fuego en la temporada seca siguiente (celda-días eq. de jul-oct), a nivel regional-anual.
- **Secundarias:** (H2) efecto del mismo mes (SPI-3/6 y fuego mensual desestacionalizado, jul-oct); (H3) contraste espacial: píxeles relativamente más secos que su región en ese año tienen más fuego; (H4) combustible: NDVI de mar-abr mayor se asocia con más fuego.
- Tipo de sequía: **meteorológica** (SPI). No se afirma sequía agrícola ni hidrológica.

## 2. Datos y unidad comparable
- **Unidad:** píxel de 0.05° (~30 km²) × año, porque el SPI de CHIRPS tiene esa resolución.
- **Fuego:** `eq_hotspots` del CSV armonizado, excluyendo `calidad = extrapolado` (años 2003-2025). Se suman jul-oct.
- **Lluvia:** CHIRPS pentadal sumada a mensual. **Compuerta de calidad:** prueba de quiebre (Pettitt) y de tendencia (Mann-Kendall); el SPI se calibra en un periodo homogéneo (≥2000). Triangular con una segunda fuente (ERA5-Land o PISCO de SENAMHI).
- **NDVI:** MOD13A3 con `SummaryQA ≤ 1`.
- **Criterio de inclusión de píxeles:** debe depender de algo ajeno al fuego del periodo analizado (altitud, cobertura). Elegir píxeles por su frecuencia de fuego en el mismo periodo condiciona sobre el resultado.

## 3. Cuántos datos comparables hay (medido en Cusco)
| Concepto | Valor |
|---|---|
| Píxeles de 0.05° en Cusco | 2,409 |
| Píxeles con fuego en ≥8 de 23 años | 540 → 12,420 píxel-años |
| Varianza del SPI-6 jun: común del año / diferencia fija entre píxeles / contraste dentro del año | 37 % / 25 % / 39 % |
| Correlación del SPI crudo entre píxeles a 0-30 / 100-200 / 200-400 km | 0.94 / 0.52 / 0.36 |
| Escala de decorrelación del contraste espacial (L) | ≈ 103 km → ~1 parche independiente por año |
| Varianza del fuego común del año (tras quitar el nivel del píxel) | 7 % |
| **Muestra efectiva** | **≈ 23 años** (contraste entre años); ≈ 25 para el contraste espacial |

Los 12 mil píxel-años no son 12 mil observaciones: la sequía es regional. Muchas regiones no ayudan tanto como parece: con 6 regiones y correlación de 0.36 entre ellas (supuesto tomado del tramo 200-400 km, por verificar), la muestra efectiva sube de 23 a ≈ 49.

## 4. Potencia a priori (simulación con ruido real, 500 réplicas por celda)
Error tipo I verificado: 5-6 % con beta=0.
| beta (sd de fuego por sd de SPI) | rho anual implícito | E1 anual | E2 efectos fijos píxel+año | E3 efecto fijo píxel |
|---|---|---|---|---|
| 0.05 | −0.22 | 18 % | 37 % | 38 % |
| 0.10 | −0.34 | 51 % | 79 % | 80 % |
| 0.20 | −0.58 | 94 % | 100 % | 100 % |

- **Mínimo detectable con 80 % de potencia:** E1 ≈ |rho| 0.50; paneles ≈ beta 0.10. Con 6 regiones (n efectivo ≈ 49) el mínimo bajaría a |rho| ≈ 0.37.
- **Regla de decisión:** si el efecto plausible (~0.3) está por debajo del mínimo detectable, el análisis se declara exploratorio y se reporta como estimación con intervalo, no como prueba confirmatoria.

## 5. Estimadores y pruebas
- **E1 (primario):** regresión anual de la media regional de log1p(fuego) sobre el SPI-6 de junio medio. n = años. Una cola.
- **E2 / E3:** panel píxel × año con efectos fijos (E2: píxel y año; E3: píxel), errores agrupados por año (t con G−1 gl). Una cola.
- **Mensual (H2):** z(log1p fuego) por mes calendario ~ SPI estandarizado; agrupación por año; con y sin tendencia lineal (sensibilidad).
- **Multiplicidad:** una prueba primaria. Familia secundaria con Holm. Todo lo demás se etiqueta exploratorio.
- **Efecto:** siempre con intervalo de confianza; los resultados nulos se reportan.

## 6. Reglas contra la bifurcación de análisis
- Resultado, índice, ventana, rezago, sentido y criterio de inclusión se congelan antes de correr.
- No cambiar de estimador tras ver el p. En el piloto de Cusco el mismo contraste dio p=0.23-0.29 (rangos y terciles) y p=0.02 (E1, regresión lineal con píxeles escogidos por su fuego): esa diferencia es exactamente el riesgo que este punto busca evitar.

## 7. Resultados del piloto Cusco (exploratorios, no citar como hallazgo)
- E1 regional anual: beta −0.133, p=0.020 (una cola).
- E2 contraste espacial: beta +0.081, p=0.977 (signo contrario; no hay efecto local relativo).
- E3: beta −0.050, p=0.089.
- Mensual, mismo mes: efecto negativo, no sobrevive a Holm en la familia de 8 pruebas. Con un mes de rezago no hay efecto.
- El SPI con base 1981-2010 no está calibrado para 2003-2025 (quiebre de CHIRPS en 1999-2000: +20 % de lluvia altoandina).

## 8. Reproducir
1. `clima_cusco_ee.py`: baja CHIRPS y NDVI de Cusco (Earth Engine).
2. `sequia_fuego.py`: análisis exploratorio, mapas y figura.
3. `pruebas_hipotesis.py`: pruebas formales y Holm.
4. `n_efectivo_potencia.py`: muestra efectiva y simulación de potencia.
Entradas: `harmonizado_cusco_celda_dia.csv` y `cusco_ref/` del zip principal.
