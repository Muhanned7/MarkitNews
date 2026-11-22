const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export async function POST(request) {
    try {
        const body = await request.json();
        const res = await fetch(`${BACKEND_URL}/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await res.json();
        return Response.json(data, { status: res.status });
    } catch (err) {
        return Response.json({ detail: err.message || 'Failed to connect to backend' }, { status: 502 });
    }
}
