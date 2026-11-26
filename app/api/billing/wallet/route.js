import { requireProxyAuthHeaders } from '@/lib/serverAuth';

const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export async function GET(request) {
    const { headers, errorResponse } = requireProxyAuthHeaders(request);
    if (errorResponse) return errorResponse;

    try {
        const res = await fetch(`${BACKEND_URL}/billing/wallet`, {
            headers,
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
                has_active_capacity: false,
                capabilities: [
                    'Real-Time Market News Feed',
                    'Personal Company Watchlist Tracking',
                    'Global Ticker Search & Sector Snapshots',
                    'Preview Demo Analysis Reports',
                ],
                permissions: {
                    agentic_company_analysis: false,
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
