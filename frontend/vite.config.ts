import { execSync } from 'child_process'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const gitSha = process.env.GIT_SHA || (() => {
  try { return execSync('git rev-parse --short HEAD').toString().trim(); }
  catch { return 'dev'; }
})();
const gitTag = process.env.GIT_TAG || (() => {
  try { return execSync('git describe --tags --abbrev=0').toString().trim(); }
  catch { return ''; }
})();

export default defineConfig({
  define: {
    __GIT_SHA__: JSON.stringify(gitSha),
    __GIT_TAG__: JSON.stringify(gitTag),
  },
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
