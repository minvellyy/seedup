import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import './DashboardPage.css'

const DashboardPage = () => {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [investorTrading, setInvestorTrading] = useState({})
  const [tradingMarketTab, setTradingMarketTab] = useState('KOSPI')
  const [marketWeather, setMarketWeather] = useState(null)
  const [marketIndices, setMarketIndices] = useState([])
  const [instrumentsStocks, setInstrumentsStocks] = useState([])
  const [recStocks, setRecStocks] = useState([])      // 추천 top3 + 실시간 주가
  const [multiPortfolios, setMultiPortfolios] = useState([])  // 3종 포트폴리오
  const [pfRecsUpdatedAt, setPfRecsUpdatedAt] = useState(null)  // last fetch timestamp
  const [stockRecsLoading, setStockRecsLoading] = useState(false)
  const [pfRecsLoading, setPfRecsLoading] = useState(false)
  const [recRequested, setRecRequested] = useState(false)  // 사용자가 추천 버튼을 누른 적 있는지
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

  useEffect(() => {
    if (!user?.userId) return
    // 추천은 사용자가 버튼을 누를 때만 실행 (자동 실행 없음)
  }, [user])

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

  const fetchStockRecs = async (userId, refresh = false) => {
    setRecRequested(true)
    setStockRecsLoading(true)
    try {
      const srRes = await fetch(`${API_BASE_URL}/api/dashboard/stock-recommendations?user_id=${userId}&refresh=${refresh}`)
      if (srRes.ok) {
        const stockData = await srRes.json()
        const top3 = (stockData.items || []).slice(0, 3)
        const codeParam = top3.map(i => i.ticker).join(',')
        if (codeParam) {
          let newStocks
          try {
            const priceRes = await fetch(`${API_BASE_URL}/api/instruments/stocks?codes=${codeParam}&limit=3`)
            const priceList = priceRes.ok ? await priceRes.json() : []
            const priceMap = Object.fromEntries(priceList.map(s => [s.stock_code, s]))
            newStocks = top3.map(item => ({
              stock_code:    item.ticker,
              name:          item.name,
              exchange:      item.market,
              current_price: priceMap[item.ticker]?.current_price ?? 0,
              change_rate:   priceMap[item.ticker]?.change_rate ?? null,
              price_date:    priceMap[item.ticker]?.price_date ?? '',
              volume:        priceMap[item.ticker]?.volume ?? null,
              rank:          item.rank,
            }))
          } catch (e) {
            console.warn('recStocks 주가 fetch 실패:', e)
            newStocks = top3.map(item => ({
              stock_code: item.ticker, name: item.name, exchange: item.market,
              current_price: 0, change_rate: null, price_date: '', volume: null, rank: item.rank,
            }))
          }
          setRecStocks(newStocks)
        }
      }
    } catch (e) {
      console.warn('종목 추천 fetch 실패:', e)
    } finally {
      setStockRecsLoading(false)
    }
  }

  const fetchPortfolioRecs = async (userId, refresh = false) => {
    setPfRecsLoading(true)
    const controller = new AbortController()
    // 190초 후 자동 중단 (백엔드 타임아웃 180초 + 여유 10초)
    const timeoutId = setTimeout(() => controller.abort(), 190000)
    try {
      const prRes = await fetch(
        `${API_BASE_URL}/api/dashboard/portfolio-recommendations-ai?user_id=${userId}&refresh=${refresh}`,
        { signal: controller.signal }
      )
      if (prRes.ok) {
        const newPortfolios = await prRes.json()
        setMultiPortfolios(newPortfolios)
        const cachedAt = newPortfolios?.[0]?._cached_at
        setPfRecsUpdatedAt(cachedAt || new Date().toISOString())
      } else {
        const detail = await prRes.json().catch(() => ({}))
        const msg = detail?.detail || `오류 코드: ${prRes.status}`
        alert(`포트폴리오 분석 실패: ${msg}`)
      }
    } catch (e) {
      if (e.name === 'AbortError') {
        alert('포트폴리오 AI 분석이 시간 초과되었습니다. 잠시 후 다시 시도해주세요.')
      } else {
        console.warn('포트폴리오 추천 fetch 실패:', e)
      }
    } finally {
      clearTimeout(timeoutId)
      setPfRecsLoading(false)
    }
  }

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
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <button
                  className="dash-analysis-btn"
                  onClick={() => user?.userId && fetchStockRecs(user.userId, true)}
                  disabled={stockRecsLoading || !user?.userId}
                >
                  {stockRecsLoading ? <><span className="dash-analysis-spinner" />분석 중...</> : '종목 분석'}
                </button>
                {recStocks.length > 0 && (
                  <button className="detail-button" onClick={() => navigate('/recommendations')}>
                    상세보기 →
                  </button>
                )}
              </div>
            </div>
            <div className="recommendations-list">
              {stockRecsLoading && recStocks.length === 0 ? (
                <div style={{ padding: '16px', color: '#888', textAlign: 'center' }}>종목 분석 중...</div>
              ) : (recStocks.length > 0 ? recStocks : instrumentsStocks.slice(0, 3)).length === 0 ? (
                <div style={{ padding: '16px', color: '#888', textAlign: 'center' }}>추천 종목 없음</div>
              ) : (
                (recStocks.length > 0 ? recStocks : instrumentsStocks.slice(0, 3)).map((stock) => (
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
                        {stock.current_price ? stock.current_price.toLocaleString() + '원' : '-'}
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
                ))
              )}
            </div>
          </div>

          {/* 포트폴리오 추천 — 단일 카드 (종목 추천과 동일한 구조) */}
          {(() => {
            const BLUE_PALETTE = ['#1E3A8A','#2D5BB5','#2563EB','#3B82F6','#60A5FA','#93C5FD','#BAD4F5','#DBEAFE']
            const getColor = (idx) => BLUE_PALETTE[Math.min(idx, BLUE_PALETTE.length - 1)]
            const RISK_COLOR = { '안정형': '#27ae60', '중립형': '#f39c12', '공격형': '#e74c3c' }
            const fmtPct = (v) => v == null ? '-' : `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`
            return (
              <div className="recommendations-card card">
                <div className="card-header">
                  <h2>포트폴리오 추천</h2>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    {pfRecsUpdatedAt && !pfRecsLoading && (
                      <span style={{ fontSize: 11, color: '#999' }}>
                        {new Date(pfRecsUpdatedAt).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })} 기준
                      </span>
                    )}
                    {multiPortfolios.length > 0 && !pfRecsLoading && (
                      <span style={{ fontSize: 11, color: '#2563EB', fontWeight: 600 }}>✨ AI 분석 포함</span>
                    )}
                    <button
                      className="dash-analysis-btn"
                      disabled={pfRecsLoading || !user?.userId}
                      onClick={() => user?.userId && fetchPortfolioRecs(user.userId, true)}
                    >
                      {pfRecsLoading ? <><span className="dash-analysis-spinner" />분석 중...</> : '포트폴리오 분석'}
                    </button>
                  </div>
                </div>
                <div className="recommendations-list">
                  {pfRecsLoading && multiPortfolios.length === 0 ? (
                    <div style={{ padding: '16px', color: '#888', textAlign: 'center' }}>AI 포트폴리오 구성 중...</div>
                  ) : multiPortfolios.length === 0 ? (
                    <div style={{ padding: '16px', color: '#888', textAlign: 'center', fontSize: 13 }}>
                      포트폴리오 분석 버튼을 눌러 AI 추천 포트폴리오를 받아보세요
                    </div>
                  ) : (
                    multiPortfolios.map((pf, pfIdx) => {
                      const items = [...(pf.portfolio_items || [])].sort((a, b) => b.weight_pct - a.weight_pct)
                      const perf = pf.performance_3y
                      const riskLabel = pf.portfolio_label || pf.risk_tier || ''
                      const accentColor = RISK_COLOR[riskLabel] || '#3498db'
                      return (
                        <div
                          key={pfIdx}
                          className="recommendation-item"
                          style={{ cursor: 'pointer', borderLeft: `3px solid ${accentColor}` }}
                          onClick={() => navigate('/portfolio/recommendation', { state: { portfolioData: pf } })}
                        >
                          <div className="recommendation-header">
                            <h3 style={{ color: accentColor }}>
                              포트폴리오 {pfIdx + 1} :&nbsp;
                              <span style={{ color: '#2c3e50', fontWeight: 600 }}>{riskLabel}</span>
                            </h3>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                              {perf && (
                                <span style={{
                                  fontSize: 11, fontWeight: 700,
                                  color: perf.ann_return_pct >= 0 ? '#e74c3c' : '#3B82F6',
                                  background: perf.ann_return_pct >= 0 ? '#fff1eb' : '#eff6ff',
                                  padding: '2px 8px', borderRadius: 10,
                                }}>
                                  3Y {fmtPct(perf.ann_return_pct)}
                                </span>
                              )}
                              <span style={{ fontSize: 14, color: '#bbb' }}>›</span>
                            </div>
                          </div>
                          <p className="recommendation-reason" style={{ color: '#888', fontSize: 12, marginBottom: 8 }}>
                            ↳ {pf.portfolio_summary || (pf.overall_summary ? pf.overall_summary.split('. ')[0] : '추천 근거 없음')}
                          </p>
                          {/* 비중 막대 */}
                          <div style={{ display: 'flex', height: 6, borderRadius: 4, overflow: 'hidden', marginBottom: 8 }}>
                            {items.map((item, idx) => (
                              <div key={item.ticker}
                                title={`${item.name} ${item.weight_pct.toFixed(1)}%`}
                                style={{ width: `${item.weight_pct}%`, background: getColor(idx) }}
                              />
                            ))}
                            {items.reduce((s, i) => s + i.weight_pct, 0) < 100 && (
                              <div style={{ flex: 1, background: '#E2E8F0' }} />
                            )}
                          </div>
                          {/* 상위 종목 태그 */}
                          <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                            {items.slice(0, 3).map((item) => (
                              <span key={item.ticker} style={{
                                fontSize: 11, padding: '2px 7px', borderRadius: 10,
                                background: '#f0f4ff', color: '#2563EB', fontWeight: 600,
                              }}>
                                {item.name} {item.weight_pct.toFixed(0)}%
                                {item.ai_fin_grade && <span style={{ color: '#888', fontWeight: 400, marginLeft: 3 }}>({item.ai_fin_grade})</span>}
                              </span>
                            ))}
                            {items.length > 3 && (
                              <span style={{ fontSize: 11, color: '#999' }}>+{items.length - 3}개</span>
                            )}
                          </div>
                        </div>
                      )
                    })
                  )}
                </div>
              </div>
            )
          })()}


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
