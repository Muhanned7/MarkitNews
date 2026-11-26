import { requireProxyAuthHeaders } from '@/lib/serverAuth';
const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
const INTERNAL_SERVICE_KEY = process.env.INTERNAL_SERVICE_KEY || '';

function getAuthHeaders(request) {
  const { headers } = requireProxyAuthHeaders(request);
  return headers;
}

export async function GET(request, { params }) {
  const { errorResponse: _authErr } = requireProxyAuthHeaders(request);
  if (_authErr) return _authErr;
  const { id } = await params;
  try {
    const res = await fetch(`${BACKEND_URL}/portfolios/${id}`, {
      headers: getAuthHeaders(request),
      cache: 'no-store'
    });
    const data = await res.json();
    return Response.json(data, { status: res.status });
  } catch (err) {
    return Response.json({ error: err.message || 'Failed to connect to backend' }, { status: 502 });
  }
}
