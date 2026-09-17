import { tagSectors } from './sectorTagger.js'

function hashStr(str) {
  let h = 0
  for (let i = 0; i < str.length; i++) {
    h = (Math.imul(31, h) + str.charCodeAt(i)) | 0
  }
  return Math.abs(h).toString(16)
}

// Pre-crafted pool of macro / broad market news
const MACRO_NEWS_POOL = [
  {
    headline: 'Federal Reserve Holds Benchmark Rate Steady as Inflation Progress Continues',
    summary: 'FOMC policymakers reiterate data-dependent stance, citing steady job market and gradual moderating of core PCE index.',
    source: 'Bloomberg',
    url: 'https://www.bloomberg.com/news/markets',
    sectors: ['Financials', 'Macro'],
    score: 8,
    sentiment: 'neutral',
    confidence: 0.94,
    rationale: 'Rate stability reduces borrowing uncertainty across equity benchmarks.'
  },
  {
    headline: 'S&P 500 & Nasdaq Hit Fresh Session Highs Led by Mega-Cap Tech Momentum',
    summary: 'Equities rallied into the afternoon session buoyed by robust semiconductor orders and optimistic forward guidance across cloud providers.',
    source: 'Reuters',
    url: 'https://www.reuters.com/markets',
    sectors: ['Technology', 'Financials'],
    score: 9,
    sentiment: 'bullish',
    confidence: 0.92,
    rationale: 'Broad-based index participation confirms institutional risk-on appetite.'
  },
  {
    headline: 'Treasury Yields Pull Back Slightly Following Tame Wholesale Inflation Print',
    summary: 'The 10-year Treasury yield slid 4 basis points to 4.21% after the producer price index came in below consensus expectations.',
    source: 'Financial Times',
    url: 'https://www.ft.com/markets',
    sectors: ['Financials', 'Macro'],
    score: 7,
    sentiment: 'bullish',
    confidence: 0.89,
    rationale: 'Lower yield pressures relieve valuation constraints for growth assets.'
  },
  {
    headline: 'Global Chip Demand Outpaces Projections on Enterprise AI Hardware Rollouts',
    summary: 'Foundries and packaging facilities operate near peak capacity as enterprise software firms accelerate multi-billion dollar capital expenditure cycles.',
    source: 'Wall Street Journal',
    url: 'https://www.wsj.com/tech',
    sectors: ['Technology'],
    score: 9,
    sentiment: 'bullish',
    confidence: 0.95,
    rationale: 'Secular capex expansion provides multi-quarter revenue visibility.'
  },
  {
    headline: 'Crude Oil Prices Fluctuate Near $78 Amid Middle East Logistics & OPEC Supply Checks',
    summary: 'Brent crude registered choppy trading as maritime transit disruptions met disciplined production quotas from OPEC+ member nations.',
    source: 'Reuters',
    url: 'https://www.reuters.com/energy',
    sectors: ['Energy', 'Macro'],
    score: 6,
    sentiment: 'neutral',
    confidence: 0.86,
    rationale: 'Geopolitical freight premiums offset by resilient non-OPEC barrel supply.'
  },
  {
    headline: 'Retail Consumer Spending Demonstrates Resilience Ahead of Quarterly Earnings',
    summary: 'Discretionary card spending metrics indicate steady household consumption, though shoppers show increased sensitivity to promotional pricing.',
    source: 'CNBC',
    url: 'https://www.cnbc.com/markets',
    sectors: ['Consumer', 'Macro'],
    score: 7,
    sentiment: 'bullish',
    confidence: 0.88,
    rationale: 'Consumer resilience cushions GDP growth projections against recession risks.'
  },
  {
    headline: 'European Central Bank Notes Inflation Deceleration, Hinting at Monetary Flex',
    summary: 'Governing council members observe consistent softening in wage growth indicators across the euro area.',
    source: 'Financial Times',
    url: 'https://www.ft.com/global-economy',
    sectors: ['Financials', 'Macro'],
    score: 6,
    sentiment: 'bullish',
    confidence: 0.84,
    rationale: 'Synchronized global rate easing narrative gains traction.'
  },
  {
    headline: 'VIX Volatility Index Dips Below Key Support as Systematic Funds Rebalance',
    summary: 'Equity volatility metrics fell to multi-month lows as systematic trend-followers and risk-parity funds increased equity allocations.',
    source: 'MarketWatch',
    url: 'https://www.marketwatch.com',
    sectors: ['Financials'],
    score: 7,
    sentiment: 'bullish',
    confidence: 0.91,
    rationale: 'Low implied volatility facilitates leveraged positioning and liquidity inflows.'
  },
  {
    headline: 'Biotech & Healthcare Equities Catch Bid on Breakthrough Phase 3 Clinical Outcomes',
    summary: 'Large-cap pharmaceutical and oncology innovators outpaced defensive benchmarks following positive regulatory designations.',
    source: 'Bloomberg',
    url: 'https://www.bloomberg.com/healthcare',
    sectors: ['Healthcare'],
    score: 8,
    sentiment: 'bullish',
    confidence: 0.9,
    rationale: 'High-margin drug approvals offer non-cyclical cash flow expansion.'
  },
  {
    headline: 'Commercial Real Estate Debt Refinancing Dynamics Draw Scrutiny from Regional Banks',
    summary: 'Regional banking institutions increase loan loss provisions prudently as maturities approach over the next two quarters.',
    source: 'Wall Street Journal',
    url: 'https://www.wsj.com/finance',
    sectors: ['Financials'],
    score: 4,
    sentiment: 'bearish',
    confidence: 0.87,
    rationale: 'Maturity walls create liquidity friction for vulnerable regional lenders.'
  },
  {
    headline: 'Dollar Index Stabilizes as Currency Traders Assess Central Bank Divergence',
    summary: 'The DXY index traded in a narrow corridor as foreign exchange participants balanced US economic resilience against G10 policy moves.',
    source: 'Reuters',
    url: 'https://www.reuters.com/currencies',
    sectors: ['Macro', 'Financials'],
    score: 5,
    sentiment: 'neutral',
    confidence: 0.82,
    rationale: 'Currency consolidation keeps cross-border export pricing steady.'
  },
  {
    headline: 'Clean Energy Infrastructure Inflows Surge Following Direct Tax Credit Monetization',
    summary: 'Renewable energy and grid battery developers secure accelerated private capital commitments following clear federal financing guidelines.',
    source: 'Bloomberg',
    url: 'https://www.bloomberg.com/green',
    sectors: ['Energy', 'Technology'],
    score: 8,
    sentiment: 'bullish',
    confidence: 0.89,
    rationale: 'Regulatory monetization pathways de-risk balance sheet expansion.'
  }
];

