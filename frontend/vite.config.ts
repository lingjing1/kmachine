import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from 'tailwindcss'
import autoprefixer from 'autoprefixer'

export default defineConfig(({ mode }) => {
  // Load env file based on `mode` in project root directory (one level up from frontend/).
  // The third parameter '' to load all env vars regardless of the `VITE_` prefix.
  const env = loadEnv(mode, '../', '')

  return {
    plugins: [react()],
    envDir: '../',
    server: {
      port: 5173,
      host: '0.0.0.0',
      proxy: {
        '/api': {
          target: env.VITE_API_URL || 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
    css: {
      postcss: {
        plugins: [
          tailwindcss(),
          autoprefixer(),
        ],
      },
    },
  }
})
