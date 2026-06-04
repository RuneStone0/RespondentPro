import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { resolveStoreMode } from '../src/lib/store/index.js';

describe('resolveStoreMode', () => {
  const env = process.env;

  beforeEach(() => {
    process.env = { ...env };
    delete process.env.DATA_STORE_MODE;
    delete process.env.MONGODB_URI;
  });

  afterEach(() => {
    process.env = env;
  });

  it('defaults to local when nothing is set', () => {
    expect(resolveStoreMode()).toEqual({ mode: 'local', uri: '' });
  });

  it('uses mongodb when MONGODB_URI is set (no DATA_STORE_MODE)', () => {
    process.env.MONGODB_URI = 'mongodb://localhost/test';
    expect(resolveStoreMode()).toEqual({ mode: 'mongodb', uri: 'mongodb://localhost/test' });
  });

  it('honours explicit local even when MONGODB_URI is set', () => {
    process.env.DATA_STORE_MODE = 'local';
    process.env.MONGODB_URI = 'mongodb://localhost/test';
    expect(resolveStoreMode()).toEqual({ mode: 'local', uri: '' });
  });

  it('requires uri when DATA_STORE_MODE is mongodb', () => {
    process.env.DATA_STORE_MODE = 'mongodb';
    expect(resolveStoreMode()).toEqual({ mode: 'mongodb', uri: '' });
  });
});
