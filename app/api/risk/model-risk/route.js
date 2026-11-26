import { requireProxyAuthHeaders } from '@/lib/serverAuth';
const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

// RSK-013 model-risk dashboard adapter.
function getAuthHeaders(request) {
  const { headers } = requireProxyAuthHeaders(request);
  return headers;
}

async function forward(url, init) {
  try {
    const res = await fetch(url, { cache: 'no-store', ...init });
    const data = await res.json();
    return Response.json(data, { status: res.status });
  } catch (err) {
    return Response.json({ error: err.message || 'Failed to connect to backend' }, { status: 502 });
  }
}

export async function GET(request) {
  const { errorResponse: _authErr } = requireProxyAuthHeaders(request);
  if (_authErr) return _authErr;
  const qs = new URL(request.url).search;
  return forward(`${BACKEND_URL}/risk/model-risk${qs}`, { headers: getAuthHeaders(request) });
}
