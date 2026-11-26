import { requireProxyAuthHeaders } from '@/lib/serverAuth';

const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export async function POST(request) {
    const { headers, errorResponse } = requireProxyAuthHeaders(request);
    if (errorResponse) return errorResponse;

    try {
        const body = await request.json();
        const res = await fetch(`${BACKEND_URL}/billing/confirm`, {
            method: 'POST',
            headers,
            body: JSON.stringify(body),
        });
        const data = await res.json();
        return Response.json(data, { status: res.status });
    } catch (err) {
        return Response.json({ detail: err.message || 'Failed to confirm payment with backend' }, { status: 502 });
    }
}
