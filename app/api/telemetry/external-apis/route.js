import { requireProxyAuthHeaders } from '@/lib/serverAuth';

const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export async function GET(request) {
  const { headers, errorResponse } = requireProxyAuthHeaders(request);
  if (errorResponse) return errorResponse;

  try {
    const res = await fetch(`${BACKEND_URL}/telemetry/external-apis`, {
      headers,
      cache: 'no-store',
    });
    const data = await res.json();
    return Response.json(data, { status: res.status });
  } catch (err) {
    return Response.json({ detail: err.message || 'Failed to fetch external API telemetry' }, { status: 502 });
  }
}
