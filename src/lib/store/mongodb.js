/**
 * MongoDB data store.
 * Requires `MONGODB_URI` env var (e.g. mongodb://user:pass@host:27017/respondentpro).
 *
 * Collections:
 *   config  — single document { _id: 'app', ...configFields }
 *   answers — one document per screener session
 */
import { MongoClient } from 'mongodb';

const DB_NAME = 'respondentpro';

function mergeConfig(defaults, stored) {
  if (!stored) return structuredClone(defaults);
  // Strip MongoDB metadata
  const { _id, ...rest } = stored;
  return {
    ...defaults,
    ...rest,
    filters:   { ...defaults.filters,   ...(rest.filters   || {}) },
    autoHide:  { ...defaults.autoHide,  ...(rest.autoHide  || {}) },
    keepAlive: { ...defaults.keepAlive, ...(rest.keepAlive || {}) },
  };
}

async function ensureCollections(db) {
  for (const name of ['config', 'answers']) {
    try {
      await db.createCollection(name);
    } catch (e) {
      // Ignore "collection already exists" — anything else is a real error
      if (e.codeName !== 'NamespaceExists') throw e;
    }
  }
}

export async function createMongoStore(uri, defaults) {
  const client = new MongoClient(uri);
  await client.connect();

  const db = client.db(DB_NAME);
  await ensureCollections(db);

  const configCol  = db.collection('config');
  const answersCol = db.collection('answers');

  console.log(`[store] MongoDB connected — db: ${DB_NAME}`);

  async function getConfig() {
    try {
      const doc = await configCol.findOne({ _id: 'app' });
      return mergeConfig(defaults, doc);
    } catch (e) {
      console.error('MongoDB getConfig error, using defaults:', e.message);
      return structuredClone(defaults);
    }
  }

  async function saveConfig(cfg) {
    // Strip in-memory-only fields before persisting
    const { ...doc } = cfg;
    await configCol.replaceOne(
      { _id: 'app' },
      { _id: 'app', ...doc },
      { upsert: true },
    );
  }

  async function getAnswers() {
    const docs = await answersCol.find({}).sort({ answeredAt: 1 }).toArray();
    // Strip MongoDB _id from each session
    return docs.map(({ _id, ...rest }) => rest);
  }

  async function appendSession(session) {
    await answersCol.insertOne({ ...session, answeredAt: new Date().toISOString() });
    return getAnswers();
  }

  return { getConfig, saveConfig, getAnswers, appendSession };
}
