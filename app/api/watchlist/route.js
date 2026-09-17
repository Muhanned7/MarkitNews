const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export async function GET(request) {
    const auth = request.headers.get('authorization');
    if (!auth) return Response.json({ error: 'Unauthorized' }, { status: 401 });

    try {
        const res = await fetch(`${BACKEND_URL}/watchlist`, {
            headers: { 'Authorization': auth }
        });
        const data = await res.json();
        return Response.json(data, { status: res.status });
    } catch (err) {
        return Response.json({ error: err.message || 'Failed to connect to backend' }, { status: 502 });
    }
}

export async function POST(request) {
    const auth = request.headers.get('authorization');
    if (!auth) return Response.json({ error: 'Unauthorized' }, { status: 401 });

    try {
        const body = await request.json();
        const res = await fetch(`${BACKEND_URL}/watchlist`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': auth
            },
            body: JSON.stringify(body)
        });
        const data = await res.json();
        return Response.json(data, { status: res.status });
    } catch (err) {
        return Response.json({ error: err.message || 'Failed to connect to backend' }, { status: 502 });
    }
}

export async function DELETE(request) {
    const auth = request.headers.get('authorization');
    if (!auth) return Response.json({ error: 'Unauthorized' }, { status: 401 });

    try {
        const body = await request.json();
        const res = await fetch(`${BACKEND_URL}/watchlist`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': auth
            },
            body: JSON.stringify(body)
        });
        const data = await res.json();
        return Response.json(data, { status: res.status });
    } catch (err) {
        return Response.json({ error: err.message || 'Failed to connect to backend' }, { status: 502 });
    }
}