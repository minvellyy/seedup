import React, { useState, useEffect } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import './ETFDetailPage.css'
import AnalysisProgressBar from '../components/AnalysisProgressBar'

// ── 포매터 ──────────────────────────────────────────────────────────────────
const fmtPrice = (v) => v == null ? '-' : Number(v).toLocaleString('ko-KR') + '원'
const fmtAum   = (v) => {
  if (v == null) return '-'
  if (v >= 10000) return `약 ${(v / 10000).toFixed(1)}조원`
  return `약 ${Math.round(v).toLocaleString('ko-KR')}억원`
}

// ── 캔들스틱 차트 ─────────────────────────────────────────────────────────
function CandlestickChart({ data, days = 30 }) {
  const [tooltip, setTooltip] = useState(null)

  if (!data || data.length < 2) return null
  const items = data.slice(-days)
  const hasOHLC = items.some(d => d.open != null && d.high != null && d.low != null)

  const W = 800, H = 180, padT = 12, padB = 28, padL = 4, padR = 4
  const plotW = W - padL - padR
  const plotH = H - padT - padB

  const allHi = items.map(d => hasOHLC ? (d.high ?? d.close) : d.close)
  const allLo = items.map(d => hasOHLC ? (d.low  ?? d.close) : d.close)
  const minY = Math.min(...allLo)
  const maxY = Math.max(...allHi)
  const range = maxY - minY || 1

  const sy = (v) => padT + plotH - ((v - minY) / range) * plotH
  const n = items.length
  const step = plotW / n
  const barW = Math.max(3, step - 2)

  const maxClose = Math.max(...items.map(d => d.high ?? d.close))
  const minClose = Math.min(...items.map(d => d.low  ?? d.close))
  const dlabels = [0, Math.floor(n / 2), n - 1]

  return (
    <div className="etf-candle-wrap" style={{ position: 'relative' }}>
      {tooltip && (
        <div
          className="etf-candle-tooltip"
          style={{
            left: tooltip.pct > 70 ? 'auto' : `${tooltip.pct}%`,
            right: tooltip.pct > 70 ? `${100 - tooltip.pct}%` : 'auto',
          }}
        >
          <div className="etf-candle-tooltip-date">{tooltip.d.date}</div>
          <div className="etf-candle-tooltip-row"><span>시가</span><span>{tooltip.d.open != null ? tooltip.d.open.toLocaleString('ko-KR') + '원' : '-'}</span></div>
          <div className="etf-candle-tooltip-row"><span>고가</span><span className="up">{tooltip.d.high != null ? tooltip.d.high.toLocaleString('ko-KR') + '원' : '-'}</span></div>
          <div className="etf-candle-tooltip-row"><span>저가</span><span className="down">{tooltip.d.low != null ? tooltip.d.low.toLocaleString('ko-KR') + '원' : '-'}</span></div>
          <div className="etf-candle-tooltip-row"><span>종가</span><span>{tooltip.d.close != null ? tooltip.d.close.toLocaleString('ko-KR') + '원' : '-'}</span></div>
        </div>
      )}
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block' }}>
        {items.map((d, i) => {
          const x = padL + i * step + step / 2
          const isUp = d.close >= (d.open ?? d.close)
          const color = isUp ? '#EA580C' : '#3B82F6'
          const openY  = sy(d.open ?? d.close)
          const closeY = sy(d.close)
          const highY  = sy(hasOHLC ? (d.high ?? d.close) : d.close)
          const lowY   = sy(hasOHLC ? (d.low  ?? d.close) : d.close)
          const bodyTop = Math.min(openY, closeY)
          const bodyH   = Math.max(Math.abs(openY - closeY), 1)
          const pct = ((x - padL) / plotW) * 100
          return (
            <g key={i}
              onMouseEnter={() => setTooltip({ d, pct })}
              onMouseLeave={() => setTooltip(null)}
              style={{ cursor: 'crosshair' }}
            >
              <rect x={x - step / 2} y={padT} width={step} height={plotH} fill="transparent" />
              <line x1={x} y1={highY} x2={x} y2={lowY} stroke={color} strokeWidth={1.5} />
              <rect x={x - barW / 2} y={bodyTop} width={barW} height={bodyH} fill={color} />
            </g>
          )
        })}
        {dlabels.map(i => (
          <text key={i} x={padL + i * step + step / 2} y={H - 4}
            fontSize={11} fill="#bbb" textAnchor="middle">{items[i]?.date}</text>
        ))}
      </svg>
      <div className="etf-candle-minmax">
        <span className="etf-candle-high">최고: {maxClose.toLocaleString('ko-KR')}원</span>
        <span className="etf-candle-low">최저: {minClose.toLocaleString('ko-KR')}원</span>
      </div>
    </div>
  )
}

