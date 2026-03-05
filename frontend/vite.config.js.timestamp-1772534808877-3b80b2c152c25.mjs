// vite.config.js
import { defineConfig } from "file:///sessions/great-youthful-pasteur/mnt/cyberhealth-scanner/frontend/node_modules/vite/dist/node/index.js";
import react from "file:///sessions/great-youthful-pasteur/mnt/cyberhealth-scanner/frontend/node_modules/@vitejs/plugin-react/dist/index.js";
var vite_config_default = defineConfig({
  plugins: [react()],
  server: {
    port: 3e3,
    proxy: {
      // Proxy l'API FastAPI en dev pour éviter les problèmes CORS
      "/scan": { target: "http://localhost:8000", changeOrigin: true },
      "/report": { target: "http://localhost:8000", changeOrigin: true },
      "/health": { target: "http://localhost:8000", changeOrigin: true }
    }
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          "vendor-react": ["react", "react-dom"],
          "vendor-motion": ["framer-motion"],
          "vendor-ui": ["lucide-react"]
        }
      }
    }
  }
});
export {
  vite_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcuanMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCIvc2Vzc2lvbnMvZ3JlYXQteW91dGhmdWwtcGFzdGV1ci9tbnQvY3liZXJoZWFsdGgtc2Nhbm5lci9mcm9udGVuZFwiO2NvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9maWxlbmFtZSA9IFwiL3Nlc3Npb25zL2dyZWF0LXlvdXRoZnVsLXBhc3RldXIvbW50L2N5YmVyaGVhbHRoLXNjYW5uZXIvZnJvbnRlbmQvdml0ZS5jb25maWcuanNcIjtjb25zdCBfX3ZpdGVfaW5qZWN0ZWRfb3JpZ2luYWxfaW1wb3J0X21ldGFfdXJsID0gXCJmaWxlOi8vL3Nlc3Npb25zL2dyZWF0LXlvdXRoZnVsLXBhc3RldXIvbW50L2N5YmVyaGVhbHRoLXNjYW5uZXIvZnJvbnRlbmQvdml0ZS5jb25maWcuanNcIjtpbXBvcnQgeyBkZWZpbmVDb25maWcgfSBmcm9tICd2aXRlJztcbmltcG9ydCByZWFjdCBmcm9tICdAdml0ZWpzL3BsdWdpbi1yZWFjdCc7XG5leHBvcnQgZGVmYXVsdCBkZWZpbmVDb25maWcoe1xuICAgIHBsdWdpbnM6IFtyZWFjdCgpXSxcbiAgICBzZXJ2ZXI6IHtcbiAgICAgICAgcG9ydDogMzAwMCxcbiAgICAgICAgcHJveHk6IHtcbiAgICAgICAgICAgIC8vIFByb3h5IGwnQVBJIEZhc3RBUEkgZW4gZGV2IHBvdXIgXHUwMEU5dml0ZXIgbGVzIHByb2JsXHUwMEU4bWVzIENPUlNcbiAgICAgICAgICAgICcvc2Nhbic6IHsgdGFyZ2V0OiAnaHR0cDovL2xvY2FsaG9zdDo4MDAwJywgY2hhbmdlT3JpZ2luOiB0cnVlIH0sXG4gICAgICAgICAgICAnL3JlcG9ydCc6IHsgdGFyZ2V0OiAnaHR0cDovL2xvY2FsaG9zdDo4MDAwJywgY2hhbmdlT3JpZ2luOiB0cnVlIH0sXG4gICAgICAgICAgICAnL2hlYWx0aCc6IHsgdGFyZ2V0OiAnaHR0cDovL2xvY2FsaG9zdDo4MDAwJywgY2hhbmdlT3JpZ2luOiB0cnVlIH0sXG4gICAgICAgIH0sXG4gICAgfSxcbiAgICBidWlsZDoge1xuICAgICAgICBvdXREaXI6ICdkaXN0JyxcbiAgICAgICAgc291cmNlbWFwOiB0cnVlLFxuICAgICAgICByb2xsdXBPcHRpb25zOiB7XG4gICAgICAgICAgICBvdXRwdXQ6IHtcbiAgICAgICAgICAgICAgICBtYW51YWxDaHVua3M6IHtcbiAgICAgICAgICAgICAgICAgICAgJ3ZlbmRvci1yZWFjdCc6IFsncmVhY3QnLCAncmVhY3QtZG9tJ10sXG4gICAgICAgICAgICAgICAgICAgICd2ZW5kb3ItbW90aW9uJzogWydmcmFtZXItbW90aW9uJ10sXG4gICAgICAgICAgICAgICAgICAgICd2ZW5kb3ItdWknOiBbJ2x1Y2lkZS1yZWFjdCddLFxuICAgICAgICAgICAgICAgIH0sXG4gICAgICAgICAgICB9LFxuICAgICAgICB9LFxuICAgIH0sXG59KTtcbiJdLAogICJtYXBwaW5ncyI6ICI7QUFBcVgsU0FBUyxvQkFBb0I7QUFDbFosT0FBTyxXQUFXO0FBQ2xCLElBQU8sc0JBQVEsYUFBYTtBQUFBLEVBQ3hCLFNBQVMsQ0FBQyxNQUFNLENBQUM7QUFBQSxFQUNqQixRQUFRO0FBQUEsSUFDSixNQUFNO0FBQUEsSUFDTixPQUFPO0FBQUE7QUFBQSxNQUVILFNBQVMsRUFBRSxRQUFRLHlCQUF5QixjQUFjLEtBQUs7QUFBQSxNQUMvRCxXQUFXLEVBQUUsUUFBUSx5QkFBeUIsY0FBYyxLQUFLO0FBQUEsTUFDakUsV0FBVyxFQUFFLFFBQVEseUJBQXlCLGNBQWMsS0FBSztBQUFBLElBQ3JFO0FBQUEsRUFDSjtBQUFBLEVBQ0EsT0FBTztBQUFBLElBQ0gsUUFBUTtBQUFBLElBQ1IsV0FBVztBQUFBLElBQ1gsZUFBZTtBQUFBLE1BQ1gsUUFBUTtBQUFBLFFBQ0osY0FBYztBQUFBLFVBQ1YsZ0JBQWdCLENBQUMsU0FBUyxXQUFXO0FBQUEsVUFDckMsaUJBQWlCLENBQUMsZUFBZTtBQUFBLFVBQ2pDLGFBQWEsQ0FBQyxjQUFjO0FBQUEsUUFDaEM7QUFBQSxNQUNKO0FBQUEsSUFDSjtBQUFBLEVBQ0o7QUFDSixDQUFDOyIsCiAgIm5hbWVzIjogW10KfQo=
