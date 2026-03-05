import React, { useState, useEffect } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import './StockDetailPage.css'

// ── 포매터 ─────────────────────────────────────────────────────────────────
const fmtPrice = (v) => v == null ? '-' : Number(v).toLocaleString('ko-KR') + '원'
const fmtVol   = (v) => v == null ? '-' : Number(v).toLocaleString('ko-KR')

// ── 미니 스파크라인 차트 (SVG) ──────────────────────────────────────────────
function Sparkline({ data, width = 560, height = 100, color = '#EA580C' }) {
  if (!data || data.length < 2) return null
  const prices = data.map(d => d.close)
  const minP = Math.min(...prices)
  const maxP = Math.max(...prices)
  const range = maxP - minP || 1

  const pts = prices.map((p, i) => {
    const x = (i / (prices.length - 1)) * width
    const y = height - ((p - minP) / range) * (height - 12) - 6
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })

  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} style={{ display: 'block' }}>
      <polyline
        points={pts.join(' ')}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  )
}


// ── 지표 카드 ──────────────────────────────────────────────────────────────
const METRICS = [
  { key: 'ret_1m',   label: '1개월 수익률',  type: 'pct',   tip: '최근 1개월 주가 변동률' },
  { key: 'ret_3m',   label: '3개월 수익률',  type: 'pct',   tip: '최근 3개월 주가 변동률' },
  { key: 'ret_6m',   label: '6개월 수익률',  type: 'pct',   tip: '최근 6개월 주가 변동률' },
  { key: 'ret_1y',   label: '1년 수익률',    type: 'pct',   tip: '최근 1년 주가 변동률' },
  { key: 'vol_ann',  label: '연간 변동성',   type: 'pct_r', tip: '연환산 표준편차 (낮을수록 안정)' },
  { key: 'high_52w', label: '52주 최고가',   type: 'price', tip: '최근 52주 최고 종가' },
  { key: 'low_52w',  label: '52주 최저가',   type: 'price', tip: '최근 52주 최저 종가' },
]

function MetricCard({ label, value, type, tip }) {
  let display = '-'
  let color = '#333'
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
    <div className="sd-feature-card" title={tip}>
      <div className="sd-feature-label">{label}</div>
      <div className="sd-feature-value" style={{ color }}>{display}</div>
    </div>
  )
}