// ── 주요 지표 카드 ──────────────────────────────────────────────────────────
const ETF_METRICS = [
  { key: 'ret_1m',   label: '1개월 수익률',  type: 'pct',   tip: '최근 1개월 NAV 변동률' },
  { key: 'ret_3m',   label: '3개월 수익률',  type: 'pct',   tip: '최근 3개월 NAV 변동률' },
  { key: 'ret_6m',   label: '6개월 수익률',  type: 'pct',   tip: '최근 6개월 NAV 변동률' },
  { key: 'ret_1y',   label: '1년 수익률',    type: 'pct',   tip: '최근 1년 NAV 변동률' },
  { key: 'vol_ann',  label: '연간 변동성',   type: 'pct_r', tip: '연환산 표준편차 (낮을수록 안정)' },
  { key: 'high_52w', label: '52주 최고가',   type: 'price', tip: '최근 52주 최고 종가' },
  { key: 'low_52w',  label: '52주 최저가',   type: 'price', tip: '최근 52주 최저 종가' },
]

function MetricCard({ label, value, type, tip }) {
  let display = '-', color = '#333'
  if (value != null) {
    if (type === 'pct') {
      display = `${value >= 0 ? '+' : ''}${Number(value).toFixed(2)}%`
      color = value >= 0 ? '#EA580C' : '#3B82F6'
    } else if (type === 'pct_r') {
      display = `${Number(value).toFixed(2)}%`
    } else if (type === 'price') {
      display = Number(value).toLocaleString('ko-KR') + '원'
    }
  }
  return (
    <div className="etf-feature-card" title={tip}>
      <div className="etf-feature-label">{label}</div>
      <div className="etf-feature-value" style={{ color }}>{display}</div>
    </div>
  )
}

// ── 스켈레톤 ──────────────────────────────────────────────────────────────
function Skeleton({ rows = 3 }) {
  return (
    <div className="etf-skeleton">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="etf-skeleton-row" style={{ width: `${85 - i * 10}%` }} />
      ))}
    </div>
  )
}

