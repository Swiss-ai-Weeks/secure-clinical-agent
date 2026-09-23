/// <reference types="vitest/config" />

import fs from 'node:fs';
import type { IncomingMessage, ServerResponse } from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vue from '@vitejs/plugin-vue';
import { defineConfig, type Connect, type Plugin } from 'vite';

const root = path.dirname(fileURLToPath(import.meta.url));

function isOhifNav(url: string): boolean {
  const pathname = url.split('?')[0].split('#')[0];
  if (pathname === '/ohif' || pathname === '/ohif/') return true;
  if (!pathname.startsWith('/ohif/')) return false;
  const last = pathname.slice(pathname.lastIndexOf('/') + 1);
  return !last.includes('.') || last === 'viewer';
}

function ohifSpa(): Plugin {
  const index = path.resolve(root, 'public/ohif/index.html');
  const serve = (req: IncomingMessage, res: ServerResponse, next: Connect.NextFunction) => {
    if (!req.url || !isOhifNav(req.url) || !fs.existsSync(index)) {
      next();
      return;
    }
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store');
    fs.createReadStream(index).pipe(res);
  };
  return {
    name: 'ohif-spa',
    configureServer(server) {
      server.middlewares.use(serve);
    },
    configurePreviewServer(server) {
      server.middlewares.use(serve);
    }
  };
}

export default defineConfig({
  plugins: [vue(), ohifSpa()],
  server: {
    port: 4173,
    proxy: {
      '/api': {
        target: process.env.PATIENT360_API_TARGET || 'http://127.0.0.1:8088',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/api/, '')
      }
    }
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    exclude: ['**/node_modules/**', 'tests/e2e/**']
  }
});
