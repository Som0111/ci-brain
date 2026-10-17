import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    // Only React/DOM tests run under Vitest. The pure-logic tests (src/lib/*.test.ts) use Node's built-in
    // runner (see the "test" script in package.json), so Vitest must not pick them up.
    include: ['src/**/*.test.tsx'],
    environment: 'jsdom',
  },
})
