const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export async function POST(request) {
    const auth = request.headers.get('authorization');
    if (!auth) {
        return Response.json({ detail: 'Unauthorized' }, { status: 401 });
    }
    try {
        const body = await request.json();
        const res = await fetch(`${BACKEND_URL}/billing/confirm`, {
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
        return Response.json({ detail: err.message || 'Failed to confirm payment with backend' }, { status: 502 });
    }
}
