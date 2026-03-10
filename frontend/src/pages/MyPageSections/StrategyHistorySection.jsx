import React from 'react'
import { useNavigate } from 'react-router-dom'

// Mock data
const mockStrategyHistory = [
  {
    id: 1,
    recommendedAt: '2026-03-05T10:00:00',
    title: '배당주 중심 안정형 전략',
    summary: '변동성을 낮춘 배당주 중심 포트폴리오',
    riskLevel: '안정형',
    expectedReturn: '5~8%',
  },
  {
    id: 2,
    recommendedAt: '2026-02-20T14:30:00',
    title: '성장주 공격형 전략',
    summary: 'IT 및 바이오 섹터 중심의 고성장 포트폴리오',
    riskLevel: '공격형',
    expectedReturn: '15~20%',
  },
  {
    id: 3,
    recommendedAt: '2026-02-10T09:15:00',
    title: '밸런스형 포트폴리오',
    summary: '안정성과 수익성의 균형을 맞춘 전략',
    riskLevel: '중립형',
    expectedReturn: '8~12%',
  },
  {
    id: 4,
    recommendedAt: '2026-01-28T16:45:00',
    title: '배당 + 성장 하이브리드',
    summary: '배당주와 성장주를 적절히 배분한 포트폴리오',
    riskLevel: '중립형',
    expectedReturn: '10~13%',
  },
  {
    id: 5,
    recommendedAt: '2026-01-15T11:20:00',
    title: '방어적 가치주 전략',
    summary: '경기 둔화에 대비한 방어적 종목 중심',
    riskLevel: '안정형',
    expectedReturn: '6~9%',
  },
]

const StrategyHistorySection = () => {
  const navigate = useNavigate()

  const formatDate = (dateString) => {
    const date = new Date(dateString)
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    const hours = String(date.getHours()).padStart(2, '0')
    const minutes = String(date.getMinutes()).padStart(2, '0')
    
    return `${year}.${month}.${day} ${hours}:${minutes}`
  }

  const getRiskLevelClass = (level) => {
    if (level === '안정형') return 'risk-stable'
    if (level === '공격형') return 'risk-aggressive'
    return 'risk-neutral'
  }

  const handleViewDetail = (strategyId) => {
    // 실제로는 상세 페이지나 모달로 이동
    console.log('전략 상세보기:', strategyId)
    alert(`전략 ID ${strategyId}의 상세 정보를 표시합니다`)
  }

  return (
    <div className="section-content">
      <h2 className="section-title">추천 전략 히스토리</h2>
      
      {mockStrategyHistory.length === 0 ? (
        <div className="empty-state-card">
          <p>추천받은 전략이 없습니다</p>
          <p className="empty-hint">투자 성향 진단을 완료하면 맞춤 전략을 추천받을 수 있습니다</p>
          <button 
            className="btn btn-primary"
            onClick={() => navigate('/invest-type-survey')}
          >
            투자 성향 진단하기
          </button>
        </div>
      ) : (
        <div className="strategy-list">
          {mockStrategyHistory.map((strategy) => (
            <div key={strategy.id} className="strategy-item">
              <div className="strategy-main">
                <div className="strategy-date">
                  <span className="date-icon">📅</span>
                  {formatDate(strategy.recommendedAt)}
                </div>
                
                <div className="strategy-content">
                  <h3 className="strategy-title">{strategy.title}</h3>
                  <p className="strategy-summary">{strategy.summary}</p>
                  
                  <div className="strategy-meta">
                    <span className={`risk-badge ${getRiskLevelClass(strategy.riskLevel)}`}>
                      {strategy.riskLevel}
                    </span>
                    <span className="return-badge">
                      예상 수익률: {strategy.expectedReturn}
                    </span>
                  </div>
                </div>
              </div>

              <div className="strategy-action">
                <button 
                  className="btn btn-outline"
                  onClick={() => handleViewDetail(strategy.id)}
                >
                  상세보기
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default StrategyHistorySection
