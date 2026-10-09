import { defineConfig } from "vitest/config";
import { loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000";
  const apiOrigin = new URL(apiTarget).origin;

  return {
    plugins: [react()],
    test: {
      environment: "jsdom",
      setupFiles: "./src/test/setup.ts",
    },
    server: {
      host: "127.0.0.1",
      port: 5173,
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true,
          secure: env.VITE_API_PROXY_INSECURE !== "true",
          configure: (proxy) => {
            proxy.on("proxyReq", (proxyRequest) => {
              // Keep browser requests same-origin through Vite while satisfying
              // the deployed API's origin check for authenticated writes.
              proxyRequest.setHeader("origin", apiOrigin);
              proxyRequest.setHeader("referer", `${apiOrigin}/`);
            });
            proxy.on("proxyRes", (proxyResponse) => {
              const cookies = proxyResponse.headers["set-cookie"];
              if (cookies) {
                // The remote production server correctly uses Secure cookies. The
                // local Vite origin is HTTP, so remove only that flag at the proxy.
                const cookieList = Array.isArray(cookies) ? cookies : [cookies];
                proxyResponse.headers["set-cookie"] = cookieList.map((cookie) =>
                  cookie.replace(/;\s*Secure/gi, ""),
                );
              }
            });
          },
        },
      },
    },
  };
});
