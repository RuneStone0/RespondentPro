/**
 * Store factory — selects backend based on DATA_STORE_MODE env var.
 *
 * DATA_STORE_MODE=local    (default) — JSON files under dataDir
 * DATA_STORE_MODE=mongodb            — requires MONGODB_URI env var
 */

export async function createStore(dataDir, defaults) {
  const mode = (process.env.DATA_STORE_MODE || 'local').toLowerCase();

  if (mode === 'mongodb') {
    const uri = process.env.MONGODB_URI;
    if (!uri) throw new Error('DATA_STORE_MODE=mongodb requires MONGODB_URI to be set');
    const { createMongoStore } = await import('./mongodb.js');
    return createMongoStore(uri, defaults);
  }

  if (mode !== 'local') {
    console.warn(`[store] Unknown DATA_STORE_MODE "${mode}", falling back to local`);
  }

  const { createLocalStore } = await import('./local.js');
  return createLocalStore(dataDir, defaults);
}
