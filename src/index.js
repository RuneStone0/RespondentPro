import 'dotenv/config';

const BASE_URL = 'https://app.respondent.io';

const cookie = process.env.RESPONDENT_COOKIE;
if (!cookie) {
  console.error('Missing RESPONDENT_COOKIE in .env');
  process.exit(1);
}

async function get(path) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: {
      cookie,
      'user-agent': 'Mozilla/5.0 (compatible; respondent-bot/1.0)',
    },
  });

  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText} — ${path}`);
  }

  const contentType = res.headers.get('content-type') ?? '';
  return contentType.includes('application/json') ? res.json() : res.text();
}

// Entry point — add your logic here
const body = await get('/');
console.log(typeof body === 'string' ? body.slice(0, 500) : body);
