import { index } from '@/lib/pinecone';
import { getEmbedding } from '@/lib/embeddings';

const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
const INTERNAL_SERVICE_KEY = process.env.INTERNAL_SERVICE_KEY;

const POPULAR_TICKERS = [
    { symbol: 'AAPL', name: 'Apple Inc.', sector: 'Technology' },
    { symbol: 'MSFT', name: 'Microsoft Corporation', sector: 'Software' },
    { symbol: 'NVDA', name: 'NVIDIA Corporation', sector: 'Semiconductors' },
    { symbol: 'TSLA', name: 'Tesla, Inc.', sector: 'Automotive / AI' },
    { symbol: 'GOOGL', name: 'Alphabet Inc.', sector: 'Internet / AI' },
    { symbol: 'AMZN', name: 'Amazon.com, Inc.', sector: 'E-Commerce / Cloud' },
    { symbol: 'META', name: 'Meta Platforms, Inc.', sector: 'Social Media / AI' },
    { symbol: 'JPM', name: 'JPMorgan Chase & Co.', sector: 'Financials' },
    { symbol: 'BAC', name: 'Bank of America Corp.', sector: 'Financials' },
    { symbol: 'WMT', name: 'Walmart Inc.', sector: 'Retail' },
    { symbol: 'NFLX', name: 'Netflix, Inc.', sector: 'Entertainment' },
    { symbol: 'AMD', name: 'Advanced Micro Devices, Inc.', sector: 'Semiconductors' },
    { symbol: 'DIS', name: 'The Walt Disney Company', sector: 'Entertainment' },
    { symbol: 'COIN', name: 'Coinbase Global, Inc.', sector: 'Crypto / Fintech' },
    { symbol: 'UBER', name: 'Uber Technologies, Inc.', sector: 'Mobility' }
];

function toTitleCase(str) {
    if (!str) return '';
    return str.toLowerCase().replace(/(?:^|\s|\/)\w/g, m => m.toUpperCase());
}

export async function GET(request) {
    try {
        const url = new URL(request.url);
        const q = url.searchParams.get('q')?.toLowerCase()?.trim();

        let dbTickers = [];
        try {
            const res = await fetch(`${BACKEND_URL}/tickers`);
            if (res.ok) {
                const data = await res.json();
                dbTickers = data.tickers || [];
            }
        } catch (e) {
            // Backend fallback
        }

        const map = new Map();
        for (const t of POPULAR_TICKERS) {
            map.set(t.symbol.toUpperCase(), {
                symbol: t.symbol.toUpperCase(),
                name: t.name,
                sector: toTitleCase(t.sector)
            });
        }
        for (const t of dbTickers) {
            if (t.symbol) {
                const sym = t.symbol.toUpperCase();
                let name = t.name || sym;
                if (sym === 'AAOI' && (name === 'Applied Opt' || !name)) {
                    name = 'Applied Optoelectronics, Inc.';
                }
                const sector = toTitleCase(t.sector);
                if (!map.has(sym)) {
                    map.set(sym, { symbol: sym, name: name, sector: sector });
                } else {
                    const existing = map.get(sym);
                    if (existing.name === sym || existing.name === 'Applied Opt') {
                        existing.name = name;
                    }
                    if (!existing.sector && sector) {
                        existing.sector = sector;
                    }
                }
            }
        }

        const all = Array.from(map.values());

        if (!q) {
            return Response.json({ tickers: all.slice(0, 30) });
        }

        const popularSet = new Set(POPULAR_TICKERS.map(p => p.symbol.toUpperCase()));
        const scored = all.map(t => {
            const sym = t.symbol.toLowerCase();
            const nm = (t.name || '').toLowerCase();
            let score = 0;
            if (sym === q) score = 100;
            else if (sym.startsWith(q)) score = 90;
            else if (nm.startsWith(q)) score = 70;
            else if (sym.includes(q)) score = 50;
            else if (nm.includes(q)) score = 30;

            if (score > 0 && popularSet.has(t.symbol.toUpperCase())) {
                score += 5;
            }

            return { ticker: t, score };
        }).filter(item => item.score > 0);

        scored.sort((a, b) => b.score - a.score || a.ticker.symbol.localeCompare(b.ticker.symbol));
        const results = scored.slice(0, 6).map(s => s.ticker);

        return Response.json({ tickers: results });
    } catch (err) {
        return Response.json({ error: err.message }, { status: 502 });
    }
}

export async function POST(request) {
    try {
        const body = await request.json();
        const targetSymbol = (body.symbol || body.ticker)?.toUpperCase();

        if (!targetSymbol) {
            return Response.json({ error: 'Symbol is required' }, { status: 400 });
        }

        // Filter out already existing ones
        const existingRes = await fetch(`${BACKEND_URL}/tickers`);
        const existingData = await existingRes.json();
        const existingSet = new Set((existingData.tickers || []).map(r => r.symbol));

        if (existingSet.has(targetSymbol)) {
            return Response.json({
                message: 'Already in DB',
                alreadyInDB: `Already in DB ${targetSymbol}`,
                newProcessed: null
            });
        }

        try {
            const res = await fetch(
                `https://finnhub.io/api/v1/stock/profile2?symbol=${targetSymbol}&token=${process.env.FINNHUB_API}`
            );
            const company = await res.json();

            if (!company || !company.name) {
                return Response.json({ error: `Ticker ${targetSymbol} not found on Finnhub` }, { status: 404 });
            }

            const symbolToStore = (company.ticker || targetSymbol).toUpperCase();

            // Save ticker to PostgreSQL via FastAPI backend
            const tRes = await fetch(`${BACKEND_URL}/tickers`, {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'X-Service-Key': INTERNAL_SERVICE_KEY
                },
                body: JSON.stringify({
                    symbol: symbolToStore,
                    name: company.name,
                    description: company.description || null,
                    sector: company.sector || null,
                    industry: company.industry || company.finnhubIndustry || null
                })
            });
            if (!tRes.ok) console.warn(`Ticker save warning: status ${tRes.status}`);

            const textToEmbed = `${company.name} ${company.sector || ''} ${company.industry || company.finnhubIndustry || ''} ${company.description || ''}`.trim();

            if (textToEmbed.length > 30) {
                const embedding = await getEmbedding(textToEmbed);

                await index.namespace('tickers').upsert({
                    records: [{
                        id: symbolToStore,
                        values: Array.from(embedding),
                        metadata: {
                            symbol: symbolToStore,
                            name: company.name,
                            sector: company.sector,
                            industry: company.industry || company.finnhubIndustry
                        }
                    }]
                });

                const embRes = await fetch(`${BACKEND_URL}/tickers/${encodeURIComponent(symbolToStore)}/embedding`, {
                    method: 'PATCH',
                    headers: { 'X-Service-Key': INTERNAL_SERVICE_KEY }
                });
                if (!embRes.ok) console.warn(`Embedding status update warning: status ${embRes.status}`);
            }

            return Response.json({
                message: "Saved to DB",
                newProcessed: symbolToStore
            });
        } catch (err) {
            console.error(`❌ Error processing ${targetSymbol}:`, err.message);
            return Response.json({ error: err.message }, { status: 500 });
        }
    } catch (err) {
        console.error(err);
        return Response.json({ error: err.message }, { status: 500 });
    }
}
