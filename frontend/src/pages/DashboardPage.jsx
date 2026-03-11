import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import './DashboardPage.css'

const DashboardPage = () => {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [investorTrading, setInvestorTrading] = useState({})
  const [marketWeather, setMarketWeather] = useState(null)
  const [marketIndices, setMarketIndices] = useState([])
  const [instrumentsStocks, setInstrumentsStocks] = useState([])
  const [recStocks, setRecStocks] = useState([])      // 추천 top3 + 실시간 주가
  const [multiPortfolios, setMultiPortfolios] = useState([])  // 3종 포트폴리오
  const [pfRecsUpdatedAt, setPfRecsUpdatedAt] = useState(null)  // last fetch timestamp
  const [stockRecsUpdatedAt, setStockRecsUpdatedAt] = useState(null)  // 종목 분석 완료 시각
  const [stockRecsLoading, setStockRecsLoading] = useState(false)
  const [pfRecsLoading, setPfRecsLoading] = useState(false)
  const [recRequested, setRecRequested] = useState(false)  // 사용자가 추천 버튼을 누른 적 있는지
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedMarket, setSelectedMarket] = useState('KOSPI')
  const [showChatbot, setShowChatbot] = useState(false)
  const [chatMessages, setChatMessages] = useState([])
  const [chatInput, setChatInput] = useState('')
  const [holdingsSummary, setHoldingsSummary] = useState(null)

  const API_BASE_URL = ''

  useEffect(() => {
    fetchDashboardData()
  }, [selectedMarket])

  useEffect(() => {
    if (!user?.userId) return
    // 페이지 진입 시 캐시된 추천 결과가 있으면 자동으로 불러옴 (refresh=false)
    fetchStockRecs(user.userId, false)
    fetchPortfolioRecs(user.userId, false)
    fetchHoldingsSummary(user.userId)
  }, [user])

  // 보유 자산 요약 정보 가져오기
  const fetchHoldingsSummary = async (userId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/holdings/${userId}/summary`)
      if (response.ok) {
        const data = await response.json()
        setHoldingsSummary(data)
      }
    } catch (err) {
      console.warn('보유 자산 조회 실패:', err)
    }
  }

  // 실시간 주가 SSE 스트림 — instrumentsStocks + recStocks 통합 구독
  const esRef = useRef(null)
  const subscribedCodesRef = useRef('')

  const connectSSE = useCallback((allCodes) => {
    const codeStr = allCodes.join(',')
    if (!codeStr || codeStr === subscribedCodesRef.current) return
    subscribedCodesRef.current = codeStr

    if (esRef.current) esRef.current.close()

    const es = new EventSource(`/api/stream/prices?codes=${codeStr}`)
    esRef.current = es

    es.onmessage = (e) => {
      try {
        const updates = JSON.parse(e.data)
        setInstrumentsStocks(prev =>
          prev.map(s => {
            const upd = updates[s.stock_code]
            if (!upd) return s
            return { ...s, current_price: upd.current_price, change: upd.change, change_rate: upd.change_rate, volume: upd.volume }
          })
        )
        setRecStocks(prev =>
          prev.map(s => {
            const upd = updates[s.stock_code]
            if (!upd) return s
            return { ...s, current_price: upd.current_price, change_rate: upd.change_rate, volume: upd.volume }
          })
        )
      } catch (err) {
        console.warn('SSE 파싱 오류:', err) 
      }
    }

    es.onerror = () => {
      console.warn('SSE 연결 오류 — 자동 재연결 대기 중')
    }
  }, [])

  // instrumentsStocks 또는 recStocks가 바뀌면 구독 목록 갱신
  useEffect(() => {
    const instCodes = instrumentsStocks.map(s => s.stock_code)
    const recCodes  = recStocks.map(s => s.stock_code)
    const merged    = [...new Set([...instCodes, ...recCodes])]
    if (merged.length === 0) return
    connectSSE(merged)
  }, [instrumentsStocks.length, recStocks.length, connectSSE])

  // 언마운트 시 SSE 닫기
  useEffect(() => {
    return () => { if (esRef.current) esRef.current.close() }
  }, [])

  const fetchStockRecs = async (userId, refresh = false) => {
    setRecRequested(true)
    setStockRecsLoading(true)
    try {
      const srRes = await fetch(`${API_BASE_URL}/api/dashboard/stock-recommendations?user_id=${userId}&refresh=${refresh}`)
      if (!srRes.ok) {
        const detail = await srRes.json().catch(() => ({}))
        const msg = detail?.detail || `오류 코드: ${srRes.status}`
        if (refresh) alert(`종목 분석 실패: ${msg}`)
        return
      }
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
              name:          item.name || priceMap[item.ticker]?.name || item.ticker,
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
          if (refresh) setStockRecsUpdatedAt(new Date().toISOString())
          else setStockRecsUpdatedAt(stockData.generated_at || new Date().toISOString())
        }
      }
    } catch (e) {
      if (refresh) alert('종목 분석 중 오류가 발생했습니다. 다시 시도해주세요.')
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

  // 로딩 중일 때
  if (loading) {
    return (
      <>
        <style>{`
          @keyframes spinLoader {
            to { transform: rotate(360deg); }
          }
        `}</style>
        <div style={{ 
          minHeight: '100vh', 
          background: 'linear-gradient(135deg, #FFF9E6 0%, #FFFBEA 50%, #FFF6DC 100%)',
          display: 'flex', 
          flexDirection: 'column', 
          alignItems: 'center', 
          justifyContent: 'center',
          width: '100%',
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0
        }}>
          <div style={{
            width: '60px',
            height: '60px',
            border: '5px solid #e8f5e9',
            borderTopColor: '#5a9068',
            borderRadius: '50%',
            animation: 'spinLoader 0.8s linear infinite',
            marginBottom: '2rem'
          }}></div>
          <p style={{ margin: 0, fontSize: '0.95rem', color: '#5a9068', fontWeight: '500', letterSpacing: '0.3px' }}>포트폴리오를 불러오는 중...</p>
        </div>
      </>
    )
  }

  return (
    <div className="dashboard-page">
      <div className="dashboard-header">
        <div style={{ maxWidth: '1600px', margin: '0 auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '2rem' }}>
          <div>
            <h1>안녕하세요, {user?.name || user?.username || '투자자'}님 </h1>
            <p className="dashboard-subtitle">
              {new Date().toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' })}
            </p>
          </div>
          
          {holdingsSummary && holdingsSummary.total_current_value > 0 && (
            <div style={{ display: 'flex', gap: '1.5rem', flexWrap: 'wrap' }}>
              {/* 총 보유 자산 */}
              <div style={{
                background: 'rgba(255, 255, 255, 0.25)',
                backdropFilter: 'blur(10px)',
                padding: '1.2rem 1.8rem',
                borderRadius: '16px',
                border: '1px solid rgba(255, 255, 255, 0.3)',
                minWidth: '200px'
              }}>
                <div style={{ fontSize: '0.85rem', color: 'rgba(255, 255, 255, 0.9)', marginBottom: '0.4rem', fontWeight: '600' }}>
                  총 보유 자산
                </div>
                <div style={{ fontSize: '2rem', fontWeight: '800', color: 'white', letterSpacing: '-0.5px' }}>
                  ₩{holdingsSummary.total_current_value.toLocaleString()}
                </div>
              </div>
              
              {/* 전일 대비 */}
              <div style={{
                background: 'rgba(255, 255, 255, 0.25)',
                backdropFilter: 'blur(10px)',
                padding: '1.2rem 1.8rem',
                borderRadius: '16px',
                border: '1px solid rgba(255, 255, 255, 0.3)',
                minWidth: '180px'
              }}>
                <div style={{ fontSize: '0.85rem', color: 'rgba(255, 255, 255, 0.9)', marginBottom: '0.4rem', fontWeight: '600' }}>
                  전일 대비
                </div>
                <div style={{ 
                  fontSize: '1.6rem', 
                  fontWeight: '800', 
                  color: holdingsSummary.total_return_amount >= 0 ? '#fef3c7' : '#bfdbfe',
                  letterSpacing: '-0.5px'
                }}>
                  {holdingsSummary.total_return_amount >= 0 ? '+' : ''}
                  {holdingsSummary.total_return_amount.toLocaleString()}원
                  <span style={{ fontSize: '1.1rem', marginLeft: '0.5rem', fontWeight: '700' }}>
                    {holdingsSummary.total_return_rate >= 0 ? '▲' : '▼'}
                    {Math.abs(holdingsSummary.total_return_rate).toFixed(2)}%
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
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

          {/* 투자자별 매매동향 - KOSPI */}
          <div className="trading-trends-card card">
            <div className="card-header">
              <h2>투자자별 매매동향</h2>
              <span className="trading-date">
                {investorTrading['KOSPI']?.date ?? ''}
              </span>
            </div>
            {/* KOSPI 마켓 표시 */}
            <div className="trading-market-label">KOSPI</div>
            {/* 테이블 */}
            {(() => {
              const d = investorTrading['KOSPI']
              const fmtSell = (v) => (v == null || Number(v) === 0) ? '-' : Number(v).toLocaleString('ko-KR')
              const fmtBuy  = fmtSell
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

          {/* 투자자별 매매동향 - KOSDAQ */}
          <div className="trading-trends-card card">
            <div className="card-header">
              <h2>투자자별 매매동향</h2>
              <span className="trading-date">
                {investorTrading['KOSDAQ']?.date ?? ''}
              </span>
            </div>
            {/* KOSDAQ 마켓 표시 */}
            <div className="trading-market-label">KOSDAQ</div>
            {/* 테이블 */}
            {(() => {
              const d = investorTrading['KOSDAQ']
              const fmtSell = (v) => (v == null || Number(v) === 0) ? '-' : Number(v).toLocaleString('ko-KR')
              const fmtBuy  = fmtSell
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
            {stockRecsUpdatedAt && (
              <div style={{ padding: '0 16px 6px', color: '#aaa', fontSize: 11 }}>
                마지막 분석: {new Date(stockRecsUpdatedAt).toLocaleString('ko-KR', { month:'numeric', day:'numeric', hour:'2-digit', minute:'2-digit' })}
              </div>
            )}
            <div className="recommendations-list" style={{ position: 'relative' }}>
              {stockRecsLoading && recStocks.length > 0 && (
                <div style={{ position: 'absolute', inset: 0, background: 'rgba(255,255,255,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 10, borderRadius: 8 }}>
                  <span className="dash-analysis-spinner" style={{ width: 20, height: 20, marginRight: 8 }} />분석 중...
                </div>
              )}
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
            const TIER_SUMMARY = {
              '안정형':    '🛡️ 원금 보존을 최우선으로, 안전하게 자산을 지키는 포트폴리오입니다.',
              '안정추구형': '🛡️ 낮은 변동성으로 꾸준히 자산을 불려가는 안정형 포트폴리오입니다.',
              '위험중립형': '⚖️ 안정성과 수익 가능성을 균형 있게 담은 포트폴리오입니다.',
              '적극투자형': '📈 성장 가능성 높은 종목에 집중해 높은 수익을 노리는 포트폴리오입니다.',
              '공격투자형': '🚀 강한 상승 모멘텀 종목으로 구성해 최대 수익을 추구하는 포트폴리오입니다.',
            }
            const INVEST_GOAL_LABEL_D = {
              '노후 준비': '노후 준비', '은퇴 준비': '노후 준비',
              '주택 마련': '내 집 마련', '집 구입': '내 집 마련',
              '자산 증식': '자산 증식', '목돈 마련': '목돈 마련',
              '여유 자금 운용': '여유 자금 운용', '자녀 교육': '자녀 교육 자금',
            }
            const buildCardSummary = (pf) => {
              const ctx = pf.survey_context || {}
              const tierIcon = { '안정형':'🛡️','안정추구형':'🛡️','위험중립형':'⚖️','적극투자형':'📈','공격투자형':'🚀' }[pf.risk_tier] || '📊'
              const GOAL_LBL = {
                '노후 준비':'노후 준비','은퇴 준비':'노후 준비',
                '주택 마련':'내 집 마련','집 구입':'내 집 마련',
                '자산 증식':'자산 증식','목돈 마련':'목돈 마련',
                '여유 자금 운용':'여유 자금 운용','자녀 교육':'자녀 교육 자금',
              }
              const goal = ctx.INVEST_GOAL ? (GOAL_LBL[ctx.INVEST_GOAL] || ctx.INVEST_GOAL) : null
              const horizon = ctx.TARGET_HORIZON || null
              const lumpAmt = ctx.LUMP_SUM_AMOUNT ? parseInt(ctx.LUMP_SUM_AMOUNT, 10) : null
              const monthlyAmt = ctx.MONTHLY_AMOUNT ? parseInt(ctx.MONTHLY_AMOUNT, 10) : null
              const contribType = ctx.CONTRIBUTION_TYPE
              const fmtKrw = (n) => n >= 100_000_000 ? `${(n/100_000_000).toFixed(0)}억 원` : `${(n/10_000).toFixed(0)}만 원`
              const mc = pf.monte_carlo_1y
              const retStr = mc?.p50_pct != null ? ` · 기대수익 ${mc.p50_pct >= 0 ? '+' : ''}${mc.p50_pct.toFixed(0)}%` : ''
              const nItems = (pf.portfolio_items || []).length
              const condParts = []
              if (goal && horizon) condParts.push(`${goal}(${horizon})`)
              else if (goal) condParts.push(goal)
              else if (horizon) condParts.push(`${horizon} 목표`)
              if (contribType === 'LUMP_SUM' && lumpAmt) condParts.push(`일시금 ${fmtKrw(lumpAmt)}`)
              else if (contribType === 'DCA' && monthlyAmt) condParts.push(`월 ${fmtKrw(monthlyAmt)} 적립식`)
              else if (monthlyAmt) condParts.push(`월 ${fmtKrw(monthlyAmt)}`)
              else if (lumpAmt) condParts.push(fmtKrw(lumpAmt))
              const pfDesc = `${pf.risk_tier} ${nItems}개 종목${retStr}`
              if (condParts.length > 0) return `${tierIcon} ${condParts.join(' · ')}에 최적화된 ${pfDesc}`
              return TIER_SUMMARY[pf.risk_tier] || `${tierIcon} ${pf.risk_tier} 성향에 맞게 구성된 포트폴리오입니다.`
            }
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
                            <h3 style={{ color: '#1a202c', fontSize: '1.05rem', fontWeight: 600 }}>
                              <span style={{ color: accentColor, fontSize: '0.9rem' }}>포트폴리오 {pfIdx + 1}</span> : {riskLabel}
                            </h3>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                              {perf && (
                                <span style={{
                                  fontSize: '0.7rem', fontWeight: 700,
                                  color: perf.ann_return_pct >= 0 ? '#e74c3c' : '#3B82F6',
                                  background: perf.ann_return_pct >= 0 ? '#fff1eb' : '#eff6ff',
                                  padding: '3px 8px', borderRadius: 10,
                                }}>
                                  3Y {fmtPct(perf.ann_return_pct)}
                                </span>
                              )}
                              <span style={{ fontSize: 14, color: '#bbb' }}>›</span>
                            </div>
                          </div>
                          <p className="recommendation-reason" style={{ color: '#64748b', fontSize: '0.85rem', marginBottom: 10, lineHeight: 1.5 }}>
                            {buildCardSummary(pf)}
                          </p>
                          {/* 비중 막대 */}
                          <div style={{ display: 'flex', height: 8, borderRadius: 6, overflow: 'hidden', marginBottom: 10 }}>
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
                          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                            {items.slice(0, 5).map((item, idx) => (
                              <span key={item.ticker} style={{
                                fontSize: '0.75rem',
                                padding: '4px 10px',
                                borderRadius: '12px',
                                background: '#2563EB',
                                color: 'white',
                                fontWeight: '600',
                                boxShadow: '0 2px 4px rgba(37, 99, 235, 0.2)',
                              }}>
                                {item.name} {item.weight_pct.toFixed(0)}%
                              </span>
                            ))}
                            {items.length > 5 && (
                              <span style={{ fontSize: 11, color: '#999', alignSelf: 'center' }}>+{items.length - 5}개</span>
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
        <svg width="46" height="46" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
          {/* 줄기 */}
          <path 
            d="M 50 75 Q 48 65, 47 55 Q 46 45, 48 38" 
            fill="none"
            stroke="#ffffff" 
            strokeWidth="6"
            strokeLinecap="round"
          />
          
          {/* 왼쪽 잎 - 더 둥글고 통통한 형태 */}
          <path 
            d="M 48 38 Q 35 35, 25 28 Q 18 23, 16 18 Q 16 15, 19 14 Q 23 14, 28 18 Q 38 25, 48 38" 
            fill="#ffffff"
            fillOpacity="0.95"
            stroke="#ffffff" 
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {/* 왼쪽 잎 중심맥 */}
          <path 
            d="M 48 38 Q 38 32, 30 26" 
            fill="none"
            stroke="#5a9068" 
            strokeWidth="2"
            strokeLinecap="round"
            opacity="0.6"
          />
          
          {/* 오른쪽 잎 - 더 둥글고 통통한 형태 */}
          <path 
            d="M 48 38 Q 61 35, 71 28 Q 78 23, 80 18 Q 80 15, 77 14 Q 73 14, 68 18 Q 58 25, 48 38" 
            fill="#ffffff"
            fillOpacity="0.95"
            stroke="#ffffff" 
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {/* 오른쪽 잎 중심맥 */}
          <path 
            d="M 48 38 Q 58 32, 66 26" 
            fill="none"
            stroke="#5a9068" 
            strokeWidth="2"
            strokeLinecap="round"
            opacity="0.6"
          />
          
          {/* 줄기 하단 (땅과의 연결) */}
          <ellipse 
            cx="50" 
            cy="78" 
            rx="8" 
            ry="3.5" 
            fill="#ffffff"
            opacity="0.85"
          />
        </svg>
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
