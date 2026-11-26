import { requireProxyAuthHeaders, buildClearAuthCookieHeader } from '@/lib/serverAuth';

const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export async function GET(request) {
  const { headers, token, errorResponse } = requireProxyAuthHeaders(request);
  if (errorResponse) return errorResponse;

  try {
    const res = await fetch(`${BACKEND_URL}/billing/wallet`, {
      headers,
      cache: 'no-store',
    });

    if (res.status === 401) {
      const respHeaders = new Headers({ 'Content-Type': 'application/json' });
      respHeaders.append('Set-Cookie', buildClearAuthCookieHeader());
      return new Response(JSON.stringify({ authenticated: false, detail: 'Session expired' }), {
        status: 401,
        headers: respHeaders,
      });
    }

    const wallet = res.ok ? await res.json() : {};
    const membership = wallet.membership || {};
    let email = wallet.email || null;
    let userId = wallet.user_id || null;
    try {
      const payloadB64 = token.split('.')[1];
      const decoded = JSON.parse(Buffer.from(payloadB64, 'base64url').toString('utf8'));
      email = email || decoded.email || null;
      userId = userId || (decoded.sub ? Number(decoded.sub) : null);
    } catch {}

    return Response.json({
      authenticated: true,
      id: userId,
      email,
      plan_code: membership.tier || wallet.plan_code || 'free',
      plan_name: membership.plan_name || wallet.plan_name || 'Starter Free',
      is_pro: Boolean(membership.is_pro),
      has_agentic_access: Boolean(membership.is_pro || membership.permissions?.agentic_company_analysis),
      capabilities: membership.capabilities || [],
    });
  } catch (err) {
    return Response.json({ detail: err.message || 'Failed to verify session' }, { status: 502 });
  }
}
