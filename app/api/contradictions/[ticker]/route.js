import { requireProxyAuthHeaders } from '@/lib/serverAuth';

const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export async function GET(request, { params }) {
  const { headers, errorResponse } = requireProxyAuthHeaders(request);
  if (errorResponse) return errorResponse;

  const { ticker } = await params;
  const url = new URL(request.url);
  const refresh = url.searchParams.get('refresh') === '1' ? '?refresh=true' : '';

  try {
    const res = await fetch(`${BACKEND_URL}/contradictions/${encodeURIComponent(ticker)}${refresh}`, {
      headers,
      cache: 'no-store',
    });
    const data = await res.json();
    return Response.json(data, { status: res.status });
  } catch (err) {
    return Response.json({ detail: err.message || 'Failed to connect to Contradiction Agent' }, { status: 502 });
  }
}
