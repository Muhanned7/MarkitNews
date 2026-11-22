const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

// RSK-001: mock-engine fat-tail / clustering / stress-correlation diagnostics.
// Service key comes from the environment only (no hard-coded fallback).
export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const tickers = searchParams.get('tickers');
  const qs = tickers ? `?tickers=${encodeURIComponent(tickers)}` : '';

  try {
    const res = await fetch(`${BACKEND_URL}/mock/diagnostics${qs}`, {
      headers: {
        'Content-Type': 'application/json',
        'x-service-key': process.env.INTERNAL_SERVICE_KEY || ''
      },
      cache: 'no-store'
    });
    const data = await res.json();
    return Response.json(data, { status: res.status });
  } catch (err) {
    return Response.json({ error: err.message || 'Failed to connect to backend' }, { status: 502 });
  }
}
