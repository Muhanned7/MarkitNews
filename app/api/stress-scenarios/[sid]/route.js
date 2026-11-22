const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

// RSK-009/010/011 adapter. Service key is read from the environment only (no hard-coded fallback).
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

export async function PUT(request, { params }) {
  const { sid } = await params;
  const body = await request.json();
  return forward(`${BACKEND_URL}/stress-scenarios/${sid}`, { method: 'PUT', headers: getAuthHeaders(request), body: JSON.stringify(body) });
}

export async function DELETE(request, { params }) {
  const { sid } = await params;
  return forward(`${BACKEND_URL}/stress-scenarios/${sid}`, { method: 'DELETE', headers: getAuthHeaders(request) });
}
