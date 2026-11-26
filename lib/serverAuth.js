export const AUTH_COOKIE_NAME = 'mp_auth_token';

/**
 * Extracts the JWT from either the Authorization header or the httpOnly auth cookie.
 */
export function extractBearerToken(request) {
  const authHeader = request.headers.get('authorization');
  if (authHeader) {
    const parts = authHeader.trim().split(/\s+/);
    if (parts.length === 2 && parts[0].toLowerCase() === 'bearer' && parts[1]) {
      return parts[1];
    }
  }

  // NextRequest cookies API (when available)
  if (request.cookies && typeof request.cookies.get === 'function') {
    const cookieVal = request.cookies.get(AUTH_COOKIE_NAME)?.value;
    if (cookieVal) return cookieVal;
  }

  // Fallback raw Cookie header parsing
  const rawCookie = request.headers.get('cookie') || '';
  const match = rawCookie.match(new RegExp(`(?:^|;\\s*)${AUTH_COOKIE_NAME}=([^;]+)`));
  if (match && match[1]) {
    return decodeURIComponent(match[1]);
  }

  return null;
}

/**
 * Requires an authenticated user session (via httpOnly cookie or Bearer header)
 * and builds clean upstream headers for FastAPI. Never injects INTERNAL_SERVICE_KEY
 * for unauthenticated requests.
 */
export function requireProxyAuthHeaders(request, extraHeaders = {}) {
  const token = extractBearerToken(request);
  if (!token) {
    return {
      headers: null,
      token: null,
      errorResponse: Response.json(
        { detail: 'Authentication required. Please sign in.' },
        { status: 401 }
      ),
    };
  }
  return {
    token,
    errorResponse: null,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...extraHeaders,
    },
  };
}

export function buildAuthCookieHeader(token) {
  const isProd = process.env.NODE_ENV === 'production';
  const parts = [
    `${AUTH_COOKIE_NAME}=${encodeURIComponent(token)}`,
    'HttpOnly',
    'Path=/',
    'SameSite=Lax',
    `Max-Age=${7 * 24 * 60 * 60}`,
  ];
  if (isProd) parts.push('Secure');
  return parts.join('; ');
}

export function buildClearAuthCookieHeader() {
  const isProd = process.env.NODE_ENV === 'production';
  const parts = [
    `${AUTH_COOKIE_NAME}=`,
    'HttpOnly',
    'Path=/',
    'SameSite=Lax',
    'Max-Age=0',
  ];
  if (isProd) parts.push('Secure');
  return parts.join('; ');
}
