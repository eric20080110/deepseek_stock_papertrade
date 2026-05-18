import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import Plotly from 'plotly.js-dist-min'
import './index.css'
import App from './App'

;(window as any).Plotly = Plotly

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
