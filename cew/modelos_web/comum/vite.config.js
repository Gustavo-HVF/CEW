import { defineConfig } from 'vite';

// Os assets convertidos pelo CEW ficam em ../web (asset_manifest.json + assets/ + dados/).
// Servidos como arquivos estaticos, com o mesmo caminho web do manifesto.
export default defineConfig({
  base: './',
  publicDir: '../web',
  build: { outDir: 'dist', emptyOutDir: true, chunkSizeWarningLimit: 4096 },
  server: { port: 5173, strictPort: false },
  preview: { port: 4173, strictPort: false },
});
