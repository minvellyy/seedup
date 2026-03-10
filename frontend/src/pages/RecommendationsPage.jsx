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
    try {
      setLoading(true)
      const [stockRes, portfolioRes] = await Promise.all([
        fetch(`/api/v1/stocks/recommend/${userId}`),
        fetch(`/api/v1/portfolio/recommend/${userId}`),
      ])
      if (!stockRes.ok) throw new Error(`종목 추천 오류 (${stockRes.status})`)
      if (!portfolioRes.ok) throw new Error(`포트폴리오 추천 오류 (${portfolioRes.status})`)
      const [stocks, portfolio] = await Promise.all([stockRes.json(), portfolioRes.json()])
      setStockData(stocks)
      setPortfolioData(portfolio)
      setError(null)
    } catch (err) {
      console.error(err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const refreshStocks = async () => {
    if (!user?.userId || stockLoading) return
    try {
      setStockLoading(true)
      const res = await fetch(`/api/v1/stocks/recommend/${user.userId}`)
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
      const res = await fetch(`/api/v1/portfolio/recommend/${user.userId}`)
      if (!res.ok) throw new Error(`포트폴리오 분석 오류 (${res.status})`)
      setPortfolioData(await res.json())
    } catch (err) {
      console.error(err)
    } finally {
      setPortfolioLoading(false)
    }
  }

  if (loading) return (
    <div className="recommendations-page">
      <div className="loading">추천 데이터를 불러오는 중...</div>
    </div>
  )
  if (error) return (
    <div className="recommendations-page">
      <div className="error-message">{error}</div>
    </div>
  )

  const sortedPortfolioItems = portfolioData
    ? [...portfolioData.portfolio_items].sort((a, b) => b.weight_pct - a.weight_pct)
    : []

  return (
    <div className="recommendations-page">
      <div className="recommendations-container">

        {/* 투자성향 배지 */}
        {stockData && (
          <div className="rec-profile-banner">
            <span className="rec-risk-grade">{stockData.risk_grade}</span>
            <span className="rec-risk-tier">{stockData.risk_tier} 맞춤 추천</span>
            <span className="rec-generated-at">{stockData.generated_at?.slice(0, 10)} 기준</span>
          </div>
        )}

        {/* ── 종목 추천 섹션 ── */}
        <section className="stocks-section">
          <div className="section-title-row">
            <h1 className="section-title">종목 Top {stockData?.items?.length ?? 0}</h1>
            <button
              className="analysis-btn"
              onClick={refreshStocks}
              disabled={stockLoading}
            >
              {stockLoading ? (
                <><span className="analysis-btn-spinner" />분석 중...</>
              ) : '종목 분석'}
            </button>
          </div>
          <p className="section-subtitle">투자성향 기반 개별 종목 추천</p>

          <div className="stocks-list">
            {stockData?.items?.map((item) => (
              <div
                key={item.ticker}
                className="stock-card"
                onClick={() => navigate(`/stock/${item.ticker}`, {
                  state: { stockItem: item, riskTier: stockData.risk_tier }
                })}
              >
                <div className="stock-header">
                  <div className="stock-rank">#{item.rank}</div>
                  <div className="stock-info">
                    <h2 className="stock-name">{item.name}</h2>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 4 }}>
                      <span className="stock-code">{item.ticker}</span>
                      <span className="rec-market-badge">{item.market}</span>
                    </div>
                  </div>
                </div>

                {/* 추천 점수 바 */}
                <div className="rec-score-row">
                  <span className="rec-score-label">추천 점수</span>
                  <div className="rec-score-bar-bg">
                    <div
                      className="rec-score-bar-fill"
                      style={{ width: `${Math.round(item.total_score * 100)}%` }}
                    />
                  </div>
                  <span className="rec-score-value">{Math.round(item.total_score * 100)}</span>
                </div>

                {/* 주요 지표 */}
                <div className="rec-features">
                  {item.features.ret_3m != null && (
                    <div className="rec-feature-chip">
                      <span>3개월수익</span>
                      <strong style={{ color: item.features.ret_3m >= 0 ? '#EA580C' : '#3B82F6' }}>
                        {fmtPct(item.features.ret_3m * 100)}
                      </strong>
                    </div>
                  )}
                  {item.features.vol_ann != null && (
                    <div className="rec-feature-chip">
                      <span>연변동성</span>
                      <strong>{fmtPct(item.features.vol_ann * 100)}</strong>
                    </div>
                  )}
                  {item.features.beta != null && (
                    <div className="rec-feature-chip">
                      <span>베타</span>
                      <strong>{item.features.beta.toFixed(2)}</strong>
                    </div>
                  )}
                </div>

                {/* 추천 근거 (1~2줄) */}
                <div className="stock-recommendation">
                  <h3 className="recommendation-title">추천 이유</h3>
                  <ul className="rec-reasons-list">
                    {item.reasons.slice(0, 2).map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ── 포트폴리오 추천 섹션 ── */}
        <section className="portfolios-section">
          <div className="section-title-row">
            <h1 className="section-title">나의 맞춤 포트폴리오</h1>
            <button
              className="analysis-btn"
              onClick={refreshPortfolio}
              disabled={portfolioLoading}
            >
              {portfolioLoading ? (
                <><span className="analysis-btn-spinner" />분석 중...</>
              ) : '포트폴리오 분석'}
            </button>
          </div>
          <p className="section-subtitle">투자성향·설문 기반 최적 구성</p>

          {portfolioData && (
            <div
              className="portfolio-card"
              onClick={() => navigate('/portfolio/recommendation', { state: { portfolioData } })}
            >
              <div className="portfolio-header">
                <div className="portfolio-info">
                  <h2 className="portfolio-name">
                    {portfolioData.risk_grade} · {portfolioData.risk_tier}
                  </h2>
                  <div className="portfolio-meta" style={{ gap: 16 }}>
                    {portfolioData.performance_3y && (
                      <>
                        <span className="expected-return">
                          연환산 수익률: <strong style={{ color: '#EA580C' }}>
                            {fmtPct(portfolioData.performance_3y.ann_return_pct)}
                          </strong>
                        </span>
                        <span className="expected-return">
                          샤프: <strong>{portfolioData.performance_3y.sharpe.toFixed(2)}</strong>
                        </span>
                      </>
                    )}
                  </div>
                </div>
              </div>

              {/* 자산 배분 바 */}
              <div className="portfolio-allocation">
                <h3 className="allocation-title">구성 종목 비중</h3>
                <div className="allocation-bar">
                  {sortedPortfolioItems.map((item, idx) => (
                    <div
                      key={item.ticker}
                      className="allocation-segment"
                      style={{
                        width: `${item.weight_pct}%`,
                        backgroundColor: COLOR_PALETTE[idx % COLOR_PALETTE.length],
                      }}
                      title={`${item.name}: ${item.weight_pct.toFixed(1)}%`}
                    />
                  ))}
                </div>
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

              {/* 요약 */}
              <div className="portfolio-recommendation">
                <h3 className="recommendation-title">포트폴리오 요약</h3>
                <p className="recommendation-text">{portfolioData.overall_summary}</p>
              </div>

              <div style={{ textAlign: 'center', marginTop: 16 }}>
                <span className="rec-detail-link">상세 보기 →</span>
              </div>
            </div>
          )}
        </section>

      </div>
    </div>
  )
}

export default RecommendationsPage
