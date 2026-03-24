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
  const [pfAvailableAmount, setPfAvailableAmount] = useState('')
  const [recRequested, setRecRequested] = useState(false)  // 사용자가 추천 버튼을 누른 적 있는지
  const [loading, setLoading] = useState(true)
  const [weatherLoading, setWeatherLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedMarket, setSelectedMarket] = useState('KOSPI')
  const [holdingsSummary, setHoldingsSummary] = useState(null)

  const API_BASE_URL = ''

  useEffect(() => {
    fetchDashboardData()
  }, [])

  useEffect(() => {
    if (loading) return
    fetchMarketWeather()
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

  const REC_SESSION_TTL = 24 * 60 * 60 * 1000  // 24시간 (ms)

  const fetchStockRecs = async (userId, refresh = false) => {
    setRecRequested(true)
    setStockRecsLoading(true)

    // sessionStorage 캐시 확인 (refresh=false 일 때만)
    if (!refresh) {
      try {
        const cached = sessionStorage.getItem(`stock_recs_${userId}`)
        if (cached) {
          const { recStocksData, updatedAt, ts } = JSON.parse(cached)
          if (Date.now() - ts < REC_SESSION_TTL) {
            setRecStocks(recStocksData || [])
            setStockRecsUpdatedAt(updatedAt)
            setStockRecsLoading(false)
            return
          }
        }
      } catch {}
    }

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
          const updatedAt = refresh ? new Date().toISOString() : (stockData.generated_at || new Date().toISOString())
          setStockRecsUpdatedAt(updatedAt)
          // sessionStorage에 저장
          try {
            sessionStorage.setItem(`stock_recs_${userId}`, JSON.stringify({
              recStocksData: newStocks,
              updatedAt,
              ts: Date.now(),
            }))
          } catch {}
        }
      }
    } catch (e) {
      if (refresh) alert('종목 분석 중 오류가 발생했습니다. 다시 시도해주세요.')
      console.warn('종목 추천 fetch 실패:', e)
    } finally {
      setStockRecsLoading(false)
    }
  }

  const fetchPortfolioRecs = async (userId, refresh = false, availableAmount = null) => {
    setPfRecsLoading(true)

    // sessionStorage 캐시 확인 (refresh=false이고 가용자산 미입력 시에만)
    if (!refresh && !availableAmount) {
      try {
        const cached = sessionStorage.getItem(`pf_recs_${userId}`)
        if (cached) {
          const { portfoliosData, cachedAt, ts } = JSON.parse(cached)
          if (Date.now() - ts < REC_SESSION_TTL) {
            setMultiPortfolios(portfoliosData || [])
            setPfRecsUpdatedAt(cachedAt)
            setPfRecsLoading(false)
            return
          }
        }
      } catch {}
    }

    const controller = new AbortController()
    // 190초 후 자동 중단 (백엔드 타임아웃 180초 + 여유 10초)
    const timeoutId = setTimeout(() => controller.abort(), 190000)
    try {
      const amountParam = availableAmount ? `&available_amount=${availableAmount}` : ''
      const prRes = await fetch(
        `${API_BASE_URL}/api/dashboard/portfolio-recommendations-ai?user_id=${userId}&refresh=${refresh}${amountParam}`,
        { signal: controller.signal }
      )
      if (prRes.ok) {
        const newPortfolios = await prRes.json()
        setMultiPortfolios(newPortfolios)
        const cachedAt = newPortfolios?.[0]?._cached_at || new Date().toISOString()
        setPfRecsUpdatedAt(cachedAt)
        // 가용자산 직접 입력 시 세션 캐시 저장 생략 (1회성 조회)
        if (!availableAmount) {
          try {
            sessionStorage.setItem(`pf_recs_${userId}`, JSON.stringify({
              portfoliosData: newPortfolios,
              cachedAt,
              ts: Date.now(),
            }))
          } catch {}
        }
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

  const fetchMarketWeather = async () => {
    setWeatherLoading(true)
    try {
      const FALLBACK_WEATHER = { weather: '흐림', score: 50, recommendation: '시장 분석 중', hint: '현재 시장 데이터를 수집하고 있습니다.' }
      const result = await fetch(`${API_BASE_URL}/api/dashboard/market-weather?market=${selectedMarket}`)
        .then(r => r.ok ? r.json() : FALLBACK_WEATHER)
        .catch(() => FALLBACK_WEATHER)
      setMarketWeather(result)
    } catch (err) {
      console.warn('시장 날씨 조회 실패:', err)
    } finally {
      setWeatherLoading(false)
    }
  }

  const fetchDashboardData = async () => {
    setLoading(true)
    setError(null)
    
    try {
      const FALLBACK_WEATHER = { weather: '흐림', score: 50, recommendation: '시장 분석 중', hint: '현재 시장 데이터를 수집하고 있습니다.' }
      const FALLBACK_INDICES = [
        { market: 'KOSPI',  index: 2500.00, change: 0, change_rate: 0, date: new Date().toISOString().split('T')[0] },
        { market: 'KOSDAQ', index: 850.00,  change: 0, change_rate: 0, date: new Date().toISOString().split('T')[0] },
      ]

      // 4개 API 동시 병렬 호출 (순차 await → Promise.allSettled)
      const [invResult, weatherResult, indicesResult, instResult] = await Promise.allSettled([
        fetch(`${API_BASE_URL}/api/dashboard/investor-trading`).then(r => r.ok ? r.json() : []),
        fetch(`${API_BASE_URL}/api/dashboard/market-weather?market=${selectedMarket}`).then(r => r.ok ? r.json() : FALLBACK_WEATHER),
        fetch(`${API_BASE_URL}/api/dashboard/market-indices`).then(r => r.ok ? r.json() : FALLBACK_INDICES),
        fetch(`${API_BASE_URL}/api/instruments/stocks?limit=20`).then(r => r.ok ? r.json() : []),
      ])

      const investorRows = invResult.status === 'fulfilled' ? invResult.value : []
      const weather      = weatherResult.status === 'fulfilled' ? weatherResult.value : FALLBACK_WEATHER
      const indices      = indicesResult.status === 'fulfilled' ? indicesResult.value : FALLBACK_INDICES
      const instStocks   = instResult.status === 'fulfilled' ? instResult.value : []

      if (invResult.status === 'rejected')     console.warn('Failed to fetch investor trading:', invResult.reason)
      if (weatherResult.status === 'rejected') console.warn('Failed to fetch market weather:', weatherResult.reason)
      if (indicesResult.status === 'rejected') console.warn('Failed to fetch market indices:', indicesResult.reason)
      if (instResult.status === 'rejected')    console.warn('Failed to fetch instruments stocks:', instResult.reason)

      // investorRows 배열 → {KOSPI: {...}, KOSDAQ: {...}} 딕셔너리로 변환
      const invMap = {}
      for (const row of investorRows) {
        invMap[row.market] = row
      }
      setInvestorTrading(invMap)
      setMarketWeather(weather)
      setMarketIndices(indices)
      setInstrumentsStocks(instStocks)

      if (!weather && indices.length === 0 && instStocks.length === 0) {
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
                background: 'rgba(255, 255, 255, 0.18)',
                backdropFilter: 'blur(10px)',
                padding: '1.2rem 1.8rem',
                borderRadius: '10px',
                border: '1px solid rgba(255, 255, 255, 0.25)',
                minWidth: '200px'
              }}>
                <div style={{ fontSize: '0.75rem', color: 'rgba(255, 255, 255, 0.75)', marginBottom: '0.5rem', fontWeight: '500', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                  총 보유 자산
                </div>
                <div style={{ fontSize: '2rem', fontWeight: '800', color: 'white', letterSpacing: '-0.5px', lineHeight: 1 }}>
                  ₩{holdingsSummary.total_current_value.toLocaleString()}
                </div>
              </div>
              
              {/* 전일 대비 */}
              <div style={{
                background: 'rgba(255, 255, 255, 0.18)',
                backdropFilter: 'blur(10px)',
                padding: '1.2rem 1.8rem',
                borderRadius: '10px',
                border: '1px solid rgba(255, 255, 255, 0.25)',
                minWidth: '180px'
              }}>
                <div style={{ fontSize: '0.75rem', color: 'rgba(255, 255, 255, 0.75)', marginBottom: '0.5rem', fontWeight: '500', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                  전일 대비
                </div>
                <div style={{ 
                  fontSize: '1.6rem', 
                  fontWeight: '800', 
                  color: holdingsSummary.total_return_amount >= 0 ? '#fef3c7' : '#bfdbfe',
                  letterSpacing: '-0.5px',
                  lineHeight: 1
                }}>
                  {holdingsSummary.total_return_amount >= 0 ? '+' : ''}
                  {holdingsSummary.total_return_amount.toLocaleString()}원
                  <span style={{ fontSize: '1rem', marginLeft: '0.5rem', fontWeight: '700' }}>
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
            {weatherLoading ? (
              <div className="weather-loading">로딩 중...</div>
            ) : marketWeather && (
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

        </div>

        {/* 우측 영역 */}
        <div className="dashboard-right">
          {/* 투자자별 매매동향 - KOSPI/KOSDAQ 동시 표시 */}
          <div className="trading-trends-card card">
            <div className="card-header">
              <h2>투자자별 매매동향</h2>
              <span className="trading-date">
                {investorTrading['KOSPI']?.date ?? investorTrading['KOSDAQ']?.date ?? ''}
              </span>
            </div>
            {(() => {
              const fmtNet = (v) => {
                if (v == null) return '-'
                const n = Number(v)
                return (n > 0 ? '+' : '') + n.toLocaleString('ko-KR', { minimumFractionDigits: 0 })
              }

              const getRows = (market) => {
                const d = investorTrading[market]
                return d ? [
                  { label: '기관(십억원)', net: d.institution_net },
                  { label: '외국인(십억원)', net: d.foreign_net },
                  { label: '개인(십억원)', net: d.individual_net },
                ] : []
              }

              return (
                <div className="trading-market-stack">
                  {['KOSPI', 'KOSDAQ'].map((market, marketIdx) => {
                    const rows = getRows(market)
                    return (
                      <div
                        key={market}
                        className={`trading-market-block ${marketIdx > 0 ? 'with-divider' : ''}`}
                      >
                        <span className="trading-market-chip">{market}</span>
                        <table className="investor-table">
                          {marketIdx === 0 && (
                            <thead>
                              <tr>
                                <th>구분</th>
                                <th>순매수</th>
                              </tr>
                            </thead>
                          )}
                          <tbody>
                            {rows.length === 0 ? (
                              <tr><td colSpan={2} style={{textAlign:'center',color:'#888',padding:'16px'}}>데이터 로딩 중...</td></tr>
                            ) : rows.map((r, i) => (
                              <tr key={`${market}-${i}`}>
                                <td className="investor-label">{r.label}</td>
                                <td className={getChangeColor(r.net)}>{fmtNet(r.net)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )
                  })}
                </div>
              )
            })()}
          </div>

        </div>
      </div>

      {/* 하단: 종목 추천 + 포트폴리오 추천 */}
      <div className="dashboard-bottom">
          <div className="recommendations-card card stock-recommendations-card">
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
            {recStocks.length > 0 && (
              <div className="stock-detail-bottom">
                <button className="detail-button" onClick={() => navigate('/recommendations')}>
                  상세보기 →
                </button>
              </div>
            )}
          </div>

          {/* 포트폴리오 추천 — 단일 카드 (종목 추천과 동일한 구조) */}
          {(() => {
            const BLUE_PALETTE = ['#C2410C','#EA580C','#F97316','#FB923C','#FDBA74','#FED7AA','#FFEDD5','#FFF4E6']
            const getColor = (idx) => BLUE_PALETTE[Math.min(idx, BLUE_PALETTE.length - 1)]
            // Top 순위별 강조색
            const TOP_COLORS = ['#FFB84D', '#FF8F00', '#FFD66B']
            const getTopColor = (idx) => TOP_COLORS[idx] || '#3498db'
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
              const nItems = (pf.portfolio_items || []).length

              // MC 수익률/리스크 요약
              const parts = []
              if (mc?.p50_pct != null) parts.push(`기대수익 ${mc.p50_pct >= 0 ? '+' : ''}${mc.p50_pct.toFixed(0)}%`)
              if (mc?.vol_ann_pct != null) parts.push(`변동성 ${mc.vol_ann_pct.toFixed(0)}%`)
              if (mc?.p10_pct != null) parts.push(`하락 시나리오 ${mc.p10_pct >= 0 ? '+' : ''}${mc.p10_pct.toFixed(0)}%`)
              const mcStr = parts.length > 0 ? parts.join(' · ') : null

              // 개인화 컨텍스트 조합
              const condParts = []
              if (goal && horizon) condParts.push(`${goal}(${horizon})`)
              else if (goal) condParts.push(goal)
              else if (horizon) condParts.push(`${horizon} 목표`)
              if (contribType === 'LUMP_SUM' && lumpAmt) condParts.push(`일시금 ${fmtKrw(lumpAmt)}`)
              else if (contribType === 'DCA' && monthlyAmt) condParts.push(`월 ${fmtKrw(monthlyAmt)} 적립식`)
              else if (monthlyAmt) condParts.push(`월 ${fmtKrw(monthlyAmt)}`)
              else if (lumpAmt) condParts.push(fmtKrw(lumpAmt))

              const ctxStr = condParts.length > 0 ? `${condParts.join(' · ')}에 맞게 선별된 ${nItems}개 종목` : `${pf.risk_tier} 성향에 맞게 선별된 ${nItems}개 종목`
              return mcStr ? `${tierIcon} ${ctxStr} — ${mcStr}` : `${tierIcon} ${ctxStr}`
            }
            const fmtPct = (v) => v == null ? '-' : `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`
            return (
              <div className="recommendations-card card">
                <div className="card-header">
                  <h2>포트폴리오 추천</h2>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <input
                        type="number"
                        min="0"
                        step="10000"
                        placeholder="가용자산 (원)"
                        value={pfAvailableAmount}
                        onChange={(e) => setPfAvailableAmount(e.target.value)}
                        style={{
                          width: 140,
                          padding: '5px 8px',
                          fontSize: 12,
                          border: '1px solid #d1d5db',
                          borderRadius: 6,
                          outline: 'none',
                          color: '#374151',
                        }}
                        disabled={pfRecsLoading}
                      />
                    </div>
                    <button
                      className="dash-analysis-btn"
                      disabled={pfRecsLoading || !user?.userId}
                      onClick={async () => {
                        const amt = pfAvailableAmount ? parseInt(pfAvailableAmount, 10) : null
                        if (amt && user?.userId) {
                          try {
                            await fetch(`${API_BASE_URL}/api/users/${user.userId}`, {
                              method: 'PUT',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({ lump_sum_amount: amt }),
                            })
                          } catch {}
                        }
                        user?.userId && fetchPortfolioRecs(user.userId, true, amt)
                      }}
                    >
                      {pfRecsLoading ? <><span className="dash-analysis-spinner" />분석 중...</> : '포트폴리오 분석'}
                    </button>
                  </div>
                </div>
                {pfRecsUpdatedAt && !pfRecsLoading && (
                  <div style={{ padding: '0 16px 6px', color: '#aaa', fontSize: 11 }}>
                    마지막 분석: {new Date(pfRecsUpdatedAt).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    {pfAvailableAmount && ` · 가용자산 ${parseInt(pfAvailableAmount).toLocaleString()}원 기준`}
                  </div>
                )}
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
                      const accentColor = getTopColor(pfIdx)
                      return (
                        <div
                          key={pfIdx}
                          className="recommendation-item"
                          style={{ cursor: 'pointer', borderLeft: `3px solid ${accentColor}` }}
                          onClick={() => navigate('/portfolio/recommendation', { state: { portfolioData: pf, portfolioRank: pfIdx + 1 } })}
                        >
                          <div className="recommendation-header">
                            <h3 style={{ color: '#1a202c', fontSize: '1.05rem', fontWeight: 600 }}>
                              <span style={{ color: accentColor, fontSize: '0.9rem' }}>Top {pfIdx + 1}</span> : {riskLabel}
                            </h3>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                              {perf && (
                                <span style={{
                                  fontSize: '0.7rem', fontWeight: 700,
                                  color: perf.ann_return_pct >= 0 ? '#C2410C' : '#3B82F6',
                                  background: perf.ann_return_pct >= 0 ? '#FFF8E1' : '#eff6ff',
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
                                background: '#FFB84D',
                                color: '#1a1a1a',
                                fontWeight: '600',
                                boxShadow: '0 2px 4px rgba(255, 184, 77, 0.3)',
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
  )
}

export default DashboardPage
