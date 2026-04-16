import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    host: "0.0.0.0",
    watch: {
      usePolling: true,
      interval: 1000,
    },
    proxy: {
      "/api": {
        target: "http://backend-dev:5000",
        changeOrigin: true,
      },
    },
  },
});
