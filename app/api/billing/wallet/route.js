const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export async function GET(request) {
    const auth = request.headers.get('authorization');
    if (!auth) {
        return Response.json({ detail: 'Unauthorized' }, { status: 401 });
    }
    try {
        const res = await fetch(`${BACKEND_URL}/billing/wallet`, {
            headers: { Authorization: auth },
            cache: 'no-store',
        });
        const data = await res.json();
        return Response.json(data, { status: res.status });
    } catch (err) {
        return Response.json({
            membership: {
                tier: 'free',
                plan_name: 'Starter Free',
                status: 'free_tier',
                is_pro: false,
                has_active_capacity: true,
                capabilities: [
                    'Real-Time Market News Feed',
                    'Personal Company Watchlist Tracking',
                    'Global Ticker Search & Sector Snapshots',
                    'Preview Demo Analysis Reports',
                ],
                permissions: {
                    agentic_company_analysis: true,
                    live_footprint_discovery: false,
                    contradiction_radar: false,
                    quant_research_qra: false,
                },
            },
            transactions: [],
            offline_fallback: true,
        });
    }
}