const TICKER_DATA = {
  AAPL: {
    name: 'Apple Inc.',
    sector: 'Technology',
    themes: [
      { trigger: 'services', headline: 'Apple Services Revenue Accelerates on Strong App Store and Cloud Subscriptions', sentiment: 'bullish', score: 9, rationale: 'High-margin recurrent subscription revenue improves gross margin durability.' },
      { trigger: 'ai', headline: 'Apple Expands Private Cloud AI Infrastructure and Siri Neural Engine Integration', sentiment: 'bullish', score: 8, rationale: 'Device ecosystem lock-in strengthens with proprietary on-device intelligence.' },
      { trigger: 'hardware', headline: 'iPhone Supply Chain Sources Report Robust Orders for Flagship Pro Models', sentiment: 'bullish', score: 8, rationale: 'Pro-tier ASP expansion supports annual gross margin expansion.' },
      { trigger: 'regulatory', headline: 'Apple Navigates Regulatory Frameworks for Alternative Digital App Marketplaces', sentiment: 'neutral', score: 6, rationale: 'Regional compliance measures expected to have minimal earnings drag.' }
    ]
  },
  NVDA: {
    name: 'NVIDIA Corporation',
    sector: 'Technology',
    themes: [
      { trigger: 'datacenter', headline: 'Nvidia Next-Gen Architecture Ramps Volume Production Across Cloud Hyperscalers', sentiment: 'bullish', score: 10, rationale: 'Compute architecture monopolization commands unprecedented gross margins.' },
      { trigger: 'software', headline: 'Nvidia CUDA and Enterprise AI Software Stack Expands ARR Milestone', sentiment: 'bullish', score: 9, rationale: 'Software licensing strengthens moat beyond raw silicon sales.' },
      { trigger: 'partners', headline: 'Global Sovereign AI Initiatives Contract Nvidia GPU Superclusters for Multi-Year Projects', sentiment: 'bullish', score: 9, rationale: 'Nation-state demand unlocks non-hyperscaler capital deployment.' },
      { trigger: 'supply', headline: 'Advanced CoWoS Packaging Capacity Expansions Clear Supply Bottlenecks for Nvidia', sentiment: 'bullish', score: 8, rationale: 'Supply throughput increases directly convert into higher quarterly shipment volume.' }
    ]
  },
  MSFT: {
    name: 'Microsoft Corp.',
    sector: 'Technology',
    themes: [
      { trigger: 'azure', headline: 'Microsoft Azure Cloud Growth Outpaces Estimates Fueled by Enterprise AI Deployments', sentiment: 'bullish', score: 9, rationale: 'Enterprise market share capture drives sustained 25%+ cloud growth.' },
      { trigger: 'copilot', headline: 'Microsoft Copilot Commercial Seat Adoption Gains Traction Among Fortune 500', sentiment: 'bullish', score: 8, rationale: 'Office 365 ARPU uplift yields expanding software operating leverage.' },
      { trigger: 'security', headline: 'Microsoft Unveils Security Copilot Upgrades to Mitigate Autonomous Cyber Threats', sentiment: 'bullish', score: 8, rationale: 'Integrated cybersecurity suite acts as an enterprise retention catalyst.' }
    ]
  },
  TSLA: {
    name: 'Tesla Inc.',
    sector: 'Consumer',
    themes: [
      { trigger: 'fsd', headline: 'Tesla Full Self-Driving V13 Achieves Critical Disengagement Milestones', sentiment: 'bullish', score: 9, rationale: 'Autonomous software progress unlocks potential high-margin robotaxi monetization.' },
      { trigger: 'energy', headline: 'Tesla Megapack Energy Storage Deployments Double Year-Over-Year', sentiment: 'bullish', score: 8, rationale: 'Utility-scale storage division delivers exponential operating profit contribution.' },
      { trigger: 'deliveries', headline: 'Tesla Global Quarterly Delivery Numbers Meet Upgraded Wall Street Expectations', sentiment: 'neutral', score: 7, rationale: 'Production efficiencies balance pricing adjustments across key international markets.' },
      { trigger: 'robotics', headline: 'Tesla Optimus Humanoid Robot Pilots Integration in Manufacturing Assembly Lines', sentiment: 'bullish', score: 8, rationale: 'Automation innovations promise drastic reduction in long-term automotive assembly cost.' }
    ]
  },
  GOOGL: {
    name: 'Alphabet Inc.',
    sector: 'Technology',
    themes: [
      { trigger: 'gemini', headline: 'Alphabet Deploys Gemini 2.5 Multi-Modal Enhancements Across Search & Workspace', sentiment: 'bullish', score: 9, rationale: 'Search monetization remains insulated with superior generative capabilities.' },
      { trigger: 'cloud', headline: 'Google Cloud Accelerates Profitability as Custom TPU Infrastructure Scales', sentiment: 'bullish', score: 8, rationale: 'In-house TPU accelerators lower inference costs, expanding operating margin.' },
      { trigger: 'youtube', headline: 'YouTube Ad Revenue Beats Forecasts with High-Engagement Shorts Monetization', sentiment: 'bullish', score: 8, rationale: 'Creator monetization flywheel outcompetes legacy social video formats.' }
    ]
  },
  AMZN: {
    name: 'Amazon.com Inc.',
    sector: 'Consumer',
    themes: [
      { trigger: 'aws', headline: 'Amazon AWS Secures Multi-Billion Dollar Enterprise Workloads with Bedrock Platform', sentiment: 'bullish', score: 9, rationale: 'Cloud re-acceleration restores AWS operating margin leadership.' },
      { trigger: 'logistics', headline: 'Amazon Regional Fulfillment Optimization Drives Record Prime Delivery Speeds & Lower Unit Costs', sentiment: 'bullish', score: 8, rationale: 'Inbound supply chain density generates direct cost savings per package.' },
      { trigger: 'ads', headline: 'Amazon Advertising Services Revenue Surges on Sponsored Video Placement', sentiment: 'bullish', score: 8, rationale: 'High-margin digital ad business offsets consumer discretionary fluctuations.' }
    ]
  },
  META: {
    name: 'Meta Platforms',
    sector: 'Technology',
    themes: [
      { trigger: 'llama', headline: 'Meta Open-Source Llama Ecosystem Gains Industry Standards Adoption', sentiment: 'bullish', score: 9, rationale: 'Dominant open-weights standard prevents vendor lock-in by proprietary competitors.' },
      { trigger: 'ads', headline: 'Meta Advantage+ AI Advertising Tools Drive Record RoAS for E-Commerce Merchants', sentiment: 'bullish', score: 9, rationale: 'Recommendation algorithm yields higher ad conversions and higher pricing power.' }
    ]
  },
  JPM: {
    name: 'JPMorgan Chase & Co.',
    sector: 'Financials',
    themes: [
      { trigger: 'nii', headline: 'JPMorgan Delivers Record Net Interest Income as Balance Sheet Flexibility Wins', sentiment: 'bullish', score: 8, rationale: 'Fortress balance sheet enables prime corporate lending without credit degradation.' },
      { trigger: 'ib', headline: 'JPMorgan Investment Banking Pipeline Rebounds on Surge in Tech M&A Advisory', sentiment: 'bullish', score: 8, rationale: 'M&A deal activity recovery boosts fee revenue significantly.' }
    ]
  },
  AMD: {
    name: 'Advanced Micro Devices',
    sector: 'Technology',
    themes: [
      { trigger: 'mi300', headline: 'AMD MI350 AI Accelerator Gains Substantial Cloud Footprint Across Top Tier Hyperscalers', sentiment: 'bullish', score: 9, rationale: 'Second-source enterprise demand drives aggressive silicon market share gains.' },
      { trigger: 'epyc', headline: 'AMD EPYC Server Processors Capture Increased Enterprise Data Center Market Share', sentiment: 'bullish', score: 8, rationale: 'Performance-per-watt advantage continues to displace legacy x86 server fleets.' }
    ]
  }
};

