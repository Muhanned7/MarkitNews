import { tagSectors } from './sectorTagger.js'

function hashStr(str) {
  let h = 0
  for (let i = 0; i < str.length; i++) {
    h = (Math.imul(31, h) + str.charCodeAt(i)) | 0
  }
  return Math.abs(h).toString(16)
}

// Simulated macro news pool (explicitly labeled as simulated mock data, never credited to real news outlets)
const MACRO_NEWS_POOL = [
  {
    headline: 'Central Bank Holds Benchmark Policy Rate Steady as Core Inflation Moderates',
    summary: 'Policymakers reiterate data-dependent stance, citing balanced labor market conditions and moderating core inflation prints.',
    source: 'FinnWinn Simulated Wire (Demo)',
    url: '#simulated-macro-1',
    sectors: ['Financials', 'Macro'],
    score: 7,
    sentiment: 'neutral',
    confidence: 0.85,
    rationale: 'Rate stability reduces borrowing uncertainty across equity benchmarks.'
  },
  {
    headline: 'Large-Cap Equity Benchmarks Advance on Semiconductor & Cloud Infrastructure Demand',
    summary: 'Technology and industrial components led session gains following constructive capital-expenditure commentary.',
    source: 'FinnWinn Simulated Wire (Demo)',
    url: '#simulated-macro-2',
    sectors: ['Technology', 'Financials'],
    score: 8,
    sentiment: 'bullish',
    confidence: 0.84,
    rationale: 'Broad index participation reflects institutional risk appetite.'
  },
  {
    headline: 'Treasury Yields Ease Following Tame Wholesale Price Report',
    summary: 'Intermediate-duration yields declined modestly after producer price figures printed inline with consensus forecasts.',
    source: 'FinnWinn Simulated Wire (Demo)',
    url: '#simulated-macro-3',
    sectors: ['Financials', 'Macro'],
    score: 7,
    sentiment: 'bullish',
    confidence: 0.82,
    rationale: 'Lower discount-rate pressure supports long-duration equity valuations.'
  }
];

const TICKER_DATA = {
  AAPL: {
    name: 'Apple Inc.',
    sector: 'Technology',
    themes: [
      { trigger: 'services', headline: 'Apple Services Revenue Expands on App Ecosystem and Cloud Subscriptions (Simulated Demo)', sentiment: 'bullish', score: 8, rationale: 'High-margin recurring services revenue supports gross margin durability.' },
      { trigger: 'ai', headline: 'Apple Integrates On-Device Neural Engine Features Across Flagship Hardware Lineup (Simulated Demo)', sentiment: 'bullish', score: 8, rationale: 'On-device AI integration reinforces hardware upgrade cycles.' },
      { trigger: 'supply', headline: 'Apple Diversifies Final Assembly Capacity Across India and Vietnam Manufacturing Hubs (Simulated Demo)', sentiment: 'bullish', score: 7, rationale: 'Multi-region assembly reduces single-hub supply chain concentration.' }
    ]
  },
  NVDA: {
    name: 'NVIDIA Corporation',
    sector: 'Technology',
    themes: [
      { trigger: 'datacenter', headline: 'NVIDIA Blackwell AI Rack Shipments Ramp Across Hyperscale Cloud Data Centers (Simulated Demo)', sentiment: 'bullish', score: 9, rationale: 'Full-stack data center systems drive sustained gross margin and revenue expansion.' },
      { trigger: 'packaging', headline: 'TSMC CoWoS Advanced Packaging Capacity Expansion Eases NVIDIA Accelerator Lead Times (Simulated Demo)', sentiment: 'bullish', score: 8, rationale: 'Expanded foundry packaging throughput converts backlog into quarterly shipments.' }
    ]
  },
  MSFT: {
    name: 'Microsoft Corporation',
    sector: 'Technology',
    themes: [
      { trigger: 'azure', headline: 'Microsoft Azure Cloud Workloads Expand on Enterprise AI Infrastructure Demand (Simulated Demo)', sentiment: 'bullish', score: 8, rationale: 'Enterprise cloud migration supports recurring commercial revenue.' },
      { trigger: 'copilot', headline: 'Microsoft Commercial Productivity Suite Adoption Lifts Seat ARPU (Simulated Demo)', sentiment: 'bullish', score: 8, rationale: 'Incremental software seat monetization expands operating leverage.' }
    ]
  },
  TSLA: {
    name: 'Tesla, Inc.',
    sector: 'Consumer',
    themes: [
      { trigger: 'energy', headline: 'Tesla Megapack Grid Storage Deployments Expand Quarterly Margin Contribution (Simulated Demo)', sentiment: 'bullish', score: 8, rationale: 'Utility-scale stationary storage diversifies earnings beyond automotive deliveries.' },
      { trigger: 'deliveries', headline: 'Tesla Global Vehicle Production Balances Regional Pricing and Factory Utilization (Simulated Demo)', sentiment: 'neutral', score: 6, rationale: 'Cost reductions partially offset competitive EV pricing pressure.' }
    ]
  },
  GOOGL: {
    name: 'Alphabet Inc.',
    sector: 'Technology',
    themes: [
      { trigger: 'cloud', headline: 'Alphabet Cloud Operating Margins Expand on Custom TPU Infrastructure Efficiency (Simulated Demo)', sentiment: 'bullish', score: 8, rationale: 'Proprietary accelerator silicon lowers inference cost per query.' }
    ]
  },
  AMZN: {
    name: 'Amazon.com, Inc.',
    sector: 'Consumer',
    themes: [
      { trigger: 'aws', headline: 'Amazon AWS and Regional Fulfillment Network Post Operating Margin Gains (Simulated Demo)', sentiment: 'bullish', score: 8, rationale: 'Fulfillment regionalization lowers outbound shipping cost per unit.' }
    ]
  },
  META: {
    name: 'Meta Platforms, Inc.',
    sector: 'Technology',
    themes: [
      { trigger: 'ads', headline: 'Meta AI Ad Ranking Models Drive Higher Conversion Rates Across Reels & Feed (Simulated Demo)', sentiment: 'bullish', score: 8, rationale: 'Improved ad targeting increases average price per ad impression.' }
    ]
  },
  JPM: {
    name: 'JPMorgan Chase & Co.',
    sector: 'Financials',
    themes: [
      { trigger: 'nii', headline: 'JPMorgan Reports Resilient Net Interest Income and Investment Banking Advisory Fees (Simulated Demo)', sentiment: 'bullish', score: 8, rationale: 'Diversified fee and net interest revenue supports capital ratios.' }
    ]
  },
  AMD: {
    name: 'Advanced Micro Devices, Inc.',
    sector: 'Technology',
    themes: [
      { trigger: 'epyc', headline: 'AMD EPYC Server and Instinct Accelerator Deployments Grow Across Enterprise Data Centers (Simulated Demo)', sentiment: 'bullish', score: 8, rationale: 'Data center silicon adoption expands enterprise market share.' }
    ]
  }
};

