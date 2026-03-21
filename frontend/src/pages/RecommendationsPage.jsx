import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import './RecommendationsPage.css'

const COLOR_PALETTE = [
  '#C2410C', '#EA580C', '#F97316', '#FB923C',
  '#FDBA74', '#FED7AA', '#FFEDD5', '#FFF4E6',
]

const fmtPct = (v) => (v == null ? '-' : `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`)
const fmtNum = (v) => (v == null ? '-' : new Intl.NumberFormat('ko-KR').format(Math.round(v)))

function buildPieSlices(items, palette) {
  const total = items.reduce((s, it) => s + it.weight_pct, 0)
  let cumAngle = -Math.PI / 2
  return items.map((item, idx) => {
    const angle = (item.weight_pct / total) * 2 * Math.PI
    const x1 = Math.cos(cumAngle)
    const y1 = Math.sin(cumAngle)
    cumAngle += angle
    const x2 = Math.cos(cumAngle)
    const y2 = Math.sin(cumAngle)
    const large = angle > Math.PI ? 1 : 0
    const path = `M 0 0 L ${x1} ${y1} A 1 1 0 ${large} 1 ${x2} ${y2} Z`
    return { path, color: palette[idx % palette.length], name: item.name, pct: item.weight_pct }
  })
}

function getGrowthBadge(item) {
  const vol = item.features?.vol_ann ?? 0
  const ret = item.features?.ret_3m ?? 0
  if (vol > 0.4) return { label: 'Volatile Growth', cls: 'badge-volatile' }
  if (ret > 0.08) return { label: 'High Momentum', cls: 'badge-momentum' }
  return { label: 'Stable Growth', cls: 'badge-stable' }
}

