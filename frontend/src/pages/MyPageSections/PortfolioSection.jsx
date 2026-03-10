import React, { useState } from 'react'

// 통합 포트폴리오 Mock data
const mockPortfolio = {
  totalAmount: 27900000,
  items: [
    { name: '삼성전자', value: 20, amount: 5580000 },
    { name: 'SK하이닉스', value: 18, amount: 5022000 },
    { name: '현대차', value: 12, amount: 3348000 },
    { name: 'LG에너지솔루션', value: 11, amount: 3069000 },
    { name: 'POSCO홀딩스', value: 10, amount: 2790000 },
    { name: '삼성바이오로직스', value: 9, amount: 2511000 },
    { name: 'KB금융', value: 8, amount: 2232000 },
    { name: '카카오', value: 7, amount: 1953000 },
    { name: '네이버', value: 5, amount: 1395000 },
  ],
}

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
      {items.map((item, index) => {
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
      })}
    </svg>
  )
}

const PortfolioSection = () => {
  const [selectedIndex, setSelectedIndex] = useState(null)
  const [hoveredIndex, setHoveredIndex] = useState(null)

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

  const selectedItem = selectedIndex !== null ? mockPortfolio.items[selectedIndex] : null

  return (
    <div className="section-content">
      <h2 className="section-title">포트폴리오 관리</h2>
      
      {mockPortfolio.items.length === 0 ? (
        <div className="empty-state-card">
          <p>등록된 포트폴리오가 없습니다</p>
          <p className="empty-hint">보유 주식 내역을 먼저 등록해주세요</p>
        </div>
      ) : (
        <div className="portfolio-unified">
          <div className="portfolio-header">
            <h3>통합 포트폴리오</h3>
            <p className="portfolio-total">
              총 자산 <strong>{formatNumber(mockPortfolio.totalAmount)}원</strong>
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
                items={mockPortfolio.items} 
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
                {mockPortfolio.items.map((item, index) => {
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