// ── 메인 컴포넌트 ──────────────────────────────────────────────────────────
function StockDetailPage() {
  const { stockCode } = useParams()
  const navigate      = useNavigate()
  const { state }     = useLocation()

  // 추천 페이지에서 넘어온 데이터 (선택적)
  const stockItem = state?.stockItem
  const riskTier  = state?.riskTier

  const [detail, setDetail]   = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)

  useEffect(() => {
    if (!stockCode) return
    setLoading(true)
    setError(null)
    fetch(`/api/instruments/stocks/${stockCode}`)
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then(data => { setDetail(data); setLoading(false) })
      .catch(err => { setError(err.message); setLoading(false) })
  }, [stockCode])

  if (loading) return (
    <div className="stock-detail-page">
      <div className="sd-loading">주가 데이터를 불러오는 중...</div>
    </div>
  )
  if (error || !detail) return (
    <div className="stock-detail-page">
      <div className="sd-error-box">
        <p>{error || '데이터를 불러올 수 없습니다.'}</p>
        <button onClick={() => navigate(-1)} className="sd-back-btn">← 뒤로</button>
      </div>
    </div>
  )

  const isUp = (detail.change_rate ?? 0) >= 0
  const chartColor = isUp ? '#EA580C' : '#3B82F6'
  const chartData  = detail.price_history.slice(-60)

  return (
    <div className="stock-detail-page">
      <div className="stock-detail-container">

        <button onClick={() => navigate(-1)} className="sd-back-btn">← 뒤로</button>

        {/* ── 헤더 ─────────────────────────────────────────────── */}
        <div className="stock-detail-header">
          <div className="sd-header-left">
            {stockItem?.rank && <span className="sd-rank-badge">#{stockItem.rank}</span>}
            <h1 className="stock-detail-name">{detail.name}</h1>
            <div style={{ display: 'flex', gap: 8, marginTop: 4, flexWrap: 'wrap' }}>
              <span className="sd-ticker">{detail.stock_code}</span>
              <span className="sd-market-badge">{detail.exchange}</span>
              {detail.sector && detail.sector !== '시장' && (
                <span className="sd-sector-badge">{detail.sector}</span>
              )}
              {riskTier && <span className="sd-risk-tier">{riskTier}</span>}
            </div>
          </div>

          <div className="sd-price-box">
            <div className="sd-current-price">{fmtPrice(detail.current_price)}</div>
            {detail.change != null && (
              <div className="sd-change-badge" style={{ color: isUp ? '#EA580C' : '#3B82F6' }}>
                {isUp ? '▲' : '▼'} {Math.abs(detail.change).toLocaleString('ko-KR')}원
                &nbsp;({detail.change_rate >= 0 ? '+' : ''}{Number(detail.change_rate).toFixed(2)}%)
              </div>
            )}
            <div className="sd-price-date">{detail.price_date} 기준</div>
          </div>
        </div>

        {/* ── 추천 점수 바 (추천 페이지 경유) ─────────────────── */}
        {stockItem?.total_score != null && (
          <div className="sd-score-row-outer">
            <span className="sd-score-label">추천 점수</span>
            <div className="sd-score-bar-bg">
              <div className="sd-score-bar-fill"
                style={{ width: `${Math.round(stockItem.total_score * 100)}%` }} />
            </div>
            <span className="sd-score-value">{Math.round(stockItem.total_score * 100)}</span>
          </div>
        )}

        {/* ── 가격 차트 ─────────────────────────────────────── */}
        {chartData.length > 1 && (
          <section className="sd-section">
            <h2 className="sd-section-heading">
              최근 60일 주가 추이
              <span style={{ fontWeight: 400, fontSize: 12, color: '#888', marginLeft: 8 }}>
                {chartData[0]?.date} ~ {chartData[chartData.length - 1]?.date}
              </span>
            </h2>
            <div className="sd-chart-wrap">
              <div className="sd-chart-yaxis">
                <span>{Number(Math.max(...chartData.map(d => d.close))).toLocaleString()}</span>
                <span>{Number(Math.min(...chartData.map(d => d.close))).toLocaleString()}</span>
              </div>
              <Sparkline data={chartData} color={chartColor} />
            </div>
          </section>
        )}

        {/* ── 주요 지표 ──────────────────────────────────────── */}
        <section className="sd-section">
          <h2 className="sd-section-heading">주요 지표</h2>
          <div className="sd-features-grid">
            {METRICS.map(m => (
              <MetricCard key={m.key} label={m.label} value={detail[m.key]} type={m.type} tip={m.tip} />
            ))}
          </div>
        </section>

        {/* ── 추천 이유 (추천 페이지 경유) ─────────────────── */}
        {stockItem?.reasons?.length > 0 && (
          <section className="sd-section">
            <h2 className="sd-section-heading">추천 이유</h2>
            <ul className="sd-reasons-list">
              {stockItem.reasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          </section>
        )}

        {/* ── 최근 10일 가격 테이블 ─────────────────────────── */}
        {detail.price_history.length > 0 && (
          <section className="sd-section">
            <h2 className="sd-section-heading">최근 거래 내역</h2>
            <div className="sd-table-wrap">
              <table className="sd-price-table">
                <thead>
                  <tr><th>날짜</th><th>종가</th><th>거래량</th><th>전일대비</th></tr>
                </thead>
                <tbody>
                  {detail.price_history.slice(-10).reverse().map((row, i, arr) => {
                    const prevClose = arr[i + 1]?.close
                    const chg = prevClose != null ? row.close - prevClose : null
                    const chgPct = prevClose ? (chg / prevClose * 100) : null
                    return (
                      <tr key={row.date}>
                        <td>{row.date}</td>
                        <td>{Number(row.close).toLocaleString()}원</td>
                        <td>{fmtVol(row.volume)}</td>
                        <td style={{ color: chg == null ? '#888' : chg >= 0 ? '#EA580C' : '#3B82F6' }}>
                          {chg == null ? '-' : `${chg >= 0 ? '+' : ''}${Number(chg).toLocaleString()}원 (${chgPct >= 0 ? '+' : ''}${Number(chgPct).toFixed(2)}%)`}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* ── 투자 유의사항 ─────────────────────────────────── */}
        <section className="sd-section sd-notice-section">
          <h2 className="sd-section-heading">투자 유의사항</h2>
          <ul className="sd-notice-list">
            <li>본 데이터는 DB 기반 참고 정보이며, 투자 손익 책임은 투자자 본인에게 있습니다.</li>
            <li>과거 수익률이 미래 수익을 보장하지 않습니다.</li>
          </ul>
        </section>

      </div>
    </div>
  )
}

export default StockDetailPage