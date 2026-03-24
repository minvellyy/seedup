import React, { useState, useEffect } from 'react'
import { useAuth } from '../../contexts/AuthContext'

// 인터랙티브 도넛 차트 컴포넌트
const DonutChart = ({ items, size = 400, selectedIndex, hoveredIndex, onSelectItem }) => {
  const colors = [
    '#4f46e5', // indigo
    '#7c3aed', // violet
    '#db2777', // pink
    '#ea580c', // orange
    '#65a30d', // lime
    '#0891b2', // cyan
    '#8b5cf6', // purple
    '#ec4899', // rose
    '#14b8a6', // teal
  ]

  let currentAngle = 0
  const radius = size / 2
  const center = radius
  const innerRadius = radius * 0.5
  const outerRadius = radius * 0.85

  const createArc = (startAngle, endAngle, index) => {
    // 선택되거나 hover된 경우 약간 튀어나오게
    const isActive = index === selectedIndex || index === hoveredIndex
    const activeOuterRadius = isActive ? outerRadius + 10 : outerRadius
    
    const start = polarToCartesian(center, center, activeOuterRadius, endAngle)
    const end = polarToCartesian(center, center, activeOuterRadius, startAngle)
    const innerStart = polarToCartesian(center, center, innerRadius, endAngle)
    const innerEnd = polarToCartesian(center, center, innerRadius, startAngle)
    
    const largeArcFlag = endAngle - startAngle <= 180 ? '0' : '1'

    const d = [
      'M', start.x, start.y,
      'A', activeOuterRadius, activeOuterRadius, 0, largeArcFlag, 0, end.x, end.y,
      'L', innerEnd.x, innerEnd.y,
      'A', innerRadius, innerRadius, 0, largeArcFlag, 1, innerStart.x, innerStart.y,
      'Z'
    ].join(' ')

    return d
  }

  const polarToCartesian = (centerX, centerY, radius, angleInDegrees) => {
    const angleInRadians = ((angleInDegrees - 90) * Math.PI) / 180.0
    return {
      x: centerX + radius * Math.cos(angleInRadians),
      y: centerY + radius * Math.sin(angleInRadians),
    }
  }

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {items.length === 1 ? (
        // 종목 1개(100%)일 때 arc 대신 circle로 렌더링
        <>
          <circle
            cx={center}
            cy={center}
            r={outerRadius}
            fill={colors[0]}
            stroke="#fff"
            strokeWidth="3"
            style={{ cursor: 'pointer' }}
            onClick={() => onSelectItem(0)}
          />
          <circle
            cx={center}
            cy={center}
            r={innerRadius}
            fill="#fff"
          />
        </>
      ) : (
        items.map((item, index) => {
          const angle = (item.value / 100) * 360
          const path = createArc(currentAngle, currentAngle + angle, index)
          currentAngle += angle

          const isActive = index === selectedIndex || index === hoveredIndex
          const hasSelection = selectedIndex !== null
          const opacity = hasSelection && !isActive ? 0.5 : 1

          return (
            <path
              key={index}
              d={path}
              fill={colors[index % colors.length]}
              stroke="#fff"
              strokeWidth="3"
              opacity={opacity}
              style={{
                cursor: 'pointer',
                transition: 'all 0.3s ease',
                transformOrigin: 'center',
              }}
              onClick={() => onSelectItem(index)}
              onMouseEnter={() => onSelectItem(index, true)}
              onMouseLeave={() => onSelectItem(null, true)}
            />
          )
        })
      )}
    </svg>
  )
}

