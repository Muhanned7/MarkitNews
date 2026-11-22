'use client'

// Minimal single-axis SVG chart for the risk tabs (RSK-004/006): lines, an area, bars,
// shaded date bands, exception markers, crosshair + tooltip on hover/focus.
import { useEffect, useMemo, useRef, useState } from 'react'
import s from './charts.module.css'

const PAD = { l: 60, r: 12, t: 12, b: 28 }

function niceTicks(min, max, n = 4) {
  if (min === max) { min -= 1; max += 1 }
  const span = max - min
  const step0 = span / n
  const mag = Math.pow(10, Math.floor(Math.log10(step0)))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((x) => x >= step0) || step0
  const lo = Math.floor(min / step) * step
  const hi = Math.ceil(max / step) * step
  const out = []
  for (let v = lo; v <= hi + step / 2; v += step) out.push(+v.toFixed(10))
  return out
}

export default function RiskChart({
  title, data, xKey = 'date', series, height = 220, yFormat = (v) => v, bands = [],
  markerKey, markerLabel = 'Exception', zeroLine = false, ariaLabel
}) {
  const [hover, setHover] = useState(null)
  const [W, setW] = useState(760)
  const svgRef = useRef(null)
  const wrapRef = useRef(null)

  // draw at the container's real pixel width so axis text stays 11px at every size
  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const update = () => setW(Math.max(280, Math.round(el.clientWidth)))
    update()
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const H = height
  const innerW = W - PAD.l - PAD.r
  const innerH = H - PAD.t - PAD.b

  const { yMin, yMax, ticks } = useMemo(() => {
    let lo = Infinity, hi = -Infinity
    for (const d of data) for (const sr of series) {
      const v = d[sr.key]
      if (v === null || v === undefined) continue
      lo = Math.min(lo, v); hi = Math.max(hi, v)
    }
    if (series.some((sr) => sr.type === 'bar' || sr.type === 'area') || zeroLine) { lo = Math.min(lo, 0); hi = Math.max(hi, 0) }
    const t = niceTicks(lo, hi)
    return { yMin: t[0], yMax: t[t.length - 1], ticks: t }
  }, [data, series, zeroLine])

  if (!data || data.length < 2) return <div ref={wrapRef} className={s.empty}>Not enough data.</div>

  const n = data.length
  const x = (i) => PAD.l + (n === 1 ? 0 : (i / (n - 1)) * innerW)
  const y = (v) => PAD.t + (1 - (v - yMin) / (yMax - yMin || 1)) * innerH
  const bw = Math.max(1, innerW / n - 2)
  const idxOf = Object.fromEntries(data.map((d, i) => [d[xKey], i]))

  function onMove(e) {
    const r = svgRef.current.getBoundingClientRect()
    const px = ((e.clientX - r.left) / r.width) * W
    const i = Math.round(((px - PAD.l) / innerW) * (n - 1))
    setHover(Math.max(0, Math.min(n - 1, i)))
  }
  function onKey(e) {
    if (e.key === 'ArrowRight') setHover((h) => Math.min(n - 1, (h ?? n - 2) + 1))
    if (e.key === 'ArrowLeft') setHover((h) => Math.max(0, (h ?? 1) - 1))
    if (e.key === 'Escape') setHover(null)
  }

  const xTickIdx = W < 480 ? [0, n - 1] : [0, Math.floor((n - 1) / 3), Math.floor((2 * (n - 1)) / 3), n - 1]
  const hv = hover !== null ? data[hover] : null
  const tipLeft = hover !== null ? (x(hover) / W) * 100 : 0

  return (
    <figure className={s.figure}>
      {title && <figcaption className={s.title}>{title}</figcaption>}
      <div className={s.legend}>
        {series.map((sr) => (
          <span key={sr.key} className={s.legendItem}>
            <span className={`${s.swatch} ${sr.dashed ? s.swatchDashed : ''} ${sr.type === 'bar' || sr.type === 'area' ? s.swatchBlock : ''}`} style={{ '--c': sr.color }} />
            {sr.label}
          </span>
        ))}
        {markerKey && <span className={s.legendItem}><span className={s.markerSwatch} />{markerLabel}</span>}
        {bands.length > 0 && <span className={s.legendItem}><span className={s.bandSwatch} />Injected stress window</span>}
      </div>
      <div className={s.plotWrap} ref={wrapRef}>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          className={s.svg}
          role="img"
          aria-label={ariaLabel || title}
          tabIndex={0}
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
          onKeyDown={onKey}
          onFocus={() => setHover(n - 1)}
          onBlur={() => setHover(null)}
        >
          {bands.map((b) => {
            const i0 = idxOf[b.start_date] ?? (b.start_date < data[0][xKey] ? 0 : null)
            const i1 = idxOf[b.end_date] ?? (b.end_date > data[n - 1][xKey] ? n - 1 : null)
            if (i0 === null || i1 === null || i1 < i0) return null
            return <rect key={b.key} x={x(i0) - bw / 2} y={PAD.t} width={Math.max(2, x(i1) - x(i0) + bw)} height={innerH} className={s.band} />
          })}
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} className={t === 0 ? s.zero : s.grid} />
              <text x={PAD.l - 8} y={y(t)} className={s.yTick} dominantBaseline="middle" textAnchor="end">{yFormat(t)}</text>
            </g>
          ))}
          {xTickIdx.map((i, k) => (
            <text key={k} x={x(i)} y={H - 8} className={s.xTick} textAnchor={k === 0 ? 'start' : k === xTickIdx.length - 1 ? 'end' : 'middle'}>{data[i][xKey]}</text>
          ))}
          {series.filter((sr) => sr.type === 'area').map((sr) => {
            const pts = data.map((d, i) => `${x(i)},${y(d[sr.key])}`).join(' ')
            return (
              <g key={sr.key}>
                <polygon points={`${x(0)},${y(0)} ${pts} ${x(n - 1)},${y(0)}`} fill={sr.color} opacity="0.18" />
                <polyline points={pts} fill="none" stroke={sr.color} strokeWidth="2" />
              </g>
            )
          })}
          {series.filter((sr) => sr.type === 'bar').map((sr) => (
            <g key={sr.key}>
              {data.map((d, i) => {
                const v = d[sr.key]
                const y0 = y(0), y1 = y(v)
                const hit = markerKey && d[markerKey]
                return <rect key={i} x={x(i) - bw / 2} y={Math.min(y0, y1)} width={bw} height={Math.max(1, Math.abs(y1 - y0))}
                  fill={hit ? 'var(--bear)' : sr.color} opacity={hit ? 1 : 0.55} />
              })}
            </g>
          ))}
          {series.filter((sr) => !sr.type || sr.type === 'line').map((sr) => (
            <polyline key={sr.key} points={data.map((d, i) => `${x(i)},${y(d[sr.key])}`).join(' ')}
              fill="none" stroke={sr.color} strokeWidth="2" strokeDasharray={sr.dashed ? '5 4' : undefined} strokeLinejoin="round" />
          ))}
          {markerKey && data.map((d, i) => d[markerKey] ? (
            <circle key={`m${i}`} cx={x(i)} cy={y(d[series.find((sr) => sr.type === 'bar')?.key || series[0].key])} r="5" className={s.marker} />
          ) : null)}
          {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={PAD.t} y2={PAD.t + innerH} className={s.crosshair} />}
          {hover !== null && series.filter((sr) => sr.type !== 'bar').map((sr) => (
            <circle key={`h${sr.key}`} cx={x(hover)} cy={y(hv[sr.key])} r="4" fill={sr.color} className={s.hoverDot} />
          ))}
        </svg>
        {hv && (
          <div className={s.tooltip} style={{ left: `${tipLeft}%`, transform: `translateX(${tipLeft > 60 ? '-105%' : '8%'})` }} role="status">
            <div className={s.tipDate}>{hv[xKey]}</div>
            {series.map((sr) => (
              <div key={sr.key} className={s.tipRow}>
                <span className={s.swatch} style={{ '--c': sr.color }} />
                <span className={s.tipLabel}>{sr.label}</span>
                <span className={s.tipVal}>{yFormat(hv[sr.key], true)}</span>
              </div>
            ))}
            {markerKey && hv[markerKey] && <div className={s.tipFlag}>✕ {markerLabel}</div>}
          </div>
        )}
      </div>
    </figure>
  )
}
