# ¿Sirve el clima de Meteomatics para anticipar el fuego en Cusco?

*Generado con `exploratorio/meteomatics/preventivo.py` · Meteomatics 2003-2025 en 8 puntos y focos armonizados de
Cusco (MAESTRO v1.2) · 14-nov-2026 · **exploratorio** (MAESTRO §1.9 y `sequia_fuego/PROTOCOLO.md`)*

## Respuesta corta

**No, con estos datos.** El clima de Meteomatics **acompaña** al fuego del mismo periodo, pero no lo **anticipa**.

- Semana y mes siguientes: lo único que anticipa algo es el fuego reciente (persistencia). Con eso descontado, el
  clima aporta |rho| < 0,1.
- Temporada: ningún predictor que se conoce el 30 de junio acierta mejor que el azar si el próximo jul-oct será
  bajo, normal o alto.

No conviene publicar en la plataforma un "pronóstico" o "índice preventivo" basado en esta relación.

## Qué se probó

En todos los casos el clima es **anterior** al fuego y se compara con lo que ya se sabría sin clima. La
significancia se calcula barajando **años completos** (1000 permutaciones), porque las semanas de un mismo año no
son independientes. Luego se corrige con Benjamini-Hochberg por las 40 pruebas.

| Escala | Pregunta | Resultado |
|---|---|---|
| Semana siguiente (8 puntos, jun-nov, n = 4 600) | ¿El clima anómalo de esta semana anticipa el fuego de la próxima? | Persistencia rho = 0,17. Clima con la persistencia descontada: entre −0,09 y +0,03. Ninguno significativo (p ajustado ≥ 0,06). |
| Mes siguiente (8 puntos, objetivo jul-oct, n = 736) | ¿Un mes seco anticipa más fuego el mes siguiente? | Persistencia rho = 0,23. Clima con la persistencia descontada: entre −0,09 y +0,08. Ninguno significativo (p ajustado ≥ 0,51). |
| Temporada (Cusco, 22 años) | ¿El clima al 30 de junio anticipa el fuego de jul-oct? | El mejor es el índice de sequía de junio: rho = −0,24, p = 0,31. **Acierto de tercil dejando un año fuera: 18-32 %**, frente al 33 % del azar. |
| Temporada (8 puntos, 176-184 punto-años) | Lo mismo, con más datos espaciales | \|rho\| ≤ 0,20. Ninguno significativo. |

Ver `preventivo.csv` (coeficientes) y `preventivo.png` (figura).

Contexto de `INFORME.md`, con el clima del **mismo** periodo:
- El ciclo anual está muy marcado: el déficit de humedad del suelo sigue al fuego con rho = 0,99 en las 12
  medianas mensuales.
- Dentro de la temporada, un mes más lluvioso de lo normal tiene menos fuego ese mismo mes (rho = −0,40).

El clima explica **cuándo** hay fuego en el año y acompaña sus variaciones, pero no las adelanta.

## Por qué puede pasar esto

1. **El fuego en Cusco es sobre todo humano:** quemas agrícolas y de pastos con fechas de manejo. El clima pone las
   condiciones, pero la decisión de quemar no sigue a la anomalía de la semana anterior.
2. **Pocos años:** la muestra efectiva entre años es de unos 23. Con 80 % de potencia solo se detectarían efectos de
   |rho| ≥ 0,5 (`sequia_fuego/PROTOCOLO.md` §4). Un efecto real de 0,2-0,3 podría existir y no verse aquí.
3. **Representatividad:** 8 puntos de una sola hora (13:00) representan ~72 000 km². Los puntos se eligieron por
   cuánto fuego tienen, un sesgo que el protocolo advierte.
4. **Fuente desconocida:** no se sabe qué modelo o reanálisis usa Meteomatics para cada variable histórica.

Dato curioso: hay una persistencia **negativa** entre temporadas (rho = −0,40, p = 0,08). Tras una temporada muy
alta suele venir una más baja, quizá porque se quemó el combustible disponible. Depende mucho del par 2005-2006, así
que no es concluyente.

## Qué sí se puede ofrecer como "preventivo" en la plataforma

| Opción | Base | Recomendación |
|---|---|---|
| **A. Calendario de preparación** | Nuestros propios datos: en qué semana empieza, sube y termina la temporada en cada zona, y qué meses superan lo habitual (percentil 75). | **Sí.** Es sólido (ciclo anual rho ≈ 0,97-0,99), no necesita Meteomatics y no es un pronóstico: "históricamente, en esta zona el fuego empieza a subir a mediados de julio". |
| **B. Condiciones del mes en curso** | Meteomatics casi en tiempo real: lluvia del mes frente a lo normal (relación del mismo mes, rho ≈ −0,4). | **Más adelante.** Necesita la licencia comercial de Meteomatics (la de prueba no permite publicar) y un texto cuidadoso. No se pueden usar "riesgo" ni "alerta" (MAESTRO). |
| **C. Pronóstico de temporada o semana** | Clima previo. | **No.** No supera al azar en estos datos. |

Para confirmar o descartar el efecto de la sequía previa, el camino es el de `sequia_fuego/PROTOCOLO.md`:
- hipótesis fijada de antemano;
- SPI-6 de CHIRPS o PISCO;
- otras regiones (con unas 6 regiones, la muestra efectiva sube de 23 a unos 49).

## Límites

Es un análisis exploratorio sobre datos ya explorados en `INFORME.md`, así que no es un hallazgo confirmado. Los
datos de Meteomatics no se publican (licencia de prueba): solo los coeficientes y las figuras. No se habla de
incendios ni de área quemada, sino de focos de calor armonizados.
