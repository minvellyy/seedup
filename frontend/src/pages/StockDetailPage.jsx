import React, { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import './StockDetailPage.css'

function StockDetailPage() {
  const { stockCode } = useParams()
  const navigate = useNavigate()
  const [stock, setStock] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [activeTooltip, setActiveTooltip] = useState(null)

  useEffect(() => {
    fetchStockDetail()
  }, [stockCode])

  const fetchStockDetail = async () => {
    try {
      setLoading(true)
      const response = await fetch(`http://localhost:8000/api/recommendations/stocks/${stockCode}`)
      
      if (!response.ok) {
        throw new Error('종목 정보를 불러오는데 실패했습니다.')
      }
      
      const data = await response.json()
      setStock(data)
      setError(null)
    } catch (err) {
      console.error('Failed to fetch stock detail:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const formatNumber = (num) => {
    return new Intl.NumberFormat('ko-KR').format(num)
  }

  const formatPercent = (num) => {
    const sign = num >= 0 ? '+' : ''
    return `${sign}${num.toFixed(2)}%`
  }

  const formatDate = (dateStr) => {
    const date = new Date(dateStr)
    return `${date.getFullYear()}년 ${date.getMonth() + 1}월 ${date.getDate()}일`
  }

  // 레이더 차트 포인트 계산
  const getRadarPoints = (analysis) => {
    const center = 150
    const maxRadius = 100
    const angleStep = (2 * Math.PI) / 5
    
    const values = [
      analysis.profitability,
      analysis.growth,
      analysis.stability,
      analysis.dividend,
      analysis.market_interest
    ]
    
    return values.map((value, index) => {
      const angle = angleStep * index - Math.PI / 2
      const radius = (value / 100) * maxRadius
      const x = center + radius * Math.cos(angle)
      const y = center + radius * Math.sin(angle)
      return `${x},${y}`
    }).join(' ')
  }

  // 레이더 차트 라벨 위치 계산
  const getRadarLabelPosition = (index, radius = 120) => {
    const center = 150
    const angleStep = (2 * Math.PI) / 5
    const angle = angleStep * index - Math.PI / 2
    const x = center + radius * Math.cos(angle)
    const y = center + radius * Math.sin(angle)
    return { x, y }
  }

  if (loading) {
    return (
      <div className="stock-detail-page">
        <div className="loading">데이터를 불러오는 중...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="stock-detail-page">
        <div className="error-message">{error}</div>
        <button onClick={() => navigate('/recommendations')} className="back-button">
          돌아가기
        </button>
      </div>
    )
  }

  if (!stock) {
    return null
  }

  // 차트 데이터에서 최소/최대값 계산
  const prices = stock.chart_data.map(d => d.high || d.price)
  const lows = stock.chart_data.map(d => d.low || d.price)
  const minPrice = Math.min(...lows)
  const maxPrice = Math.max(...prices)

  return (
    <div className="stock-detail-page">
      <div className="stock-detail-container">
        
        <button onClick={() => navigate('/recommendations')} className="back-button">
          ← 추천 목록으로
        </button>

        {/* 헤더: 종목명, 시장구분, 가격 정보 */}
        <div className="stock-detail-header">
          <div className="header-left">
            <div className="stock-title-row">
              <h1 className="stock-detail-name">{stock.stock_name}</h1>
              <span className="market-badge">{stock.company_info?.market_type || 'KOSPI'}</span>
            </div>
            <p className="stock-detail-code">{stock.stock_code}</p>
          </div>
          <div className="header-right">
            <div className="current-price-large">{formatNumber(stock.current_price)}원</div>
            <div className={`price-change-large ${stock.price_change >= 0 ? 'positive' : 'negative'}`}>
              <span>{formatNumber(stock.price_change)}원</span>
              <span className="percent">{formatPercent(stock.price_change_percent)}</span>
            </div>
          </div>
        </div>

        <div className="stock-detail-content">
          
          {/* 캔들 차트 */}
          <section className="chart-section">
            <h2 className="section-heading">주가 차트 (최근 30일)</h2>
            <div className="chart-container">
              <svg width="100%" height="400" viewBox="0 0 900 400" preserveAspectRatio="xMidYMid meet">
                {/* 배경 그리드 */}
                {[0, 1, 2, 3, 4].map(i => (
                  <line 
                    key={i}
                    x1="50" 
                    y1={50 + i * 75} 
                    x2="850" 
                    y2={50 + i * 75} 
                    stroke="#f0f0f0" 
                    strokeWidth="1" 
                  />
                ))}
                
                {/* 캔들스틱 */}
                {stock.chart_data.map((candle, idx) => {
                  const x = 50 + (idx / (stock.chart_data.length - 1)) * 800
                  const open = candle.open || candle.price
                  const close = candle.close || candle.price
                  const high = candle.high || candle.price
                  const low = candle.low || candle.price
                  
                  const yOpen = 350 - ((open - minPrice) / (maxPrice - minPrice)) * 300
                  const yClose = 350 - ((close - minPrice) / (maxPrice - minPrice)) * 300
                  const yHigh = 350 - ((high - minPrice) / (maxPrice - minPrice)) * 300
                  const yLow = 350 - ((low - minPrice) / (maxPrice - minPrice)) * 300
                  
                  const isUp = close >= open
                  const bodyHeight = Math.abs(yClose - yOpen)
                  const bodyY = Math.min(yOpen, yClose)
                  
                  return (
                    <g key={idx}>
                      {/* 심지 (고가-저가 라인) */}
                      <line
                        x1={x}
                        y1={yHigh}
                        x2={x}
                        y2={yLow}
                        stroke={isUp ? "#F97316" : "#3B82F6"}
                        strokeWidth="1"
                      />
                      {/* 캔들 본체 */}
                      <rect
                        x={x - 4}
                        y={bodyY}
                        width="8"
                        height={bodyHeight || 1}
                        fill={isUp ? "#F97316" : "#3B82F6"}
                        stroke={isUp ? "#EA580C" : "#2563EB"}
                        strokeWidth="1"
                      />
                    </g>
                  )
                })}
              </svg>
              
              <div className="chart-labels">
                <div className="chart-date-labels">
                  <span>{stock.chart_data[0]?.date}</span>
                  <span>{stock.chart_data[Math.floor(stock.chart_data.length / 2)]?.date}</span>
                  <span>{stock.chart_data[stock.chart_data.length - 1]?.date}</span>
                </div>
                <div className="chart-price-labels">
                  <span className="max-price">최고: {formatNumber(Math.round(maxPrice))}원</span>
                  <span className="min-price">최저: {formatNumber(Math.round(minPrice))}원</span>
                </div>
              </div>
            </div>
          </section>

          {/* 투자 원칙 적합도 */}
          {stock.investment_fit && (
            <section className="investment-fit-section">
              <h2 className="section-heading">내 투자 원칙 적합도 분석</h2>
              <div className="fit-container">
                <div className="fit-score-box">
                  <div className="fit-score">{stock.investment_fit.score}</div>
                  <div className="fit-score-label">적합도 점수</div>
                </div>
                <div className="fit-details">
                  <p className="fit-summary">{stock.investment_fit.summary}</p>
                  <ul className="fit-list">
                    {stock.investment_fit.details.map((detail, idx) => (
                      <li key={idx}>{detail}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </section>
          )}

          {/* 기업 요약 */}
          {stock.company_info && (
            <section className="company-info-section">
              <h2 className="section-heading">기업 요약</h2>
              <div className="company-info-grid">
                <div className="info-item">
                  <span className="info-label">기업명</span>
                  <span className="info-value">{stock.stock_name}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">대표이사</span>
                  <span className="info-value">{stock.company_info.ceo}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">설립일자</span>
                  <span className="info-value">{formatDate(stock.company_info.founded_date)}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">산업분류</span>
                  <span className="info-value">{stock.company_info.industry}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">사업영역</span>
                  <span className="info-value">{stock.company_info.business_area}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">시가총액</span>
                  <span className="info-value">{stock.company_info.market_cap}</span>
                </div>
              </div>
            </section>
          )}

          {/* 기업/산업 분석 */}
          {stock.industry_analysis && stock.industry_analysis.length > 0 && (
            <section className="industry-analysis-section">
              <h2 className="section-heading">기업/산업 분석</h2>
              <ul className="analysis-list">
                {stock.industry_analysis.map((point, idx) => (
                  <li key={idx}>{point}</li>
                ))}
              </ul>
            </section>
          )}

          {/* 종합 분석 시각화 */}
          {stock.comprehensive_analysis && (
            <section className="comprehensive-analysis-section">
              <h2 className="section-heading">종합 분석</h2>
              <div className="radar-chart-container">
                <svg viewBox="0 0 300 300" className="radar-chart">
                  {/* 배경 원들 */}
                  {[20, 40, 60, 80, 100].map((percent) => (
                    <polygon
                      key={percent}
                      points={(() => {
                        const center = 150
                        const radius = percent
                        const angleStep = (2 * Math.PI) / 5
                        return Array.from({ length: 5 }, (_, i) => {
                          const angle = angleStep * i - Math.PI / 2
                          const x = center + radius * Math.cos(angle)
                          const y = center + radius * Math.sin(angle)
                          return `${x},${y}`
                        }).join(' ')
                      })()}
                      fill="none"
                      stroke="#e0e0e0"
                      strokeWidth="1"
                    />
                  ))}
                  
                  {/* 축 라인 */}
                  {[0, 1, 2, 3, 4].map((i) => {
                    const pos = getRadarLabelPosition(i, 100)
                    return (
                      <line
                        key={i}
                        x1="150"
                        y1="150"
                        x2={pos.x}
                        y2={pos.y}
                        stroke="#d0d0d0"
                        strokeWidth="1"
                      />
                    )
                  })}
                  
                  {/* 데이터 폴리곤 */}
                  <polygon
                    points={getRadarPoints(stock.comprehensive_analysis)}
                    fill="rgba(249, 115, 22, 0.3)"
                    stroke="#F97316"
                    strokeWidth="2"
                  />
                  
                  {/* 데이터 포인트 */}
                  {getRadarPoints(stock.comprehensive_analysis).split(' ').map((point, idx) => {
                    const [x, y] = point.split(',')
                    return (
                      <circle
                        key={idx}
                        cx={x}
                        cy={y}
                        r="4"
                        fill="#EA580C"
                      />
                    )
                  })}
                </svg>
                
                {/* 라벨 */}
                <div className="radar-labels">
                  {['수익성', '성장성', '안정성', '배당 매력', '시장 관심'].map((label, idx) => {
                    const pos = getRadarLabelPosition(idx, 140)
                    const values = [
                      stock.comprehensive_analysis.profitability,
                      stock.comprehensive_analysis.growth,
                      stock.comprehensive_analysis.stability,
                      stock.comprehensive_analysis.dividend,
                      stock.comprehensive_analysis.market_interest
                    ]
                    return (
                      <div
                        key={idx}
                        className="radar-label"
                        style={{
                          left: `${pos.x}px`,
                          top: `${pos.y}px`
                        }}
                        onMouseEnter={() => setActiveTooltip(idx)}
                        onMouseLeave={() => setActiveTooltip(null)}
                      >
                        <span className="label-text">{label}</span>
                        <span className="label-value">{values[idx]}</span>
                        {activeTooltip === idx && (
                          <div className="tooltip">
                            {label} 지표는 재무제표 및 시장 데이터를 기반으로 산출됩니다.
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            </section>
          )}

          {/* 추천 이유 */}
          <section className="recommendation-section">
            <h2 className="section-heading">추천 이유</h2>
            <div className="recommendation-box">
              <p className="recommendation-detail">{stock.recommendation_reason}</p>
            </div>
          </section>

        </div>
      </div>
    </div>
  )
}

export default StockDetailPage
