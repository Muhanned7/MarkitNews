import { requireProxyAuthHeaders } from '@/lib/serverAuth';
const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

// RSK-014 tear-sheet export adapter (CSV or HTML).
function getAuthHeaders(request) {
  const { headers } = requireProxyAuthHeaders(request);
  return headers;
}

export async function GET(request, { params }) {
  const { errorResponse: _authErr } = requireProxyAuthHeaders(request);
  if (_authErr) return _authErr;
  const { id } = await params;
  const qs = new URL(request.url).search;
  try {
    const res = await fetch(`${BACKEND_URL}/portfolios/${id}/tear-sheet/export${qs}`, {
      cache: 'no-store',
      headers: getAuthHeaders(request),
    });
    const text = await res.text();
    const contentType = res.headers.get('content-type') || 'text/csv; charset=utf-8';
    const disposition = res.headers.get('content-disposition') || `attachment; filename="portfolio_${id}_morning_tear_sheet.csv"`;
    return new Response(text, {
      status: res.status,
      headers: {
        'Content-Type': contentType,
        'Content-Disposition': disposition,
      },
    });
  } catch (err) {
    return Response.json({ error: err.message || 'Failed to connect to backend' }, { status: 502 });
  }
}