function generateCrossTickerArticles(tickers) {
  const articles = [];
  const upperTickers = tickers.map(t => t.toUpperCase());

  if (upperTickers.includes('NVDA') && upperTickers.includes('TSLA')) {
    articles.push({
      headline: 'Tesla & Nvidia Expand Next-Gen AI Compute Cluster for Autonomous Vehicle Fleet Training',
      summary: 'Autonomous driving compute requirements drive record H100 and Blackwell deployments in Tesla Dojo and supercomputing clusters.',
      source: 'Bloomberg',
      url: 'https://www.bloomberg.com/technology',
      sectors: ['Technology', 'Consumer'],
      score: 9,
      sentiment: 'bullish',
      confidence: 0.96,
      rationale: 'Synergy between leading automotive vision software and high-density semiconductor infrastructure.'
    });
  }

  if (upperTickers.includes('MSFT') && upperTickers.includes('NVDA')) {
    articles.push({
      headline: 'Microsoft and Nvidia Deepen Hyperscale AI Partnership Across Azure Enterprise Infrastructure',
      summary: 'Azure announces native integration of Nvidia Omniverse and DGX Cloud, unlocking turn-key foundation model deployment for global enterprises.',
      source: 'Wall Street Journal',
      url: 'https://www.wsj.com/tech',
      sectors: ['Technology'],
      score: 10,
      sentiment: 'bullish',
      confidence: 0.98,
      rationale: 'Tight hardware-software co-optimization establishes structural barrier to competitors.'
    });
  }

  if (upperTickers.includes('AAPL') && upperTickers.includes('GOOGL')) {
    articles.push({
      headline: 'Apple and Alphabet Coordinate AI Integration Options to Power iOS Ecosystem Search & Intelligence',
      summary: 'Talks between Cupertino and Mountain View point to Gemini multimodal cloud capabilities powering auxiliary features on future iOS updates.',
      source: 'Financial Times',
      url: 'https://www.ft.com/tech',
      sectors: ['Technology'],
      score: 8,
      sentiment: 'bullish',
      confidence: 0.92,
      rationale: 'Strategic cooperation maintains search monetization while accelerating on-device AI rollout.'
    });
  }

  if (upperTickers.includes('AMD') && upperTickers.includes('NVDA')) {
    articles.push({
      headline: 'Nvidia and AMD Chip Battle Intensifies as Enterprise Demand Broadens Across AI Hardware',
      summary: 'Hardware benchmarks reveal aggressive competitive positioning between Nvidia Blackwell and AMD MI350X architectures among tier-1 cloud providers.',
      source: 'Reuters',
      url: 'https://www.reuters.com/technology',
      sectors: ['Technology'],
      score: 8,
      sentiment: 'bullish',
      confidence: 0.93,
      rationale: 'Intense technological competition expands the total addressable accelerator market.'
    });
  }

  if (upperTickers.includes('AMZN') && upperTickers.includes('MSFT')) {
    articles.push({
      headline: 'Cloud Giants Amazon AWS and Microsoft Azure Post Synchronized Acceleration in Enterprise Migration',
      summary: 'Quarterly industry surveys reflect enterprise IT budgets allocating higher proportions to hybrid cloud and distributed storage solutions.',
      source: 'Bloomberg',
      url: 'https://www.bloomberg.com/cloud',
      sectors: ['Technology'],
      score: 8,
      sentiment: 'bullish',
      confidence: 0.91,
      rationale: 'Secular digital transformation sustains mid-teens compounded growth for cloud leaders.'
    });
  }

  if (upperTickers.includes('JPM') && (upperTickers.includes('AAPL') || upperTickers.includes('MSFT') || upperTickers.includes('NVDA'))) {
    const techTicker = upperTickers.find(t => ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL'].includes(t));
    articles.push({
      headline: 'JPMorgan Equity Strategy Highlights ' + techTicker + ' as Key Pillar in Institutional Portfolios',
      summary: 'JPMorgan institutional strategy desk reiterates Overweight positioning on ' + techTicker + ', pointing to superior free cash flow generation and balance sheet qualities.',
      source: 'Financial Times',
      url: 'https://www.ft.com/markets',
      sectors: ['Financials', 'Technology'],
      score: 9,
      sentiment: 'bullish',
      confidence: 0.94,
      rationale: 'Institutional liquidity flow endorsements reinforce mega-cap valuation multiples.'
    });
  }

  if (upperTickers.length >= 2) {
    const tickerListStr = upperTickers.join(', ');
    articles.push({
      headline: 'Sector Momentum Watch: Institutional Capital Reallocates Toward ' + tickerListStr,
      summary: 'Hedge fund flow metrics and proprietary trading desks report correlated accumulation across ' + tickerListStr + ' amid favorable macro tailwinds and sector leadership.',
      source: 'MarketPulse News',
      url: 'https://finance.yahoo.com/quotes/' + encodeURIComponent(upperTickers.join(',')),
      sectors: ['Financials', 'Technology'],
      score: 8,
      sentiment: 'bullish',
      confidence: 0.9,
      rationale: 'Portfolio rebalancing highlights multi-asset synergy across ' + tickerListStr + '.'
    });

    articles.push({
      headline: 'Earnings Preview & Key Catalysts for ' + tickerListStr + ' in Focus This Week',
      summary: 'Analysts outline critical performance indicators, supply chain checks, and forward operating margin guidance anticipated for ' + tickerListStr + '.',
      source: 'Wall Street Journal',
      url: 'https://www.wsj.com/market-data',
      sectors: ['Financials', 'Consumer'],
      score: 7,
      sentiment: 'neutral',
      confidence: 0.88,
      rationale: 'Catalyst watch provides near-term volatility and liquidity triggers across selected holdings.'
    });
  }

  return articles;
}

function generateTickerArticles(ticker) {
  const upper = ticker.toUpperCase().trim();
  const profile = TICKER_DATA[upper];
  const articles = [];

  if (profile && profile.themes) {
    profile.themes.forEach(theme => {
      articles.push({
        headline: theme.headline,
        summary: profile.name + ' continues to show strong execution. ' + theme.headline + ' as market participants evaluate long-term competitive positioning and sector catalysts.',
        source: ['Bloomberg', 'Reuters', 'Financial Times', 'Wall Street Journal'][Math.floor(Math.random() * 4)],
        url: 'https://finance.yahoo.com/quote/' + encodeURIComponent(upper),
        sectors: tagSectors(theme.headline + ' ' + profile.sector),
        score: theme.score,
        sentiment: theme.sentiment,
        confidence: 0.92,
        rationale: theme.rationale
      });
    });
  }

  articles.push(
    {
      headline: upper + ' Posts Resilient Quarterly Operational Metrics Amid Market Rotation',
      summary: 'Institutional investors note steady volume and margin stability in ' + upper + ' as market sentiment broadens across key industry players.',
      source: 'Reuters',
      url: 'https://finance.yahoo.com/quote/' + encodeURIComponent(upper),
      sectors: tagSectors(upper + ' stock earnings operational performance'),
      score: 8,
      sentiment: 'bullish',
      confidence: 0.89,
      rationale: 'Operational metrics reinforce fundamental valuation support for ' + upper + '.'
    },
    {
      headline: 'Wall Street Analyst Consensus Upgrades Target Price for ' + upper,
      summary: 'Equity research desks highlight upcoming catalysts, favorable secular demand trends, and resilient pricing power for ' + upper + '.',
      source: 'Bloomberg',
      url: 'https://www.bloomberg.com/search?query=' + encodeURIComponent(upper),
      sectors: tagSectors(upper + ' analyst upgrade price target finance'),
      score: 8,
      sentiment: 'bullish',
      confidence: 0.91,
      rationale: 'Sell-side revisions drive incremental institutional buying interest.'
    },
    {
      headline: 'Industry Supply Chain Survey Highlights Execution Momentum at ' + upper,
      summary: 'Channel checks indicate stable lead times and expanding customer commitments supporting ' + upper + ' forward operational projections.',
      source: 'Financial Times',
      url: 'https://www.ft.com/search?q=' + encodeURIComponent(upper),
      sectors: tagSectors(upper + ' supply chain manufacturing industry'),
      score: 7,
      sentiment: 'neutral',
      confidence: 0.86,
      rationale: 'Supply chain normalization mitigates margin volatility risk.'
    },
    {
      headline: 'Options Market Points to Implied Volatility Shift Ahead of ' + upper + ' Milestones',
      summary: 'Derivatives activity reveals heightened call open interest for ' + upper + ', suggesting options traders anticipate significant near-term movement.',
      source: 'MarketWatch',
      url: 'https://www.marketwatch.com/investing/stock/' + encodeURIComponent(upper),
      sectors: ['Financials'],
      score: 7,
      sentiment: 'bullish',
      confidence: 0.85,
      rationale: 'Bullish skew in call contracts indicates upside positioning by systematic funds.'
    }
  );

  return articles;
}

export function getMockNews({ tickers = [], query = '', page = 1, limit = 6 } = {}) {
  const activeTickers = (Array.isArray(tickers) ? tickers : [tickers])
    .filter(t => typeof t === 'string' && t.trim().length > 0)
    .map(t => t.trim().toUpperCase());

  let combinedPool = [];

  if (activeTickers.length === 0) {
    if (query && query.trim() && query.trim().toLowerCase() !== 'market news') {
      const q = query.trim().toUpperCase();
      const queryArticles = generateTickerArticles(q);
      combinedPool = [...queryArticles, ...MACRO_NEWS_POOL];
    } else {
      combinedPool = [...MACRO_NEWS_POOL];
    }
  } else if (activeTickers.length === 1) {
    const ticker = activeTickers[0];
    const tickerArticles = generateTickerArticles(ticker);
    combinedPool = [...tickerArticles, ...MACRO_NEWS_POOL.slice(0, 4)];
  } else {
    const crossArticles = generateCrossTickerArticles(activeTickers);
    const perTickerArticles = activeTickers.flatMap(t => generateTickerArticles(t).slice(0, 3));
    combinedPool = [...crossArticles, ...perTickerArticles];
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
    const minutesAgo = 10 + idx * 22;
    const publishedDate = new Date(now - minutesAgo * 60 * 1000).toISOString();
    const id = hashStr(article.headline + article.source + idx);

    return {
      id,
      headline: article.headline,
      summary: article.summary,
      source: article.source || 'MarketPulse',
      url: article.url || '#',
      published: publishedDate,
      sectors: article.sectors || tagSectors(article.headline + ' ' + article.summary),
      score: article.score || 7,
      sentiment: article.sentiment || 'neutral',
      confidence: article.confidence || 0.88,
      rationale: article.rationale || 'Market sentiment scored based on momentum indicators.',
      tickers: activeTickers.length > 0 ? activeTickers : []
    };
  });

  enrichedArticles.sort((a, b) => new Date(b.published).getTime() - new Date(a.published).getTime());

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
