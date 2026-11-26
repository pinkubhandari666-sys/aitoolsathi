// Dedicated Gemini endpoint for AI Document Maker.
// Uses the same Interactions API flow as gemini-generate.js so both AI tools
// share one compatible request/response format while keeping their prompts separate.

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
  if (!apiKey) {
    return { statusCode: 500, headers, body: JSON.stringify({ error: 'Gemini API key is missing. Add GEMINI_API_KEY in Netlify environment variables, then redeploy.' }) };
  }

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
    'For a resume or CV, create clear sections such as Contact Information, Professional Summary, Skills, Education, Experience, Projects and Certifications when relevant. Use placeholders for missing facts; never invent personal details, qualifications, dates or experience.',
    'Follow the user request closely. Use clean plain text with readable line breaks.',
    'Do not invent personal details, dates, addresses, qualifications, legal facts, or official information. Use clear placeholders such as [Your Name] when details are missing.',
    'Return only the finished document. Do not add commentary about being an AI and do not use markdown code fences.',
    '',
    'USER REQUEST:',
    prompt
  ].join('\n');

  // Keep the same model order and Interactions API used by the site's main Gemini function.
  const models = ['gemini-3.8-flash', 'gemini-3.6-flash', 'gemini-3.5-flash-lite'];
  let lastStatus = 502;
  let lastMessage = 'Gemini could not generate the document. Please try again.';
  let lastCode = null;

  for (let i = 0; i < models.length; i++) {
    const model = models[i];
    try {
      const upstream = await fetch('https://generativelanguage.googleapis.com/v1beta/interactions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-goog-api-key': apiKey },
        body: JSON.stringify({ model, input: instruction })
      });
      const payload = await upstream.json().catch(() => ({}));

      if (!upstream.ok) {
        lastStatus = upstream.status;
        lastMessage = payload?.error?.message || `Gemini API returned HTTP ${upstream.status}.`;
        lastCode = payload?.error?.status || payload?.error?.code || null;
        console.error('Gemini Document Maker upstream error:', { model, status: lastStatus, code: lastCode, message: lastMessage });

        const retryable = [404, 408, 429, 500, 502, 503, 504].includes(upstream.status);
        if (retryable && i < models.length - 1) continue;

        const clientStatus = upstream.status >= 400 && upstream.status < 500 && upstream.status !== 429
          ? upstream.status : 502;
        let friendly = lastMessage;
        if (upstream.status === 401 || upstream.status === 403) friendly = 'Gemini API key is invalid or does not have permission to use this model. Check GEMINI_API_KEY in Netlify.';
        else if (upstream.status === 429) friendly = 'Gemini API quota or rate limit reached. Check your Google AI Studio billing and usage limits, then try again.';
        else if (upstream.status === 404) friendly = 'The configured Gemini model or API endpoint was not found for this API key.';
        return {
          statusCode: clientStatus,
          headers,
          body: JSON.stringify({ error: friendly, upstreamStatus: upstream.status, upstreamCode: lastCode, model, attemptedModels: models.slice(0, i + 1) })
        };
      }

      let output = String(payload.output_text || '').trim();
      if (!output && Array.isArray(payload.steps)) {
        output = payload.steps
          .filter(step => step?.type === 'model_output' && Array.isArray(step.content))
          .flatMap(step => step.content)
          .filter(part => part?.type === 'text')
          .map(part => part.text || '')
          .join('\n')
          .trim();
      }

      if (!output) {
        lastStatus = 502;
        lastMessage = 'Gemini connected but returned no document text. Please try a shorter instruction.';
        console.error('Gemini Document Maker empty response:', { model, responseStatus: payload?.status || null });
        if (i < models.length - 1) continue;
        return { statusCode: 502, headers, body: JSON.stringify({ error: lastMessage, upstreamStatus: lastStatus, model, attemptedModels: models }) };
      }

      return { statusCode: 200, headers, body: JSON.stringify({ text: output, model }) };
    } catch (error) {
      lastStatus = 502;
      lastMessage = error?.name === 'AbortError'
        ? 'Gemini request timed out. Please try again with a shorter instruction.'
        : 'Could not connect to Gemini from the Netlify function. Check the function logs and try again.';
      console.error('Gemini Document Maker request exception:', { model, name: error?.name, message: error?.message });
      if (i < models.length - 1) continue;
    }
  }

  return {
    statusCode: 502,
    headers,
    body: JSON.stringify({
      error: 'All configured Gemini models failed. Check the upstream error in Netlify Function logs.',
      upstreamStatus: lastStatus,
      upstreamCode: lastCode,
      details: lastMessage,
      attemptedModels: models
    })
  };
};
