const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

// RSK-002/003 adapter. Service key is read from the environment only (no hard-coded fallback).
function getAuthHeaders(request) {
  const headers = {
    'Content-Type': 'application/json',
    'x-service-key': process.env.INTERNAL_SERVICE_KEY || ''
  };
  const auth = request.headers.get('authorization');
  if (auth) headers['Authorization'] = auth;
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

export async function GET(request, { params }) {
  const { id } = await params;
  return forward(`${BACKEND_URL}/portfolios/${id}/limits`, { headers: getAuthHeaders(request) });
}
