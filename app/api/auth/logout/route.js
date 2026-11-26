import { buildClearAuthCookieHeader } from '@/lib/serverAuth';

export async function POST() {
  const headers = new Headers({ 'Content-Type': 'application/json' });
  headers.append('Set-Cookie', buildClearAuthCookieHeader());
  return new Response(JSON.stringify({ authenticated: false, message: 'Signed out' }), {
    status: 200,
    headers,
  });
}
