import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/strategies': { target: 'http://localhost:8000', ws: true },
      '/health': { target: 'http://localhost:8000', ws: true },
      '/backtest': { target: 'http://localhost:8000', ws: true },
      '/param-space': { target: 'http://localhost:8000', ws: true },
      '/fitness': { target: 'http://localhost:8000', ws: true },
      '/tasks': { target: 'http://localhost:8000', ws: true },
      '/analysis': { target: 'http://localhost:8000', ws: true },
      '/paper-trading': { target: 'http://localhost:8000', ws: true },
      '/gene-pool': { target: 'http://localhost:8000', ws: true },
      '/system': { target: 'http://localhost:8000', ws: true },
    },
  },
})
