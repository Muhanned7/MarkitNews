const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

const FALLBACK_PACKAGES = {
    currency: 'USD',
    stripe_mode: 'sandbox_checkout',
    packages: [
        {
            id: 'free',
            name: 'Starter Free',
            kind: 'subscription',
            tier: 'free',
            price_usd: 0,
            price_cents: 0,
            billing_interval: 'forever',
            badge: 'Current Default',
            tagline: 'Essential market monitoring and watchlist tracking.',
            description: 'Track your favorite companies, follow live market news, and browse ticker snapshots.',
            capabilities: [
                'Real-Time Market News Feed',
                'Personal Company Watchlist Tracking',
                'Global Ticker Search & Sector Snapshots',
                'Preview Demo Analysis Reports',
            ],
        },
        {
            id: 'pro_monthly',
            name: 'Pro Package',
            kind: 'subscription',
            tier: 'pro',
            price_usd: 19,
            price_cents: 1900,
            billing_interval: 'month',
            badge: 'Recommended',
            tagline: 'Full autonomous multi-agent intelligence for every company you track.',
            description:
                'Unlock deep 6-agent consensus equity research, live SEC 10-K & Wikipedia supply-chain footprint discovery, cross-perspective contradiction alerts, and quantitative position sizing.',
            capabilities: [
                'Agentic AI Analysis for Tracked Companies (News, Sentiment, Fundamentals, Technical, Equity & Risk Agents)',
                'Autonomous Corporate Footprint & Tier-1 Supplier Discovery (SEC 10-K + Wikipedia + Web Verification)',
                'Contradiction Radar (Western Wires vs. Local On-Ground Hub Press)',
                'Quantitative Factor Research (QRA) & Portfolio Position Sizing',
                'Priority AI Synthesis & Guardrail-Verified Citations',
            ],
        },
    ],
};

export async function GET() {
    try {
        const res = await fetch(`${BACKEND_URL}/billing/packages`, { cache: 'no-store' });
        if (res.ok) {
            const data = await res.json();
            return Response.json(data);
        }
    } catch (err) {
        // Fallback when backend is offline in local dev
    }
    return Response.json(FALLBACK_PACKAGES);
}
