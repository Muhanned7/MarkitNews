import { requireProxyAuthHeaders } from '@/lib/serverAuth';

const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export async function GET(request) {
    const { headers, errorResponse } = requireProxyAuthHeaders(request);
    if (errorResponse) return errorResponse;

    try {
        const res = await fetch(`${BACKEND_URL}/watchlist`, { headers, cache: 'no-store' });
        const data = await res.json();
        return Response.json(data, { status: res.status });
    } catch (err) {
        return Response.json({ error: err.message || 'Failed to connect to backend' }, { status: 502 });
    }
}

export async function POST(request) {
    const { headers, errorResponse } = requireProxyAuthHeaders(request);
    if (errorResponse) return errorResponse;

    try {
        const body = await request.json();
        const res = await fetch(`${BACKEND_URL}/watchlist`, {
            method: 'POST',
            headers,
            body: JSON.stringify(body)
        });
        const data = await res.json();
        return Response.json(data, { status: res.status });
    } catch (err) {
        return Response.json({ error: err.message || 'Failed to connect to backend' }, { status: 502 });
    }
}

export async function DELETE(request) {
    const { headers, errorResponse } = requireProxyAuthHeaders(request);
    if (errorResponse) return errorResponse;

    try {
        const body = await request.json();
        const res = await fetch(`${BACKEND_URL}/watchlist`, {
            method: 'DELETE',
            headers,
            body: JSON.stringify(body)
        });
        const data = await res.json();
        return Response.json(data, { status: res.status });
    } catch (err) {
        return Response.json({ error: err.message || 'Failed to connect to backend' }, { status: 502 });
    }
}
