import 'dotenv/config';

const BASE_URL = 'https://app.respondent.io';
const cookie = process.env.RESPONDENT_COOKIE;

async function getText(url) {
  const res = await fetch(url, {
    headers: { cookie, 'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36' }
  });
  return res.text();
}

// Find the latest app bundle from the HTML
const html = await getText(BASE_URL + '/respondents/v2/projects/browse');
const jsPreloads = [...html.matchAll(/href=([^>\s]+\.js[^>\s]*)/g)].map(m => m[1]);
console.log('JS preloads:', jsPreloads);

// Fetch each JS bundle and find all fetch/axios/http calls
for (const jsPath of jsPreloads) {
  const fullUrl = jsPath.startsWith('http') ? jsPath : BASE_URL + jsPath;
  try {
    const js = await getText(fullUrl);
    // Find all string patterns that look like API paths
    const allStrings = [...js.matchAll(/["'`](\/[a-zA-Z][^"'`\n]{4,80})["'`]/g)].map(m => m[1]);
    const apiStrings = allStrings.filter(s =>
      s.includes('/api/') || s.includes('/v2/') || s.includes('/v3') || s.includes('/v4/') ||
      (s.includes('/project') || s.includes('/user') || s.includes('/auth'))
    );
    const unique = [...new Set(apiStrings)];
    if (unique.length > 0) {
      console.log(`\n=== ${jsPath.split('/').pop()} (${unique.length} paths) ===`);
      unique.forEach(p => console.log(' ', p));
    }
  } catch(e) {
    console.log('Error:', jsPath, e.message);
  }
}
