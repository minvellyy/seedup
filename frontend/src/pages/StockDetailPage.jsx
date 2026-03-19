import React, { useState, useEffect } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import './StockDetailPage.css'

// ── 포매터 ──────────────────────────────────────────────────────────────────
const fmtPrice = (v) => v == null ? '-' : Number(v).toLocaleString('ko-KR') + '원'
const fmtVol   = (v) => v == null ? '-' : Number(v).toLocaleString('ko-KR')
const fmtMcap  = (v) => {
  if (v == null) return '-'
  const t = v / 1e12
  if (t >= 1) return `약 ${t.toFixed(0)}조원`
  const b = v / 1e8
  return `약 ${b.toFixed(0)}억원`
}

// ── 일중 차트 (FinanceDataReader) ─────────────────────────────────────────
function IntradayChart({ data }) {
  if (!data || !data.data || data.data.length < 2) {
    return (
      <div className="sd-intraday-empty">
        <p>일중 데이터가 없습니다.</p>
      </div>
    )
  }

  const chartData = data.data
  const W = 800, H = 180, padT = 12, padB = 28, padL = 4, padR = 4
  const plotW = W - padL - padR
  const plotH = H - padT - padB

  const prices = chartData.map(d => d.close)
  const minY = Math.min(...prices)
  const maxY = Math.max(...prices)
  const range = maxY - minY || 1

  const sy = (v) => padT + plotH - ((v - minY) / range) * plotH
  const n = chartData.length
  const step = plotW / (n - 1)

  // 라인 경로 생성
  const linePath = chartData
    .map((d, i) => {
      const x = padL + i * step
      const y = sy(d.close)
      return `${i === 0 ? 'M' : 'L'}${x},${y}`
    })
    .join(' ')

  // 날짜 레이블
  const firstDate = chartData[0].date
  const lastDate = chartData[chartData.length - 1].date
  const midDate = chartData[Math.floor(n / 2)]?.date || ''

  // 가격 변동
  const firstPrice = prices[0]
  const lastPrice = prices[prices.length - 1]
  const priceChange = lastPrice - firstPrice
  const changeRate = ((priceChange / firstPrice) * 100).toFixed(2)
  const isUp = priceChange >= 0
  const lineColor = isUp ? '#EA580C' : '#3B82F6'

  return (
    <div className="sd-intraday-wrap">
      <div className="sd-intraday-header">
        <span className="sd-intraday-title">최근 {data.period} 가격 추이</span>
        <span className={`sd-intraday-change ${isUp ? 'up' : 'down'}`}>
          {isUp ? '▲' : '▼'} {Math.abs(priceChange).toLocaleString()}원 ({isUp ? '+' : ''}{changeRate}%)
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block' }}>
        {/* 그라데이션 정의 */}
        <defs>
          <linearGradient id="lineGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor={lineColor} stopOpacity="0.8" />
            <stop offset="100%" stopColor={lineColor} stopOpacity="1" />
          </linearGradient>
          <filter id="shadow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur in="SourceAlpha" stdDeviation="2"/>
            <feOffset dx="0" dy="2" result="offsetblur"/>
            <feComponentTransfer>
              <feFuncA type="linear" slope="0.3"/>
            </feComponentTransfer>
            <feMerge>
              <feMergeNode/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>
        </defs>
        
        {/* Y축 */}
        <line x1={padL} y1={padT} x2={padL} y2={H - padB} stroke="#e5e7eb" strokeWidth={1.5} />
        <line x1={padL} y1={H - padB} x2={W - padR} y2={H - padB} stroke="#e5e7eb" strokeWidth={1.5} />
        
        {/* 가격 라인 */}
        <path d={linePath} fill="none" stroke="url(#lineGradient)" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" filter="url(#shadow)" />
        
        {/* 데이터 포인트 */}
        {chartData.map((d, i) => {
          const x = padL + i * step
          const y = sy(d.close)
          return (
            <g key={i}>
              <circle cx={x} cy={y} r={4} fill="white" stroke={lineColor} strokeWidth={2} />
              <circle cx={x} cy={y} r={2} fill={lineColor} />
            </g>
          )
        })}
        
        {/* Y축 레이블 */}
        <g>
          <rect x={padL - 60} y={sy(maxY) - 12} width="55" height="24" rx="6" fill="white" stroke="#e5e7eb" strokeWidth="1"/>
          <text x={padL - 32} y={sy(maxY)} fontSize={11} fill="#EA580C" textAnchor="middle" dominantBaseline="middle" fontWeight="600">
            {maxY.toLocaleString()}
          </text>
        </g>
        <g>
          <rect x={padL - 60} y={sy(minY) - 12} width="55" height="24" rx="6" fill="white" stroke="#e5e7eb" strokeWidth="1"/>
          <text x={padL - 32} y={sy(minY)} fontSize={11} fill="#3B82F6" textAnchor="middle" dominantBaseline="middle" fontWeight="600">
            {minY.toLocaleString()}
          </text>
        </g>
        
        {/* X축 날짜 레이블 */}
        <text x={padL} y={H - 5} fontSize={11} fill="#666" textAnchor="start" fontWeight="600">{firstDate}</text>
        <text x={padL + plotW / 2} y={H - 5} fontSize={11} fill="#999" textAnchor="middle" fontWeight="500">{midDate}</text>
        <text x={W - padR} y={H - 5} fontSize={11} fill="#666" textAnchor="end" fontWeight="600">{lastDate}</text>
      </svg>
    </div>
  )
}

// ── 캔들스틱 차트 (SVG) ────────────────────────────────────────────────────
function CandlestickChart({ data, days = 30 }) {
  if (!data || data.length < 2) return null
  const items = data.slice(-days)
  const hasOHLC = items.some(d => d.open != null && d.high != null && d.low != null)

  const W = 800, H = 180, padT = 12, padB = 28, padL = 4, padR = 4
  const plotW = W - padL - padR
  const plotH = H - padT - padB

  const allHi = items.map(d => hasOHLC ? (d.high ?? d.close) : d.close)
  const allLo = items.map(d => hasOHLC ? (d.low  ?? d.close) : d.close)
  const minY = Math.min(...allLo)
  const maxY = Math.max(...allHi)
  const range = maxY - minY || 1

  const sy = (v) => padT + plotH - ((v - minY) / range) * plotH
  const n = items.length
  const step = plotW / n
  const barW = Math.max(3, step - 2)

  const maxClose = Math.max(...items.map(d => d.high ?? d.close))
  const minClose = Math.min(...items.map(d => d.low  ?? d.close))

  const dlabels = [0, Math.floor(n / 2), n - 1]

  return (
    <div className="sd-candle-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block' }}>
        {items.map((d, i) => {
          const x  = padL + i * step + step / 2
          const isUp  = d.close >= (d.open ?? d.close)
          const color = isUp ? '#EA580C' : '#3B82F6'
          const openY  = sy(d.open ?? d.close)
          const closeY = sy(d.close)
          const highY  = sy(hasOHLC ? (d.high ?? d.close) : d.close)
          const lowY   = sy(hasOHLC ? (d.low  ?? d.close) : d.close)
          const bodyTop = Math.min(openY, closeY)
          const bodyH   = Math.max(Math.abs(openY - closeY), 1)
          return (
            <g key={i}>
              <line x1={x} y1={highY} x2={x} y2={lowY} stroke={color} strokeWidth={1.5} />
              <rect x={x - barW / 2} y={bodyTop} width={barW} height={bodyH} fill={color} />
            </g>
          )
        })}
        {dlabels.map(i => (
          <text key={i} x={padL + i * step + step / 2} y={H - 4}
            fontSize={11} fill="#bbb" textAnchor="middle">{items[i]?.date}</text>
        ))}
      </svg>
      <div className="sd-candle-minmax">
        <span className="sd-candle-high">최고: {maxClose.toLocaleString('ko-KR')}원</span>
        <span className="sd-candle-low">최저: {minClose.toLocaleString('ko-KR')}원</span>
      </div>
    </div>
  )
}

// ── 레이더(오각형) 차트 (SVG) ──────────────────────────────────────────────
function RadarChart({ points }) {
  if (!points || points.length < 3) return null
  const SIZE = 260, cx = 130, cy = 130, R = 90
  const n = points.length

  const coord = (i, ratio) => {
    const a = (2 * Math.PI * i / n) - Math.PI / 2
    return { x: cx + Math.cos(a) * R * ratio, y: cy + Math.sin(a) * R * ratio }
  }
  const gridPath = (ratio) => {
    const pts = Array.from({ length: n }, (_, i) => coord(i, ratio))
    return pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ') + 'Z'
  }
  const dataPts  = points.map((p, i) => coord(i, Math.min(p.score ?? 0, 100) / 100))
  const dataPath = dataPts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ') + 'Z'
  const labelPos = points.map((_, i) => coord(i, 1.42))

  return (
    <div className="sd-radar-wrap">
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} width="100%" style={{ display: 'block' }}>
        {[0.2, 0.4, 0.6, 0.8, 1.0].map(r => (
          <path key={r} d={gridPath(r)} fill="none" stroke="#e5e7eb" strokeWidth={1} />
        ))}
        {points.map((_, i) => {
          const tip = coord(i, 1.0)
          return <line key={i} x1={cx} y1={cy} x2={tip.x.toFixed(1)} y2={tip.y.toFixed(1)} stroke="#e5e7eb" strokeWidth={1} />
        })}
        <path d={dataPath} fill="rgba(249,115,22,0.18)" stroke="#F97316" strokeWidth={2} />
        {dataPts.map((p, i) => (
          <circle key={i} cx={p.x.toFixed(1)} cy={p.y.toFixed(1)} r={4} fill="#F97316" stroke="white" strokeWidth={1.5} />
        ))}
      </svg>
      {points.map((p, i) => {
        const pos = labelPos[i]
        return (
          <div key={i} className="sd-radar-label"
            style={{ left: `${(pos.x / SIZE * 100).toFixed(1)}%`, top: `${(pos.y / SIZE * 100).toFixed(1)}%` }}>
            <span className="sd-radar-label-name">{p.label}</span>
            <span className="sd-radar-label-score">{p.score != null ? Math.round(p.score) : '-'}</span>
          </div>
        )
      })}
    </div>
  )
}

