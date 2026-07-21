import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const productRoutes = [
  '/overview',
  '/invoices',
  '/review-queue',
  '/review/',
  '/exceptions',
  '/exports',
  '/evaluation',
  '/system',
  '/settings',
]

const productHistoryFallback = {
  name: 'product-history-fallback',
  configureServer(server: { middlewares: { use: (handler: (request: { method?: string; url?: string; headers: { accept?: string } }, response: unknown, next: () => void) => void) => void } }) {
    server.middlewares.use((request, _response, next) => {
      const pathname = new URL(request.url ?? '/', 'http://localhost').pathname
      const isProductNavigation = productRoutes.some((route) => (
        route.endsWith('/') ? pathname.startsWith(route) : pathname === route
      ))

      if (request.method === 'GET' && request.headers.accept?.includes('text/html') && isProductNavigation) {
        request.url = '/index.html'
      }
      next()
    })
  },
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [productHistoryFallback, react(), tailwindcss()],
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
      '/system': 'http://127.0.0.1:8000',
      '/overview': 'http://127.0.0.1:8000',
      '/metrics': 'http://127.0.0.1:8000',
    },
  },
})
