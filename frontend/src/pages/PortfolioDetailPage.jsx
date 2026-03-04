import React, { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import './PortfolioDetailPage.css'

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

function PortfolioDetailPage() {
  const { portfolioId } = useParams()
  const navigate = useNavigate()
  const [portfolio, setPortfolio] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchPortfolioDetail()
  }, [portfolioId])

  const fetchPortfolioDetail = async () => {
    try {
      setLoading(true)
      const response = await fetch(`http://localhost:8000/api/recommendations/portfolios/${portfolioId}`)
      
      if (!response.ok) {
        throw new Error('포트폴리오 정보를 불러오는데 실패했습니다.')
      }
      
      const data = await response.json()
      setPortfolio(data)
      setError(null)
    } catch (err) {
      console.error('Failed to fetch portfolio detail:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleDownloadPDF = () => {
    // TODO: PDF 생성 및 다운로드 구현
    alert('PDF 다운로드 기능은 준비 중입니다.')
  }

  const handleStockClick = (stockCode) => {
    navigate(`/stock/${stockCode}`)
  }

  if (loading) {
    return (
      <div className="portfolio-detail-page">
        <div className="loading">데이터를 불러오는 중...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="portfolio-detail-page">
        <div className="error-message">{error}</div>
        <button onClick={() => navigate('/recommendations')} className="back-button">
          돌아가기
        </button>
      </div>
    )
  }

  if (!portfolio) {
    return null
  }

  const sortedAssets = [...portfolio.assets].sort((a, b) => b.allocation_percent - a.allocation_percent)

  return (
    <div className="portfolio-detail-page">
      <div className="portfolio-detail-container">
        
        <div className="header-actions">
          <button onClick={() => navigate('/recommendations')} className="back-button">
            ← 추천 목록으로
          </button>
          <button onClick={handleDownloadPDF} className="download-button">
            📄 포트폴리오 다운받기
          </button>
        </div>

        {/* 포트폴리오명 및 요약 */}
        <div className="portfolio-detail-header">
          <h1 className="portfolio-detail-name">{portfolio.portfolio_name}</h1>
          <p className="portfolio-summary">{portfolio.recommendation_reason}</p>
        </div>

        <div className="portfolio-detail-content">
          
          {/* 종목 구성 / 구성 비율 */}
          <section className="composition-section">
            <h2 className="section-heading">종목 구성 / 구성 비율</h2>
            
            {/* 비율 바 */}
            <div className="composition-bar-container">
              <div className="composition-bar">
                {sortedAssets.map((asset, idx) => (
                  <div
                    key={idx}
                    className="composition-segment"
                    style={{
                      width: `${asset.allocation_percent}%`,
                      backgroundColor: COLOR_PALETTE[idx % COLOR_PALETTE.length]
                    }}
                    title={`${asset.stock_name}: ${asset.allocation_percent}%`}
                  />
                ))}
              </div>
              <div className="composition-legend">
                {sortedAssets.map((asset, idx) => (
                  <div 
                    key={idx} 
                    className="legend-item"
                    onClick={() => handleStockClick(asset.stock_code)}
                    style={{ cursor: 'pointer' }}
                  >
                    <span
                      className="legend-color"
                      style={{ backgroundColor: COLOR_PALETTE[idx % COLOR_PALETTE.length] }}
                    />
                    <span className="legend-name">{asset.stock_name}</span>
                    <span className="legend-percent">{asset.allocation_percent}%</span>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* 수익률 / 리스크 */}
          <section className="returns-risk-section">
            <h2 className="section-heading">수익률 / 리스크</h2>
            
            <div className="returns-risk-container">
              {/* 수익률 카드 */}
              <div className="returns-cards">
                <div className="return-card">
                  <div className="return-label">단기 수익률 (3개월)</div>
                  <div className="return-value">
                    {portfolio.short_term_return ? `${portfolio.short_term_return}%` : '-'}
                  </div>
                </div>
                <div className="return-card">
                  <div className="return-label">중장기 수익률 (1년)</div>
                  <div className="return-value highlight">
                    {portfolio.mid_long_term_return ? `${portfolio.mid_long_term_return}%` : '-'}
                  </div>
                </div>
                <div className="return-card">
                  <div className="return-label">기대 수익률</div>
                  <div className="return-value">
                    {portfolio.expected_return}%
                  </div>
                </div>
              </div>

              {/* 리스크 분석 */}
              {portfolio.risk_analysis && (
                <div className="risk-analysis-box">
                  <h3 className="risk-title">
                    <span className="risk-icon">⚠️</span>
                    리스크 분석
                  </h3>
                  <p className="risk-content">{portfolio.risk_analysis}</p>
                </div>
              )}
            </div>
          </section>

          {/* 종목별 분석 */}
          {sortedAssets.some(asset => asset.analysis) && (
            <section className="stock-analysis-section">
              <h2 className="section-heading">종목별 분석</h2>
              <div className="stock-analysis-list">
                {sortedAssets.map((asset, idx) => (
                  asset.analysis && (
                    <div 
                      key={idx} 
                      className="stock-analysis-card"
                      onClick={() => handleStockClick(asset.stock_code)}
                    >
                      <div className="stock-analysis-header">
                        <div className="stock-title-row">
                          <span
                            className="stock-color-indicator"
                            style={{ backgroundColor: COLOR_PALETTE[idx % COLOR_PALETTE.length] }}
                          />
                          <h3 className="stock-analysis-name">{asset.stock_name}</h3>
                          <span className="stock-analysis-percent">{asset.allocation_percent}%</span>
                        </div>
                        <span className="stock-code-badge">{asset.stock_code}</span>
                      </div>
                      <p className="stock-analysis-content">{asset.analysis}</p>
                      <div className="stock-link">
                        <span>종목 상세보기 →</span>
                      </div>
                    </div>
                  )
                ))}
              </div>
            </section>
          )}

          {/* 투자 유의사항 */}
          <section className="notice-section">
            <h2 className="section-heading">투자 유의사항</h2>
            <div className="notice-box">
              <ul className="notice-list">
                <li>본 포트폴리오는 AI가 생성한 참고용 추천이며, 투자 결정의 책임은 투자자 본인에게 있습니다.</li>
                <li>과거 수익률이 미래 수익을 보장하지 않으며, 시장 상황에 따라 손실이 발생할 수 있습니다.</li>
                <li>투자 전 개인의 투자 성향과 재무 상태를 고려하여 신중히 결정하시기 바랍니다.</li>
                <li>정기적인 포트폴리오 리밸런싱을 통해 목표 자산 배분을 유지하는 것이 중요합니다.</li>
                <li>시장 변동성, 금리 변화, 환율 등 다양한 외부 요인이 수익률에 영향을 미칠 수 있습니다.</li>
              </ul>
            </div>
          </section>

        </div>
      </div>
    </div>
  )
}

export default PortfolioDetailPage