// ── 지표 카드 ──────────────────────────────────────────────────────────────
const METRICS = [
  { key: 'ret_1m',   label: '1개월 수익률',  type: 'pct',   tip: '최근 1개월 주가 변동률' },
  { key: 'ret_3m',   label: '3개월 수익률',  type: 'pct',   tip: '최근 3개월 주가 변동률' },
  { key: 'ret_6m',   label: '6개월 수익률',  type: 'pct',   tip: '최근 6개월 주가 변동률' },
  { key: 'ret_1y',   label: '1년 수익률',    type: 'pct',   tip: '최근 1년 주가 변동률' },
  { key: 'vol_ann',  label: '연간 변동성',   type: 'pct_r', tip: '연환산 표준편차 (낮을수록 안정)' },
  { key: 'high_52w', label: '52주 최고가',   type: 'price', tip: '최근 52주 최고 종가' },
  { key: 'low_52w',  label: '52주 최저가',   type: 'price', tip: '최근 52주 최저 종가' },
]

function MetricCard({ label, value, type, tip }) {
  let display = '-', color = '#333'
  if (value != null) {
    if (type === 'pct') {
      display = `${value >= 0 ? '+' : ''}${Number(value).toFixed(2)}%`
      color = value >= 0 ? '#EA580C' : '#3B82F6'
    } else if (type === 'pct_r') {
      display = `${Number(value).toFixed(2)}%`
    } else if (type === 'price') {
      display = Number(value).toLocaleString('ko-KR') + '원'
    }
  }
  return (
    <div className="sd-feature-card" title={tip}>
      <div className="sd-feature-label">{label}</div>
      <div className="sd-feature-value" style={{ color }}>{display}</div>
    </div>
  )
}

