import { buildAuthCookieHeader, getFrontendServiceHeaders } from '@/lib/serverAuth';

const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export async function POST(request) {
    try {
        const body = await request.json();
        const res = await fetch(`${BACKEND_URL}/auth/login`, {
            method: 'POST',
            headers: getFrontendServiceHeaders(),
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (!res.ok) {
            return Response.json(data, { status: res.status });
        }

        const token = data.access_token || data.token;
        const headers = new Headers({ 'Content-Type': 'application/json' });
        if (token) {
            headers.append('Set-Cookie', buildAuthCookieHeader(token));
        }

        return new Response(
            JSON.stringify({
                authenticated: true,
                email: data.email || body.email,
                user_id: data.user_id ?? null,
                message: 'Signed in successfully'
            }),
            { status: 200, headers }
        );
    } catch (err) {
        return Response.json({ detail: err.message || 'Failed to connect to backend' }, { status: 502 });
    }
}