function generateTickerArticles(ticker) {
  const upper = ticker.toUpperCase().trim();
  const profile = TICKER_DATA[upper];
  if (!profile || !profile.themes) {
    // NEVER fabricate template articles for unknown or gibberish symbols (e.g. "zzqqxx")
    return [];
  }

  return profile.themes.map(theme => ({
    headline: theme.headline,
    summary: `${profile.name}: ${theme.rationale}`,
    source: 'FinnWinn Simulated Wire (Demo)',
    url: `https://finance.yahoo.com/quote/${encodeURIComponent(upper)}`,
    sectors: tagSectors(`${theme.headline} ${profile.sector}`),
    score: theme.score,
    sentiment: theme.sentiment,
    confidence: 0.85,
    rationale: theme.rationale
  }));
}

export function getMockNews({ tickers = [], query = '', page = 1, limit = 6 } = {}) {
  const activeTickers = (Array.isArray(tickers) ? tickers : [tickers])
    .filter(t => typeof t === 'string' && t.trim().length > 0)
    .map(t => t.trim().toUpperCase());

  let combinedPool = [];
  const cleanQuery = (query || '').trim();
  const lowerQuery = cleanQuery.toLowerCase();

  if (activeTickers.length === 0) {
    if (cleanQuery && lowerQuery !== 'market news') {
      const upperQ = cleanQuery.toUpperCase();
      if (TICKER_DATA[upperQ]) {
        combinedPool = generateTickerArticles(upperQ);
      } else {
        // Filter curated pools by actual query substring match; return [] if gibberish ("zzqqxx")
        const allKnown = [
          ...MACRO_NEWS_POOL,
          ...Object.keys(TICKER_DATA).flatMap(t => generateTickerArticles(t))
        ];
        combinedPool = allKnown.filter(
          item =>
            item.headline.toLowerCase().includes(lowerQuery) ||
            item.summary.toLowerCase().includes(lowerQuery)
        );
      }
    } else {
      combinedPool = [...MACRO_NEWS_POOL];
    }
  } else {
    const perTickerArticles = activeTickers.flatMap(t => generateTickerArticles(t));
    combinedPool = cleanQuery
      ? perTickerArticles.filter(
          item =>
            item.headline.toLowerCase().includes(lowerQuery) ||
            item.summary.toLowerCase().includes(lowerQuery)
        )
      : perTickerArticles;
  }

  const seenHeadlines = new Set();
  const uniqueArticles = [];
  for (const item of combinedPool) {
    if (!seenHeadlines.has(item.headline)) {
      seenHeadlines.add(item.headline);
      uniqueArticles.push(item);
    }
  }

  const now = Date.now();
  const enrichedArticles = uniqueArticles.map((article, idx) => {
    const minutesAgo = 15 + idx * 25;
    const publishedDate = new Date(now - minutesAgo * 60 * 1000).toISOString();
    const id = hashStr(article.headline + article.source + idx);

    return {
      id,
      headline: article.headline,
      summary: article.summary,
      source: article.source,
      url: article.url,
      published: publishedDate,
      sectors: article.sectors || tagSectors(`${article.headline} ${article.summary}`),
      score: article.score || 7,
      sentiment: article.sentiment || 'neutral',
      confidence: article.confidence || 0.85,
      rationale: article.rationale,
      tickers: activeTickers,
      is_mock: true
    };
  });

  const pageNum = Math.max(1, parseInt(page, 10) || 1);
  const limitNum = Math.max(1, parseInt(limit, 10) || 6);
  const startIndex = (pageNum - 1) * limitNum;
  const paginatedArticles = enrichedArticles.slice(startIndex, startIndex + limitNum);
  const hasMore = startIndex + limitNum < enrichedArticles.length;

  return {
    articles: paginatedArticles,
    page: pageNum,
    limit: limitNum,
    hasMore,
    total: enrichedArticles.length
  };
}
