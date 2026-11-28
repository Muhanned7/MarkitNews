import { tagSectors } from '@/lib/sectorTagger'
import { index } from '@/lib/pinecone'
import { getEmbedding } from '@/lib/embeddings'

export const maxDuration = 60 // seconds

const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'
const INTERNAL_SERVICE_KEY = process.env.INTERNAL_SERVICE_KEY

function reportExternalApiCall(payload) {
  fetch(`${BACKEND_URL}/telemetry/external-apis/log`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }).catch(() => {})
}

// In-memory cache with 10-minute TTL to protect API quotas
const cache = new Map()

function hashStr(str) {
  let h = 0
  for (let i = 0; i < str.length; i++) {
    h = (Math.imul(31, h) + str.charCodeAt(i)) | 0
  }
  return Math.abs(h).toString(16)
}

function scoreHeadlineDeterministically(title = '', summary = '') {
  const text = `${title} ${summary}`.toLowerCase()
  const bullWords = ['beat', 'beats', 'surge', 'rally', 'growth', 'upgrade', 'record', 'strong', 'expands', 'gain', 'profit', 'bullish', 'raises']
  const bearWords = ['miss', 'misses', 'drop', 'plunge', 'slump', 'downgrade', 'probe', 'lawsuit', 'recall', 'shortage', 'delay', 'cuts', 'bearish', 'fall', 'loss', 'tariff']
  let bull = 0
  let bear = 0
  for (const w of bullWords) if (text.includes(w)) bull++
  for (const w of bearWords) if (text.includes(w)) bear++

  if (bull > bear) {
    return {
      score: Math.min(9, 6 + (bull - bear)),
      sentiment: 'bullish',
      confidence: Math.min(0.85, 0.55 + bull * 0.1),
      rationale: 'Headline lexical cues indicate positive earnings, guidance, or momentum.'
    }
  }
  if (bear > bull) {
    return {
      score: Math.max(2, 5 - (bear - bull)),
      sentiment: 'bearish',
      confidence: Math.min(0.85, 0.55 + bear * 0.1),
      rationale: 'Headline lexical cues indicate operational, regulatory, or earnings headwinds.'
    }
  }
  return {
    score: 5,
    sentiment: 'neutral',
    confidence: 0.5,
    rationale: 'Headline presents balanced or informational market coverage.'
  }
}

function decodeXmlEntities(str = '') {
  return str
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/<[^>]+>/g, '')
    .trim()
}

async function fetchGoogleNewsRss(searchQuery, maxItems = 12) {
  const t0 = Date.now()
  try {
    const q = `${searchQuery} when:14d`
    const url = `https://news.google.com/rss/search?q=${encodeURIComponent(q)}&hl=en-US&gl=US&ceid=US:en`
    const res = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/rss+xml, application/xml, text/xml'
      },
      signal: AbortSignal.timeout(8000)
    })
    reportExternalApiCall({
      provider: 'google_news_rss',
      endpoint: 'https://news.google.com/rss/search',
      operation: `search_rss (${searchQuery.slice(0, 32)})`,
      status_code: res.status,
      success: res.ok,
      duration_ms: Date.now() - t0
    })
    if (!res.ok) return []
    const xml = await res.text()
    const items = []
    const itemRegex = /<item>([\s\S]*?)<\/item>/g
    let match
    while ((match = itemRegex.exec(xml)) !== null && items.length < maxItems) {
      const block = match[1]
      const rawTitle = (block.match(/<title>([\s\S]*?)<\/title>/) || [])[1] || ''
      const rawLink = (block.match(/<link>([\s\S]*?)<\/link>/) || [])[1] || ''
      const rawPubDate = (block.match(/<pubDate>([\s\S]*?)<\/pubDate>/) || [])[1] || ''
      const rawSource = (block.match(/<source[^>]*>([\s\S]*?)<\/source>/) || [])[1] || ''

      let title = decodeXmlEntities(rawTitle)
      let source = decodeXmlEntities(rawSource)
      if (!source && title.includes(' - ')) {
        const idx = title.lastIndexOf(' - ')
        source = title.slice(idx + 3).trim()
        title = title.slice(0, idx).trim()
      }
      const link = decodeXmlEntities(rawLink)
      const pubDate = decodeXmlEntities(rawPubDate)
      if (title && link) {
        items.push({
          title,
          description: title,
          source: { name: source || 'Google News' },
          url: link,
          publishedAt: pubDate ? new Date(pubDate).toISOString() : new Date().toISOString()
        })
      }
    }
    return items
  } catch (err) {
    console.warn('Google News RSS fetch warning:', err.message)
    return []
  }
}

