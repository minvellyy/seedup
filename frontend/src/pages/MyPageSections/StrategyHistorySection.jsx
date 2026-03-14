import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'

const StrategyHistorySection = () => {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [strategyHistory, setStrategyHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const fetchHistory = async () => {
      if (!user?.userId) {
        setError('로그인이 필요합니다')
        setLoading(false)
        return
      }

      try {
        setLoading(true)
        const response = await fetch(`/api/dashboard/portfolio-history?user_id=${user.userId}&limit=20`)
        
        if (!response.ok) {
          throw new Error(`히스토리 조회 실패 (${response.status})`)
        }

        const data = await response.json()
        setStrategyHistory(data)
        setError(null)
      } catch (err) {
        console.error('히스토리 조회 오류:', err)
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }

    fetchHistory()
  }, [user])

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
    if (level === '안정형' || level.includes('안정')) return 'risk-stable'
    if (level === '공격형' || level.includes('공격')) return 'risk-aggressive'
    return 'risk-neutral'
  }

  const getStrategyLabel = (strategyName, portfolioLabel) => {
    // portfolio_label이 있으면 우선 사용
    if (portfolioLabel) return portfolioLabel
    
    // strategy_name 매핑
    const strategyMap = {
      'balanced': '균형 추천형',
      'momentum': '모멘텀 집중형',
      'lowvol': '안정 우선형',
    }
    return strategyMap[strategyName] || strategyName || '포트폴리오 추천'
  }

  const getExpectedReturn = (mc) => {
    if (!mc) return '데이터 없음'
    if (mc.mean_pct !== undefined) {
      return `${mc.mean_pct > 0 ? '+' : ''}${mc.mean_pct.toFixed(1)}%`
    }
    return '계산 중'
  }

  const handleViewDetail = (strategy) => {
    console.log('전략 상세보기:', strategy)
    navigate('/portfolio/recommendation', { 
      state: { 
        portfolioData: strategy.recommendation 
      } 
    })
  }

  if (loading) {
    return (
      <div className="section-content">
        <h2 className="section-title">추천 전략 히스토리</h2>
        <div className="empty-state-card">
          <p>히스토리를 불러오는 중...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="section-content">
        <h2 className="section-title">추천 전략 히스토리</h2>
        <div className="empty-state-card">
          <p style={{ color: '#e74c3c' }}>❌ {error}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="section-content">
      <h2 className="section-title">추천 전략 히스토리</h2>
      
      {strategyHistory.length === 0 ? (
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
          {strategyHistory.map((strategy) => {
            const rec = strategy.recommendation || {}
            const mc = rec.monte_carlo_1y || {}
            const riskTier = rec.risk_tier || rec.risk_grade || '중립형'
            
            return (
              <div key={strategy.id} className="strategy-item">
                <div className="strategy-main">
                  <div className="strategy-date">
                    <span className="date-icon">📅</span>
                    {formatDate(strategy.created_at)}
                  </div>
                  
                  <div className="strategy-content">
                    <h3 className="strategy-title">
                      {getStrategyLabel(strategy.strategy_name, rec.portfolio_label)}
                    </h3>
                    <p className="strategy-summary">
                      {rec.overall_summary || rec.portfolio_summary || '맞춤형 포트폴리오 추천'}
                    </p>
                    
                    <div className="strategy-meta">
                      <span className={`risk-badge ${getRiskLevelClass(riskTier)}`}>
                        {riskTier}
                      </span>
                      <span className="return-badge">
                        예상 수익률: {getExpectedReturn(mc)}
                      </span>
                      {strategy.state === 'ARCHIVED' && (
                        <span className="archived-badge">과거</span>
                      )}
                      {strategy.state === 'ACTIVE' && (
                        <span className="active-badge">현재</span>
                      )}
                    </div>
                  </div>
                </div>

                <div className="strategy-action">
                  <button 
                    className="btn btn-outline"
                    onClick={() => handleViewDetail(strategy)}
                  >
                    상세보기
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default StrategyHistorySection
