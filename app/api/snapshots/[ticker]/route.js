const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
const INTERNAL_SERVICE_KEY = process.env.INTERNAL_SERVICE_KEY || '';

function getAuthHeaders(request) {
  const auth = request.headers.get('authorization');
  const headers = {
    'Content-Type': 'application/json',
    'x-service-key': INTERNAL_SERVICE_KEY
  };
  if (auth) headers['Authorization'] = auth;
  return headers;
}

export async function GET(request, { params }) {
  const { ticker } = await params;
  try {
    const res = await fetch(`${BACKEND_URL}/snapshots/${ticker}`, {
      headers: getAuthHeaders(request),
      cache: 'no-store'
    });
    const data = await res.json();
    return Response.json(data, { status: res.status });
  } catch (err) {
    return Response.json({ error: err.message || 'Failed to connect to backend' }, { status: 502 });
  }
}
