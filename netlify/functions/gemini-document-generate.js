// Dedicated Gemini endpoint for AI Document Maker.
// Kept separate so AI Writer, Ask PDF and PDF Summary remain unchanged.
const allowedOrigin = (origin) => {
  if (!origin) return false;
  try {
    const u = new URL(origin);
    return u.protocol === 'https:' &&
      (u.hostname === 'aitoolsathi.in' ||
       u.hostname === 'www.aitoolsathi.in' ||
       u.hostname.endsWith('.netlify.app'));
  } catch (_) { return false; }
};

exports.handler = async (event) => {
  const origin = event.headers?.origin || event.headers?.Origin || '';
  const corsOrigin = allowedOrigin(origin) ? origin : 'https://aitoolsathi.in';
  const headers = {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': corsOrigin,
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Vary': 'Origin',
    'Cache-Control': 'no-store'
  };

  if (event.httpMethod === 'OPTIONS') return { statusCode: 204, headers, body: '' };
  if (!allowedOrigin(origin)) return { statusCode: 403, headers, body: JSON.stringify({ error: 'This website origin is not allowed.' }) };
  if (event.httpMethod !== 'POST') return { statusCode: 405, headers, body: JSON.stringify({ error: 'Method not allowed.' }) };

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) return { statusCode: 500, headers, body: JSON.stringify({ error: 'Gemini API key is not configured in Netlify. Add GEMINI_API_KEY and redeploy.' }) };

  let input;
  try { input = JSON.parse(event.body || '{}'); }
  catch (_) { return { statusCode: 400, headers, body: JSON.stringify({ error: 'Invalid request body.' }) }; }

  const prompt = String(input.prompt || '').trim();
  const language = String(input.language || 'Match my prompt').slice(0, 40);
  const tone = String(input.tone || 'Professional').slice(0, 40);
  const documentType = String(input.documentType || 'Choose automatically').slice(0, 80);

  if (!prompt) return { statusCode: 400, headers, body: JSON.stringify({ error: 'Please enter your instruction.' }) };
  if (prompt.length > 5000) return { statusCode: 413, headers, body: JSON.stringify({ error: 'Instruction is too long. Maximum 5,000 characters.' }) };

  const instruction = [
    'You are the document-writing engine for AI Tool Sathi.',
    `Document type: ${documentType}.`,
    `Required output language: ${language}.`,
    `Tone: ${tone}.`,
    'Create a complete, useful, well-structured document with an appropriate title, headings, subject where relevant, clear paragraphs, and a polite closing where appropriate.',
    'Follow the user request closely. Use clean plain text with readable line breaks.',
    'Do not invent personal details, dates, addresses, qualifications, legal facts, or official information. Use clear placeholders such as [Your Name] when details are missing.',
    'Return only the finished document. Do not add commentary about being an AI and do not use markdown code fences.',
    '',
    'USER REQUEST:',
    prompt
  ].join('\n');

  const models = ['gemini-3.8-flash', 'gemini-3.5-flash-lite'];
  let lastStatus = 502;
  let lastMessage = 'Gemini could not generate the document. Please try again.';

  for (let i = 0; i < models.length; i++) {
    const model = models[i];
    try {
      const upstream = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'x-goog-api-key': apiKey },
          body: JSON.stringify({
            contents: [{ role: 'user', parts: [{ text: instruction }] }],
            generationConfig: { temperature: 0.6, maxOutputTokens: 8192 }
          })
        }
      );

      const payload = await upstream.json().catch(() => ({}));
      if (!upstream.ok) {
        lastStatus = upstream.status;
        lastMessage = payload?.error?.message || `Gemini API returned ${upstream.status}.`;
        const retryable = [408, 429, 500, 502, 503, 504].includes(upstream.status);
        if (i === 0 && retryable) continue;
        const clientStatus = upstream.status >= 400 && upstream.status < 500 && upstream.status !== 429
          ? upstream.status : 502;
        return {
          statusCode: clientStatus,
          headers,
          body: JSON.stringify({
            error: upstream.status === 429 || upstream.status === 503
              ? 'Gemini is temporarily busy. Please wait a few seconds and try again.'
              : lastMessage,
            upstreamStatus: upstream.status,
            model
          })
        };
      }

      const output = (payload?.candidates || [])
        .flatMap(candidate => candidate?.content?.parts || [])
        .map(part => part?.text || '')
        .join('\n')
        .trim();

      if (!output) {
        lastStatus = 502;
        lastMessage = 'Gemini returned an empty document. Please try again.';
        if (i === 0) continue;
        return { statusCode: 502, headers, body: JSON.stringify({ error: lastMessage, model }) };
      }

      return {
        statusCode: 200,
        headers,
        body: JSON.stringify({ text: output, model })
      };
    } catch (error) {
      lastStatus = 502;
      lastMessage = 'Could not connect to Gemini. Please check your connection and try again.';
      if (i === 0) continue;
    }
  }

  return {
    statusCode: 502,
    headers,
    body: JSON.stringify({
      error: 'Gemini is temporarily unavailable. Please wait a few seconds and try again.',
      upstreamStatus: lastStatus,
      details: lastMessage
    })
  };
};
