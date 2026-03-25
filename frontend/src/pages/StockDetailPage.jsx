import React, { useState, useEffect } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import './StockDetailPage.css'
import { TermText, DynamicTermProvider } from '../components/TermTooltip'
import AnalysisProgressBar from '../components/AnalysisProgressBar'

// ── AI 텍스트 내 1인칭 → 이름으로 치환 ─────────────────────────────────────
const personalizeText = (text, name) => {
  if (!text || !name) return text
  return text
    .replace(/나에게/g, `${name}님에게`)
    .replace(/나의\s/g, `${name}님의 `)
    .replace(/내\s/g, `${name}님의 `)
    .replace(/내가/g, `${name}님이`)
    .replace(/귀하의/g, `${name}님의`)
    .replace(/귀하에게/g, `${name}님에게`)
}

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
  const W = 800, H = 180, padT = 12, padB = 28, padL = 10, padR = 10
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
        <span className={`sd-intraday-change ${isUp ? 'up' : 'down'}`} style={{ marginLeft: 'auto' }}>
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
  const [tooltip, setTooltip] = useState(null)

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
    <div className="sd-candle-wrap" style={{ position: 'relative' }}>
      {tooltip && (
        <div
          className="sd-candle-tooltip"
          style={{
            left: tooltip.pct > 70 ? 'auto' : `${tooltip.pct}%`,
            right: tooltip.pct > 70 ? `${100 - tooltip.pct}%` : 'auto',
          }}
        >
          <div className="sd-candle-tooltip-date">{tooltip.d.date}</div>
          <div className="sd-candle-tooltip-row"><span>시가</span><span>{(tooltip.d.open ?? '-').toLocaleString?.('ko-KR')}원</span></div>
          <div className="sd-candle-tooltip-row"><span>고가</span><span className="up">{(tooltip.d.high ?? '-').toLocaleString?.('ko-KR')}원</span></div>
          <div className="sd-candle-tooltip-row"><span>저가</span><span className="down">{(tooltip.d.low ?? '-').toLocaleString?.('ko-KR')}원</span></div>
          <div className="sd-candle-tooltip-row"><span>종가</span><span>{(tooltip.d.close ?? '-').toLocaleString?.('ko-KR')}원</span></div>
        </div>
      )}
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
          const pct = ((x - padL) / plotW) * 100
          return (
            <g key={i}
              onMouseEnter={() => setTooltip({ d, pct })}
              onMouseLeave={() => setTooltip(null)}
              style={{ cursor: 'crosshair' }}
            >
              <rect x={x - step / 2} y={padT} width={step} height={plotH} fill="transparent" />
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

// ── 레이더 지표별 산정 설명 ─────────────────────────────────────────────────
const RADAR_TOOLTIPS = {
  profitability: {
    title: '수익성',
    desc: '기업이 얼마나 효율적으로 이익을 창출하는지 측정합니다.',
    items: [
      'ROE (자기자본이익률): 주주 자본 대비 순이익 비율',
      'ROA (총자산이익률): 보유 자산 대비 순이익 비율',
      '영업이익률: 매출 대비 영업이익 비율',
      '순이익률: 매출 대비 최종 순이익 비율',
    ],
  },
  growth: {
    title: '성장성',
    desc: '기업의 매출·이익이 얼마나 빠르게 성장하고 있는지 측정합니다.',
    items: [
      '매출 성장률: 전년 대비 매출액 증가율',
      '영업이익 성장률: 전년 대비 영업이익 증가율',
      'EPS 성장률: 주당순이익 증가율',
    ],
  },
  stability: {
    title: '안정성',
    desc: '재무 구조의 건전성과 채무 상환 능력을 측정합니다.',
    items: [
      '부채비율: 총부채 ÷ 자기자본 (낮을수록 안전)',
      '유동비율: 유동자산 ÷ 유동부채 (높을수록 단기 안전)',
      '이자보상배율: 영업이익 ÷ 이자비용 (높을수록 채무 여유)',
    ],
  },
  cashflow: {
    title: '현금흐름',
    desc: '실제 현금 창출 능력과 투자·재무 활동의 건전성을 측정합니다.',
    items: [
      '영업현금흐름: 본업에서 벌어들이는 현금',
      'FCF (잉여현금흐름): 영업현금흐름 − 설비투자',
      '현금흐름 대비 부채 비율: 채무 상환 여력',
    ],
  },
  valuation: {
    title: '밸류에이션',
    desc: '현재 주가가 기업 가치 대비 얼마나 저평가·고평가됐는지 측정합니다.',
    items: [
      'PER (주가수익비율): 주가 ÷ EPS (낮을수록 저평가)',
      'PBR (주가순자산비율): 주가 ÷ BPS (낮을수록 저평가)',
      'EV/EBITDA: 기업가치 ÷ 세전영업이익 (낮을수록 저평가)',
    ],
  },
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
  const dataPts  = points.map((p, i) => coord(i, p.score != null ? Math.min(p.score, 100) / 100 : 0.08))
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
          <circle key={i} cx={p.x.toFixed(1)} cy={p.y.toFixed(1)} r={4}
            fill={points[i].score != null ? "#F97316" : "#d1d5db"}
            stroke="white" strokeWidth={1.5} />
        ))}
      </svg>
      {points.map((p, i) => {
        const pos = labelPos[i]
        const tip = RADAR_TOOLTIPS[p.key]
        return (
          <div key={i} className="sd-radar-label"
            style={{ left: `${(pos.x / SIZE * 100).toFixed(1)}%`, top: `${(pos.y / SIZE * 100).toFixed(1)}%` }}>
            <span className="sd-radar-label-name">{p.label}</span>
            <span className="sd-radar-label-score" style={p.score == null ? { color: '#9ca3af' } : undefined}>
              {p.score != null ? Math.round(p.score) : '-'}
            </span>
            {tip && (
              <div className="sd-radar-tooltip">
                <p className="sd-radar-tooltip-desc">{tip.desc}</p>
                <ul className="sd-radar-tooltip-items">
                  {tip.items.map((item, idx) => <li key={idx}>{item}</li>)}
                </ul>
              </div>
            )}
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

// ── 스켈레톤 로딩 ──────────────────────────────────────────────────────────
function Skeleton({ rows = 3 }) {
  return (
    <div className="sd-skeleton">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="sd-skeleton-row" style={{ width: `${85 - i * 10}%` }} />
      ))}
    </div>
  )
}

// ── 메인 컴포넌트 ──────────────────────────────────────────────────────────
function StockDetailPage() {
  const { stockCode } = useParams()
  const navigate      = useNavigate()
  const { state }     = useLocation()

  const stockItem = state?.stockItem
  const userName  = localStorage.getItem('name') || '회원'
  const riskTier  = state?.riskTier

  const [chartDays,        setChartDays]        = useState(30)
  const [detail,           setDetail]           = useState(null)
  const [loading,          setLoading]          = useState(true)
  const [error,            setError]            = useState(null)
  const [scores,           setScores]           = useState(null)
  const [analysis,         setAnalysis]         = useState(null)
  const [analysisLoading,  setAnalysisLoading]  = useState(false)
  const [realtimePrice,    setRealtimePrice]    = useState(null) // 실시간 가격 데이터
  const [intradayData,     setIntradayData]     = useState(null) // 일중 차트 데이터
  const [wsStatus,         setWsStatus]         = useState(null) // WebSocket 상태 (디버그용)
  const [reportItems,      setReportItems]      = useState(null) // 증권사 리포트 직접 조회 결과
  const [reportLoading,    setReportLoading]    = useState(false)
  const [dynamicTerms,     setDynamicTerms]     = useState({})   // LLM 동적 용어 사전

  // ── WebSocket 상태 확인 (디버그용) ──────────────────────────────────────
  const checkWebSocketStatus = async () => {
    try {
      const res = await fetch('/api/stream/ws-status')
      const data = await res.json()
      setWsStatus(data)
      console.log('[WebSocket 상태]', data)
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
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 30000)
    Promise.all([
      fetch(`/api/instruments/stocks/${stockCode}`, { signal: controller.signal }).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() }),
      fetch(`/api/instruments/stocks/${stockCode}/scores`, { signal: controller.signal }).then(r => r.json()).catch(() => null),
    ]).then(([det, sc]) => {
      clearTimeout(timer)
      setDetail(det)
      setScores(sc)
      setLoading(false)
    }).catch(err => {
      clearTimeout(timer)
      setError(err.name === 'AbortError' ? '데이터 로딩 시간이 초과되었습니다. 다시 시도해 주세요.' : err.message)
      setLoading(false)
    })
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


  // ── 증권사 리포트 직접 조회 (ChromaDB, 빠른 로드) ────────────────────────
  useEffect(() => {
    if (!stockCode) return
    setReportLoading(true)
    fetch(`/api/v1/reports/insights/${stockCode}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data && data.items && data.items.length > 0) setReportItems(data.items)
        setReportLoading(false)
      })
      .catch(() => setReportLoading(false))
  }, [stockCode])


  // ── AI 분석 로드 (sessionStorage 캐시, 비동기) ─────────────────────────
  useEffect(() => {
    if (!stockCode) return

    // 종목 전환 시 이전 분석 즉시 초기화 (잘못된 내용이 잠깐 보이는 것 방지)
    setAnalysis(null)

    const cacheKey = `stock_analysis_v2_${stockCode}`
    try {
      const raw = sessionStorage.getItem(cacheKey)
      if (raw) {
        const { data, ts } = JSON.parse(raw)
        if (Date.now() - ts < 3_600_000) { setAnalysis(data); return }
      }
    } catch {}

    const investmentType = localStorage.getItem('investment_type') || '위험중립형'
    const userProfile = JSON.stringify({
      risk_tier: investmentType, grade: '3등급', horizon_years: 3,
      goal: '자산증식', deployment: '분산투자',
      monthly_contribution_krw: 300000, total_assets_krw: 10000000,
      dividend_pref_1to5: 3, account_type: '일반',
    })

    setAnalysisLoading(true)
    fetch('/api/v1/analysis/report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ticker: stockCode, mode: 'stock_detail',
        user_profile_json: userProfile,
        stock_item_json: stockItem ? JSON.stringify(stockItem) : '{}',
      }),
    })
      .then(r => r.json())
      .then(data => {
        let parsed = null
        try { parsed = JSON.parse(data.report) } catch { parsed = { raw: data.report } }
        setAnalysis(parsed)
        setAnalysisLoading(false)
        try { sessionStorage.setItem(cacheKey, JSON.stringify({ data: parsed, ts: Date.now() })) } catch {}

        // ── LLM 동적 용어 추출 ──────────────────────────────────────────
        const texts = [
          ...(parsed?.industry_analysis?.current_trends ?? []),
          ...(parsed?.company_analysis?.strengths ?? []),
          parsed?.page_summary,
          parsed?.company_analysis?.overall_company_view,
          parsed?.investment_fit?.fit_summary,
          ...(parsed?.investment_fit?.reason_explanations ?? []),
          parsed?.investment_fit?.caution,
          parsed?.industry_analysis?.industry,
          parsed?.company_analysis?.sector,
        ].filter(Boolean)
        const combinedText = texts.join('\n')
        if (combinedText.length > 30) {
          fetch('/api/v1/terms/extract', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: combinedText }),
          })
            .then(r => r.json())
            .then(d => setDynamicTerms(d.terms || {}))
            .catch(() => {})
        }
      })
      .catch(() => setAnalysisLoading(false))
  }, [stockCode])

  if (loading) return (
    <div className="stock-detail-page">
      <div className="sd-loading">
        <div className="sd-spinner" />
        <p>주가 데이터를 불러오는 중...</p>
      </div>
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
    ...(analysis?.industry_analysis?.current_trends ?? []),
    ...(analysis?.company_analysis?.strengths ?? []).slice(0, 2),
  ]

  // ── 기업 요약 그리드 ─────────────────────────────────────────────────────
  const mcap = scores?.market_cap ? fmtMcap(scores.market_cap) : '-'
  // 산업분류: AI 분석의 섹터 → DB 섹터(비의미 값 제외) 순으로 폴백
  const sectorLabel =
    analysis?.company_analysis?.sector ||
    analysis?.industry_analysis?.sector ||
    (detail.sector && detail.sector !== '시장' ? detail.sector : null) ||
    '-'
  // 사업영역: AI 분석의 세부 업종 → 섹터 순으로 폴백 (줄글 제외)
  const industryLabel =
    analysis?.industry_analysis?.industry ||
    analysis?.company_analysis?.sector ||
    analysis?.industry_analysis?.sector ||
    (detail.sector && detail.sector !== '시장' ? detail.sector : null) ||
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
  const radarPoints = scores?.available ? scores.radar : null

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
  const hasUnstructured = esgRisks || esgOpportunities || newsSummary || reportsInsight || (reportItems && reportItems.length > 0)


  return (
    <DynamicTermProvider extraDict={dynamicTerms}>
    <div className="stock-detail-page">
      <div className="stock-detail-container">

        <button onClick={() => navigate(-1)} className="sd-back-btn">← 추천 목록으로</button>

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
            <h2 className="sd-section-heading">최근 가격 추이 (5D)</h2>
            <IntradayChart data={intradayData} />
          </section>
        )}

        {/* ── 3. 주가 차트 ──────────────────────────────────────── */}
        {detail.price_history.length > 1 && (
          <section className="sd-section">
            <div className="sd-chart-header">
              <h2 className="sd-section-heading" style={{ margin: 0, borderBottom: 'none', paddingBottom: 0 }}>주가 차트</h2>
              <div className="sd-chart-tabs">
                {[
                  { label: '1W', days: 7 },
                  { label: '1M', days: 30 },
                  { label: '3M', days: 90 },
                  { label: '6M', days: 180 },
                  { label: '1Y', days: 365 },
                ].map(({ label, days }) => (
                  <button
                    key={days}
                    className={`sd-chart-tab${chartDays === days ? ' active' : ''}`}
                    onClick={() => setChartDays(days)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <CandlestickChart data={detail.price_history} days={chartDays} />
          </section>
        )}

        {/* ── 3. 내 투자 원칙 적합도 분석 ───────────────────────── */}
        {(fitScore != null || fitSummary) && (
          <section className="investment-fit-section">
            <h2 className="section-heading">내 투자 원칙 적합도 분석</h2>
            <div className="fit-container">
              <div className="fit-details">
                <div className="fit-metrics">
                  {detail.ret_1m != null && (
                    <span className={`fit-metric-chip ${detail.ret_1m >= 0 ? 'up' : 'down'}`}>
                      1개월 {detail.ret_1m >= 0 ? '+' : ''}{Number(detail.ret_1m).toFixed(1)}%
                    </span>
                  )}
                  {detail.ret_3m != null && (
                    <span className={`fit-metric-chip ${detail.ret_3m >= 0 ? 'up' : 'down'}`}>
                      3개월 {detail.ret_3m >= 0 ? '+' : ''}{Number(detail.ret_3m).toFixed(1)}%
                    </span>
                  )}
                  {detail.ret_1y != null && (
                    <span className={`fit-metric-chip ${detail.ret_1y >= 0 ? 'up' : 'down'}`}>
                      1년 {detail.ret_1y >= 0 ? '+' : ''}{Number(detail.ret_1y).toFixed(1)}%
                    </span>
                  )}
                  {detail.vol_ann != null && (
                    <span className="fit-metric-chip neutral">
                      변동성 {Number(detail.vol_ann).toFixed(1)}%
                    </span>
                  )}
                  {detail.high_52w != null && (
                    <span className="fit-metric-chip neutral">
                      52주 최고 {Number(detail.high_52w).toLocaleString('ko-KR')}원
                    </span>
                  )}
                </div>
                <p className="fit-summary">
                  {detail.name}은(는) {userName}님의 {riskTier ?? '투자'} 성향에 맞는 주식으로 보입니다.
                  {fitSummary ? ` ${fitSummary.replace(/^[^.]+\.\s*/, '')}` : ''}
                </p>
                <ul className="fit-list">
                  {fitReasons.slice(0, 3).map((r, i) => (
                    <li key={i}>✓ {personalizeText(r, userName)}</li>
                  ))}
                  {newsSummary && (
                    <li>✓ {personalizeText(newsSummary.split('.')[0], userName)}.</li>
                  )}
                  {reportsInsight && (
                    <li>✓ {personalizeText(reportsInsight.split('.')[0], userName)}.</li>
                  )}
                  {!reportsInsight && reportItems?.[0] && (
                    <li>✓ {reportItems[0].brokerage} 리포트에 따르면 {personalizeText(reportItems[0].title, userName)}입니다.</li>
                  )}
                  {fitCaution && <li className="fit-caution">△ {personalizeText(fitCaution, userName)}</li>}
                </ul>
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
                <span className="info-value"><TermText text={String(value)} /></span>
              </div>
            ))}
          </div>
        </section>

        {/* ── 5. 기업/산업 분석 ─────────────────────────────────── */}
        <section className="industry-analysis-section">
          <h2 className="section-heading">기업/산업 분석</h2>
          {analysisLoading && industryBullets.length === 0
            ? <AnalysisProgressBar loading={analysisLoading} />
            : industryBullets.length > 0
              ? (
                <ul className="analysis-list">
                  {industryBullets.map((b, i) => (
                    <li key={i}><TermText text={b} /></li>
                  ))}
                </ul>
              )
              : !analysisLoading && (
                <p className="sd-analysis-pending">AI 분석 데이터를 불러오는 중입니다. 잠시 후 페이지를 새로고침해 주세요.</p>
              )
          }
        </section>

        {/* ── 5.5. ESG · 뉴스 · 증권사 리포트 인사이트 ─────────── */}
        {hasUnstructured && (
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
              {/* 증권사 리포트: 직접 조회(reportItems) 우선, AI 요약(reportsInsight) 보조 */}
              {(reportItems && reportItems.length > 0) ? (
                <div className="unstructured-card">
                  <h3 className="unstructured-card-title">📑 증권사 리포트</h3>
                  {reportsInsight && <p className="reports-ai-summary">{reportsInsight}</p>}
                  <div className="reports-list">
                    {reportItems.map((item, idx) => (
                      <div key={idx} className="report-item">
                        <div className="report-item-meta">
                          <span className="report-brokerage">{item.brokerage}</span>
                          <span className="report-date">{item.date}</span>
                          {item.pdf_url && (
                            <a
                              href={item.pdf_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="report-pdf-btn"
                            >
                              📄 원문 보기
                            </a>
                          )}
                        </div>
                        <p className="report-title">{item.title}</p>
                        <p className="report-content">{item.content}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : reportsInsight ? (
                <div className="unstructured-card">
                  <h3 className="unstructured-card-title">📑 증권사 리포트</h3>
                  <p>{reportsInsight}</p>
                </div>
              ) : null}
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

        {/* ── 7. 추천 이유 ──────────────────────────────────────── */}
        {(recText || analysisLoading) && (
          <section className="recommendation-section">
            <h2 className="section-heading">추천 이유</h2>
            {analysisLoading && !recText
              ? <p className="sd-analysis-pending" style={{ fontSize: 13, color: '#9ca3af' }}>기업/산업 분석이 완료되면 표시됩니다.</p>
              : recText && (
                <div className="recommendation-box">
                  <p className="recommendation-detail"><TermText text={recText} /></p>
                </div>
              )
            }
          </section>
        )}

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
    </DynamicTermProvider>
  )
}

export default StockDetailPage