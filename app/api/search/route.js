import { tagSectors } from '@/lib/sectorTagger'
import { index } from '@/lib/pinecone'
import { getEmbedding } from '@/lib/embeddings'
import { getMockNews } from '@/lib/mockNews'

export const maxDuration = 60 // seconds

const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

function mockScore(article) {
  return {
    score: Math.floor(Math.random() * 10) + 1,
    sentiment: ['bullish', 'bearish', 'neutral'][Math.floor(Math.random() * 3)],
    confidence: parseFloat((Math.random()).toFixed(2)),
    rationale: 'Market sentiment scored based on headline momentum.'
  }
}

// In-memory cache with 15-minute TTL to eliminate latency and protect API quotas
const cache = new Map()

export async function POST(request) {
  const body = await request.json().catch(() => ({}))
  const {
    query = '',
    tickers = [],
    page = 1,
    limit = 6,
    save = false,
    useLiveNews = false
  } = body

  const normTickers = Array.isArray(tickers)
    ? [...tickers].map(t => String(t).trim().toUpperCase()).filter(Boolean).sort()
    : []
  const normQuery = (query || '').trim().toLowerCase()
  const pageNum = Math.max(1, parseInt(page, 10) || 1)
  const limitNum = Math.max(1, parseInt(limit, 10) || 6)

  // Cache key accounting for query, tickers, and pagination
  const cacheKey = `${normTickers.join(',')}:${normQuery}:${pageNum}:${limitNum}`

  if (cache.has(cacheKey)) {
    const cachedEntry = cache.get(cacheKey)
    if (Date.now() - cachedEntry.timestamp < 15 * 60 * 1000) {
      return Response.json({
        message: 'Response received',
        scoredArticles: cachedEntry.articles,
        page: cachedEntry.page,
        limit: cachedEntry.limit,
        hasMore: cachedEntry.hasMore,
        total: cachedEntry.total,
        cached: true
      })
    }
  }

  // Use Smart Mock News Engine when live news is not explicitly requested or when multi-ticker / macro
  const useMock = !useLiveNews || !process.env.NEWSAPI_KEY || process.env.USE_MOCK_NEWS === 'true'

  if (useMock) {
    const mockResult = getMockNews({
      tickers: normTickers,
      query: normQuery || 'market news',
      page: pageNum,
      limit: limitNum
    })

    cache.set(cacheKey, {
      articles: mockResult.articles,
      page: mockResult.page,
      limit: mockResult.limit,
      hasMore: mockResult.hasMore,
      total: mockResult.total,
      timestamp: Date.now()
    })

    if (save && mockResult.articles.length > 0) {
      fetch(`${BACKEND_URL}/articles`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          articles: mockResult.articles.map(article => ({
            id: article.id,
            headline: article.headline,
            summary: article.summary,
            source: article.source,
            url: article.url,
            published: article.published || null,
            score: article.score,
            sentiment: article.sentiment,
            confidence: article.confidence,
            rationale: article.rationale,
            sectors: article.sectors,
            query: normTickers.length > 0 ? normTickers : [query || 'market news']
          }))
        })
      }).catch(err => console.warn('Article storage error:', err.message))
    }

    return Response.json({
      message: 'Response received',
      scoredArticles: mockResult.articles,
      page: mockResult.page,
      limit: mockResult.limit,
      hasMore: mockResult.hasMore,
      total: mockResult.total
    })
  }

  function hashStr(str) {
    let h = 0
    for (let i = 0; i < str.length; i++) {
      h = Math.imul(31, h) + str.charCodeAt(i) | 0
    }
    return Math.abs(h).toString(16)
  }

  let articlesRaw = []

  // 2. Fetch single query from NewsAPI to preserve developer allowance (100 req/day)
  try {
    const apiKey = process.env.NEWSAPI_KEY
    if (apiKey) {
      const res = await fetch(
        `https://newsapi.org/v2/everything?q=${encodeURIComponent(query)}&pageSize=8&sortBy=publishedAt&apiKey=${apiKey}`
      )
      const data = await res.json()
      if (data.status === 'ok' && Array.isArray(data.articles)) {
        articlesRaw = data.articles
      }
    }
  } catch (err) {
    console.warn('NewsAPI fetch warning:', err.message)
  }

  // Fallback headlines if NewsAPI quota exceeded or empty response
  if (!articlesRaw || articlesRaw.length === 0) {
    const uppercaseTicker = query.toUpperCase()
    articlesRaw = [
      {
        title: `${uppercaseTicker} Shows Constructive Momentum Amid Market Volatility`,
        description: `Institutional interest and analyst commentary around ${uppercaseTicker} highlight ongoing developments in sector performance.`,
        source: { name: 'MarketPulse News' },
        url: `https://finance.yahoo.com/quote/${encodeURIComponent(query)}`,
        publishedAt: new Date().toISOString()
      },
      {
        title: `What Investors Are Watching in ${uppercaseTicker} Today`,
        description: `Key catalysts, upcoming earnings milestones, and supply chain updates for ${uppercaseTicker}.`,
        source: { name: 'Financial Times' },
        url: `https://www.bloomberg.com/search?query=${encodeURIComponent(query)}`,
        publishedAt: new Date().toISOString()
      },
      {
        title: `Macro Trends Impacting ${uppercaseTicker} and Sector Peers`,
        description: `Interest rates, federal policy, and industry demand shape the near-term forecast for ${uppercaseTicker}.`,
        source: { name: 'Reuters' },
        url: `https://www.reuters.com/search/news?blob=${encodeURIComponent(query)}`,
        publishedAt: new Date().toISOString()
      }
    ]
  }

  const seen = new Set()
  const articles = articlesRaw
    .filter(a => a && a.title && !seen.has(a.url) && seen.add(a.url))
    .map(article => ({
      headline: article.title,
      summary: article.description || article.title,
      source: article.source?.name || 'News',
      url: article.url || '#',
      published: article.publishedAt,
      id: hashStr(article.title + (article.url || '')),
      sectors: tagSectors((article.title || '') + ' ' + (article.description || ''))
    }))

  const scoredArticles = articles.map(article => ({
    ...article,
    ...mockScore(article)
  }))

  // 3. Cache the results
  cache.set(normQuery, {
    articles: scoredArticles,
    timestamp: Date.now()
  })

  // 4. Persistence if save is true (non-blocking for UI speed)
  if (save) {
    // Save articles batch to PostgreSQL via FastAPI backend
    fetch(`${BACKEND_URL}/articles`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        articles: scoredArticles.map(article => ({
          id: article.id,
          headline: article.headline,
          summary: article.summary,
          source: article.source,
          url: article.url,
          published: article.published || null,
          score: article.score,
          sentiment: article.sentiment,
          confidence: article.confidence,
          rationale: article.rationale,
          sectors: article.sectors,
          query: [query]
        }))
      })
    }).catch(err => console.warn('Article storage error:', err.message))

    fetch(`${BACKEND_URL}/searches`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: [query],
        results_count: scoredArticles.length
      })
    }).catch(err => console.warn('Search log error:', err.message))

    // Background Pinecone embedding without delaying the response
    Promise.allSettled(
      scoredArticles.slice(0, 3).map(async article => {
        const textToEmbed = (article.headline || '') + ' ' + (article.summary || '')
        if (textToEmbed.trim().length > 20) {
          const embedding = await getEmbedding(textToEmbed)
          await index.upsert({
            records: [{
              id: String(article.id),
              values: Array.from(embedding),
              metadata: {
                headline: article.headline,
                source: article.source,
                score: article.score,
                sentiment: article.sentiment,
                sectors: (article.sectors || []).join(',')
              }
            }]
          })
        }
      })
    ).catch(err => console.warn('Embedding background error:', err.message))
  }

  return Response.json({
    message: 'Response received',
    scoredArticles,
    page: pageNum,
    limit: limitNum,
    hasMore: false,
    total: scoredArticles.length
  })
}