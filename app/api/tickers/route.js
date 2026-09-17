import { index } from '@/lib/pinecone';
import { getEmbedding } from '@/lib/embeddings';

const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export async function GET() {
    try {
        const res = await fetch(`${BACKEND_URL}/tickers`);
        const data = await res.json();
        return Response.json(data);
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
            await fetch(`${BACKEND_URL}/tickers`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    symbol: symbolToStore,
                    name: company.name,
                    description: company.description || null,
                    sector: company.sector || null,
                    industry: company.industry || company.finnhubIndustry || null
                })
            });

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

                await fetch(`${BACKEND_URL}/tickers/${encodeURIComponent(symbolToStore)}/embedding`, {
                    method: 'PATCH'
                });
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