const PortfolioSection = () => {
  const { user } = useAuth()
  
  const [selectedIndex, setSelectedIndex] = useState(null)
  const [hoveredIndex, setHoveredIndex] = useState(null)
  const [portfolio, setPortfolio] = useState({ totalAmount: 0, items: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // 보유 주식 데이터 가져오기
  useEffect(() => {
    if (!user?.userId) {
      setLoading(false)
      setPortfolio({ totalAmount: 0, items: [] })
      return
    }

    const fetchPortfolio = async () => {
      try {
        setLoading(true)
        setError(null)

        const response = await fetch(`http://localhost:8000/api/holdings/${user.userId}/summary`)
        if (!response.ok) {
          throw new Error('포트폴리오 조회에 실패했습니다')
        }

        const data = await response.json()

        // 데이터 변환: holdings를 차트용 items로 변환
        const items = data.holdings.map(holding => {
          const value = data.total_current_value > 0 
            ? (holding.current_value / data.total_current_value * 100) 
            : 0
          return {
            name: holding.stock_name,
            code: holding.stock_code,
            value: parseFloat(value.toFixed(1)),
            amount: holding.current_value || (holding.purchase_price * holding.shares),
            shares: holding.shares,
            returnRate: holding.return_rate || 0
          }
        })

        setPortfolio({
          totalAmount: data.total_current_value,
          items: items
        })
      } catch (err) {
        console.error('포트폴리오 조회 실패:', err)
        setError(err.message)
        setPortfolio({ totalAmount: 0, items: [] })
      } finally {
        setLoading(false)
      }
    }

    fetchPortfolio()
  }, [user])

  const colors = [
    '#4f46e5', '#7c3aed', '#db2777', '#ea580c', '#65a30d', '#0891b2', '#8b5cf6', '#ec4899', '#14b8a6'
  ]

  const formatNumber = (num) => {
    return new Intl.NumberFormat('ko-KR').format(num)
  }

  const handleSelectItem = (index, isHover = false) => {
    if (isHover) {
      setHoveredIndex(index)
    } else {
      setSelectedIndex(selectedIndex === index ? null : index)
    }
  }

  const handleLegendClick = (index) => {
    setSelectedIndex(selectedIndex === index ? null : index)
  }

  const selectedItem = selectedIndex !== null ? portfolio.items[selectedIndex] : null

  // 로딩 상태
  if (loading) {
    return (
      <div className="section-content">
        <h2 className="section-title">포트폴리오 관리</h2>
        <div className="loading-state">
          <div className="spinner"></div>
          <p>포트폴리오를 불러오는 중...</p>
        </div>
      </div>
    )
  }

  // 에러 상태
  if (error) {
    return (
      <div className="section-content">
        <h2 className="section-title">포트폴리오 관리</h2>
        <div className="error-state">
          <p>⚠️ {error}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="section-content">
      <h2 className="section-title">포트폴리오 관리</h2>
      
      {portfolio.items.length === 0 ? (
        <div className="empty-state-card">
          <p>등록된 포트폴리오가 없습니다</p>
          <p className="empty-hint">보유 주식 내역을 먼저 등록해주세요</p>
        </div>
      ) : (
        <div className="portfolio-unified">
          <div className="portfolio-header">
            <h3>통합 포트폴리오</h3>
            <p className="portfolio-total">
              총 자산 <strong>{formatNumber(portfolio.totalAmount)}원</strong>
            </p>
          </div>

          {/* 선택된 종목 정보 카드 */}
          {selectedItem && (
            <div className="portfolio-selected-info">
              <div className="selected-color" style={{ backgroundColor: colors[selectedIndex] }}></div>
              <div className="selected-content">
                <h4>{selectedItem.name}</h4>
                <div className="selected-details">
                  <span className="selected-amount">{formatNumber(selectedItem.amount)}원</span>
                  <span className="selected-value">{selectedItem.value}%</span>
                </div>
              </div>
              <button 
                className="selected-close"
                onClick={() => setSelectedIndex(null)}
              >
                ✕
              </button>
            </div>
          )}

          <div className="portfolio-layout">
            {/* 차트 영역 */}
            <div className="portfolio-chart-section">
              <DonutChart 
                items={portfolio.items} 
                size={400}
                selectedIndex={selectedIndex}
                hoveredIndex={hoveredIndex}
                onSelectItem={handleSelectItem}
              />
            </div>

            {/* 종목 리스트 */}
            <div className="portfolio-legend-section">
              <h4>보유 종목</h4>
              <div className="portfolio-legend">
                {portfolio.items.map((item, index) => {
                  const isActive = index === selectedIndex || index === hoveredIndex
                  const hasSelection = selectedIndex !== null
                  const opacity = hasSelection && !isActive ? 0.5 : 1
                  
                  return (
                    <div 
                      key={index} 
                      className={`legend-item ${isActive ? 'active' : ''}`}
                      style={{ opacity }}
                      onClick={() => handleLegendClick(index)}
                      onMouseEnter={() => setHoveredIndex(index)}
                      onMouseLeave={() => setHoveredIndex(null)}
                    >
                      <span 
                        className="legend-color" 
                        style={{ backgroundColor: colors[index % colors.length] }}
                      ></span>
                      <div className="legend-text">
                        <span className="legend-name">{item.name}</span>
                        <span className="legend-value">{item.value}%</span>
                      </div>
                      <span className="legend-amount">{formatNumber(item.amount)}원</span>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default PortfolioSection
