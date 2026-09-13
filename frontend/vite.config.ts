import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    host: '0.0.0.0',
    port: 18473,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8473', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8473', changeOrigin: true },
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 18473,
  },
})