// ── 메인 컴포넌트 ─────────────────────────────────────────────────────────
function ETFDetailPage() {
  const { etfCode } = useParams()
  const navigate    = useNavigate()
  const { state }   = useLocation()

  const etfItem  = state?.etfItem
  const riskTier = state?.riskTier

  const [chartDays,       setChartDays]       = useState(30)
  const [detail,          setDetail]          = useState(null)
  const [loading,         setLoading]         = useState(true)
  const [error,           setError]           = useState(null)
  const [holdings,        setHoldings]        = useState([])
  const [holdingsLoading, setHoldingsLoading] = useState(true)
  const [analysis,        setAnalysis]        = useState(null)
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [analysisError,   setAnalysisError]   = useState(false)
  const [analysisRetry,   setAnalysisRetry]   = useState(0)
  const [realtimePrice,   setRealtimePrice]   = useState(null)

  // ── 기본 데이터 로드 ──────────────────────────────────────────────────
  useEffect(() => {
    if (!etfCode) return
    setLoading(true)
    setError(null)
    fetch(`/api/instruments/etfs/${etfCode}`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(det => { setDetail(det); setLoading(false) })
      .catch(err => { setError(err.message); setLoading(false) })
  }, [etfCode])

  // ── 포트폴리오 보유 종목 로드 ─────────────────────────────────────────
  useEffect(() => {
    if (!etfCode) return
    setHoldingsLoading(true)
    fetch(`/api/instruments/etfs/${etfCode}/holdings?limit=10`)
      .then(r => r.ok ? r.json() : [])
      .then(data => { setHoldings(data); setHoldingsLoading(false) })
      .catch(() => setHoldingsLoading(false))
  }, [etfCode])

  // ── 실시간 가격 SSE ──────────────────────────────────────────────────
  useEffect(() => {
    if (!etfCode || loading) return
    let eventSource = null
    let reconnectTimer = null
    let isActive = true

    const connect = () => {
      if (!isActive) return
      try {
        eventSource = new EventSource(`/api/stream/prices?codes=${etfCode}`)
        eventSource.onmessage = (event) => {
          try {
            const updates = JSON.parse(event.data)
            const priceData = updates[etfCode]
            if (priceData) setRealtimePrice(priceData)
          } catch {}
        }
        eventSource.onerror = () => {
          if (eventSource) eventSource.close()
          if (isActive) reconnectTimer = setTimeout(connect, 5000)
        }
      } catch {}
    }

    connect()
    return () => {
      isActive = false
      if (eventSource) eventSource.close()
      if (reconnectTimer) clearTimeout(reconnectTimer)
    }
  }, [etfCode, loading])

  // ── AI 분석 로드 ─────────────────────────────────────────────────────
  useEffect(() => {
    if (!etfCode) return
    const cacheKey = `etf_analysis_${etfCode}`

    if (analysisRetry === 0) {
      try {
        const raw = sessionStorage.getItem(cacheKey)
        if (raw) {
          const { data, ts } = JSON.parse(raw)
          if (Date.now() - ts < 3_600_000) { setAnalysis(data); return }
        }
      } catch {}
    }

    const investmentType = localStorage.getItem('investment_type') || '위험중립형'
    const userProfile = JSON.stringify({
      risk_tier: investmentType, grade: '3등급', horizon_years: 3,
      goal: '자산증식', deployment: '분산투자',
      monthly_contribution_krw: 300000, total_assets_krw: 10000000,
      dividend_pref_1to5: 3, account_type: '일반',
    })

    setAnalysisLoading(true)
    setAnalysisError(false)
    setAnalysis(null)

    const controller = new AbortController()
    const timerId = setTimeout(() => controller.abort(), 450_000)

    fetch('/api/v1/analysis/report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      body: JSON.stringify({
        ticker: etfCode,
        mode: 'stock_detail',
        user_profile_json: userProfile,
        stock_item_json: etfItem ? JSON.stringify(etfItem) : '{}',
      }),
    })
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(data => {
        let parsed = null
        try { parsed = JSON.parse(data.report) } catch {}
        const hasContent = parsed &&
          (parsed.investment_fit || parsed.company_analysis || parsed.industry_analysis || parsed.etf_analysis)
        if (!hasContent) { setAnalysisLoading(false); setAnalysisError(true); return }
        setAnalysis(parsed)
        setAnalysisLoading(false)
        try { sessionStorage.setItem(cacheKey, JSON.stringify({ data: parsed, ts: Date.now() })) } catch {}
      })
      .catch(err => {
        if (err.name === 'AbortError') return
        setAnalysisLoading(false)
        setAnalysisError(true)
      })

    return () => { clearTimeout(timerId); controller.abort() }
  }, [etfCode, analysisRetry])

  if (loading) return (
    <div className="etf-detail-page">
      <div className="etf-loading">ETF 데이터를 불러오는 중...</div>
    </div>
  )
  if (error || !detail) return (
    <div className="etf-detail-page">
      <div className="etf-error-box">
        <p>{error || '데이터를 불러올 수 없습니다.'}</p>
        <button onClick={() => navigate(-1)} className="etf-back-btn">← 뒤로</button>
      </div>
    </div>
  )

  const currentPrice = realtimePrice?.current_price ?? detail.current_price
  const change       = realtimePrice?.change ?? detail.change
  const changeRate   = realtimePrice?.change_rate ?? detail.change_rate
  const isUp = (changeRate ?? 0) >= 0

  // ── 투자 원칙 적합도 ─────────────────────────────────────────────────
  const fitScore   = etfItem?.total_score != null
    ? Math.round(etfItem.total_score * 100)
    : analysis?.investment_fit?.fit_score != null
      ? Math.round(analysis.investment_fit.fit_score * 100)
      : null
  const fitReasons = etfItem?.reasons ?? analysis?.investment_fit?.reason_explanations ?? []
  const fitCaution = analysis?.investment_fit?.caution ?? null
  const fitSummary = analysis?.investment_fit?.fit_summary
    ?? (riskTier ? `귀하의 ${riskTier} 투자 성향에 적합한 ETF입니다.` : null)

  // ── ETF 종합 분석 불릿 ───────────────────────────────────────────────
  const etfBullets = [
    ...(analysis?.etf_analysis?.highlights ?? []),
    ...(analysis?.industry_analysis?.current_trends ?? []),
    ...(analysis?.company_analysis?.strengths ?? []).slice(0, 2),
  ]

  // ── ETF 상품 설명 필드 ───────────────────────────────────────────────
  const etfInfoFields = [
    { label: 'ETF명',      value: detail.name },
    { label: '추종 지수',  value: detail.tracking_index || '-' },
    { label: '운용사',     value: detail.fund_manager || '-' },
    { label: '순자산(AUM)', value: detail.aum != null ? fmtAum(detail.aum) : '-' },
    { label: '거래소',     value: detail.exchange || '-' },
    { label: '섹터',       value: detail.sector || '-' },
  ]

  // ── AI 요약 ─────────────────────────────────────────────────────────
  const recText = analysis?.page_summary
    ?? analysis?.etf_analysis?.overview
    ?? analysis?.company_analysis?.overall_company_view
    ?? (fitReasons.length > 0 ? fitReasons.join(' ') : null)

  return (
    <div className="etf-detail-page">
      <div className="etf-detail-container">

        <button onClick={() => navigate(-1)} className="etf-back-btn">← 추천 목록으로</button>

        {/* ── 1. 헤더 ─────────────────────────────────────────────── */}
        <div className="etf-detail-header">
          <div className="etf-header-left">
            {etfItem?.rank && <span className="etf-rank-badge">#{etfItem.rank}</span>}
            <h1 className="etf-detail-name">{detail.name}</h1>
            <div className="etf-badges">
              <span className="etf-ticker">{detail.stock_code}</span>
              <span className="etf-market-badge">{detail.exchange}</span>
              <span className="etf-type-badge">ETF</span>
              {detail.sector && detail.sector !== '-' && (
                <span className="etf-sector-badge">{detail.sector}</span>
              )}
              {riskTier && <span className="etf-risk-tier">{riskTier}</span>}
            </div>
          </div>
          <div className="etf-price-box">
            <div className="etf-current-price">
              {fmtPrice(currentPrice)}
              {realtimePrice && (
                <span className="etf-realtime-badge" title="실시간 업데이트">🔴 LIVE</span>
              )}
            </div>
            {change != null && (
              <div className="etf-change-badge" style={{ color: isUp ? '#EA580C' : '#3B82F6' }}>
                {isUp ? '▲' : '▼'} {Math.abs(change).toLocaleString('ko-KR')}원
                &nbsp;({changeRate >= 0 ? '+' : ''}{Number(changeRate).toFixed(2)}%)
              </div>
            )}
            <div className="etf-price-date">{detail.price_date} 기준</div>
          </div>
        </div>

        {/* ── 2. 주가 차트 ─────────────────────────────────────────── */}
        {detail.price_history.length > 1 && (
          <section className="etf-section">
            <div className="etf-chart-header">
              <h2 className="etf-section-heading" style={{ margin: 0, borderBottom: 'none', paddingBottom: 0 }}>NAV 차트</h2>
              <div className="etf-chart-tabs">
                {[
                  { label: '1W', days: 7 },
                  { label: '1M', days: 30 },
                  { label: '3M', days: 90 },
                  { label: '6M', days: 180 },
                  { label: '1Y', days: 365 },
                ].map(({ label, days }) => (
                  <button
                    key={days}
                    className={`etf-chart-tab${chartDays === days ? ' active' : ''}`}
                    onClick={() => setChartDays(days)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <CandlestickChart data={detail.price_history} days={chartDays} />
          </section>
        )}

        {/* ── 3. 투자 원칙 적합도 ──────────────────────────────────── */}
        {(fitSummary || fitReasons.length > 0) && (
          <section className="etf-fit-section">
            <h2 className="etf-section-heading">내 투자 원칙 적합도 분석</h2>
            <div className="etf-fit-container">
              <div className="etf-fit-details">
                {fitSummary && <p className="etf-fit-summary">{fitSummary}</p>}
                {fitReasons.length > 0 && (
                  <ul className="etf-fit-list">
                    {fitReasons.slice(0, 3).map((r, i) => <li key={i}>✓ {r}</li>)}
                    {fitCaution && <li>△ {fitCaution}</li>}
                  </ul>
                )}
              </div>
            </div>
          </section>
        )}

        {/* ── 4. ETF 상품 설명 ─────────────────────────────────────── */}
        <section className="etf-info-section">
          <h2 className="etf-section-heading">ETF 상품 설명</h2>
          <div className="etf-info-grid">
            {etfInfoFields.map(({ label, value }) => (
              <div key={label} className="etf-info-item">
                <span className="etf-info-label">{label}</span>
                <span className="etf-info-value">{value}</span>
              </div>
            ))}
          </div>
        </section>

        {/* ── 5. ETF 종합 분석 ─────────────────────────────────────── */}
        <section className="etf-analysis-section">
          <h2 className="etf-section-heading">ETF 종합 분석</h2>
          {analysisLoading && etfBullets.length === 0
            ? <AnalysisProgressBar loading={analysisLoading} />
            : etfBullets.length > 0
              ? (
                <ul className="etf-analysis-list">
                  {etfBullets.map((b, i) => <li key={i}>{b}</li>)}
                </ul>
              )
              : analysisError
                ? (
                  <p className="etf-analysis-pending">
                    AI 분석을 불러오지 못했습니다.
                    <button className="etf-retry-btn" onClick={() => setAnalysisRetry(r => r + 1)}>🔄 다시 시도</button>
                  </p>
                )
                : !analysisLoading && (
                  <p className="etf-analysis-pending">분석 데이터를 준비 중입니다. 잠시 후 새로고침해 주세요.</p>
                )
          }
        </section>

        {/* ── 6. ETF 구성 Top10 ────────────────────────────────────── */}
        <section className="etf-section">
          <h2 className="etf-section-heading">ETF 구성 Top10</h2>
          {holdingsLoading ? (
            <Skeleton rows={5} />
          ) : holdings.length > 0 ? (
            <div className="etf-holdings-table-wrap">
              <table className="etf-holdings-table">
                <thead>
                  <tr>
                    <th>순위</th>
                    <th>구분</th>
                    <th>종목명</th>
                    <th>편입비중</th>
                  </tr>
                </thead>
                <tbody>
                  {holdings.map((h) => (
                    <tr key={h.rank}>
                      <td className="etf-holdings-rank">{h.rank}</td>
                      <td className="etf-holdings-type">{h.asset_type}</td>
                      <td className="etf-holdings-name">{h.name}</td>
                      <td className="etf-holdings-weight">
                        {Number(h.weight).toFixed(2)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="etf-analysis-pending">포트폴리오 구성 종목 데이터가 없습니다.</p>
          )}
        </section>

        {/* ── 7. AI 분석 요약 ─────────────────────────────────────── */}
        <section className="etf-section">
          <h2 className="etf-section-heading">{etfItem ? '추천 이유' : 'AI 분석 요약'}</h2>
          {analysisLoading && !recText
            ? <Skeleton rows={2} />
            : recText
              ? (
                <div className="etf-rec-box">
                  <p className="etf-rec-detail">{recText}</p>
                </div>
              )
              : analysisError
                ? (
                  <p className="etf-analysis-pending">
                    AI 분석을 불러오지 못했습니다.
                    <button className="etf-retry-btn" onClick={() => setAnalysisRetry(r => r + 1)}>🔄 다시 시도</button>
                  </p>
                )
                : !analysisLoading && (
                  <p className="etf-analysis-pending">분석 데이터를 준비 중입니다. 잠시 후 새로고침해 주세요.</p>
                )
          }
        </section>

        {/* ── 8. 주요 지표 ─────────────────────────────────────────── */}
        <section className="etf-section">
          <h2 className="etf-section-heading">주요 지표</h2>
          <div className="etf-features-grid">
            {ETF_METRICS.map(m => (
              <MetricCard key={m.key} label={m.label} value={detail[m.key]} type={m.type} tip={m.tip} />
            ))}
          </div>
        </section>

        {/* ── 9. 투자 유의사항 ─────────────────────────────────────── */}
        <section className="etf-section etf-notice-section">
          <h2 className="etf-section-heading">투자 유의사항</h2>
          <ul className="etf-notice-list">
            <li>본 데이터는 참고 정보이며, 투자 손익 책임은 투자자 본인에게 있습니다.</li>
            <li>과거 수익률이 미래 수익을 보장하지 않습니다.</li>
            <li>ETF는 기초지수를 추종하며 시장 상황에 따라 괴리율이 발생할 수 있습니다.</li>
          </ul>
        </section>

      </div>
    </div>
  )
}

export default ETFDetailPage
