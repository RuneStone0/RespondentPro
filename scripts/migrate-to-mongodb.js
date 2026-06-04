/**
 * One-shot migration: local JSON files → MongoDB
 *
 * Reads data/config.json, data/keywords.json (optional), and data/answers.json
 * and upserts them into the MongoDB instance configured in .env.
 *
 * Safe to run multiple times:
 *   - config is upserted without keyword lists (those live in `keywords` collection)
 *   - keywords are upserted into the `keywords` collection
 *   - answer sessions are deduplicated by projectId + answeredAt
 *
 * Usage:
 *   node scripts/migrate-to-mongodb.js
 *   node scripts/migrate-to-mongodb.js --dry-run
 */

import 'dotenv/config';
import { existsSync, readFileSync } from 'fs';
import { MongoClient } from 'mongodb';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { keywordsFromFilters, stripKeywordsFromConfig } from '../src/lib/store/keywords.js';

const ROOT     = join(dirname(fileURLToPath(import.meta.url)), '..');
const DATA_DIR = join(ROOT, 'data');
const DRY_RUN  = process.argv.includes('--dry-run');

const DB_NAME = 'respondentpro';

function redactUri(uri) {
  return uri.replace(/\/\/([^@]+)@/, '//***@');
}

function readJson(file) {
  const path = join(DATA_DIR, file);
  if (!existsSync(path)) return null;
  return JSON.parse(readFileSync(path, 'utf8'));
}

async function main() {
  const uri = process.env.MONGODB_URI;
  if (!uri) {
    console.error('❌  MONGODB_URI is not set. Check your .env file.');
    process.exit(1);
  }

  console.log(`\n📦  RespondentPro — local → MongoDB migration`);
  console.log(`    URI:     ${redactUri(uri)}`);
  console.log(`    DB:      ${DB_NAME}`);
  console.log(`    Dry run: ${DRY_RUN}\n`);

  // ── Load local files ─────────────────────────────────────
  const rawConfig   = readJson('config.json');
  const rawKeywords = readJson('keywords.json');
  const rawAnswers  = readJson('answers.json');

  if (!rawConfig) {
    console.warn('⚠️   data/config.json not found — skipping config migration.');
  } else {
    // Rename stale field if present (openaiApiKey → gptApiKey) // nosemgrep
    if ('openaiApiKey' in rawConfig && !('gptApiKey' in rawConfig)) { // nosemgrep
      rawConfig.gptApiKey = rawConfig.openaiApiKey; // nosemgrep
      delete rawConfig.openaiApiKey; // nosemgrep
      console.log('    ✏️  Renamed gpt key field in config'); // nosemgrep
    }
  }

  const sessions = Array.isArray(rawAnswers) ? rawAnswers : [];
  const keywordSource = rawKeywords
    ? { exclude: rawKeywords.exclude || [], priority: rawKeywords.priority || [] }
    : rawConfig
      ? keywordsFromFilters(rawConfig.filters)
      : { exclude: [], priority: [] };

  console.log(`    Config:   ${rawConfig ? 'found' : 'missing'}`);
  console.log(`    Keywords: ${keywordSource.exclude.length} exclude, ${keywordSource.priority.length} priority`);
  console.log(`    Answers:  ${sessions.length} session(s)\n`);

  if (DRY_RUN) {
    console.log('🔍  Dry run — no changes written.');
    return;
  }

  // ── Connect ───────────────────────────────────────────────
  const client = new MongoClient(uri);
  try {
    console.log('🔌  Connecting to MongoDB…');
    await client.connect();
    const db          = client.db(DB_NAME);
    const configCol   = db.collection('config');
    const keywordsCol = db.collection('keywords');
    const answersCol  = db.collection('answers');

    // Ensure collections exist
    for (const name of ['config', 'keywords', 'answers']) {
      try { await db.createCollection(name); } catch (e) {
        if (e.codeName !== 'NamespaceExists') throw e;
      }
    }
    console.log('✅  Connected\n');

    // ── Migrate config ────────────────────────────────────
    let keywords = keywordSource;
    if (!keywords.exclude.length && !keywords.priority.length) {
      const existingConfig = await configCol.findOne({ _id: 'app' });
      keywords = keywordsFromFilters(existingConfig?.filters);
    }

    if (rawConfig) {
      const existing = await configCol.findOne({ _id: 'app' });
      if (existing) {
        console.log('⚠️   Config document already exists in MongoDB.');
        console.log('    Overwriting with local data (cookie, filter settings, stats — not keywords)…');
      }
      await configCol.replaceOne(
        { _id: 'app' },
        { _id: 'app', ...stripKeywordsFromConfig(rawConfig) },
        { upsert: true },
      );
      console.log('✅  Config migrated');
    }

    // ── Migrate keywords ────────────────────────────────────
    if (keywords.exclude.length || keywords.priority.length) {
      await keywordsCol.replaceOne(
        { _id: 'app' },
        { _id: 'app', ...keywords },
        { upsert: true },
      );
      console.log(`✅  Keywords migrated (${keywords.exclude.length} exclude, ${keywords.priority.length} priority)`);
    } else {
      console.log('ℹ️   No keywords to migrate');
    }

    // ── Migrate answers ───────────────────────────────────
    if (sessions.length > 0) {
      // Fetch existing keys in one query — no per-session findOne needed,
      // which avoids passing variable data into MongoDB queries entirely.
      const existing = await answersCol.find({}, { projection: { projectId: 1, answeredAt: 1 } }).toArray();
      const seen = new Set(existing.map(d => `${d.projectId}::${d.answeredAt}`));

      let inserted = 0;
      let skipped  = 0;
      for (const session of sessions) {
        const key = `${session.projectId}::${session.answeredAt}`;
        if (seen.has(key)) {
          skipped++;
        } else {
          await answersCol.insertOne({ ...session });
          seen.add(key);
          inserted++;
        }
      }
      console.log(`✅  Answers: ${inserted} inserted, ${skipped} already present`);
    } else {
      console.log('ℹ️   No answer sessions to migrate');
    }

    // ── Verify ────────────────────────────────────────────
    const configCount   = await configCol.countDocuments();
    const keywordsCount = await keywordsCol.countDocuments();
    const answerCount   = await answersCol.countDocuments();
    console.log(`\n📊  MongoDB state after migration:`);
    console.log(`    config   collection: ${configCount} document(s)`);
    console.log(`    keywords collection: ${keywordsCount} document(s)`);
    console.log(`    answers  collection: ${answerCount} document(s)`);
    console.log('\n🎉  Migration complete!\n');

  } finally {
    await client.close();
  }
}

main().catch(err => {
  console.error('\n❌  Migration failed:', err.message);
  process.exit(1);
});
