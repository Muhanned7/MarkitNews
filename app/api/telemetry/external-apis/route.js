import { requireProxyAuthHeaders } from '@/lib/serverAuth';

const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export async function GET(request) {
  const { headers, token, errorResponse } = requireProxyAuthHeaders(request);
  if (errorResponse) return errorResponse;

  // Enforce developer admin check on the Next.js proxy layer before calling backend
  try {
    const payloadB64 = token.split('.')[1];
    const decoded = JSON.parse(Buffer.from(payloadB64, 'base64url').toString('utf8'));
    const email = (decoded.email || '').toLowerCase();
    const isAdmin =
      decoded.role === 'admin' ||
      decoded.is_admin === true ||
      email === 'admin@marketpulse.ai' ||
      email === 'dev@marketpulse.ai';
    if (!isAdmin) {
      return Response.json(
        { detail: 'Forbidden: Developer Admin account required to access production telemetry.' },
        { status: 403 }
      );
    }
  } catch {
    return Response.json({ detail: 'Invalid authentication token' }, { status: 401 });
  }

  try {
    const res = await fetch(`${BACKEND_URL}/telemetry/external-apis`, {
      headers,
      cache: 'no-store',
    });
    const data = await res.json();
    return Response.json(data, { status: res.status });
  } catch (err) {
    return Response.json(
      { detail: err.message || 'Failed to fetch developer telemetry from backend' },
      { status: 502 }
    );
  }
}
