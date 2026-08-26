import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

// base './' 让构建产物可以被后端挂在任意路径下直接服务
export default defineConfig({
  base: "./",
  plugins: [vue()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/charts": "http://localhost:8000",
      "/healthz": "http://localhost:8000",
    },
  },
});
