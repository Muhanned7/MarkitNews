import { requireProxyAuthHeaders } from '@/lib/serverAuth';

const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export async function POST(request, { params }) {
    const { headers, errorResponse } = requireProxyAuthHeaders(request);
    if (errorResponse) return errorResponse;

    const resolvedParams = await params;
    const ticker = resolvedParams.ticker;
    const url = new URL(request.url);
    const nocache = url.searchParams.get('nocache') || '';
    const backendUrl = `${BACKEND_URL}/analyse/${ticker}${nocache ? `?nocache=${nocache}` : ''}`;

    try {
        const res = await fetch(backendUrl, {
            method: 'POST',
            headers
        });
        const data = await res.json();
        return Response.json(data, { status: res.status });
    } catch (err) {
        return Response.json({ detail: err.message || 'Failed to connect to backend' }, { status: 502 });
    }
}
