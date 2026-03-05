import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import './DashboardPage.css'

const DashboardPage = () => {
  const navigate = useNavigate()
  const [investorTrading, setInvestorTrading] = useState({})
  const [tradingMarketTab, setTradingMarketTab] = useState('KOSPI')
  const [marketWeather, setMarketWeather] = useState(null)
  const [marketIndices, setMarketIndices] = useState([])
  const [instrumentsStocks, setInstrumentsStocks] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedMarket, setSelectedMarket] = useState('KOSPI')
  const [showChatbot, setShowChatbot] = useState(false)
  const [chatMessages, setChatMessages] = useState([])
  const [chatInput, setChatInput] = useState('')

  const API_BASE_URL = ''

  useEffect(() => {
    fetchDashboardData()
  }, [selectedMarket])

  // 실시간 주가 SSE 스트림 연결 (종목 로드 완료 후 1회 구독)
  useEffect(() => {
    if (instrumentsStocks.length === 0) return

    const codes = instrumentsStocks.map(s => s.stock_code).join(',')
    const es = new EventSource(`/api/stream/prices?codes=${codes}`)

    es.onmessage = (e) => {
      try {
        const updates = JSON.parse(e.data)
        setInstrumentsStocks(prev =>
          prev.map(s => {
            const upd = updates[s.stock_code]
            if (!upd) return s
            return {
              ...s,
              current_price: upd.current_price,
              change:        upd.change,
              change_rate:   upd.change_rate,
              volume:        upd.volume,
            }
          })
        )
      } catch (err) {
        console.warn('SSE 파싱 오류:', err)
      }
    }

    es.onerror = () => {
      console.warn('SSE 연결 오류 — 자동 재연결 대기 중')
    }

    return () => {
      es.close()
    }
  }, [instrumentsStocks.length])   // 종목 수가 변할 때만 재구독

  const fetchDashboardData = async () => {
    setLoading(true)
    setError(null)
    
    try {
      // 각 API를 개별적으로 처리하여 일부 실패해도 계속 진행
      let weather = null
      let indices = []
      
      // Investor Trading (당일)
      let investorRows = []
      try {
        const invRes = await fetch(`${API_BASE_URL}/api/dashboard/investor-trading`)
        if (invRes.ok) {
          investorRows = await invRes.json()
        }
      } catch (e) {
        console.warn('Failed to fetch investor trading:', e)
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

      // 실제 종목 주가 (instruments DB)
      let instStocks = []
      try {
        const instRes = await fetch(`${API_BASE_URL}/api/instruments/stocks?limit=20`)
        if (instRes.ok) {
          instStocks = await instRes.json()
        }
      } catch (e) {
        console.warn('Failed to fetch instruments stocks:', e)
      }

      // investorRows 배열 → {KOSPI: {...}, KOSDAQ: {...}} 딕셔너리로 변환
      const invMap = {}
      for (const row of investorRows) {
        invMap[row.market] = row
      }
      setInvestorTrading(invMap)
      setMarketWeather(weather)
      setMarketIndices(indices)
      setInstrumentsStocks(instStocks)
      
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
      setInstrumentsStocks([])
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
            <div className="card-header">
              <h2>투자자별 매매동향</h2>
              <span className="trading-date">
                {Object.values(investorTrading)[0]?.date ?? ''}
              </span>
            </div>
            {/* 시장 탭 */}
            <div className="trading-market-tabs">
              {['KOSPI', 'KOSDAQ'].map(m => (
                <button
                  key={m}
                  className={`trading-tab${tradingMarketTab === m ? ' active' : ''}`}
                  onClick={() => setTradingMarketTab(m)}
                >{m}</button>
              ))}
            </div>
            {/* 테이블 */}
            {(() => {
              const d = investorTrading[tradingMarketTab]
              // 매도/매수: 양수 값을 그대로 표시, 0이면 데이터 없음('-')
              const fmtSell = (v) => (v == null || Number(v) === 0) ? '-' : Number(v).toLocaleString('ko-KR')
              const fmtBuy  = fmtSell
              // 순매수: +/- 부호 포함
              const fmtNet = (v) => {
                if (v == null) return '-'
                const n = Number(v)
                return (n > 0 ? '+' : '') + n.toLocaleString('ko-KR', { minimumFractionDigits: 0 })
              }
              const rows = d ? [
                { label: '기관(십억원)',   sell: d.institution_sell, buy: d.institution_buy, net: d.institution_net },
                { label: '외국인(십억원)', sell: d.foreign_sell,     buy: d.foreign_buy,     net: d.foreign_net },
                { label: '개인(십억원)',   sell: d.individual_sell,  buy: d.individual_buy,  net: d.individual_net },
              ] : []
              return (
                <table className="investor-table">
                  <thead>
                    <tr>
                      <th>구분</th>
                      <th>매도</th>
                      <th>매수</th>
                      <th>순매수</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.length === 0 ? (
                      <tr><td colSpan={4} style={{textAlign:'center',color:'#888',padding:'16px'}}>데이터 로딩 중...</td></tr>
                    ) : rows.map((r, i) => (
                      <tr key={i}>
                        <td className="investor-label">{r.label}</td>
                        <td>{fmtSell(r.sell)}</td>
                        <td>{fmtBuy(r.buy)}</td>
                        <td className={getChangeColor(r.net)}>{fmtNet(r.net)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )
            })()}
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
              {instrumentsStocks.length === 0 && (
                <div style={{ padding: '16px', color: '#888', textAlign: 'center' }}>주가 데이터 로딩 중...</div>
              )}
              {instrumentsStocks.map((stock) => (
                <div
                  key={stock.stock_code}
                  className="recommendation-item"
                  style={{ cursor: 'pointer' }}
                  onClick={() => navigate(`/stock/${stock.stock_code}`)}
                >
                  <div className="recommendation-header">
                    <h3>{stock.name}</h3>
                    <span className="stock-code">{stock.exchange}</span>
                  </div>
                  <div className="recommendation-details">
                    <div className="stock-price">
                      {stock.current_price.toLocaleString()}원
                    </div>
                    {stock.change_rate != null && (
                      <div className={`change-badge ${stock.change_rate >= 0 ? 'up' : 'down'}`}>
                        {stock.change_rate >= 0 ? '▲' : '▼'} {Math.abs(stock.change_rate).toFixed(2)}%
                      </div>
                    )}
                  </div>
                  <p className="recommendation-reason" style={{ color: '#666', fontSize: 12 }}>
                    {stock.price_date} 기준 &nbsp;|
                    거래량 {stock.volume ? stock.volume.toLocaleString() : '-'}
                  </p>
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
