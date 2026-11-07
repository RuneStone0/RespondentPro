/**
 * Build the client-visible view of the stored config.
 *
 * Credentials must never leave the server: the cookie and every `*ApiKey`
 * field are dropped by pattern, so a legacy key still present in an old data
 * store cannot leak through a field nobody remembered to strip. Presence is
 * reported as booleans only.
 */
export function publicConfig(config) {
  const safe = {};
  for (const [key, value] of Object.entries(config || {})) {
    if (key === 'cookie' || key.endsWith('ApiKey')) continue;
    safe[key] = value;
  }
  return {
    ...safe,
    hasCookie: Boolean(config?.cookie),
    hasGrokKey: Boolean(config?.grokApiKey),
    hasDeepseekKey: Boolean(config?.deepseekApiKey),
  };
}