function RecommendationsPage() {
  const [stockData, setStockData] = useState(null)
  const [portfolioData, setPortfolioData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [stockLoading, setStockLoading] = useState(false)
  const [portfolioLoading, setPortfolioLoading] = useState(false)
  const [error, setError] = useState(null)
  const navigate = useNavigate()
  const { user } = useAuth()

  useEffect(() => {
    if (user?.userId) {
      fetchRecommendations(user.userId)
    } else {
      setError('로그인이 필요합니다.')
      setLoading(false)
    }
  }, [user])

  const fetchRecommendations = async (userId) => {
    setLoading(true)
    setError(null)

    // 종목 추천: 대시보드와 동일한 엔드포인트 사용
    fetch(`/api/dashboard/stock-recommendations?user_id=${userId}&refresh=false`)
      .then(res => {
        if (!res.ok) throw new Error(`종목 추천 오류 (${res.status})`)
        return res.json()
      })
      .then(stocks => {
        setStockData(stocks)
        setLoading(false)
      })
      .catch(err => {
        console.error(err)
        setError(err.message)
        setLoading(false)
      })

    // 포트폴리오 추천: 대시보드와 동일한 엔드포인트 사용
    setPortfolioLoading(true)
    fetch(`/api/dashboard/portfolio-recommendations-ai?user_id=${userId}&refresh=false`)
      .then(res => {
        if (!res.ok) throw new Error(`포트폴리오 추천 오류 (${res.status})`)
        return res.json()
      })
      .then(data => {
        setPortfolioData(Array.isArray(data) ? data[0] : data)
      })
      .catch(err => console.error(err))
      .finally(() => setPortfolioLoading(false))
  }

  const refreshStocks = async () => {
    if (!user?.userId || stockLoading) return
    try {
      setStockLoading(true)
      const res = await fetch(`/api/dashboard/stock-recommendations?user_id=${user.userId}&refresh=true`)
      if (!res.ok) throw new Error(`종목 분석 오류 (${res.status})`)
      setStockData(await res.json())
    } catch (err) {
      console.error(err)
    } finally {
      setStockLoading(false)
    }
  }

  const refreshPortfolio = async () => {
    if (!user?.userId || portfolioLoading) return
    try {
      setPortfolioLoading(true)
      const res = await fetch(`/api/dashboard/portfolio-recommendations-ai?user_id=${user.userId}&refresh=true`)
      if (!res.ok) throw new Error(`포트폴리오 분석 오류 (${res.status})`)
      const data = await res.json()
      const portfolios = data?.portfolios || data
      setPortfolioData(Array.isArray(portfolios) ? portfolios[0] : portfolios)
    } catch (err) {
      console.error(err)
    } finally {
      setPortfolioLoading(false)
    }
  }

  if (loading) return (
    <div className="rec-page">
      <div className="rec-loading-box">
        <div className="loading-spinner"></div>
        <p>추천 데이터를 불러오는 중...</p>
      </div>
    </div>
  )
  if (error) return (
    <div className="rec-page">
      <div className="rec-error-box">{error}</div>
    </div>
  )

  const sortedPortfolioItems = portfolioData
    ? [...portfolioData.portfolio_items].sort((a, b) => b.weight_pct - a.weight_pct)
    : []

  return (
    <div className="rec-page">

      {/* ── Editorial Header ── */}
      <div className="rec-editorial-header">
        <div className="rec-editorial-inner">
          <span className="rec-premium-badge">PREMIUM EDITORIAL</span>
          <h1 className="rec-main-title">
            맞춤 추천 Top {stockData?.items?.length ?? 0}
          </h1>
          <p className="rec-main-subtitle">
            성장 잠재력과 재무 건전성을 바탕으로 엄선된,<br />
            {stockData?.risk_tier} 투자자를 위한 프리미엄 추천 종목 리스트입니다.
          </p>
        </div>
      </div>

      {/* ── 종목 카드 섹션 ── */}
      <div className="rec-cards-section">
        <div className="rec-cards-inner">
          <div className="rec-cards-grid">
            {stockData?.items?.map((item) => {
              const score = Math.round(item.total_score * 100)
              const barPct = Math.min(score / 10, 100)
              const badge = getGrowthBadge(item)
              const vol = item.features?.vol_ann
              return (
                <div key={item.ticker} className="rec-card">
                  {/* 카드 헤더 */}
                  <div className="rec-card-header">
                    <div className="rec-card-name-row">
                      <span className="rec-card-name">{item.name}</span>
                      <span className="rec-card-code">{item.ticker}</span>
                    </div>
                    <div className="rec-card-market">{item.market}</div>
                  </div>

                  <hr className="rec-divider" />

                  {/* 추천 점수 */}
                  <div className="rec-score-section">
                    <div className="rec-score-header">
                      <span className="rec-score-label">Recommendation Score</span>
                      <span className="rec-score-num">
                        {score} <span className="rec-score-total">/ 1000</span>
                      </span>
                    </div>
                    <div className="rec-score-bar-bg">
                      <div className="rec-score-bar-fill" style={{ width: `${barPct}%` }} />
                    </div>
                  </div>

                  {/* 변동성 지수 */}
                  {vol != null && (
                    <div className="rec-vol-box">
                      <span className="rec-vol-label">변동성 지수</span>
                      <span className="rec-vol-value">
                        ± {(vol * 100).toFixed(1)}%
                        <span className="rec-vol-trend">
                          {vol > 0.3 ? ' ▲' : vol > 0.15 ? ' →' : ' ↘'}
                        </span>
                      </span>
                    </div>
                  )}

                  {/* WHY RECOMMEND */}
                  <div className="rec-why">
                    <div className="rec-why-title">WHY RECOMMEND</div>
                    <ul className="rec-why-list">
                      {item.reasons.slice(0, 2).map((r, i) => (
                        <li key={i}>
                          <span className="rec-check-icon">✓</span>
                          {r}
                        </li>
                      ))}
                    </ul>
                  </div>

                  {/* 리포트 버튼 */}
                  <button
                    className="rec-report-btn"
                    onClick={() => navigate(`/stock/${item.ticker}`, {
                      state: { stockItem: item, riskTier: stockData.risk_tier }
                    })}
                  >
                    상세 분석 리포트 보기
                  </button>
                </div>
              )
            })}
          </div>

          {/* 종목 갱신 */}
          <div className="rec-refresh-row">
            <button className="rec-refresh-btn" onClick={refreshStocks} disabled={stockLoading}>
              {stockLoading
                ? <><span className="analysis-btn-spinner" /> 분석 중...</>
                : '🔄 종목 다시 분석'}
            </button>
          </div>
        </div>
      </div>

      {/* ── 포트폴리오 섹션 ── */}
      <div className="rec-portfolio-section">
        <div className="rec-portfolio-inner">
          <div className="rec-portfolio-header-row">
            <div>
              <h2 className="rec-portfolio-title">나의 맞춤 포트폴리오</h2>
              <p className="rec-portfolio-sub">투자성향·설문 기반 최적 구성</p>
            </div>
            <button className="rec-refresh-btn" onClick={refreshPortfolio} disabled={portfolioLoading}>
              {portfolioLoading
                ? <><span className="analysis-btn-spinner" /> 분석 중...</>
                : '🔄 포트폴리오 분석'}
            </button>
          </div>

          {portfolioLoading && !portfolioData && (
            <div className="rec-loading-box">
              <div className="loading-spinner"></div>
              <p>포트폴리오를 구성하는 중입니다...</p>
            </div>
          )}

          {portfolioData && (
            <div
              className="rec-portfolio-card"
              onClick={() => navigate('/portfolio/recommendation', { state: { portfolioData } })}
            >
              <div className="rec-portfolio-card-header">
                <h3 className="rec-portfolio-card-name">
                  {portfolioData.risk_grade} · {portfolioData.risk_tier}
                </h3>
                {portfolioData.performance_3y && (
                  <div className="rec-portfolio-meta">
                    <span>연환산 수익률&nbsp;
                      <strong style={{ color: '#1B4332' }}>
                        {fmtPct(portfolioData.performance_3y.ann_return_pct)}
                      </strong>
                    </span>
                    <span>샤프&nbsp;
                      <strong>{portfolioData.performance_3y.sharpe.toFixed(2)}</strong>
                    </span>
                  </div>
                )}
              </div>

              <div className="rec-pie-layout">
                {/* SVG 파이차트 */}
                <svg className="rec-pie-svg" viewBox="-1.1 -1.1 2.2 2.2">
                  {buildPieSlices(sortedPortfolioItems, COLOR_PALETTE).map((slice, i) => (
                    <path
                      key={i}
                      d={slice.path}
                      fill={slice.color}
                      stroke="#fff"
                      strokeWidth="0.03"
                    >
                      <title>{slice.name}: {slice.pct.toFixed(1)}%</title>
                    </path>
                  ))}
                </svg>

                {/* 범례 */}
                <div className="allocation-list">
                  {sortedPortfolioItems.slice(0, 6).map((item, idx) => (
                    <div key={item.ticker} className="allocation-item">
                      <span className="allocation-color" style={{ backgroundColor: COLOR_PALETTE[idx % COLOR_PALETTE.length] }} />
                      <span className="allocation-name">{item.name}</span>
                      <span className="allocation-percent">{item.weight_pct.toFixed(1)}%</span>
                    </div>
                  ))}
                  {sortedPortfolioItems.length > 6 && (
                    <div className="allocation-item" style={{ color: '#888' }}>
                      외 {sortedPortfolioItems.length - 6}종목
                    </div>
                  )}
                </div>
              </div>

              <div className="portfolio-recommendation">
                <p className="recommendation-text">{portfolioData.overall_summary}</p>
              </div>

              <button className="rec-report-btn" style={{ marginTop: 20 }}>
                포트폴리오 상세 보기 →
              </button>
            </div>
          )}
        </div>
      </div>

    </div>
  )
}

export default RecommendationsPage
