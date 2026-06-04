/**
 * Store factory — selects backend based on DATA_STORE_MODE and MONGODB_URI.
 *
 * DATA_STORE_MODE=local    — JSON files under dataDir
 * DATA_STORE_MODE=mongodb  — requires MONGODB_URI
 *
 * When DATA_STORE_MODE is unset, MONGODB_URI alone selects MongoDB (Docker/Portainer
 * deployments often inject only the URI).
 */

export function resolveStoreMode() {
  const explicit = (process.env.DATA_STORE_MODE || '').toLowerCase();
  const uri = process.env.MONGODB_URI || '';

  if (explicit === 'mongodb') return { mode: 'mongodb', uri };
  if (explicit === 'local') return { mode: 'local', uri: '' };
  if (uri) return { mode: 'mongodb', uri };
  return { mode: 'local', uri: '' };
}

export async function createStore(dataDir, defaults) {
  const { mode, uri } = resolveStoreMode();

  if (mode === 'mongodb') {
    if (!uri) throw new Error('DATA_STORE_MODE=mongodb requires MONGODB_URI to be set');
    const { createMongoStore } = await import('./mongodb.js');
    return createMongoStore(uri, defaults);
  }

  const explicit = (process.env.DATA_STORE_MODE || '').toLowerCase();
  if (explicit && explicit !== 'local') {
    console.warn(`[store] Unknown DATA_STORE_MODE "${explicit}", falling back to local`);
  }

  const { createLocalStore } = await import('./local.js');
  return createLocalStore(dataDir, defaults);
}