export async function POST(request) {
  // Strict JSON validation (PROD-015): return 400 on malformed JSON
  let body
  try {
    const rawText = await request.text()
    if (!rawText || !rawText.trim()) {
      return Response.json({ error: 'Request body must be valid JSON' }, { status: 400 })
    }
    body = JSON.parse(rawText)
    if (!body || typeof body !== 'object' || Array.isArray(body)) {
      return Response.json({ error: 'Request body must be a JSON object' }, { status: 400 })
    }
  } catch {
    return Response.json({ error: 'Malformed JSON in request body' }, { status: 400 })
  }

  const {
    query = '',
    tickers = [],
    page = 1,
    limit = 6,
    save = false
  } = body

  if (query !== undefined && typeof query !== 'string') {
    return Response.json({ error: 'Field "query" must be a string' }, { status: 400 })
  }
  if (tickers !== undefined && !Array.isArray(tickers)) {
    return Response.json({ error: 'Field "tickers" must be an array' }, { status: 400 })
  }

  const normTickers = Array.isArray(tickers)
    ? [...tickers].map(t => String(t).trim().toUpperCase()).filter(Boolean).sort()
    : []
  const normQuery = (query || '').trim()
  const pageNum = Math.max(1, parseInt(page, 10) || 1)
  const limitNum = Math.min(25, Math.max(1, parseInt(limit, 10) || 6))

  // Build effective search term (default to live macro financial markets when home feed requests empty query)
  const effectiveQuery = normQuery
    ? (normTickers.length > 0 ? `${normQuery} ${normTickers.join(' OR ')}` : normQuery)
    : (normTickers.length > 0 ? `${normTickers.join(' OR ')} stock` : 'stock market earnings economy')

  const cacheKey = `${effectiveQuery.toLowerCase()}:${pageNum}:${limitNum}`

  if (cache.has(cacheKey)) {
    const cachedEntry = cache.get(cacheKey)
    if (Date.now() - cachedEntry.timestamp < 10 * 60 * 1000) {
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

  let articlesRaw = []

  // 1. Primary: NewsAPI live search (real articles only; never fabricate)
  try {
    const apiKey = process.env.NEWSAPI_KEY
    if (apiKey) {
      const t0 = Date.now()
      const fromDate = new Date(Date.now() - 14 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
      const res = await fetch(
        `https://newsapi.org/v2/everything?q=${encodeURIComponent(effectiveQuery)}&from=${fromDate}&language=en&pageSize=24&sortBy=publishedAt&apiKey=${apiKey}`,
        { signal: AbortSignal.timeout(8000) }
      )
      reportExternalApiCall({
        provider: 'newsapi',
        endpoint: 'https://newsapi.org/v2/everything',
        operation: `search_everything (${effectiveQuery.slice(0, 32)})`,
        status_code: res.status,
        success: res.ok,
        duration_ms: Date.now() - t0
      })
      if (res.ok) {
        const data = await res.json()
        if (data.status === 'ok' && Array.isArray(data.articles)) {
          articlesRaw = data.articles.filter(a => a && a.title && a.title !== '[Removed]' && a.url)
        }
      }
    }
  } catch (err) {
    console.warn('NewsAPI fetch warning:', err.message)
  }

  // 2. Secondary: Live Google News RSS (still 100% real articles; returns [] for gibberish like "zzqqxx")
  if (articlesRaw.length === 0) {
    articlesRaw = await fetchGoogleNewsRss(effectiveQuery, 24)
  }

  // NEVER fabricate fake articles or attribute invented quotes to real outlets (PROD-002).
  // If no real articles match, return an honest empty array [].
  const seen = new Set()
  const allRealArticles = articlesRaw
    .filter(a => a && a.title && a.url && !seen.has(a.url) && seen.add(a.url))
    .map(article => {
      const headline = article.title.trim()
      const summary = (article.description || article.title).trim()
      const scoring = scoreHeadlineDeterministically(headline, summary)
      return {
        headline,
        summary,
        source: article.source?.name || 'Financial News',
        url: article.url,
        published: article.publishedAt || null,
        id: hashStr(headline + article.url),
        sectors: tagSectors(`${headline} ${summary}`),
        ...scoring
      }
    })

  const startIdx = (pageNum - 1) * limitNum
  const pageArticles = allRealArticles.slice(startIdx, startIdx + limitNum)
  const hasMore = startIdx + limitNum < allRealArticles.length

  cache.set(cacheKey, {
    articles: pageArticles,
    page: pageNum,
    limit: limitNum,
    hasMore,
    total: allRealArticles.length,
    timestamp: Date.now()
  })

  // Optional non-blocking persistence when save=true and real articles exist
  if (save && pageArticles.length > 0 && INTERNAL_SERVICE_KEY) {
    fetch(`${BACKEND_URL}/articles`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Service-Key': INTERNAL_SERVICE_KEY
      },
      body: JSON.stringify({
        articles: pageArticles.map(article => ({
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
          query: normTickers.length > 0 ? normTickers : [normQuery || 'market']
        }))
      })
    }).catch(err => console.warn('Article storage error:', err.message))

    fetch(`${BACKEND_URL}/searches`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Service-Key': INTERNAL_SERVICE_KEY
      },
      body: JSON.stringify({
        query: [effectiveQuery],
        results_count: pageArticles.length
      })
    }).catch(err => console.warn('Search log error:', err.message))

    Promise.allSettled(
      pageArticles.slice(0, 3).map(async article => {
        const textToEmbed = `${article.headline || ''} ${article.summary || ''}`
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
    message: pageArticles.length > 0 ? 'Response received' : 'No matching live news articles found',
    scoredArticles: pageArticles,
    page: pageNum,
    limit: limitNum,
    hasMore,
    total: allRealArticles.length
  })
}
