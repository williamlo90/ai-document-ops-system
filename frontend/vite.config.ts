import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    exclude: ['e2e/**', 'node_modules/**'],
    css: true,
    restoreMocks: true,
    clearMocks: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/backoffice': 'http://127.0.0.1:8000',
      '/documents': 'http://127.0.0.1:8000',
      '/invoices': 'http://127.0.0.1:8000',
      '/review': 'http://127.0.0.1:8000',
      '/agentops': 'http://127.0.0.1:8000',
      '/agent': 'http://127.0.0.1:8000',
      '/auth': 'http://127.0.0.1:8000',
      '/providers': 'http://127.0.0.1:8000',
      '/integrations': 'http://127.0.0.1:8000',
      '/operations': 'http://127.0.0.1:8000',
      '/exports': 'http://127.0.0.1:8000',
      '/exceptions': 'http://127.0.0.1:8000',
      '/evaluation': 'http://127.0.0.1:8000',
      '/metrics': 'http://127.0.0.1:8000',
    },
  },
})
