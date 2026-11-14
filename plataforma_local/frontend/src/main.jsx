import React from 'react'
import ReactDOM from 'react-dom/client'
import 'maplibre-gl/dist/maplibre-gl.css'
import './fire-map.css'
import './firecal.css'
import App from './FireMapApp.jsx'
import { getLang, setLang } from './i18n.js'

setLang(getLang())          // fija <html lang> y el título según el idioma inicial

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
