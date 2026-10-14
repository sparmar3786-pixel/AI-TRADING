import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  // Configure base path for GitHub Pages deployment
  // This will be '/' for TradingGoose.github.io
  base: '/',
  server: {
    host: "::",
    port: 8080,
  },
  plugins: [
    react(),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    // Ensure assets are properly referenced with base path
    assetsDir: 'assets',
    sourcemap: false, // Disable sourcemaps for production
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true
      }
    },
    target: 'es2020',
    modulePreload: {
      polyfill: true,
    },
    rollupOptions: {
      output: {
        // Ensure JS files have proper extensions and format for GitHub Pages
        format: 'es',
        entryFileNames: '[name]-[hash].js',
        chunkFileNames: 'chunks/[name]-[hash].js',
        assetFileNames: (assetInfo) => {
          const info = assetInfo.names?.[0] || '';
          if (/\.(css)$/.test(info)) {
            return 'css/[name]-[hash][extname]';
          }
          if (/\.(png|jpg|jpeg|gif|svg|ico|webp)$/.test(info)) {
            return 'images/[name]-[hash][extname]';
          }
          return 'assets/[name]-[hash][extname]';
        },
        manualChunks: {
          // Vendor chunk for stable libraries
          vendor: ['react', 'react-dom'],
          // UI components chunk
          ui: ['@radix-ui/react-dialog', '@radix-ui/react-dropdown-menu', '@radix-ui/react-tabs', '@radix-ui/react-select'],
          // Chart and data visualization
          charts: ['recharts'],
          // Auth and data fetching
          auth: ['@supabase/supabase-js', '@tanstack/react-query'],
          // Firebase chunk
          firebase: ['firebase/app', 'firebase/firestore', 'firebase/auth'],
          // Router chunk
          router: ['react-router-dom'],
          // Utilities
          utils: ['class-variance-authority', 'clsx', 'tailwind-merge', 'zod']
        }
      }
    }
  },
}));
