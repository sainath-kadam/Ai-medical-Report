import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': '/src' },
  },
  server: {
    port: 5173,
    proxy: {
      // 127.0.0.1, not "localhost": Node 17+ resolves "localhost" to the IPv6 loopback
      // (::1) first on many systems, but uvicorn only binds the IPv4 loopback by default
      // -- that mismatch silently ECONNREFUSEs every proxied request (signed file URLs
      // in particular, since those are the one thing still fetched via a relative path
      // through this proxy rather than axiosInstance's absolute VITE_API_URL).
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
});