// ── AI 분석 로딩 스피너 ────────────────────────────────────────────────────
function AnalysisSpinner() {
  return (
    <div className="sd-spinner-wrap">
      <div className="sd-spinner" />
      <p className="sd-spinner-text">분석 데이터를 준비중입니다. 잠시 기다려 주세요.</p>
    </div>
  )
}


// ── 메인 컴포넌트 ──────────────────────────────────────────────────────────
function StockDetailPage() {
  const { stockCode } = useParams()
  const navigate      = useNavigate()
  const { state }     = useLocation()

  const stockItem = state?.stockItem
  const riskTier  = state?.riskTier

  const [detail,           setDetail]           = useState(null)
  const [loading,          setLoading]          = useState(true)
  const [error,            setError]            = useState(null)
  const [scores,           setScores]           = useState(null)
  const [analysis,         setAnalysis]         = useState(null)
  const [analysisLoading,  setAnalysisLoading]  = useState(true)
  const [analysisError,    setAnalysisError]    = useState(false)
  const [analysisErrorMsg, setAnalysisErrorMsg] = useState(null)  // 디버그용 오류 상세
  const [analysisRetry,    setAnalysisRetry]    = useState(0)
  const [realtimePrice,    setRealtimePrice]    = useState(null) // 실시간 가격 데이터
  const [intradayData,     setIntradayData]     = useState(null) // 일중 차트 데이터
  const [wsStatus,         setWsStatus]         = useState(null) // WebSocket 상태 (디버그용)

  // ── WebSocket 상태 확인 (디버그용) ──────────────────────────────────────
  const checkWebSocketStatus = async () => {
    try {
      const res = await fetch('/api/stream/ws-status')
      const data = await res.json()
      setWsStatus(data)
      console.log('[WebSocket 상태]', data)
      // 백엔드 응답: single → subscribed_count / subscribed_sample, pool → total_subscribed / workers
      const subscribedCount = data.subscribed_count ?? data.total_subscribed ?? 0
      const subscribedSample = data.subscribed_sample ?? []
      const isInSample = subscribedSample.includes(stockCode)
      const sampleNote = subscribedCount > subscribedSample.length ? ` (상위 ${subscribedSample.length}개만 표시)` : ''
      alert(`WebSocket 초기화: ${data.initialized ? '성공' : '실패'}\n유형: ${data.type ?? '-'}\n구독 종목: ${subscribedCount}개\n현재 종목(${stockCode}): ${isInSample ? '구독됨' : subscribedCount > 0 ? `샘플 미포함${sampleNote}` : '미구독'}`)
    } catch (err) {
      console.error('WebSocket 상태 확인 실패:', err)
      alert('WebSocket 상태 확인 실패')
    }
  }

  // ── 테스트 가격 주입 (장 마감 시 테스트용) ────────────────────────────────
  const injectTestPrices = async () => {
    try {
      const res = await fetch(`/api/stream/test-inject?codes=${stockCode}`)
      const data = await res.json()
      console.log('[테스트 주입]', data)
      alert('10초간 테스트 가격 변동 시작 (콘솔 확인)')
    } catch (err) {
      console.error('테스트 주입 실패:', err)
      alert('테스트 주입 실패')
    }
  }

  // ── 기본 데이터 & 점수 로드 ─────────────────────────────────────────────
  useEffect(() => {
    if (!stockCode) return
    setLoading(true)
    setError(null)
    Promise.all([
      fetch(`/api/instruments/stocks/${stockCode}`).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() }),
      fetch(`/api/instruments/stocks/${stockCode}/scores`).then(r => r.json()).catch(() => null),
    ]).then(([det, sc]) => {
      setDetail(det)
      setScores(sc)
      setLoading(false)
    }).catch(err => { setError(err.message); setLoading(false) })
  }, [stockCode])

  // ── 실시간 가격 스트림 (SSE) ──────────────────────────────────────────────
  useEffect(() => {
    if (!stockCode || loading) return

    let eventSource = null
    let reconnectTimer = null
    let isActive = true

    const connect = () => {
      if (!isActive) return

      try {
        const url = `/api/stream/prices?codes=${stockCode}`
        console.log('[실시간 가격] SSE 연결 시도:', url)
        eventSource = new EventSource(url)
        
        eventSource.onopen = () => {
          console.log('[실시간 가격] SSE 연결 성공:', stockCode)
        }
        
        eventSource.onmessage = (event) => {
          try {
            const updates = JSON.parse(event.data)
            console.log('[실시간 가격] 데이터 수신:', updates)
            const priceData = updates[stockCode]
            if (priceData) {
              console.log('[실시간 가격] 가격 업데이트:', priceData)
              setRealtimePrice(priceData)
            }
          } catch (err) {
            console.warn('[실시간 가격] 파싱 오류:', err, event.data)
          }
        }

        eventSource.onerror = (err) => {
          console.warn('[실시간 가격] 연결 오류:', err)
          if (eventSource) {
            eventSource.close()
          }
          
          // 5초 후 재연결 시도
          if (isActive) {
            reconnectTimer = setTimeout(() => {
              console.log('[실시간 가격] 재연결 시도...')
              connect()
            }, 5000)
          }
        }
      } catch (err) {
        console.error('[실시간 가격] EventSource 생성 실패:', err)
      }
    }

    connect()

    return () => {
      isActive = false
      console.log('[실시간 가격] SSE 연결 종료')
      if (eventSource) {
        eventSource.close()
      }
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
      }
    }
  }, [stockCode, loading])

  // ── 일중 차트 데이터 로드 (FinanceDataReader) ─────────────────────────
  useEffect(() => {
    if (!stockCode) return
    
    const fetchIntradayData = async () => {
      try {
        const response = await fetch(`/api/v1/stocks/intraday/${stockCode}?days=5`)
        if (response.ok) {
          const data = await response.json()
          console.log('[일중 데이터] 로드 완료:', data)
          setIntradayData(data)
        } else {
          console.warn('[일중 데이터] 로드 실패:', response.status)
        }
      } catch (err) {
        console.warn('[일중 데이터] 조회 오류:', err)
      }
    }
    
    fetchIntradayData()
  }, [stockCode])


  // ── AI 분석 로드 (sessionStorage 캐시, 비동기) ─────────────────────────
  useEffect(() => {
    if (!stockCode) return
    const cacheKey = `stock_analysis_${stockCode}`

    // 재시도가 아닐 때만 캐시 사용
    if (analysisRetry === 0) {
      try {
        const raw = sessionStorage.getItem(cacheKey)
        if (raw) {
          const { data, ts } = JSON.parse(raw)
          if (Date.now() - ts < 3_600_000) { setAnalysis(data); setAnalysisLoading(false); return }
        }
      } catch {}
    }

    const investmentType = localStorage.getItem('investment_type') || '위험중립형'
    const userProfile = JSON.stringify({
      risk_tier: investmentType, grade: '3등급', horizon_years: 3,
      goal: '자산증식', deployment: '분산투자',
      monthly_contribution_krw: 300000, total_assets_krw: 10000000,
      dividend_pref_1to5: 3, account_type: '일반',
    })

    setAnalysisLoading(true)
    setAnalysisError(false)
    setAnalysisErrorMsg(null)
    setAnalysis(null)

    const controller = new AbortController()
    // cleanup에 의한 abort와 timeout에 의한 abort를 구분하는 flag
    let cleanedUp = false
    // 서버 타임아웃(420s)보다 30초 여유를 두고 클라이언트에서도 abort
    const timerId = setTimeout(() => controller.abort(), 450_000)

    fetch('/api/v1/analysis/report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      body: JSON.stringify({
        ticker: stockCode, mode: 'stock_detail',
        user_profile_json: userProfile,
        stock_item_json: stockItem ? JSON.stringify(stockItem) : '{}',
      }),
    })
      .then(async r => {
        if (cleanedUp) return   // cleanup 이후 응답은 무시
        if (!r.ok) {
          let detail = `HTTP ${r.status}`
          try { const body = await r.json(); detail = body.detail || detail } catch {}
          console.error('[AI 분석] 오류 응답:', r.status, detail)
          throw new Error(detail)
        }
        return r.json()
      })
      .then(data => {
        if (cleanedUp || !data) return   // cleanup 이후 응답은 무시
        let parsed = null
        try { parsed = JSON.parse(data.report) } catch { /* parsed stays null */ }
        // JSON 파싱 실패 또는 필수 섹션 없으면 에러로 처리
        const hasContent = parsed &&
          (parsed.investment_fit || parsed.company_analysis || parsed.industry_analysis)
        if (!hasContent) {
          console.error('[AI 분석] 응답 파싱 실패 또는 필수 섹션 없음:', data.report?.slice(0, 200))
          setAnalysisLoading(false)
          setAnalysisError(true)
          setAnalysisErrorMsg('분석 결과 형식 오류')
          return
        }
        setAnalysis(parsed)
        setAnalysisLoading(false)
        try { sessionStorage.setItem(cacheKey, JSON.stringify({ data: parsed, ts: Date.now() })) } catch {}
      })
      .catch(err => {
        if (cleanedUp) return   // cleanup abort는 에러로 처리하지 않음
        if (err.name === 'AbortError') {
          console.error('[AI 분석] 타임아웃 (450s 초과)')
          setAnalysisLoading(false)
          setAnalysisError(true)
          setAnalysisErrorMsg('분석 시간 초과')
          return
        }
        console.error('[AI 분석] fetch 오류:', err.message)
        setAnalysisLoading(false)
        setAnalysisError(true)
        setAnalysisErrorMsg(err.message)
      })

    return () => {
      cleanedUp = true   // cleanup 플래그 설정 → catch/then 핸들러가 상태 업데이트 안 함
      clearTimeout(timerId)
      controller.abort()
    }
  }, [stockCode, analysisRetry])

  if (loading) return (
    <div className="stock-detail-page">
      <div className="sd-loading">주가 데이터를 불러오는 중...</div>
    </div>
  )
  if (error || !detail) return (
    <div className="stock-detail-page">
      <div className="sd-error-box">
        <p>{error || '데이터를 불러올 수 없습니다.'}</p>
        <button onClick={() => navigate(-1)} className="sd-back-btn">← 뒤로</button>
      </div>
    </div>
  )

  // 실시간 가격 데이터가 있으면 사용, 없으면 기본 데이터 사용
  const currentPrice = realtimePrice?.current_price ?? detail.current_price
  const change = realtimePrice?.change ?? detail.change
  const changeRate = realtimePrice?.change_rate ?? detail.change_rate
  
  const isUp = (changeRate ?? 0) >= 0

  // ── 투자 원칙 적합도 데이터 ──────────────────────────────────────────────
  const fitScore = stockItem?.total_score != null
    ? Math.round(stockItem.total_score * 100)
    : analysis?.investment_fit?.fit_score != null
      ? Math.round(analysis.investment_fit.fit_score * 100)
      : null
  const fitReasons  = stockItem?.reasons ?? analysis?.investment_fit?.reason_explanations ?? []
  const fitCaution  = analysis?.investment_fit?.caution ?? null
  const fitSummary  = analysis?.investment_fit?.fit_summary
    ?? (riskTier ? `귀하의 ${riskTier} 투자 성향에 적합한 종목입니다.` : null)

  // ── 기업/산업 분석 불릿 ──────────────────────────────────────────────────
  const industryBullets = [
    ...(analysis?.industry_analysis?.current_trends ?? 
      []),
    ...(analysis?.company_analysis?.strengths ?? []).slice(0, 2),
  ]

  // ── 기업 요약 그리드 ─────────────────────────────────────────────────────
  const mcap = scores?.market_cap ? fmtMcap(scores.market_cap) : '-'
  // 산업분류: DB 섹터(확정값) 우선 → AI 분석 폴백
  const sectorLabel =
    (detail.sector && detail.sector !== '시장' ? detail.sector : null) ||
    analysis?.company_analysis?.sector ||
    analysis?.industry_analysis?.sector ||
    '-'
  // 사업영역: AI 분석의 세부 업종(industry) 우선 → DB 섹터 순으로 폴백
  const industryLabel =
    analysis?.industry_analysis?.industry ||
    (detail.sector && detail.sector !== '시장' ? detail.sector : null) ||
    analysis?.company_analysis?.sector ||
    '-'
  const companyFields = [
    { label: '기업명',   value: detail.name },
    { label: '산업분류', value: sectorLabel },
    { label: '거래소',   value: detail.exchange || '-' },
    { label: '자산유형', value: detail.asset_type || '-' },
    { label: '시가총액', value: mcap },
    { label: '사업영역', value: industryLabel },
  ]

  // ── 레이더 점수 ───────────────────────────────────────────────────────────
  const fallbackRadarPoints = fitScore != null
    ? [
      { key: 'profitability', label: '수익성', score: fitScore },
      { key: 'growth', label: '성장성', score: fitScore },
      { key: 'stability', label: '안정성', score: fitScore },
      { key: 'cashflow', label: '현금흐름', score: fitScore },
      { key: 'valuation', label: '밸류에이션', score: fitScore },
    ]
    : null

  const radarPoints =
    scores?.available && Array.isArray(scores?.radar) && scores.radar.length >= 3
      ? scores.radar
      : fallbackRadarPoints

  // ── 추천 이유 (분석 API 또는 stockItem) ─────────────────────────────────
  const recText = analysis?.page_summary
    ?? analysis?.company_analysis?.overall_company_view
    ?? (fitReasons.length > 0 ? fitReasons.join(' ') : null)

  // ── 비정형 분석 (ESG · 뉴스 · 증권사 리포트) ─────────────────────────────
  const ua = analysis?.unstructured_analysis
  const esgRisks        = ua?.esg_risks ?? null
  const esgOpportunities = ua?.esg_opportunities ?? null
  const newsSummary     = ua?.news_summary ?? null
  const reportsInsight  = ua?.reports_insight ?? null
  const hasUnstructured = esgRisks || esgOpportunities || newsSummary || reportsInsight

  return (
    <div className="stock-detail-page">
      <div className="stock-detail-container">

        <button onClick={() => navigate(-1)} className="sd-back-btn">← 추천 목록으로</button>

        {/* 디버그 버튼 (개발용 - 나중에 제거 가능) */}
        {process.env.NODE_ENV === 'development' && (
          <div style={{ display: 'flex', gap: '10px', marginBottom: '20px' }}>
            <button onClick={checkWebSocketStatus} className="sd-debug-btn">
              🔍 WebSocket 상태 확인
            </button>
            <button onClick={injectTestPrices} className="sd-debug-btn">
              🧪 테스트 가격 주입 (10초)
            </button>
          </div>
        )}

        {/* ── 1. 헤더 ────────────────────────────────────────────── */}
        <div className="stock-detail-header">
          <div className="sd-header-left">
            {stockItem?.rank && <span className="sd-rank-badge">#{stockItem.rank}</span>}
            <h1 className="stock-detail-name">{detail.name}</h1>
            <div style={{ display: 'flex', gap: 8, marginTop: 4, flexWrap: 'wrap', alignItems: 'center' }}>
              <span className="sd-ticker">{detail.stock_code}</span>
              <span className="sd-market-badge">{detail.exchange}</span>
              {sectorLabel && sectorLabel !== '-' && (
                <span className="sd-sector-badge">{sectorLabel}</span>
              )}
              {riskTier && <span className="sd-risk-tier">{riskTier}</span>}
            </div>
          </div>
          <div className="sd-price-box">
            <div className="sd-current-price">
              {fmtPrice(currentPrice)}
              {realtimePrice && (
                <span className="sd-realtime-badge" title="실시간 업데이트">🔴 LIVE</span>
              )}
            </div>
            {change != null && (
              <div className="sd-change-badge" style={{ color: isUp ? '#EA580C' : '#3B82F6' }}>
                {isUp ? '▲' : '▼'} {Math.abs(change).toLocaleString('ko-KR')}원
                &nbsp;({changeRate >= 0 ? '+' : ''}{Number(changeRate).toFixed(2)}%)
              </div>
            )}
            <div className="sd-price-date">{detail.price_date} 기준</div>
          </div>
        </div>

        {/* ── 2. 일중 차트 (FinanceDataReader) ──────────────────── */}
        {intradayData && intradayData.data && intradayData.data.length > 0 && (
          <section className="sd-section">
            <h2 className="sd-section-heading">📈 최근 가격 추이 (FinanceDataReader)</h2>
            <IntradayChart data={intradayData} />
          </section>
        )}

        {/* ── 3. 주가 차트 (최근 30일) ──────────────────────────── */}
        {detail.price_history.length > 1 && (
          <section className="sd-section">
            <h2 className="sd-section-heading">주가 차트 (최근 30일)</h2>
            <CandlestickChart data={detail.price_history} days={30} />
          </section>
        )}


        {/* ── 3. 내 투자 원칙 적합도 분석 ───────────────────────── */}
        {(fitScore != null || fitSummary) && (
          <section className="investment-fit-section">
            <h2 className="section-heading">내 투자 원칙 적합도 분석</h2>
            <div className="fit-container">
              {fitScore != null && (
                <div className="fit-score-box">
                  <div className="fit-score">{fitScore}</div>
                  <div className="fit-score-label">적합도 점수</div>
                </div>
              )}
              <div className="fit-details">
                {fitSummary && <p className="fit-summary">{fitSummary}</p>}
                {fitReasons.length > 0 && (
                  <ul className="fit-list">
                    {fitReasons.slice(0, 3).map((r, i) => (
                      <li key={i}>✓ {r}</li>
                    ))}
                    {fitCaution && <li>△ {fitCaution}</li>}
                  </ul>
                )}
              </div>
            </div>
          </section>
        )}

        {/* ── 4. 기업 요약 ──────────────────────────────────────── */}
        <section className="company-info-section">
          <h2 className="section-heading">기업 요약</h2>
          <div className="company-info-grid">
            {companyFields.map(({ label, value }) => (
              <div key={label} className="info-item">
                <span className="info-label">{label}</span>
                <span className="info-value">{value}</span>
              </div>
            ))}
          </div>
        </section>

        {/* ── 5. 기업/산업 분석 ─────────────────────────────────── */}
        <section className="industry-analysis-section">
          <h2 className="section-heading">기업/산업 분석</h2>
          {analysisLoading && industryBullets.length === 0
            ? <AnalysisSpinner />
            : industryBullets.length > 0
              ? (
                <ul className="analysis-list">
                  {industryBullets.map((b, i) => <li key={i}>{b}</li>)}
                </ul>
              )
              : analysisError
                ? (
                  <p className="sd-analysis-pending">
                    AI 분석을 불러오지 못했습니다.{analysisErrorMsg && <span style={{fontSize:'0.8em',color:'#999',marginLeft:6}}>[{analysisErrorMsg}]</span>}
                    <button className="sd-retry-btn" onClick={() => {
                      setAnalysisError(false)
                      setAnalysisLoading(true)
                      setAnalysisRetry(r => r + 1)
                    }}>🔄 다시 시도</button>
                  </p>
                )
                : null
          }
        </section>

        {/* ── 5.5. ESG · 뉴스 · 증권사 리포트 인사이트 ─────────── */}
        {!analysisLoading && hasUnstructured && (
          <section className="sd-section">
            <h2 className="sd-section-heading">ESG · 뉴스 · 리포트 인사이트</h2>
            <div className="unstructured-grid">
              {(esgRisks || esgOpportunities) && (
                <div className="unstructured-card">
                  <h3 className="unstructured-card-title">🌱 ESG 분석</h3>
                  {esgRisks && (
                    <div className="unstructured-item">
                      <span className="unstr-label unstr-risk">리스크</span>
                      <p>{esgRisks}</p>
                    </div>
                  )}
                  {esgOpportunities && (
                    <div className="unstructured-item">
                      <span className="unstr-label unstr-opp">기대요인</span>
                      <p>{esgOpportunities}</p>
                    </div>
                  )}
                </div>
              )}
              {newsSummary && (
                <div className="unstructured-card">
                  <h3 className="unstructured-card-title">📰 최신 뉴스</h3>
                  <p>{newsSummary}</p>
                </div>
              )}
              {reportsInsight && (
                <div className="unstructured-card">
                  <h3 className="unstructured-card-title">📑 증권사 리포트</h3>
                  <p>{reportsInsight}</p>
                </div>
              )}
            </div>
          </section>
        )}

        {/* ── 6. 종합 분석 (레이더 차트) ────────────────────────── */}
        <section className="comprehensive-analysis-section">
          <h2 className="section-heading">종합 분석</h2>
          {radarPoints
            ? <RadarChart points={radarPoints} />
            : <p className="sd-analysis-pending">재무 점수 데이터가 없습니다.</p>
          }
        </section>

        {/* ── 7. 추천 이유 / AI 분석 요약 ─────────────────────── */}
        <section className="recommendation-section">
          <h2 className="section-heading">{stockItem ? '추천 이유' : 'AI 분석 요약'}</h2>
          {analysisLoading && !recText
            ? <AnalysisSpinner />
            : recText
              ? (
                <div className="recommendation-box">
                  <p className="recommendation-detail">{recText}</p>
                </div>
              )
              : analysisError
                ? (
                  <p className="sd-analysis-pending">
                    AI 분석을 불러오지 못했습니다.{analysisErrorMsg && <span style={{fontSize:'0.8em',color:'#999',marginLeft:6}}>[{analysisErrorMsg}]</span>}
                    <button className="sd-retry-btn" onClick={() => {
                      setAnalysisError(false)
                      setAnalysisLoading(true)
                      setAnalysisRetry(r => r + 1)
                    }}>🔄 다시 시도</button>
                  </p>
                )
                : null
          }
        </section>

        {/* ── 주요 지표 ──────────────────────────────────────────── */}
        <section className="sd-section">
          <h2 className="sd-section-heading">주요 지표</h2>
          <div className="sd-features-grid">
            {METRICS.map(m => (
              <MetricCard key={m.key} label={m.label} value={detail[m.key]} type={m.type} tip={m.tip} />
            ))}
          </div>
        </section>

        {/* ── 투자 유의사항 ─────────────────────────────────────── */}
        <section className="sd-section sd-notice-section">
          <h2 className="sd-section-heading">투자 유의사항</h2>
          <ul className="sd-notice-list">
            <li>본 데이터는 참고 정보이며, 투자 손익 책임은 투자자 본인에게 있습니다.</li>
            <li>과거 수익률이 미래 수익을 보장하지 않습니다.</li>
          </ul>
        </section>

      </div>
    </div>
  )
}

export default StockDetailPage