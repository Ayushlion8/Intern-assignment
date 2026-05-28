const API_BASE = import.meta.env.VITE_API_URL || '';

async function request(method, path, body = null, apiKey = '', timeout = 30000) {
  const headers = { 'Content-Type': 'application/json' };
  if (apiKey) headers['X-API-Key'] = apiKey;

  const opts = { method, headers, signal: AbortSignal.timeout(timeout) };
  if (body && method !== 'GET') opts.body = JSON.stringify(body);

  const resp = await fetch(`${API_BASE}${path}`, opts);

  if (!resp.ok) {
    const detail = await resp.json().catch(() => null);
    const err = detail?.detail?.error || {};
    const e = new Error(err.message || `HTTP ${resp.status}`);
    e.code = err.code || `HTTP_${resp.status}`;
    e.action = err.action || 'retry';
    e.docUrl = err.doc_url || null;
    throw e;
  }

  return resp.json();
}

export const api = {
  health: () => fetch(`${API_BASE}/health`).then(r => r.json()),
  createKey: (name = '', tier = 'free') => request('POST', '/api/v1/keys', { name, tier }),
  listKeys: () => request('GET', '/api/v1/keys'),
  transcribe: (url, model, apiKey) => request('POST', '/api/v1/transcribe', { url, model }, apiKey),
  getJob: (jobId, apiKey) => request('GET', `/api/v1/jobs/${jobId}`, null, apiKey),
  getUsage: (apiKey) => request('GET', '/api/v1/usage', null, apiKey),
};
