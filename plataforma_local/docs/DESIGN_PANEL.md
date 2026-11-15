# Brief de diseño · panel "Entender" (antes "En palabras simples")

*Rama `ui/panel-historia` · pedido: `PROMPT_PANEL_NIKAL.md` · cifras reales de `/api/resumen` (Cusco, datos `cusco-v1.3`)*

## Usuario y momento de uso
Gestores de riesgo (gobierno regional y municipios), analistas de SERFOR/COER y brigadistas. Llegan desde el mapa con poco
tiempo y quieren tres respuestas antes de decidir **cuándo preparar la prevención y dónde mirar**: ¿este año es normal?,
¿cuándo empieza la temporada?, ¿dónde se concentra? Después vuelven al mapa (área, Ámbitos o informe técnico).

## Las 3 preguntas, en orden de lectura (con datos reales)
**Titular** (frase dinámica; los números resaltados son botones que llevan a su gráfico):
> En **2025**, Cusco registró **387 focos armonizados**, un **30 % menos** que un año típico (**555**). La temporada va
> de **julio a octubre** y el pico es **septiembre**.

1. **¿Este año es normal?** · *2025 terminó muy por debajo de lo habitual*. Subtítulo: "Focos armonizados acumulados en
   el año; la banda es donde cae 8 de cada 10 años (2003–2025)". Curva grande con etiquetas directas ("2025", "lo
   habitual"); si el año está incompleto, la curva termina en un marcador "hoy".
2. **¿Cuándo prevenir?** · *La temporada empieza en julio: junio es el mes para prepararse*. Subtítulo: "Focos
   armonizados por mes en un año típico (mediana 2003–2025)". Barras por mes con la ventana de prevención (junio)
   marcada y el pico anotado. **Ojo:** por mediana el pico es septiembre (194), pero agosto reúne más focos del año (32 %
   frente a 30 %): los títulos se calculan con los datos, no con frases fijas.
3. **¿Dónde se concentra?** · *La mitad de los focos ocurre por debajo de 1 500 m*. Subtítulo: "Parte de los focos
   armonizados por franja de altitud". Barras horizontales ordenadas + una línea: "1 488 lugares de ~1 km tuvieron
   focos en 4 o más años desde 2013" con el botón **Ver en el mapa** (Fase B).
- **Contexto** (pequeño): tira de 25 años con 2025 resaltado. Ejemplo: *2025 fue el 23.º de 25 años en focos*.

## Boceto (wireframe)
```
Escritorio (1440 px)                                         drawer 480 px, oscuro, sobre el mapa
┌──────┐                                    ┌─────────────────────────────────────────────┐ ┌────┐
│ 01 ◼ │   mapa visible e interactivo       │ Cusco · 2003–2025                    ⓘ   ✕  │ │ ES │
│ 02 ◼ │                                    │ En 2025, Cusco registró [387 focos], un     │ │ ◼  │
│ 03 ◼ │                                    │ [30 % menos] que un año típico ([555]). La  │ └────┘
│ 04 ◼ │                                    │ temporada va de [julio a octubre]…          │
└──────┘                                    │─────────────────────────────────────────────│
                                            │ 2025 terminó muy por debajo de lo habitual  │
                                            │ Focos acumulados en el año · banda 8 de 10   │
                                            │  ╭──────── lo habitual ─────────╮           │
                                            │  │░░░░░░░░░░░░░░░╱‾‾‾‾‾‾‾‾‾‾‾‾‾‾ │  2025     │
                                            │  ╰──────────────────────────────╯           │
                                            │ Fuente: NASA FIRMS · armonización Nikal  ⤓  │
                                            │ La temporada empieza en julio: prepararse…  │
                                            │  ▁ ▁ ▁ ▁ ▁ ▂ ▅ █ █ ▅ ▂ ▁   ← junio marcado  │
                                            │ La mitad de los focos, por debajo de 1 500 m│
                                            │  ███████████ <1 500 m … [Ver en el mapa]    │
                                            │ ▂▅▃▂▃▄▃▃▂… 2025 = 23.º de 25                 │
└──── cinta de temporada (sigue visible) ───┴─────────────────────────────────────────────┘

Móvil (390 px): hoja inferior que tapa la cinta mientras está abierta
┌─────────────────────────┐
│ mapa                    │
│▔▔▔▔▔▔▔▔ ━━━ ▔▔▔▔▔▔▔▔▔▔▔│  ← asa: arrastrar / tocar para cerrar
│ En 2025, Cusco … [387]  │
│ 2025 terminó muy por…   │
│ [curva]                 │
│ … (una columna, scroll) │
└─────────────────────────┘
```

## Criterio de éxito
Un gestor entiende **si el año es normal en menos de 5 segundos sin leer notas**: el titular y el primer título lo dicen
con números, y el primer gráfico lo confirma sin leyenda.

## Qué se elimina y por qué
- **Fila de 5 resúmenes**: repite palabra por palabra el texto bajo cada gráfico → queda solo el titular.
- **Rótulos naranjas en mayúsculas** y **preguntas como títulos** → títulos que afirman el hallazgo.
- **Notas "cómo leer"** siempre visibles → ícono ⓘ con la nota (y "describe lo que ya pasó; no es pronóstico").
- **Botones PNG/CSV en cada tarjeta** → un botón de ícono discreto en el pie (menú PNG / CSV).
- **Modal claro de 4 tarjetas iguales** → drawer oscuro de una columna, con un gráfico protagonista.
- **Paleta crema, terracota y verde azulado** → año actual `#FCA50A`, lo habitual gris claro punteado, banda gris
  translúcida; nada más.

## Decisiones que necesito confirmar
1. **"Lo habitual" en toda la app:** el pedido lo quiere gris punteado, y la cinta inferior hoy lo dibuja en puna (verde
   azulado). Propongo **unificar**: el año en `#FCA50A` y lo habitual en gris también en la cinta.
2. **Confiabilidad:** la API no devuelve `reliability`. Propongo usar la misma regla del backend (si ningún mes tiene
   mediana ≥ 0,5 focos) para mostrar "Pocos focos en esta zona: interpreta con cautela".
3. **"Cuándo prevenir":** la regla del equipo es que las analíticas describen, no pronostican. Propongo "la temporada
   *suele* empezar en julio: junio es el mes para prepararse", con la aclaración en el ⓘ.
4. **Tipografía:** Space Grotesk para el titular, las cifras y los títulos; el cuerpo en la fuente del sistema (no hay
   Inter instalada y no agrego dependencias).
5. **Fase A** = drawer, titular, 3 capítulos, contexto, ES/EN y tokens. **Fase B** = mes ↔ mapa, cifras del titular
   que llevan al gráfico y "Ver en el mapa" con las celdas recurrentes (la API ya las devuelve: `/api/analitica/recurrencia`).

## Estado (solo la parte de diseño del pedido)
Implementado en `PanelHistoria.jsx` + `panel-historia.css` (tokens): drawer oscuro / hoja inferior, titular con cifras
resaltadas, 3 capítulos con título-hallazgo y subtítulo, tira de contexto, etiquetas directas, ⓘ con la nota de lectura,
una sola descarga (PNG/CSV) por gráfico, ES/EN, año en `#FCA50A` y lo habitual en gris punteado (también en la cinta).
Sin botón de cerrar: se sale eligiendo otro capítulo (indicación previa de Julio). Queda fuera lo funcional: mapa ↔
gráficos, cifras del titular que llevan al gráfico y "Ver en el mapa" con las celdas recurrentes.
