import { describe, it, expect } from 'vitest';
import { publicConfig } from '../src/lib/config-view.js';

const base = () => ({
  aiProvider: 'deepseek',
  grokApiKey: 'xai-real-key',
  deepseekApiKey: 'sk-real-key',
  cookie: 'respondent.session.sid=secret',
  filters: { sort: 'publishedAt' },
});

describe('publicConfig', () => {
  it('never returns a credential value', () => {
    const view = publicConfig(base());
    const json = JSON.stringify(view);
    expect(json).not.toContain('xai-real-key');
    expect(json).not.toContain('sk-real-key');
    expect(json).not.toContain('sid=secret');
  });

  it('drops the cookie field and every *ApiKey field, including legacy ones', () => {
    const view = publicConfig({ ...base(), claudeApiKey: 'sk-ant-legacy', gptApiKey: 'sk-openai-legacy' });
    expect(view.cookie).toBeUndefined();
    expect(Object.keys(view).filter(k => k.endsWith('ApiKey'))).toEqual([]);
    expect(JSON.stringify(view)).not.toContain('legacy');
  });

  it('reports key presence as booleans only', () => {
    const view = publicConfig(base());
    expect(view.hasGrokKey).toBe(true);
    expect(view.hasDeepseekKey).toBe(true);
    expect(view.hasCookie).toBe(true);
  });

  it('reports false for providers without a stored key', () => {
    const view = publicConfig({ aiProvider: 'deepseek', deepseekApiKey: 'sk-real', cookie: '' });
    expect(view.hasGrokKey).toBe(false);
    expect(view.hasDeepseekKey).toBe(true);
    expect(view.hasCookie).toBe(false);
  });

  it('keeps non-credential settings intact', () => {
    const view = publicConfig(base());
    expect(view.aiProvider).toBe('deepseek');
    expect(view.filters).toEqual({ sort: 'publishedAt' });
  });

  it('tolerates a missing config', () => {
    expect(() => publicConfig(undefined)).not.toThrow();
  });
});
