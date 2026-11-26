import { requireProxyAuthHeaders } from '@/lib/serverAuth';
const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export async function POST(request) {
    const { headers: _authHeaders, errorResponse: _authErr } = requireProxyAuthHeaders(request);
    if (_authErr) return _authErr;
    const auth = _authHeaders.Authorization;, { status: 401 });
    }
    try {
        const body = await request.json();
        const res = await fetch(`${BACKEND_URL}/billing/checkout`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Authorization: auth,
            },
            body: JSON.stringify(body),
        });
        const data = await res.json();
        return Response.json(data, { status: res.status });
    } catch (err) {
        return Response.json({ detail: err.message || 'Failed to connect to billing service' }, { status: 502 });
    }
}
