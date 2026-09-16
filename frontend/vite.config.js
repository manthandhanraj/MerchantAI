import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Tailwind v4 is wired in as a Vite plugin: there is deliberately no
// tailwind.config.js or postcss.config.js. See docs/SETUP.md.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        // Recharts is ~85% of the bundle and changes only when it is upgraded,
        // while the app code changes on every deploy. Splitting them means a
        // redeploy invalidates only the small app chunk instead of all 592 kB.
        // React is left where Rollup puts it: Recharts imports it, so pulling
        // it out separately produced an empty chunk.
        manualChunks: {
          charts: ['recharts'],
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.js'],
  },
  server: {
    port: 5173,
    // Lets the app call the API with relative '/api/...' paths in dev,
    // so no CORS setup or base URL is needed locally.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
