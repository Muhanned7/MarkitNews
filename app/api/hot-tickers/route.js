import { extractBearerToken, getFrontendServiceHeaders } from '@/lib/serverAuth';

const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export async function GET(request) {
  const token = extractBearerToken(request);
  const url = new URL(request.url);
  const refresh = url.searchParams.get('refresh') === '1' ? '?refresh=true' : '';

  const headers = getFrontendServiceHeaders(
    token ? { Authorization: `Bearer ${token}` } : {}
  );

  try {
    const res = await fetch(`${BACKEND_URL}/hot-tickers${refresh}`, {
      headers,
      cache: 'no-store',
    });
    const data = await res.json();
    return Response.json(data, { status: res.status });
  } catch (err) {
    return Response.json(
      { detail: err.message || 'Failed to fetch live hot tickers from backend' },
      { status: 502 }
    );
  }
}
