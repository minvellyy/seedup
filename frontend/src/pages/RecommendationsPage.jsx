import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import './RecommendationsPage.css'

// 주황색 계열 색상 팔레트 (진한 색 → 옅은 색)
const COLOR_PALETTE = [
  '#C2410C',  // 매우 진한 주황
  '#EA580C',  // 진한 주황
  '#F97316',  // 표준 오렌지
  '#FB923C',  // 밝은 주황
  '#FDBA74',  // 연한 주황
  '#FED7AA',  // 피치
  '#FFEDD5',  // 밝은 피치
  '#FFF4E6'   // 크림
]

function RecommendationsPage() {
  const [recommendations, setRecommendations] = useState({ stocks: [], portfolios: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    fetchRecommendations()
  }, [])

  const fetchRecommendations = async () => {
    try {
      setLoading(true)
      const response = await fetch('http://localhost:8000/api/recommendations/')
      
      if (!response.ok) {
        throw new Error('추천 데이터를 불러오는데 실패했습니다.')
      }
      
      const data = await response.json()
      setRecommendations(data)
      setError(null)
    } catch (err) {
      console.error('Failed to fetch recommendations:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleStockClick = (stockCode) => {
    navigate(`/stock/${stockCode}`)
  }

  const handlePortfolioClick = (portfolioId) => {
    navigate(`/portfolio/${portfolioId}`)
  }

  const formatNumber = (num) => {
    return new Intl.NumberFormat('ko-KR').format(num)
  }

  const formatPercent = (num) => {
    const sign = num >= 0 ? '+' : ''
    return `${sign}${num.toFixed(2)}%`
  }

  if (loading) {
    return (
      <div className="recommendations-page">
        <div className="loading">데이터를 불러오는 중...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="recommendations-page">
        <div className="error-message">{error}</div>
      </div>
    )
  }

  return (
    <div className="recommendations-page">
      <div className="recommendations-container">
        
        {/* 종목 Top3 섹션 */}
        <section className="stocks-section">
          <h1 className="section-title">종목 Top 3</h1>
          <p className="section-subtitle">맞춤형 종목 추천</p>
          
          <div className="stocks-list">
            {recommendations.stocks.map((stock, index) => (
              <div 
                key={stock.stock_code} 
                className="stock-card"
                onClick={() => handleStockClick(stock.stock_code)}
              >
                <div className="stock-header">
                  <div className="stock-rank">#{index + 1}</div>
                  <div className="stock-info">
                    <h2 className="stock-name">{stock.stock_name}</h2>
                    <span className="stock-code">{stock.stock_code}</span>
                  </div>
                </div>
                
                <div className="stock-price-info">
                  <div className="current-price">
                    <span className="price-label">현재가</span>
                    <span className="price-value">{formatNumber(stock.current_price)}원</span>
                  </div>
                  <div className={`price-change ${stock.price_change >= 0 ? 'positive' : 'negative'}`}>
                    <span className="change-amount">{formatNumber(stock.price_change)}원</span>
                    <span className="change-percent">{formatPercent(stock.price_change_percent)}</span>
                  </div>
                </div>
                
                {/* 간단한 차트 표현 (최근 30일) */}
                <div className="mini-chart">
                  <svg width="100%" height="80" preserveAspectRatio="none">
                    {stock.chart_data && stock.chart_data.length > 1 && (
                      <polyline
                        fill="none"
                        stroke={stock.price_change >= 0 ? "#e74c3c" : "#3498db"}
                        strokeWidth="2"
                        points={stock.chart_data.map((point, idx) => {
                          const x = (idx / (stock.chart_data.length - 1)) * 100
                          const prices = stock.chart_data.map(p => p.price)
                          const minPrice = Math.min(...prices)
                          const maxPrice = Math.max(...prices)
                          const y = 70 - ((point.price - minPrice) / (maxPrice - minPrice)) * 60
                          return `${x},${y}`
                        }).join(' ')}
                      />
                    )}
                  </svg>
                </div>
                
                <div className="stock-recommendation">
                  <h3 className="recommendation-title">추천 이유</h3>
                  <p className="recommendation-text">{stock.recommendation_reason}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
        
        {/* 포트폴리오 Top3 섹션 */}
        <section className="portfolios-section">
          <h1 className="section-title">포트폴리오 Top 3</h1>
          <p className="section-subtitle">맞춤형 포트폴리오 추천</p>
          
          <div className="portfolios-list">
            {recommendations.portfolios.map((portfolio, index) => (
              <div 
                key={portfolio.portfolio_id} 
                className="portfolio-card"
                onClick={() => handlePortfolioClick(portfolio.portfolio_id)}
              >
                <div className="portfolio-header">
                  <div className="portfolio-rank">#{index + 1}</div>
                  <div className="portfolio-info">
                    <h2 className="portfolio-name">{portfolio.portfolio_name}</h2>
                    <div className="portfolio-meta">
                      <span className="expected-return">
                        기대 수익률: <strong>{portfolio.expected_return}%</strong>
                      </span>
                      <span className={`risk-level risk-${portfolio.risk_level}`}>
                        리스크: {portfolio.risk_level}
                      </span>
                    </div>
                  </div>
                </div>
                
                {/* 자산 배분 */}
                <div className="portfolio-allocation">
                  <h3 className="allocation-title">자산 배분</h3>
                  <div className="allocation-bar">
                    {[...portfolio.assets]
                      .sort((a, b) => b.allocation_percent - a.allocation_percent)
                      .map((asset, idx) => (
                      <div
                        key={idx}
                        className="allocation-segment"
                        style={{ 
                          width: `${asset.allocation_percent}%`,
                          backgroundColor: COLOR_PALETTE[idx % COLOR_PALETTE.length]
                        }}
                        title={`${asset.stock_name}: ${asset.allocation_percent}%`}
                      />
                    ))}
                  </div>
                  <div className="allocation-list">
                    {[...portfolio.assets]
                      .sort((a, b) => b.allocation_percent - a.allocation_percent)
                      .map((asset, idx) => (
                      <div key={idx} className="allocation-item">
                        <span 
                          className="allocation-color"
                          style={{ backgroundColor: COLOR_PALETTE[idx % COLOR_PALETTE.length] }}
                        />
                        <span className="allocation-name">{asset.stock_name}</span>
                        <span className="allocation-percent">{asset.allocation_percent}%</span>
                      </div>
                    ))}
                  </div>
                </div>
                
                <div className="portfolio-recommendation">
                  <h3 className="recommendation-title">추천 이유</h3>
                  <p className="recommendation-text">{portfolio.recommendation_reason}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
        
      </div>
    </div>
  )
}

export default RecommendationsPage
