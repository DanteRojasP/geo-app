# Aviso al equipo: Nikal Cusco ya está publicado 🚀

*Sábado 14-nov-2026, ~17:20 · Julio*

**URL de la app:** https://firecal-316891526626.southamerica-east1.run.app
**Documentación de la API:** https://firecal-316891526626.southamerica-east1.run.app/docs

## Qué hay

- Datos reales de NASA FIRMS armonizados de **Cusco** (2000-11 a 2025-12), según `MAESTRO.md`.
- Calendario mes × año de **focos armonizados**, mapa (MapLibre), selección de área, descarga CSV (18 columnas del
  contrato) y panel **"En simple"** con cinco respuestas y cuatro gráficos descargables.
- El código está en `main` (PR #8). La guía está en `plataforma_local/README.md` y el protocolo de llamadas a la
  API, en `ACTIVIDADES_JULIO.md`.
- **La versión de Vercel no es la oficial:** la URL de arriba es la que entregamos (incluye la interfaz y la API).

## Actualización (14-nov, noche): nueva interfaz

- Ya está la interfaz nueva de Dante: relieve, logo, línea de tiempo y calendario con años recientes primero.
- La app abre en **inglés**. El botón **EN/ES** (arriba a la derecha) la pasa a español.
- Para la evaluación con usuarios, anoten qué no se entiende, qué tarda y qué falla en el celular.
  Recomendado: un formulario de comentarios (Google Forms) con el enlace en el grupo.
- Cambios y recomendaciones: `CAMBIOS_Y_RECOMENDACIONES.md`.

## Qué le toca a cada uno

- **Erik y Gabriel (QA):** prueben la URL, también desde el celular, y reporten errores con captura. Los registros
  están en la consola: https://console.cloud.google.com/run?project=sonic-mile-514718-r5
- **Antonio y Dante:** pueden ver el servicio y volver a la versión anterior si algo falla
  (*Revisiones → Administrar tráfico*). **Antes de desplegar algo nuevo, avisen en el grupo.** El procedimiento está
  en `plataforma_local/docs/DESPLIEGUE_Y_FALENCIAS.md` (opción B).

## Prueba pendiente (2 personas)

Una persona abre la URL con **datos móviles** (sin wifi) mientras otra recarga la página muchas veces seguidas.
A quien usa el celular **no** debería salirle "Demasiadas solicitudes": cada visitante tiene su propio cupo.
Avisen el resultado en el grupo.

## Reglas

- Cada uno entra a Google Cloud con su propia cuenta. No compartan sesiones, contraseñas ni claves (tampoco las de
  Meteomatics o FIRMS): nunca en el repositorio ni en chats.
- No cambien roles, facturación ni la configuración del servicio sin avisar.
- El servicio consume créditos mientras esté encendido. Después de la evaluación se baja a 0 instancias o se borra.
