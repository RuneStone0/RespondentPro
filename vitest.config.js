import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
    include: ['test/**/*.test.js'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src/lib/**/*.js'],
      thresholds: {
        lines: 100,
        functions: 100,
        statements: 100,
        branches: 100,
      },
    },
  },
});
