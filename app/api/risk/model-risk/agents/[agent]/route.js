import { requireProxyAuthHeaders } from '@/lib/serverAuth';
const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

// RSK-013 per-agent kill-switch & threshold control adapter.
function getAuthHeaders(request) {
  const { headers } = requireProxyAuthHeaders(request);
  return headers;
}

export async function PUT(request, { params }) {
  const { errorResponse: _authErr } = requireProxyAuthHeaders(request);
  if (_authErr) return _authErr;
  const { agent } = await params;
  const body = await request.text();
  try {
    const res = await fetch(`${BACKEND_URL}/risk/model-risk/agents/${agent}`, {
      method: 'PUT',
      cache: 'no-store',
      headers: getAuthHeaders(request),
      body,
    });
    const data = await res.json();
    return Response.json(data, { status: res.status });
  } catch (err) {
    return Response.json({ error: err.message || 'Failed to connect to backend' }, { status: 502 });
  }
}
