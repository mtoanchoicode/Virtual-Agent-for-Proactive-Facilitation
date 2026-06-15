import fs from "fs";
import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const certDir = path.resolve(__dirname, "certs");
const certFile = path.join(certDir, "192.168.1.20+3.pem");
const keyFile = path.join(certDir, "192.168.1.20+3-key.pem");

const httpsConfig =
  fs.existsSync(certFile) && fs.existsSync(keyFile)
    ? {
        key: fs.readFileSync(keyFile),
        cert: fs.readFileSync(certFile),
      }
    : true;

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    https: httpsConfig,
    headers: {
      "Cross-Origin-Opener-Policy": "same-origin",
      "Cross-Origin-Embedder-Policy": "require-corp",
    },
    proxy: {
      "/api": {
        target: "https://127.0.0.1:3000",
        secure: false,
      },
      "/chat": {
        target: "https://127.0.0.1:3000",
        secure: false,
      },
      "/ws/voice": {
        target: "wss://127.0.0.1:3000",
        ws: true,
        secure: false,
      },
    },
  },
  optimizeDeps: {
    exclude: ["@mediapipe/tasks-vision"],
  },
  assetsInclude: ["**/*.tflite"], // let Vite serve .tflite model files if needed
});
