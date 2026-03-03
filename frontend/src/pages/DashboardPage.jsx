import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import './DashboardPage.css'

const DashboardPage = () => {
  const navigate = useNavigate()
  const [tradingTrends, setTradingTrends] = useState([])
  const [marketWeather, setMarketWeather] = useState(null)
  const [marketIndices, setMarketIndices] = useState([])
  const [stockRecommendations, setStockRecommendations] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedMarket, setSelectedMarket] = useState('KOSPI')
  const [showChatbot, setShowChatbot] = useState(false)
  const [chatMessages, setChatMessages] = useState([])
  const [chatInput, setChatInput] = useState('')

  const API_BASE_URL = 'http://127.0.0.1:8000'

  useEffect(() => {
    fetchDashboardData()
  }, [selectedMarket])

  const fetchDashboardData = async () => {
    setLoading(true)
    setError(null)
    
    try {
      // 각 API를 개별적으로 처리하여 일부 실패해도 계속 진행
      let trends = []
      let weather = null
      let indices = []
      let stocks = []
      
      // Trading Trends
      try {
        const trendsRes = await fetch(`${API_BASE_URL}/api/dashboard/trading-trends?days=5`)
        if (trendsRes.ok) {
          trends = await trendsRes.json()
        }
      } catch (e) {
        console.warn('Failed to fetch trading trends:', e)
      }

      // Market Weather
      try {
        const weatherRes = await fetch(`${API_BASE_URL}/api/dashboard/market-weather?market=${selectedMarket}`)
        if (weatherRes.ok) {
          weather = await weatherRes.json()
        } else {
          // 기본 날씨 정보
          weather = {
            weather: '흐림',
            score: 50,
            recommendation: '시장 분석 중',
            hint: '현재 시장 데이터를 수집하고 있습니다.'
          }
        }
      } catch (e) {
        console.warn('Failed to fetch market weather:', e)
        weather = {
          weather: '흐림',
          score: 50,
          recommendation: '시장 분석 중',
          hint: '현재 시장 데이터를 수집하고 있습니다.'
        }
      }

      // Market Indices
      try {
        const indicesRes = await fetch(`${API_BASE_URL}/api/dashboard/market-indices`)
        if (indicesRes.ok) {
          indices = await indicesRes.json()
        } else {
          // 기본 지수 정보
          indices = [
            {
              market: 'KOSPI',
              index: 2500.00,
              change: 0,
              change_rate: 0,
              date: new Date().toISOString().split('T')[0]
            },
            {
              market: 'KOSDAQ',
              index: 850.00,
              change: 0,
              change_rate: 0,
              date: new Date().toISOString().split('T')[0]
            }
          ]
        }
      } catch (e) {
        console.warn('Failed to fetch market indices:', e)
        indices = [
          {
            market: 'KOSPI',
            index: 2500.00,
            change: 0,
            change_rate: 0,
            date: new Date().toISOString().split('T')[0]
          },
          {
            market: 'KOSDAQ',
            index: 850.00,
            change: 0,
            change_rate: 0,
            date: new Date().toISOString().split('T')[0]
          }
        ]
      }

      // Stock Recommendations
      try {
        const stocksRes = await fetch(`${API_BASE_URL}/api/dashboard/stock-recommendations`)
        if (stocksRes.ok) {
          stocks = await stocksRes.json()
        } else {
          // 기본 추천 정보
          stocks = [
            {
              stock_code: '005930',
              stock_name: '삼성전자',
              current_price: 75000,
              recommendation_type: '보유',
              reason: '시장 분석 중입니다.'
            }
          ]
        }
      } catch (e) {
        console.warn('Failed to fetch stock recommendations:', e)
        stocks = [
          {
            stock_code: '005930',
            stock_name: '삼성전자',
            current_price: 75000,
            recommendation_type: '보유',
            reason: '시장 분석 중입니다.'
          }
        ]
      }

      setTradingTrends(trends)
      setMarketWeather(weather)
      setMarketIndices(indices)
      setStockRecommendations(stocks)
      
      // 백엔드 서버가 아예 응답이 없는 경우에만 에러 표시
      if (!weather && indices.length === 0 && stocks.length === 0) {
        setError('백엔드 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요.')
      }
    } catch (err) {
      console.error('Error fetching dashboard data:', err)
      // 기본 데이터 설정
      setMarketWeather({
        weather: '흐림',
        score: 50,
        recommendation: '시장 분석 중',
        hint: '백엔드 서버에 연결할 수 없습니다.'
      })
      setMarketIndices([
        {
          market: 'KOSPI',
          index: 2500.00,
          change: 0,
          change_rate: 0,
          date: new Date().toISOString().split('T')[0]
        },
        {
          market: 'KOSDAQ',
          index: 850.00,
          change: 0,
          change_rate: 0,
          date: new Date().toISOString().split('T')[0]
        }
      ])
      setStockRecommendations([
        {
          stock_code: '005930',
          stock_name: '삼성전자',
          current_price: 75000,
          recommendation_type: '보유',
          reason: '백엔드 서버를 실행해주세요.'
        }
      ])
      setError('백엔드 서버에 연결할 수 없습니다. 서버를 실행한 후 다시 시도해주세요.')
    } finally {
      setLoading(false)
    }
  }

  const getWeatherIcon = (weather) => {
    switch (weather) {
      case '맑음':
        return '☀️'
      case '구름조금':
        return '⛅'
      case '흐림':
        return '☁️'
      case '비':
        return '🌧️'
      default:
        return '🌤️'
    }
  }

  const getChangeColor = (change) => {
    if (change > 0) return 'positive'
    if (change < 0) return 'negative'
    return 'neutral'
  }

  const handleSendMessage = () => {
    if (!chatInput.trim()) return

    const newMessage = {
      id: Date.now(),
      text: chatInput,
      sender: 'user',
      timestamp: new Date()
    }

    setChatMessages([...chatMessages, newMessage])
    setChatInput('')

    // 봇 응답 시뮬레이션
    setTimeout(() => {
      const botResponse = {
        id: Date.now(),
        text: '안녕하세요! 투자 관련 질문이 있으시면 언제든지 물어보세요.',
        sender: 'bot',
        timestamp: new Date()
      }
      setChatMessages(prev => [...prev, botResponse])
    }, 500)
  }

  if (loading) {
    return (
      <div className="dashboard-page">
        <div className="loading-container">
          <div className="loading-spinner"></div>
          <p>대시보드를 불러오는 중...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="dashboard-page">
        <div className="dashboard-header">
          <h1>투자 대시보드</h1>
          <p className="dashboard-subtitle">실시간 시장 동향과 맞춤형 투자 정보를 확인하세요</p>
        </div>
        <div className="error-container">
          <h2>⚠️ 서버 연결 오류</h2>
          <p>{error}</p>
          <div className="error-instructions">
            <p><strong>백엔드 서버를 실행하는 방법:</strong></p>
            <ol>
              <li>터미널을 열고 프로젝트의 backend 폴더로 이동</li>
              <li><code>pip install -r requirements.txt</code> 실행 (처음 한 번)</li>
              <li><code>python main.py</code> 또는 <code>uvicorn main:app --reload</code> 실행</li>
            </ol>
          </div>
          <button onClick={fetchDashboardData} className="retry-button">
            다시 시도
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="dashboard-page">
      <div className="dashboard-header">
        <h1>투자 대시보드</h1>
        <p className="dashboard-subtitle">실시간 시장 동향과 맞춤형 투자 정보를 확인하세요</p>
      </div>

      <div className="dashboard-content">
        {/* 좌측 영역 */}
        <div className="dashboard-left">
          {/* 시장 날씨 */}
          <div className="weather-card card">
            <div className="card-header">
              <h2>오늘의 시장 날씨</h2>
              <select 
                value={selectedMarket} 
                onChange={(e) => setSelectedMarket(e.target.value)}
                className="market-selector"
              >
                <option value="KOSPI">KOSPI</option>
                <option value="KOSDAQ">KOSDAQ</option>
              </select>
            </div>
            {marketWeather && (
              <div className="weather-content">
                <div className="weather-icon">
                  {getWeatherIcon(marketWeather.weather)}
                </div>
                <div className="weather-details">
                  <h3 className="weather-status">{marketWeather.weather}</h3>
                  <div className="weather-score">
                    <span className="score-label">시장 점수</span>
                    <span className="score-value">{marketWeather.score}/100</span>
                  </div>
                  <p className="weather-recommendation">{marketWeather.recommendation}</p>
                  <p className="weather-hint">{marketWeather.hint}</p>
                </div>
              </div>
            )}
          </div>

          {/* 코스피/코스닥 지수 */}
          <div className="indices-card card">
            <h2>시장 지수</h2>
            <div className="indices-grid">
              {marketIndices.map((index) => (
                <div key={index.market} className="index-item">
                  <div className="index-header">
                    <h3>{index.market}</h3>
                    <span className="index-date">{index.date}</span>
                  </div>
                  <div className="index-value">{index.index.toFixed(2)}</div>
                  <div className={`index-change ${getChangeColor(index.change)}`}>
                    {index.change > 0 ? '▲' : index.change < 0 ? '▼' : '─'} 
                    {Math.abs(index.change).toFixed(2)} ({index.change_rate > 0 ? '+' : ''}{index.change_rate.toFixed(2)}%)
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 투자자별 매매동향 */}
          <div className="trading-trends-card card">
            <h2>투자자별 매매동향 (최근 5일)</h2>
            <div className="table-container">
              <table className="trends-table">
                <thead>
                  <tr>
                    <th>날짜</th>
                    <th>시장</th>
                    <th>기관 (억원)</th>
                    <th>외국인 (억원)</th>
                    <th>개인 (억원)</th>
                  </tr>
                </thead>
                <tbody>
                  {tradingTrends.slice(-10).map((trend, index) => (
                    <tr key={index}>
                      <td>{trend.date}</td>
                      <td>{trend.market}</td>
                      <td className={getChangeColor(trend.institution)}>
                        {trend.institution > 0 ? '+' : ''}{trend.institution.toFixed(0)}
                      </td>
                      <td className={getChangeColor(trend.foreign)}>
                        {trend.foreign > 0 ? '+' : ''}{trend.foreign.toFixed(0)}
                      </td>
                      <td className={getChangeColor(trend.individual)}>
                        {trend.individual > 0 ? '+' : ''}{trend.individual.toFixed(0)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* 우측 영역 */}
        <div className="dashboard-right">
          {/* 종목/포트폴리오 추천 */}
          <div className="recommendations-card card">
            <div className="card-header">
              <h2>종목 추천</h2>
              <button className="detail-button" onClick={() => navigate('/recommendations')}>
                상세보기 →
              </button>
            </div>
            <div className="recommendations-list">
              {stockRecommendations.map((stock) => (
                <div key={stock.stock_code} className="recommendation-item">
                  <div className="recommendation-header">
                    <h3>{stock.stock_name}</h3>
                    <span className="stock-code">{stock.stock_code}</span>
                  </div>
                  <div className="recommendation-details">
                    <div className="stock-price">
                      {stock.current_price.toLocaleString()}원
                    </div>
                    <div className={`recommendation-type ${stock.recommendation_type === '매수' ? 'buy' : 'hold'}`}>
                      {stock.recommendation_type}
                    </div>
                  </div>
                  <p className="recommendation-reason">{stock.reason}</p>
                </div>
              ))}
            </div>
          </div>

          {/* 포트폴리오 추천 */}
          <div className="portfolio-card card">
            <div className="card-header">
              <h2>포트폴리오 추천</h2>
              <button className="detail-button" onClick={() => navigate('/portfolio')}>
                상세보기 →
              </button>
            </div>
            <div className="portfolio-list">
              <div className="portfolio-item">
                <h3>안정형 포트폴리오</h3>
                <div className="portfolio-info">
                  <span className="expected-return">예상 수익률: 8.5%</span>
                  <span className="risk-level low">리스크: 낮음</span>
                </div>
              </div>
              <div className="portfolio-item">
                <h3>성장형 포트폴리오</h3>
                <div className="portfolio-info">
                  <span className="expected-return">예상 수익률: 15.2%</span>
                  <span className="risk-level medium">리스크: 중간</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 플로팅 챗봇 버튼 */}
      <button 
        className="chatbot-float-button" 
        onClick={() => setShowChatbot(!showChatbot)}
        aria-label="챗봇 열기"
      >
        💬
      </button>

      {/* 챗봇 모달 */}
      {showChatbot && (
        <div className="chatbot-modal">
          <div className="chatbot-header">
            <h3>투자 도우미 챗봇</h3>
            <button onClick={() => setShowChatbot(false)} className="close-button">
              ✕
            </button>
          </div>
          <div className="chatbot-messages">
            {chatMessages.length === 0 ? (
              <div className="chatbot-welcome">
                <p>안녕하세요! 투자 관련 질문이 있으시면 언제든지 물어보세요.</p>
              </div>
            ) : (
              chatMessages.map((msg) => (
                <div key={msg.id} className={`chat-message ${msg.sender}`}>
                  <p>{msg.text}</p>
                </div>
              ))
            )}
          </div>
          <div className="chatbot-input">
            <input
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
              placeholder="질문을 입력하세요..."
            />
            <button onClick={handleSendMessage}>전송</button>
          </div>
        </div>
      )}

      {/* 면책 조항 */}
      <div className="disclaimer">
        <p>
          ※ 본 정보는 투자 판단의 참고 자료이며, 투자 결과에 대한 책임은 본인에게 있습니다.
        </p>
      </div>
    </div>
  )
}

export default DashboardPage
