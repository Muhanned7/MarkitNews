const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
const INTERNAL_SERVICE_KEY = process.env.INTERNAL_SERVICE_KEY || '';

function getAuthHeaders(request) {
  const auth = request.headers.get('authorization');
  const headers = {
    'Content-Type': 'application/json',
    'x-service-key': INTERNAL_SERVICE_KEY
  };
  if (auth) {
    headers['Authorization'] = auth;
  }
  return headers;
}

export async function GET(request, context) {
  try {
    const params = await context.params;
    const slugPath = Array.isArray(params?.slug) ? params.slug.join('/') : '';
    const url = new URL(request.url);
    const targetUrl = `${BACKEND_URL}/research/${slugPath}${url.search}`;

    const res = await fetch(targetUrl, {
      headers: getAuthHeaders(request),
      cache: 'no-store'
    });

    const contentType = res.headers.get('content-type') || '';
    if (contentType.includes('text/csv') || slugPath.endsWith('.csv')) {
      const text = await res.text();
      return new Response(text, {
        status: res.status,
        headers: {
          'Content-Type': 'text/csv; charset=utf-8',
          'Content-Disposition': 'attachment; filename="research_panel_pit.csv"'
        }
      });
    }

    const data = await res.json();
    return Response.json(data, { status: res.status });
  } catch (err) {
    return Response.json({ error: err.message || 'Failed to connect to research backend' }, { status: 502 });
  }
}

export async function POST(request, context) {
  try {
    const params = await context.params;
    const slugPath = Array.isArray(params?.slug) ? params.slug.join('/') : '';
    const url = new URL(request.url);
    const body = await request.json();

    const res = await fetch(`${BACKEND_URL}/research/${slugPath}${url.search}`, {
      method: 'POST',
      headers: getAuthHeaders(request),
      body: JSON.stringify(body)
    });
    const data = await res.json();
    return Response.json(data, { status: res.status });
  } catch (err) {
    return Response.json({ error: err.message || 'Failed to connect to research backend' }, { status: 502 });
  }
}

export async function PATCH(request, context) {
  try {
    const params = await context.params;
    const slugPath = Array.isArray(params?.slug) ? params.slug.join('/') : '';
    const body = await request.json();

    const res = await fetch(`${BACKEND_URL}/research/${slugPath}`, {
      method: 'PATCH',
      headers: getAuthHeaders(request),
      body: JSON.stringify(body)
    });
    const data = await res.json();
    return Response.json(data, { status: res.status });
  } catch (err) {
    return Response.json({ error: err.message || 'Failed to connect to research backend' }, { status: 502 });
  }
}
