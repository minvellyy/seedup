import React, { useState, useRef, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import html2canvas from 'html2canvas'
import { jsPDF } from 'jspdf'
import { useAuth } from '../contexts/AuthContext'
import AnalysisProgressBar from '../components/AnalysisProgressBar'
import './PortfolioDetailPage.css'

const COLOR_PALETTE = [
  '#C2410C', '#EA580C', '#F97316', '#FB923C',
  '#FDBA74', '#FED7AA', '#FFEDD5', '#FFF4E6',
]

function isLightColor(hex) {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.55
}

function DonutChart({ items, centerAmount, navigate, riskData }) {
  const [hovered, setHovered] = React.useState(null)
  const [tooltipPos, setTooltipPos] = React.useState({ x: 0, y: 0 })
  const wrapRef = React.useRef(null)

  const hoveredRisk = hovered && riskData
    ? riskData.find(r => r.ticker === hovered)
    : null

  const handleMouseMove = (e) => {
    if (!wrapRef.current) return
    const rect = wrapRef.current.getBoundingClientRect()
    setTooltipPos({ x: e.clientX - rect.left, y: e.clientY - rect.top })
  }
  const size = 300
  const cx = size / 2
  const cy = size / 2
  const r = 105
  const strokeWidth = 50
  const circumference = 2 * Math.PI * r
  let cumulative = 0
  const segments = items.map((item, idx) => {
    const length = (item.weight_pct / 100) * circumference
    const dashOffset = circumference - cumulative
    const midAngleDeg = ((cumulative + length / 2) / circumference) * 360 - 90
    const midAngleRad = (midAngleDeg * Math.PI) / 180
    const lx = cx + r * Math.cos(midAngleRad)
    const ly = cy + r * Math.sin(midAngleRad)
    cumulative += length
    return { ...item, length, dashOffset, color: COLOR_PALETTE[idx % COLOR_PALETTE.length], lx, ly }
  })
  const centerLabel = centerAmount == null ? '-'
    : centerAmount >= 100_000_000
      ? `${(centerAmount / 100_000_000).toFixed(0)}억원`
      : `${(centerAmount / 10_000).toFixed(0)}만원`

  return (
    <div className="pd-donut-wrap" ref={wrapRef} onMouseMove={handleMouseMove}>
      {hoveredRisk && (
        <div className="pd-donut-tooltip" style={{ left: tooltipPos.x + 14, top: tooltipPos.y - 10 }}>
          <span className="pd-donut-tooltip-name">{hoveredRisk.name}</span>
          <span className="pd-donut-tooltip-text">{hoveredRisk.risk_text}</span>
        </div>
      )}
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ overflow: 'visible' }}>
        {segments.map((seg) => {
          const isActive = hovered === seg.ticker
          const isDimmed = hovered !== null && !isActive
          return (
            <circle
              key={seg.ticker}
              cx={cx} cy={cy} r={r}
              fill="none"
              stroke={seg.color}
              strokeWidth={isActive ? strokeWidth + 8 : strokeWidth}
              strokeDasharray={`${seg.length} ${circumference - seg.length}`}
              strokeDashoffset={seg.dashOffset}
              transform={`rotate(-90 ${cx} ${cy})`}
              opacity={isDimmed ? 0.3 : 1}
              style={{ cursor: 'pointer', transition: 'all 0.2s ease' }}
              onMouseEnter={() => setHovered(seg.ticker)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => navigate(`/stock/${seg.ticker}`)}
            />
          )
        })}
        {segments.map((seg) => seg.weight_pct >= 5 && (
          <text
            key={`lbl-${seg.ticker}`}
            x={seg.lx} y={seg.ly}
            textAnchor="middle" dominantBaseline="middle"
            fontSize="11" fontWeight="700"
            fill={isLightColor(seg.color) ? '#1e293b' : '#ffffff'}
            opacity={hovered !== null && hovered !== seg.ticker ? 0.3 : 1}
            style={{ pointerEvents: 'none', transition: 'opacity 0.2s ease' }}
          >
            {seg.weight_pct.toFixed(0)}%
          </text>
        ))}
        <text x={cx} y={cy - 10} textAnchor="middle" fontSize="13" fill="#94a3b8">가용금액</text>
        <text x={cx} y={cy + 14} textAnchor="middle" fontSize="20" fontWeight="800" fill="#1e293b">{centerLabel}</text>
      </svg>
      <div className="pd-donut-legend">
        {items.map((item, idx) => {
          const isActive = hovered === item.ticker
          const isDimmed = hovered !== null && !isActive
          return (
          <div
            key={item.ticker}
            className="pd-donut-legend-item"
            style={{
              opacity: isDimmed ? 0.35 : 1,
              fontWeight: isActive ? 700 : 400,
              transform: isActive ? 'translateX(6px)' : 'none',
              transition: 'all 0.2s ease',
              cursor: 'default',
            }}
            onMouseEnter={() => setHovered(item.ticker)}
            onMouseLeave={() => setHovered(null)}
            onClick={() => navigate(`/stock/${item.ticker}`)}
          >
            <span className="pd-donut-dot" style={{ background: COLOR_PALETTE[idx % COLOR_PALETTE.length], transform: isActive ? 'scale(1.3)' : 'scale(1)', transition: 'transform 0.2s ease' }} />
            <span className="pd-donut-name">{item.name}</span>
            <span className="pd-donut-pct">{item.weight_pct.toFixed(1)}%</span>
          </div>
        )
        })}
      </div>
    </div>
  )
}

const fmtNum = (v) =>
  v == null ? '-' : new Intl.NumberFormat('ko-KR').format(Math.round(v))
const fmtPct = (v, plus = true) =>
  v == null ? '-' : `${plus && v >= 0 ? '+' : ''}${v.toFixed(1)}%`

const TIER_INFO = {
  '안정형':    { icon: '🛡️', summary: '원금 보존을 최우선으로, 안전하게 자산을 지키는 포트폴리오입니다.', desc: '자산을 안전하게 보관하면서 소폭의 수익을 추구하는', riskNote: '이 포트폴리오는 가장 보수적인 방식으로, 큰 수익보다 원금 보존을 최우선으로 합니다. 시장 충격에도 비교적 안정적으로 자산을 지킬 수 있도록 설계되었습니다.' },
  '안정추구형': { icon: '🛡️', summary: '낮은 변동성으로 꾸준히 자산을 불려가는 안정형 포트폴리오입니다.', desc: '원금 손실을 최소화하면서 안정적인 수익을 추구하는', riskNote: '변동성이 낮은 종목 위주로 구성하여 큰 손실 없이 꾸준한 자산 성장을 목표로 합니다. 시장이 흔들릴 때도 비교적 안정적으로 자산을 지킬 수 있도록 설계되었습니다.' },
  '위험중립형': { icon: '⚖️', summary: '안정성과 수익 가능성을 균형 있게 담은 포트폴리오입니다.', desc: '안정성과 수익 가능성을 균형 있게 추구하는', riskNote: '수익과 안전성을 균형 있게 배분하였습니다. 시장 전체가 하락할 때 일부 손실이 발생할 수 있지만, 시장이 회복되면 함께 상승하는 구조입니다.' },
  '적극투자형': { icon: '📈', summary: '성장 가능성 높은 종목에 집중해 높은 수익을 노리는 포트폴리오입니다.', desc: '높은 수익을 위해 일정 수준의 위험을 감수할 준비가 된', riskNote: '성장주 비중이 높아 시장 상황에 따라 수익률 변동이 클 수 있습니다. 단기 등락에 흔들리지 않고 중장기 관점으로 보유하는 것이 중요합니다.' },
  '공격투자형': { icon: '🚀', summary: '강한 상승 모멘텀 종목으로 구성해 최대 수익을 추구하는 포트폴리오입니다.', desc: '높은 성장 가능성을 위해 단기 변동성을 기꺼이 감수하는', riskNote: '변동성이 높아 단기적으로 큰 등락이 있을 수 있습니다. 고수익을 기대하는 만큼 그에 상응하는 손실 가능성도 존재하므로, 최소 1년 이상의 장기 보유를 권장합니다.' },
}

const INVEST_GOAL_LABEL = {
  '노후 준비': '노후를 위한 자산 형성', '은퇴 준비': '노후를 위한 자산 형성',
  '주택 마련': '내 집 마련을 위한 목돈',  '집 구입': '내 집 마련을 위한 목돈',
  '자산 증식': '자산을 빠르게 불려나가기', '목돈 마련': '목돈 마련',
  '여유 자금 운용': '여유 자금의 효율적 운용', '자녀 교육': '자녀 교육 자금 마련',
}

function buildRecommendationReason({ risk_tier, monte_carlo_1y, portfolio_items = [], quant_signals, survey_context = {} }) {
  const info = TIER_INFO[risk_tier] || { icon: '📊', desc: '투자자 성향에 맞게 구성된', riskNote: '시장 상황에 따라 수익률은 달라질 수 있으니, 분산 투자의 원칙을 지켜주세요.' }
  const topItems = [...portfolio_items].sort((a, b) => b.weight_pct - a.weight_pct).slice(0, 2)
  const top2Names = topItems.map(i => i.name)

  // 설문 데이터 추출
  const goal = survey_context.INVEST_GOAL
  const goalLabel = goal ? (INVEST_GOAL_LABEL[goal] || goal) : null
  const horizon = survey_context.TARGET_HORIZON
  const contribType = survey_context.CONTRIBUTION_TYPE  // LUMP_SUM | DCA
  const lumpAmt = survey_context.LUMP_SUM_AMOUNT ? parseInt(survey_context.LUMP_SUM_AMOUNT, 10) : null
  const monthlyAmt = survey_context.MONTHLY_AMOUNT ? parseInt(survey_context.MONTHLY_AMOUNT, 10) : null
  const dividendPref = survey_context.DIVIDEND_PREF  // HIGH | MID | LOW
  const maxHoldings = survey_context.MAX_HOLDINGS ? parseInt(survey_context.MAX_HOLDINGS, 10) : null

  const fmtKrw = (n) => n >= 100_000_000
    ? `${(n / 100_000_000).toFixed(0)}억 원`
    : `${(n / 10_000).toFixed(0)}만 원`

  const paras = []

  // ① 포트폴리오 소개 — 설문 목표·기간 반영
  {
    const introParts = []
    if (goalLabel && horizon) {
      introParts.push(
        `설문에서 `, { b: goalLabel }, `을 목표로, `, { b: horizon }, `을 목표 시점으로 답해주셨습니다. `,
        `이 응답을 바탕으로 `, { b: risk_tier }, ` 성향에 맞는 포트폴리오를 구성하였습니다.`,
      )
    } else if (goalLabel) {
      introParts.push(
        `설문에서 `, { b: goalLabel }, `을 목표로 설정하셨습니다. `,
        `이를 반영해 `, { b: risk_tier }, ` 성향에 맞는 포트폴리오를 구성하였습니다.`,
      )
    } else if (horizon) {
      introParts.push(
        `설문에서 목표 시점을 `, { b: horizon }, `으로 설정하셨습니다. `,
        `이에 맞춰 `, { b: risk_tier }, ` 성향에 최적화된 포트폴리오를 구성하였습니다.`,
      )
    } else {
      introParts.push(
        `이 포트폴리오는 `, { b: risk_tier }, ` 투자자를 위해 특별히 설계되었습니다. ${info.desc} 투자자에게 적합하며, `,
      )
    }
    introParts.push(
      ` 총 `, { b: `${portfolio_items.length}개 종목` },
      `에 자산을 분산해 한 종목이 크게 하락해도 전체 자산에 미치는 충격을 줄이는 구조입니다.`,
    )
    paras.push({ icon: info.icon, parts: introParts })
  }

  // ② 투자 방식·금액 반영
  {
    const moneyParts = []
    if (contribType === 'LUMP_SUM' && lumpAmt) {
      moneyParts.push(
        `투자 방식으로 `, { b: '일시금 투자' }, `를 선택하셨으며, `,
        { b: fmtKrw(lumpAmt) }, `을 한 번에 투자하는 방식으로 포트폴리오를 짰습니다. `,
        `일시금은 지금 당장 시장에 참여하여 상승 흐름을 함께 탈 수 있다는 장점이 있습니다.`,
      )
    } else if (contribType === 'DCA' && monthlyAmt) {
      moneyParts.push(
        `투자 방식으로 `, { b: '적립식 투자' }, `를 선택하셨으며, 매달 `,
        { b: fmtKrw(monthlyAmt) }, `씩 분할 투자하는 방식입니다. `,
        `적립식은 시장이 오를 때도, 내릴 때도 꾸준히 사서 평균 매입 단가를 낮출 수 있어 변동성 리스크를 자연스럽게 줄여줍니다.`,
      )
    } else if (monthlyAmt) {
      moneyParts.push(
        `월 `, { b: fmtKrw(monthlyAmt) }, `의 투자 가능 금액을 기준으로 종목 비중과 매수 수량을 계산하였습니다.`,
      )
    } else if (lumpAmt) {
      moneyParts.push(
        { b: fmtKrw(lumpAmt) }, `의 투자금을 기준으로 종목 비중과 매수 수량을 계산하였습니다.`,
      )
    }
    if (dividendPref === 'HIGH') {
      moneyParts.push(` 또한 `, { b: '배당 수익을 중시' }, `하신다고 하셔서, 배당 성향이 있는 종목에도 비중을 두었습니다.`)
    } else if (dividendPref === 'LOW') {
      moneyParts.push(` 배당보다 `, { b: '시세 차익(성장 수익)' }, `을 우선하신다는 점을 반영해 모멘텀 강한 성장주 위주로 구성하였습니다.`)
    }
    if (moneyParts.length > 0) {
      paras.push({ icon: '💳', parts: moneyParts })
    }
  }

  // ③ 주요 종목 소개
  if (top2Names.length > 0) {
    const namesText = top2Names.length === 1
      ? [{ b: top2Names[0] }]
      : [{ b: top2Names[0] }, ', ', { b: top2Names[1] }]
    paras.push({
      icon: '🏢',
      parts: [
        `비중이 가장 큰 `, ...namesText,
        ` 등은 최근 강한 상승 흐름을 보인 종목들입니다. `,
        maxHoldings
          ? [`설문에서 `, { b: `최대 ${maxHoldings}개 종목` }, `을 원하신다고 하셔서 집중도 높게 구성하였고, `]
          : [],
        `지난 1년간 시장 평균보다 높은 수익률을 기록해 성장 모멘텀이 뛰어나다고 판단해 편입하였습니다.`,
      ].flat(),
    })
  }

  // ④ 기대수익률
  if (monte_carlo_1y) {
    const { p10_pct, p50_pct, p90_pct } = monte_carlo_1y
    const budget = lumpAmt || (monthlyAmt ? monthlyAmt * 12 : 1_000_000)
    const exampleBase = Math.round(budget / 10_000)
    const exampleResult = Math.round(budget * (1 + p50_pct / 100) / 10_000)
    paras.push({
      icon: '💰',
      parts: [
        `AI 시뮬레이션 기준 1년 후 예상 수익률은 중앙값 `, { b: `+${p50_pct.toFixed(1)}%` }, `입니다. `,
        `시장이 좋을 경우 최대 `, { b: `+${p90_pct.toFixed(1)}%` },
        `, 나쁜 경우에도 `, { b: `${p10_pct >= 0 ? '+' : ''}${p10_pct.toFixed(1)}%` }, ` 수준입니다. `,
        `예를 들어 `, { b: `${exampleBase}만 원` }, ` 투자 시 중간 시나리오 기준 약 `,
        { b: `${exampleResult}만 원` }, `이 될 수 있습니다.`,
      ],
    })
  } else if (quant_signals?.medium_term?.weighted_ret_12m_pct != null) {
    const ret = quant_signals.medium_term.weighted_ret_12m_pct
    paras.push({
      icon: '💰',
      parts: [
        `최근 12개월 과거 수익률 기반 연간 기대수익률은 `,
        { b: `${ret >= 0 ? '+' : ''}${ret.toFixed(1)}%` },
        `입니다. 과거 수익률이 미래를 보장하지는 않지만 현재 편입 종목들의 성장 흐름은 강한 상태입니다.`,
      ],
    })
  }

  // ⑤ 리스크 안내
  paras.push({ icon: '⚠️', parts: [info.riskNote] })

  return paras
}

function buildStockNarrative(item, ai) {
  // 뉴스 기반 narrative 우선 사용 (mode='news' 결과)
  if (ai?.narrative) return ai.narrative

  const reason = ai?.selection_reason || item.selection_reason || ''
  const strengths = ai?.strengths || item.ai_strengths || []
  const weaknesses = ai?.weaknesses || item.ai_weaknesses || []

  const parts = []

  if (reason) {
    // 기존 reason이 "1년 수익률 +XXX% / 변동성 XX%" 형태면 자연어로 변환
    const momentumMatch = reason.match(/1년 수익률 ([+-]?\d+\.?\d*)%.*변동성 (\d+\.?\d*)%/)
    if (momentumMatch) {
      const ret = parseFloat(momentumMatch[1])
      const vol = parseFloat(momentumMatch[2])
      if (ret >= 100) {
        parts.push(`지난 1년간 ${ret.toFixed(0)}%라는 뛰어난 상승률을 기록한 종목으로, 현재 강한 상승 모멘텀을 보이고 있습니다.`)
      } else if (ret >= 0) {
        parts.push(`지난 1년간 ${ret.toFixed(0)}% 상승하며 꾸준한 성장세를 보인 종목입니다.`)
      } else {
        parts.push(`최근 1년 수익률은 ${ret.toFixed(0)}%이지만, 포트폴리오 균형을 위해 편입하였습니다.`)
      }
      if (vol >= 60) {
        parts.push(`다만 변동성이 ${vol.toFixed(0)}%로 높은 편이어서 단기 등락이 클 수 있습니다.`)
      } else if (vol <= 30) {
        parts.push(`변동성이 ${vol.toFixed(0)}%로 상대적으로 낮아 안정적인 흐름을 유지합니다.`)
      }
    } else {
      parts.push(reason)
    }
  }

  if (strengths.length > 0) {
    parts.push(`강점으로는 ${strengths.slice(0, 2).join(', ')}이(가) 있습니다.`)
  }
  if (weaknesses.length > 0) {
    parts.push(`유의할 점은 ${weaknesses.slice(0, 1).join(', ')}입니다.`)
  }

  return parts.join(' ')
}

function buildPersonalizedOneLiner({ risk_tier, monte_carlo_1y, portfolio_items = [], survey_context = {} }) {
  const nItems = portfolio_items.length
  const mc = monte_carlo_1y
  const retStr = mc?.p50_pct != null ? ` · 기대수익 ${mc.p50_pct >= 0 ? '+' : ''}${mc.p50_pct.toFixed(0)}%` : ''
  const GOAL_LABELS = {
    '노후 준비': '노후 준비', '은퇴 준비': '노후 준비',
    '주택 마련': '내 집 마련', '집 구입': '내 집 마련',
    '자산 증식': '자산 증식', '목돈 마련': '목돈 마련',
    '여유 자금 운용': '여유 자금 운용', '자녀 교육': '자녀 교육 자금',
  }
  const goal = survey_context.INVEST_GOAL ? (GOAL_LABELS[survey_context.INVEST_GOAL] || survey_context.INVEST_GOAL) : null
  const horizon = survey_context.TARGET_HORIZON || null
  const lumpAmt = survey_context.LUMP_SUM_AMOUNT ? parseInt(survey_context.LUMP_SUM_AMOUNT, 10) : null
  const monthlyAmt = survey_context.MONTHLY_AMOUNT ? parseInt(survey_context.MONTHLY_AMOUNT, 10) : null
  const contribType = survey_context.CONTRIBUTION_TYPE
  const fmtKrw = (n) => n >= 100_000_000 ? `${(n / 100_000_000).toFixed(0)}억 원` : `${(n / 10_000).toFixed(0)}만 원`

  const condParts = []
  if (goal && horizon) condParts.push(`${goal}(${horizon})`)
  else if (goal) condParts.push(goal)
  else if (horizon) condParts.push(`${horizon} 목표`)

  if (contribType === 'LUMP_SUM' && lumpAmt) condParts.push(`일시금 ${fmtKrw(lumpAmt)}`)
  else if (contribType === 'DCA' && monthlyAmt) condParts.push(`월 ${fmtKrw(monthlyAmt)} 적립식`)
  else if (monthlyAmt) condParts.push(`월 ${fmtKrw(monthlyAmt)}`)
  else if (lumpAmt) condParts.push(fmtKrw(lumpAmt))

  const pfDesc = `${risk_tier} ${nItems}개 종목${retStr}`
  if (condParts.length > 0) {
    return `${condParts.join(' · ')}에 최적화된 ${pfDesc}`
  }
  return TIER_INFO[risk_tier]?.summary || `${risk_tier} 성향에 맞게 ${nItems}개 종목으로 구성했습니다.`
}

function ReasonParts({ parts }) {
  return (
    <>
      {parts.map((p, i) =>
        typeof p === 'string' ? p : <strong key={i}>{p.b}</strong>
      )}
    </>
  )
}

function PortfolioDetailPage() {
  const navigate = useNavigate()
  const { state } = useLocation()
  const { user } = useAuth()
  const portfolioData = state?.portfolioData
  const portfolioRank = state?.portfolioRank
  const [isLoading, setIsLoading] = useState(!portfolioData)

  const passedAiData = state?.aiEnrichData || (() => {
    const items = state?.portfolioData?.portfolio_items || []
    const entries = items
      .filter(item => item.ai_fin_grade || (item.ai_strengths && item.ai_strengths.length))
      .map(item => [item.ticker, {
        fin_grade: item.ai_fin_grade,
        selection_reason: item.selection_reason,
        strengths: item.ai_strengths || [],
        weaknesses: item.ai_weaknesses || [],
      }])
    return Object.fromEntries(entries)
  })()

  const [aiStatus, setAiStatus] = useState(Object.keys(passedAiData).length > 0 ? 'done' : 'idle')
  const [aiData, setAiData] = useState(passedAiData)
  const [riskStatus, setRiskStatus] = useState('idle')
  const [riskAnalysis, setRiskAnalysis] = useState(null)
  const cardRef = useRef(null)

  // 데이터가 없을 때 3초 후에 로딩을 멈추고 에러 표시
  useEffect(() => {
    if (!portfolioData) {
      const timer = setTimeout(() => {
        setIsLoading(false)
      }, 3000)
      return () => clearTimeout(timer)
    }
  }, [portfolioData])

  const buildPdfParts = () => {
    const today = new Date().toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' })
    const userName = user?.name || user?.userId || '투자자'
    const fmtA = (n) => n == null ? '-' : n >= 100_000_000 ? `${(n / 100_000_000).toFixed(0)}억 원` : `${(n / 10_000).toFixed(0)}만 원`
    const lbl = 'font-size:12px;font-weight:700;color:#F97316;padding-bottom:6px;border-bottom:2px solid #F97316;margin-bottom:12px;'
    // 각 유닛을 독립 렌더링 가능한 794px div로 감쌈
    const W = `font-family:'Malgun Gothic','맑은 고딕',AppleGothic,sans-serif;font-size:13px;color:#1e293b;background:white;width:794px;`
    const divider = ``

    // ── 헤더 (매 페이지 상단) ──────────────────────────────────
    const headerHtml = `<div id="pdf-header" style="${W}background:#1e293b;padding:20px 40px;display:flex;justify-content:space-between;align-items:center;">
      <div><span style="color:#ffec48;font-size:22px;font-weight:700;letter-spacing:-0.5px;">SeedUP</span>
        <span style="color:#94a3b8;font-size:12px;margin-left:12px;">포트폴리오 분석 보고서</span></div>
      <div style="color:#94a3b8;font-size:11px;">${today}</div>
    </div>`

    // ── 푸터 (매 페이지 하단) ──────────────────────────────────
    const footerHtml = `<div id="pdf-footer" style="${W}">
      <div style="padding:10px 40px;background:#f8fafc;border-top:1px solid #e2e8f0;">
        <ul style="margin:0;padding-left:18px;font-size:11px;color:#94a3b8;line-height:1.7;">
          <li>본 포트폴리오는 AI가 생성한 참고용이며, 최종 투자 결정은 투자자 본인의 판단으로 합니다.</li>
          <li>과거 성과지표가 미래의 성과를 보장하지 않으며, 투자 원금의 일부 또는 전부를 잃을 수 있습니다.</li>
        </ul>
      </div>
      <div style="background:#1e293b;padding:14px 40px;display:flex;justify-content:space-between;align-items:center;">
        <span style="color:#ffec48;font-size:16px;font-weight:700;">SeedUP</span>
        <span style="color:#64748b;font-size:11px;">AI 기반 투자 포트폴리오 분석 서비스</span>
        <span style="color:#94a3b8;font-size:11px;">${today}</span>
      </div>
    </div>`

    // ── 바디 유닛 배열 ──────────────────────────────────────────
    const units = []

    // 타이틀
    units.push(`<div style="${W}padding:20px 40px;background:#fff7ed;border-bottom:1px solid #fed7aa;">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div>
          <div style="font-size:18px;font-weight:700;color:#1e293b;margin-bottom:4px;">${risk_tier || '포트폴리오'} 보고서</div>
          <div style="font-size:12px;color:#64748b;">${userName} 님을 위한 맞춤 포트폴리오</div>
        </div>
        ${investable_amount_krw != null ? `<div style="text-align:right;"><div style="font-size:11px;color:#94a3b8;margin-bottom:2px;">투자 가능 금액</div>
          <div style="font-size:18px;font-weight:700;color:#F97316;">${fmtA(investable_amount_krw)}</div></div>` : ''}
      </div>
    </div>`)

    // 추천 이유 — 항목별 개별 유닛
    const reasons = buildRecommendationReason({ risk_tier, monte_carlo_1y, portfolio_items: sortedItems, quant_signals, survey_context })
    units.push(`<div style="${W}padding:16px 40px 4px;"><div style="${lbl}">포트폴리오 추천 이유</div></div>`)
    reasons.forEach(r => {
      const txt = r.parts.map(p => typeof p === 'string' ? p : `<strong>${p.b}</strong>`).join('')
      units.push(`<div style="${W}padding:4px 40px 4px 58px;font-size:12px;color:#1e293b;line-height:1.65;">• ${txt}</div>`)
    })
    units.push(divider)

    // 구성종목 — 고정 컬럼 너비로 헤더+행 정렬 맞춤
    const hasShares = sortedItems.some(i => i.shares_to_buy != null)
    const colW = hasShares ? ['45%', '20%', '17%', '18%'] : ['55%', '25%', '20%']
    const thBase = 'padding:8px 12px;font-size:11px;font-weight:600;color:#475569;border-bottom:2px solid #e2e8f0;'
    const colGroup = `<colgroup>
      <col style="width:${colW[0]}"/><col style="width:${colW[1]}"/>
      <col style="width:${colW[2]}"/>${hasShares ? `<col style="width:${colW[3]}"/>` : ''}
    </colgroup>`

    units.push(`<div style="${W}padding:16px 40px 0;">
      <div style="${lbl}">구성종목</div>
      <table style="width:100%;border-collapse:collapse;table-layout:fixed;">
        ${colGroup}
        <thead><tr style="background:#f1f5f9;">
          <th style="${thBase}text-align:left;">종목명</th>
          <th style="${thBase}text-align:left;">코드</th>
          <th style="${thBase}text-align:right;">비중</th>
          ${hasShares ? `<th style="${thBase}text-align:right;">매수수량</th>` : ''}
        </tr></thead>
      </table>
    </div>`)
    sortedItems.forEach((item, idx) => {
      units.push(`<div style="${W}padding:0 40px;">
        <table style="width:100%;border-collapse:collapse;table-layout:fixed;">
          ${colGroup}
          <tbody><tr style="background:${idx % 2 === 0 ? '#ffffff' : '#f8fafc'};">
            <td style="padding:8px 12px;font-size:12px;overflow:hidden;">${item.name}</td>
            <td style="padding:8px 12px;font-size:11px;color:#94a3b8;">${item.ticker}</td>
            <td style="padding:8px 12px;font-size:12px;font-weight:600;text-align:right;">${item.weight_pct.toFixed(1)}%</td>
            ${hasShares ? `<td style="padding:8px 12px;font-size:12px;text-align:right;">${item.shares_to_buy != null ? item.shares_to_buy + '주' : '-'}</td>` : ''}
          </tr></tbody>
        </table>
      </div>`)
    })
    if (total_invested_krw != null) {
      units.push(`<div style="${W}padding:6px 40px 16px;font-size:11px;color:#64748b;">총 투자금액: <strong>${fmtA(total_invested_krw)}</strong>${leftover_krw != null ? ` · 잔여금: ${fmtA(leftover_krw)}` : ''}</div>`)
    }
    units.push(divider)

    // 몬테카를로
    if (monte_carlo_1y) {
      units.push(`<div style="${W}padding:16px 40px 20px;">
        <div style="${lbl}">향후 1년 수익률 시뮬레이션</div>
        <table style="width:100%;border-collapse:collapse;"><tbody><tr>
          <td style="width:33%;padding-right:8px;"><div style="background:#fef2f2;border-radius:8px;padding:14px;text-align:center;">
            <div style="font-size:11px;color:#64748b;margin-bottom:6px;">비관적 시나리오</div>
            <div style="font-size:20px;font-weight:700;color:#ef4444;">${fmtPct(monte_carlo_1y.p10_pct)}</div>
          </div></td>
          <td style="width:33%;padding:0 4px;"><div style="background:#fff7ed;border:2px solid #F97316;border-radius:8px;padding:14px;text-align:center;">
            <div style="font-size:11px;color:#64748b;margin-bottom:6px;">중립 시나리오 (중앙값)</div>
            <div style="font-size:20px;font-weight:700;color:#F97316;">${fmtPct(monte_carlo_1y.p50_pct)}</div>
          </div></td>
          <td style="width:33%;padding-left:8px;"><div style="background:#f0fdf4;border-radius:8px;padding:14px;text-align:center;">
            <div style="font-size:11px;color:#64748b;margin-bottom:6px;">낙관적 시나리오</div>
            <div style="font-size:20px;font-weight:700;color:#16a34a;">${fmtPct(monte_carlo_1y.p90_pct)}</div>
          </div></td>
        </tr></tbody></table>
        ${monte_carlo_1y.interpretation ? `<div style="font-size:11px;color:#64748b;margin-top:10px;line-height:1.65;">${monte_carlo_1y.interpretation}</div>` : ''}
      </div>`)
      units.push(divider)
    }

    // 퀀트 시그널
    const stOk = quant_signals?.short_term?.weighted_p_adj != null
    const mtOk = quant_signals?.medium_term?.weighted_ret_12m_pct != null
    if (stOk || mtOk) {
      const stItems = stOk ? quant_signals.short_term.items.filter(si => si.p_adj != null).map(si =>
        `<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #f1f5f9;font-size:12px;">
          <span>${si.name}</span><span style="font-weight:600;color:${si.p_adj >= 0.5 ? '#16a34a' : '#ef4444'}">${(si.p_adj * 100).toFixed(1)}%</span>
        </div>`).join('') : ''
      const ret = mtOk ? quant_signals.medium_term.weighted_ret_12m_pct : 0
      const mtItems = mtOk ? quant_signals.medium_term.items.filter(mi => mi.ret_12m_pct != null).map(mi =>
        `<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #f1f5f9;font-size:12px;">
          <span>${mi.name}</span><span style="font-weight:600;color:${mi.ret_12m_pct >= 0 ? '#16a34a' : '#ef4444'}">${mi.ret_12m_pct >= 0 ? '+' : ''}${mi.ret_12m_pct.toFixed(1)}%</span>
        </div>`).join('') : ''
      units.push(`<div style="${W}padding:16px 40px 20px;">
        <table style="width:100%;border-collapse:collapse;"><tbody><tr>
          <td style="width:50%;padding-right:20px;vertical-align:top;">
            ${stOk ? `<div style="${lbl}">5일 후 상승 확률</div>
              <div style="background:#fff7ed;border-radius:6px;padding:10px 14px;margin-bottom:10px;">
                <span style="font-size:15px;font-weight:700;color:#ea580c;">상승확률 ${(quant_signals.short_term.weighted_p_adj * 100).toFixed(1)}%</span>
              </div>${stItems}` : ''}
          </td>
          <td style="width:50%;padding-left:20px;vertical-align:top;border-left:1px solid #e2e8f0;">
            ${mtOk ? `<div style="${lbl}">최근 12개월 과거 수익률</div>
              <div style="background:${ret >= 0 ? '#f0fdf4' : '#fef2f2'};border-radius:6px;padding:10px 14px;margin-bottom:10px;">
                <span style="font-size:22px;font-weight:700;color:${ret >= 0 ? '#16a34a' : '#ef4444'}">${ret >= 0 ? '+' : ''}${ret.toFixed(1)}%</span>
              </div>${mtItems}` : ''}
          </td>
        </tr></tbody></table>
      </div>`)
      units.push(divider)
    }

    // 리스크 — 헤더+요약 + 카드별 개별 유닛
    if (riskAnalysis) {
      units.push(`<div style="${W}padding:16px 40px 8px;">
        <div style="${lbl}">리스크</div>
        ${riskAnalysis.risk_summary ? `<div style="background:#fff1f2;border-left:3px solid #ef4444;padding:10px 14px;border-radius:0 6px 6px 0;font-size:12px;line-height:1.6;">${riskAnalysis.risk_summary}</div>` : ''}
      </div>`)
      ;(riskAnalysis.per_stock || []).forEach(ps => {
        units.push(`<div style="${W}padding:4px 40px;">
          <div style="background:#f8fafc;border-radius:6px;padding:10px 14px;">
            <strong style="font-size:12px;">${ps.name}</strong>
            <div style="font-size:12px;color:#475569;margin-top:4px;line-height:1.5;">${ps.risk_text}</div>
          </div>
        </div>`)
      })
      units.push(`<div style="${W}padding-bottom:16px;"></div>`)
      units.push(divider)
    }

    // 매수 계획
    if (buy_plan && buy_plan.length > 0) {
      const fmtN = (n) => n == null ? '-' : n.toLocaleString('ko-KR')
      const thS = 'padding:8px 12px;font-size:11px;font-weight:600;color:#475569;border-bottom:2px solid #e2e8f0;'
      units.push(`<div style="${W}padding:16px 40px 0;">
        <div style="${lbl}">매수 계획</div>
        ${investable_amount_krw != null ? `<div style="font-size:12px;color:#64748b;margin-bottom:10px;">가용자산 <strong style="color:#1e293b">${fmtA(investable_amount_krw)}</strong> 기준</div>` : ''}
        <table style="width:100%;border-collapse:collapse;table-layout:fixed;">
          <colgroup><col style="width:35%"/><col style="width:16%"/><col style="width:13%"/><col style="width:12%"/><col style="width:24%"/></colgroup>
          <thead><tr style="background:#f1f5f9;">
            <th style="${thS}text-align:left;">종목</th>
            <th style="${thS}text-align:right;">현재가</th>
            <th style="${thS}text-align:right;">목표비중</th>
            <th style="${thS}text-align:right;">수량</th>
            <th style="${thS}text-align:right;">투자금액</th>
          </tr></thead>
        </table>
      </div>`)
      buy_plan.forEach((bp, i) => {
        const unaffordable = bp.shares === 0
        const matchedItem = sortedItems.find(it => it.ticker === bp.ticker)
        units.push(`<div style="${W}padding:0 40px;">
          <table style="width:100%;border-collapse:collapse;table-layout:fixed;">
            <colgroup><col style="width:35%"/><col style="width:16%"/><col style="width:13%"/><col style="width:12%"/><col style="width:24%"/></colgroup>
            <tbody><tr style="background:${unaffordable ? '#fef9f0' : (i % 2 === 0 ? '#fff' : '#f8fafc')};opacity:${unaffordable ? '0.75' : '1'};">
              <td style="padding:8px 12px;font-size:12px;">
                <span style="font-weight:600;color:${unaffordable ? '#9ca3af' : '#1e293b'}">${bp.name}</span>
                <span style="margin-left:6px;font-size:10px;color:#94a3b8;">${bp.ticker}</span>
                ${unaffordable ? `<span style="margin-left:6px;font-size:10px;color:#f97316;font-weight:600;">매수불가</span>` : ''}
              </td>
              <td style="padding:8px 12px;font-size:12px;text-align:right;color:${unaffordable ? '#9ca3af' : '#374151'}">${fmtN(bp.price_krw)}원</td>
              <td style="padding:8px 12px;font-size:12px;text-align:right;color:#64748b;">${matchedItem ? matchedItem.weight_pct.toFixed(1) + '%' : '-'}</td>
              <td style="padding:8px 12px;font-size:12px;text-align:right;color:${unaffordable ? '#f97316' : '#374151'};font-weight:${unaffordable ? '600' : '400'};">${unaffordable ? '0주' : fmtN(bp.shares) + '주'}</td>
              <td style="padding:8px 12px;font-size:12px;text-align:right;font-weight:600;color:${unaffordable ? '#9ca3af' : '#1e293b'}">${unaffordable ? '-' : fmtN(bp.allocated_budget_krw) + '원'}</td>
            </tr></tbody>
          </table>
        </div>`)
      })
      units.push(`<div style="${W}padding:6px 40px 16px;">
        <div style="background:#f8fafc;border-radius:6px;padding:8px 14px;font-size:12px;color:#64748b;display:flex;gap:20px;">
          <span>총 투자금액: <strong style="color:#1e293b">${fmtN(total_invested_krw ?? 0)}원</strong></span>
          <span>잔여금: <strong style="color:#64748b">${fmtN(leftover_krw ?? 0)}원</strong></span>
        </div>
      </div>`)
      units.push(divider)
    }

    // 종목별 분석 — 항목별 개별 유닛
    units.push(`<div style="${W}padding:16px 40px 4px;"><div style="${lbl}">종목별 분석</div></div>`)
    sortedItems.forEach((item, idx) => {
      const ai = aiData[item.ticker]
      const narrative = buildStockNarrative(item, ai)
      const color = COLOR_PALETTE[idx % COLOR_PALETTE.length]
      units.push(`<div style="${W}padding:4px 40px 14px;border-bottom:1px solid #f1f5f9;">
        <div style="margin-bottom:6px;">
          <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${color};margin-right:8px;vertical-align:middle;"></span>
          <strong style="font-size:13px;vertical-align:middle;">${item.name}</strong>
          <span style="font-size:11px;color:#94a3b8;margin-left:8px;vertical-align:middle;">${item.ticker}</span>
          <span style="font-size:12px;color:#64748b;float:right;">${item.weight_pct.toFixed(1)}%</span>
        </div>
        ${narrative ? `<div style="font-size:12px;color:#475569;line-height:1.7;padding-left:18px;">${narrative}</div>` : ''}
      </div>`)
    })

    return { headerHtml, footerHtml, units }
  }

  const handlePdf = async () => {
    const pfLabel = portfolioData.portfolio_label || risk_tier || '포트폴리오'
    const filename = `${new Date().toISOString().slice(0, 10).replace(/-/g, '')}_${pfLabel}_${user?.name || user?.userId || 'user'}.pdf`

    const overlay = document.createElement('div')
    overlay.style.cssText = 'position:fixed;inset:0;background:white;z-index:9999;display:flex;align-items:center;justify-content:center;'
    overlay.innerHTML = '<div class="loading-container"><div class="loading-spinner"></div><p>PDF 생성 중...</p></div>'
    document.body.appendChild(overlay)

    try {
      const { headerHtml, footerHtml, units } = buildPdfParts()
      const opts = { scale: 2, useCORS: true, scrollX: 0, scrollY: 0, windowWidth: 794, logging: false }

      // 헤더·푸터 캡처
      const renderUnit = async (html) => {
        const div = document.createElement('div')
        div.style.cssText = 'position:absolute;top:0;left:900px;z-index:9998;'
        div.innerHTML = html
        document.body.appendChild(div)
        const canvas = await html2canvas(div.firstElementChild || div, opts)
        document.body.removeChild(div)
        return canvas
      }

      const headerCanvas = await renderUnit(headerHtml)
      const footerCanvas = await renderUnit(footerHtml)

      // 유닛별 개별 캡처
      const sectionCanvases = []
      for (const html of units) {
        if (!html) continue
        sectionCanvases.push(await renderUnit(html))
      }

      // jsPDF bin-packing 조립
      const pdf = new jsPDF({ unit: 'mm', format: 'a4', orientation: 'portrait' })
      const pageW = pdf.internal.pageSize.getWidth()
      const pageH = pdf.internal.pageSize.getHeight()

      const pxPerMm = headerCanvas.width / pageW
      const hMm = headerCanvas.height / pxPerMm
      const fMm = footerCanvas.height / pxPerMm
      const hImg = headerCanvas.toDataURL('image/jpeg', 0.95)
      const fImg = footerCanvas.toDataURL('image/jpeg', 0.95)

      const addHF = () => {
        pdf.addImage(hImg, 'JPEG', 0, 0, pageW, hMm)
        pdf.addImage(fImg, 'JPEG', 0, pageH - fMm, pageW, fMm)
      }

      let isFirst = true
      let curYMm = hMm  // 첫 페이지: 헤더에 바로 붙음
      addHF()

      for (const canvas of sectionCanvases) {
        const sHMm = canvas.height / pxPerMm
        const bottomLimit = pageH - fMm

        // 현재 페이지에 안 들어가면 새 페이지
        if (curYMm + sHMm > bottomLimit) {
          pdf.addPage()
          isFirst = false
          addHF()
          curYMm = hMm + 3  // 2페이지부터 3mm gap
        }

        pdf.addImage(canvas.toDataURL('image/jpeg', 0.95), 'JPEG', 0, curYMm, pageW, sHMm)
        curYMm += sHMm
      }

      pdf.save(filename)
    } finally {
      document.body.removeChild(overlay)
    }
  }

  if (isLoading) {
    return (
      <div className="portfolio-detail-page">
        <div className="loading-container">
          <div className="loading-spinner"></div>
          <p>포트폴리오를 불러오는 중...</p>
        </div>
      </div>
    )
  }

  if (!portfolioData) {
    return (
      <div className="portfolio-detail-page">
        <div className="pd-error-box">
          <p>포트폴리오 데이터가 없습니다. 대시보드에서 다시 선택해 주세요.</p>
          <button onClick={() => navigate('/dashboard')} className="pd-back-btn">
            ← 뒤로
          </button>
        </div>
      </div>
    )
  }

  const {
    risk_tier, risk_grade,
    overall_summary: _overall_summary,
    portfolio_summary: _portfolio_summary,
    portfolio_items = [], buy_plan = [],
    performance_3y, monte_carlo_1y,
    investable_amount_krw, total_invested_krw, leftover_krw,
    quant_signals,
    survey_context = {},
  } = portfolioData
  const overall_summary = _portfolio_summary || _overall_summary

  const sortedItems = [...portfolio_items].sort((a, b) => b.weight_pct - a.weight_pct)

  const runAiEnrich = async () => {
    const tickers = sortedItems.map(i => i.ticker)
    if (!tickers.length) return
    setAiStatus('loading')
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 180000)
    try {
      const items = sortedItems.map(i => ({ ticker: i.ticker, name: i.name }))
      const res = await fetch('/api/dashboard/portfolio-ai-enrich', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tickers, items, mode: 'news' }),
        signal: controller.signal,
      })
      if (!res.ok) throw new Error(await res.text())
      setAiData(await res.json())
      setAiStatus('done')
    } catch (e) {
      console.warn('AI 분석 실패:', e)
      setAiStatus(e.name === 'AbortError' ? 'timeout' : 'error')
    } finally {
      clearTimeout(timer)
    }
  }

  const runRiskAnalysis = async () => {
    const riskItems = sortedItems.map(i => ({ ticker: i.ticker, name: i.name }))
    if (!riskItems.length) return
    setRiskStatus('loading')
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 180000)
    try {
      const res = await fetch('/api/dashboard/portfolio-risk-analysis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: riskItems, risk_tier: risk_tier || '' }),
        signal: controller.signal,
      })
      if (!res.ok) throw new Error(await res.text())
      const riskData = await res.json()
      setRiskAnalysis(riskData)
      // per_stock의 company_overview + narrative를 aiData에 병합
      if (riskData.per_stock?.length) {
        setAiData(prev => {
          const next = { ...prev }
          riskData.per_stock.forEach(ps => {
            next[ps.ticker] = {
              ...(next[ps.ticker] || {}),
              ...(ps.company_overview ? { company_overview: ps.company_overview } : {}),
              ...(ps.narrative ? { narrative: ps.narrative } : {}),
            }
          })
          return next
        })
        setAiStatus('done')
      }
      setRiskStatus('done')
    } catch (e) {
      console.warn('리스크 분석 실패:', e)
      setRiskStatus(e.name === 'AbortError' ? 'timeout' : 'error')
    } finally {
      clearTimeout(timer)
    }
  }

  useEffect(() => {
    if (sortedItems.length > 0) runRiskAnalysis()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="portfolio-detail-page">
      <div className="portfolio-detail-container">

        {/* 뒤로가기 */}
        <button onClick={() => navigate('/dashboard')} className="pd-back-btn">
          ← 뒤로
        </button>

        <div className="pd-main-card" ref={cardRef}>

          {/* 헤더 */}
          <div className="pd-section-row pd-header-row">
            <div className="pd-section-label">
              {risk_tier || '포트폴리오'}
            </div>
            {(() => {
              const oneLiner = buildPersonalizedOneLiner({
                risk_tier,
                monte_carlo_1y,
                portfolio_items: sortedItems,
                survey_context,
                portfolio_style: portfolioData.portfolio_style,
              })
              return oneLiner ? <ul className="pd-tier-summary-list"><li>{oneLiner}</li></ul> : null
            })()}
          </div>

          <div className="pd-divider" />

          {/* 추천 이유 */}
          <div className="pd-section-row pd-reason-section">
            <div className="pd-section-label">포트폴리오 추천 이유</div>
            <ul className="pd-reason-list">
              {buildRecommendationReason({
                risk_tier,
                monte_carlo_1y,
                portfolio_items: sortedItems,
                quant_signals,
                survey_context,
              }).map((r, i) => (
                <li key={i} className="pd-reason-item">
                  <ReasonParts parts={r.parts} />
                </li>
              ))}
            </ul>
          </div>

          <div className="pd-divider" />

          {/* 몬테카를로 시뮬레이션 */}
          {monte_carlo_1y && (
            <>
              <div className="pd-section-row">
                <div className="pd-section-label">향후 1년 수익률 시뮬레이션 (과거 변동성·수익률 기반)</div>
                <div className="pd-mc-row">
                  <div className="pd-mc-box pd-mc-bear">
                    <div className="pd-mc-label">비관적 시나리오 (90% 확률로 이보다 높음)</div>
                    <div className="pd-mc-value">{fmtPct(monte_carlo_1y.p10_pct)}</div>
                  </div>
                  <div className="pd-mc-box pd-mc-base">
                    <div className="pd-mc-label">중립 시나리오 (중앙값)</div>
                    <div className="pd-mc-value">{fmtPct(monte_carlo_1y.p50_pct)}</div>
                  </div>
                  <div className="pd-mc-box pd-mc-bull">
                    <div className="pd-mc-label">낙관적 시나리오 (10% 확률로 이보다 높음)</div>
                    <div className="pd-mc-value">{fmtPct(monte_carlo_1y.p90_pct)}</div>
                  </div>
                </div>
                {monte_carlo_1y.interpretation && (
                  <div className="pd-interpretation">{monte_carlo_1y.interpretation}</div>
                )}
              </div>
              <div className="pd-divider" />
            </>
          )}

          {/* 구성비율 */}
          <div className="pd-section-row pdf-page-break">
            <div className="pd-section-label">구성비율 / 구성종목</div>
            <DonutChart items={sortedItems} centerAmount={investable_amount_krw} navigate={navigate} riskData={riskAnalysis?.per_stock} />
          </div>

          <div className="pd-divider" />

          {/* 단기 방향성 / 중장기 기대수익률 / 리스크 */}
          {quant_signals && (
            <>
              {/* 5일 후 상승확률 / 최근 12개월 과거 수익률 - 좌우 배치 */}
              <div className="pd-section-row pd-two-col">
                <div className="pd-col">
                  <div className="pd-section-label">5일 후 상승 확률</div>
                  {quant_signals.short_term?.weighted_p_adj != null ? (
                    <>
                      <div className="pd-signal-bar-wrap">
                        <div
                          className="pd-signal-bar"
                          style={{ width: `${(quant_signals.short_term.weighted_p_adj * 100).toFixed(1)}%` }}
                        />
                        <span className="pd-signal-pct">
                          상승 확률 {(quant_signals.short_term.weighted_p_adj * 100).toFixed(1)}%
                        </span>
                      </div>
                      <div className="pd-signal-items">
                        {quant_signals.short_term.items
                          .filter(si => si.p_adj != null)
                          .map(si => (
                            <div key={si.ticker} className="pd-signal-item">
                              <span className="pd-signal-name">{si.name}</span>
                              <span className={si.p_adj >= 0.5 ? 'pd-pos' : 'pd-neg'}>
                                {(si.p_adj * 100).toFixed(1)}%
                              </span>
                            </div>
                          ))}
                      </div>
                    </>
                  ) : <p className="pd-no-data">데이터 없음</p>}
                </div>

                <div className="pd-col">
                  <div className="pd-section-label">최근 12개월 과거 수익률</div>
                  {quant_signals.medium_term?.weighted_ret_12m_pct != null ? (
                    <>
                      <div className={`pd-big-value ${quant_signals.medium_term.weighted_ret_12m_pct >= 0 ? 'pd-pos' : 'pd-neg'}`}>
                        {quant_signals.medium_term.weighted_ret_12m_pct >= 0 ? '+' : ''}
                        {quant_signals.medium_term.weighted_ret_12m_pct.toFixed(1)}%
                      </div>
                      <div className="pd-signal-items">
                        {quant_signals.medium_term.items
                          .filter(mi => mi.ret_12m_pct != null)
                          .map(mi => (
                            <div key={mi.ticker} className="pd-signal-item">
                              <span className="pd-signal-name">{mi.name}</span>
                              <span className={mi.ret_12m_pct >= 0 ? 'pd-pos' : 'pd-neg'}>
                                {mi.ret_12m_pct >= 0 ? '+' : ''}{mi.ret_12m_pct.toFixed(1)}%
                              </span>
                            </div>
                          ))}
                      </div>
                    </>
                  ) : <p className="pd-no-data">데이터 없음</p>}
                </div>
              </div>

              <div className="pd-divider" />

              {/* 리스크 - 전체 폭 */}
              <div className="pd-section-row">
                <div className="pd-section-label">리스크</div>
                {riskStatus === 'loading' && (
                  <AnalysisProgressBar loading={true} steps={[
                    { label: '포트폴리오 리스크 산출', icon: '📐' },
                    { label: '종목별 변동성 분석', icon: '📉' },
                    { label: '시나리오 시뮬레이션', icon: '🔬' },
                    { label: 'AI 리스크 리포트 생성', icon: '✍️' },
                  ]} />
                )}
                {riskStatus === 'done' && riskAnalysis ? (
                  <>
                    <div className="pd-risk-summary">{riskAnalysis.risk_summary}</div>
                    <div className="pd-signal-items">
                      {(riskAnalysis.per_stock || []).map(ps => (
                        <div key={ps.ticker} className="pd-signal-item pd-risk-item">
                          <span className="pd-signal-name">{ps.name}</span>
                          <span className="pd-risk-text pd-neg">{ps.risk_text}</span>
                        </div>
                      ))}
                    </div>
                  </>
                ) : riskStatus !== 'loading' && quant_signals.risk?.weighted_vol_3m_pct != null ? (
                  <>
                    <div className="pd-big-value pd-neg">
                      {quant_signals.risk.weighted_vol_3m_pct.toFixed(1)}%
                      <span className="pd-big-value-sub"> 3개월 변동성</span>
                    </div>
                    <div className="pd-signal-items">
                      {quant_signals.risk.items
                        .filter(ri => ri.vol_3m_pct != null)
                        .map(ri => (
                          <div key={ri.ticker} className="pd-signal-item">
                            <span className="pd-signal-name">{ri.name}</span>
                            <span className="pd-neg">{ri.vol_3m_pct.toFixed(1)}%</span>
                          </div>
                        ))}
                    </div>
                  </>
                ) : riskStatus === 'error' || riskStatus === 'timeout' ? (
                  <p className="pd-no-data">리스크 분석을 불러오지 못했습니다.</p>
                ) : (
                  <p className="pd-no-data">데이터 없음</p>
                )}
              </div>
              <div className="pd-divider" />
            </>
          )}

          {/* 성과 + 리스크 (portfolio_model 구형 데이터가 있을 때만) */}
          {performance_3y && (
            <>
              <div className="pd-section-row pd-two-col">
                <div className="pd-col">
                  <div className="pd-section-label">(시뮬) 최근 3년 성과지표</div>
                  <div className="pd-perf-boxes">
                    <div className="pd-perf-box">
                      <div className="pd-perf-box-label">연환산 수익률</div>
                      <div className={`pd-perf-box-value ${performance_3y.ann_return_pct >= 0 ? 'pd-pos' : 'pd-neg'}`}>
                        {fmtPct(performance_3y.ann_return_pct)}
                      </div>
                    </div>
                    <div className="pd-perf-box">
                      <div className="pd-perf-box-label">샤프 지수</div>
                      <div className="pd-perf-box-value">{performance_3y.sharpe?.toFixed(2) ?? '-'}</div>
                    </div>
                  </div>
                  {performance_3y.interpretation && (
                    <div className="pd-interpretation">{performance_3y.interpretation}</div>
                  )}
                </div>
                <div className="pd-col">
                  <div className="pd-section-label">리스크</div>
                  {riskStatus === 'loading' && (
                    <AnalysisProgressBar loading={true} steps={[
                      { label: '포트폴리오 리스크 산출', icon: '📐' },
                      { label: '종목별 변동성 분석', icon: '📉' },
                      { label: '시나리오 시뮬레이션', icon: '🔬' },
                      { label: 'AI 리스크 리포트 생성', icon: '✍️' },
                    ]} />
                  )}
                  {riskStatus === 'done' && riskAnalysis ? (
                    <div className="pd-risk-summary">{riskAnalysis.risk_summary}</div>
                  ) : riskStatus !== 'loading' ? (
                    <div className="pd-perf-boxes">
                      <div className="pd-perf-box">
                        <div className="pd-perf-box-label">연간 변동성</div>
                        <div className="pd-perf-box-value pd-neg">{fmtPct(performance_3y.ann_vol_pct, false)}</div>
                      </div>
                      <div className="pd-perf-box">
                        <div className="pd-perf-box-label">최대 낙폭(MDD)</div>
                        <div className="pd-perf-box-value pd-neg">{fmtPct(performance_3y.mdd_pct, false)}</div>
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>
              <div className="pd-divider" />
            </>
          )}

          {/* 종목별 분석 */}
          <div className="pd-section-row pdf-page-break">
            <div className="pd-section-label">종목별 분석</div>

            {riskStatus === 'loading' && aiStatus !== 'done' && (
              <p className="pd-status-msg" style={{ fontSize: 12, color: '#94a3b8' }}>⏳ 리스크 분석 완료 후 기업 설명이 표시됩니다.</p>
            )}

            <div className="pd-stock-list">
              {sortedItems.map((item, idx) => {
                const ai = aiData[item.ticker]
                const narrative = buildStockNarrative(item, ai)
                return (
                  <div key={item.ticker} className="pd-stock-row">
                    <div className="pd-stock-left">
                      <span className="pd-stock-dot" style={{ background: COLOR_PALETTE[idx % COLOR_PALETTE.length] }} />
                      <strong className="pd-stock-name">{item.name}</strong>
                      <span className="pd-stock-code">{item.ticker}</span>
                    </div>
                    <div className="pd-stock-right">
                      {narrative && <p className="pd-stock-reason">{narrative}</p>}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="pd-divider" />

          {/* 매수 계획 */}
          {buy_plan && buy_plan.length > 0 && (
            <>
              <div className="pd-section-row pdf-page-break">
                <div className="pd-section-label">매수 계획</div>
                {investable_amount_krw != null && (
                  <div style={{ marginBottom: 10, fontSize: 13, color: '#64748b' }}>
                    가용자산 <strong style={{ color: '#1e293b' }}>{investable_amount_krw.toLocaleString()}원</strong> 기준
                  </div>
                )}
                {buy_plan.some(bp => bp.shares === 0) && (
                  <div style={{ marginBottom: 10, padding: '8px 12px', background: '#fff7ed', border: '1px solid #fed7aa', borderRadius: 6, fontSize: 12, color: '#c2410c' }}>
                    ⚠️ 입력하신 가용자산으로 매수 불가한 종목이 있습니다. 가용자산을 늘리면 더 많은 종목으로 구성된 포트폴리오를 받을 수 있습니다.
                  </div>
                )}
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                    <thead>
                      <tr style={{ borderBottom: '2px solid #e2e8f0', textAlign: 'left' }}>
                        <th style={{ padding: '8px 12px', color: '#64748b', fontWeight: 600 }}>종목</th>
                        <th style={{ padding: '8px 12px', color: '#64748b', fontWeight: 600, textAlign: 'right' }}>현재가</th>
                        <th style={{ padding: '8px 12px', color: '#64748b', fontWeight: 600, textAlign: 'right' }}>목표비중</th>
                        <th style={{ padding: '8px 12px', color: '#64748b', fontWeight: 600, textAlign: 'right' }}>수량</th>
                        <th style={{ padding: '8px 12px', color: '#64748b', fontWeight: 600, textAlign: 'right' }}>투자금액</th>
                      </tr>
                    </thead>
                    <tbody>
                      {buy_plan.map((bp, i) => {
                        const unaffordable = bp.shares === 0
                        const matchedItem = sortedItems.find(it => it.ticker === bp.ticker)
                        return (
                          <tr key={bp.ticker} style={{ borderBottom: '1px solid #f1f5f9', background: unaffordable ? '#fef9f0' : (i % 2 === 0 ? '#fff' : '#f8fafc'), opacity: unaffordable ? 0.7 : 1 }}>
                            <td style={{ padding: '8px 12px' }}>
                              <span style={{ fontWeight: 600, color: unaffordable ? '#9ca3af' : '#1e293b' }}>{bp.name}</span>
                              <span style={{ marginLeft: 6, fontSize: 11, color: '#94a3b8' }}>{bp.ticker}</span>
                              {unaffordable && <span style={{ marginLeft: 6, fontSize: 10, color: '#f97316', fontWeight: 600 }}>매수불가</span>}
                            </td>
                            <td style={{ padding: '8px 12px', textAlign: 'right', color: unaffordable ? '#9ca3af' : '#374151' }}>
                              {bp.price_krw.toLocaleString()}원
                            </td>
                            <td style={{ padding: '8px 12px', textAlign: 'right', color: '#64748b' }}>
                              {matchedItem ? `${matchedItem.weight_pct.toFixed(1)}%` : '-'}
                            </td>
                            <td style={{ padding: '8px 12px', textAlign: 'right', color: unaffordable ? '#f97316' : '#374151', fontWeight: unaffordable ? 600 : 400 }}>
                              {unaffordable ? '0주' : `${bp.shares.toLocaleString()}주`}
                            </td>
                            <td style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, color: unaffordable ? '#9ca3af' : '#1e293b' }}>
                              {unaffordable ? '-' : `${bp.allocated_budget_krw.toLocaleString()}원`}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
                <div style={{ marginTop: 10, padding: '8px 12px', background: '#f8fafc', borderRadius: 6, fontSize: 12, color: '#64748b', display: 'flex', gap: 16 }}>
                  <span>총 투자금액: <strong style={{ color: '#1e293b' }}>{(total_invested_krw ?? 0).toLocaleString()}원</strong></span>
                  <span>잔여금: <strong style={{ color: '#64748b' }}>{(leftover_krw ?? 0).toLocaleString()}원</strong></span>
                </div>
              </div>
              <div className="pd-divider" />
            </>
          )}

          {/* 투자 유의사항 */}
          <div className="pd-section-row pd-notice">
            <ul>
              <li>본 포트폴리오는 AI가 생성한 참고용이며, 최종 투자 결정은 투자자 본인의 판단으로 합니다.</li>
              <li>과거 성과지표가 미래의 성과를 보장하지 않으며, 투자 원금의 일부 또는 전부를 잃을 수 있습니다.</li>
            </ul>
          </div>

          {/* 다운로드 버튼 */}
          <div className="pd-footer">
            <button className="pd-download-btn" onClick={handlePdf}>
              PDF로 저장하기
            </button>
          </div>

        </div>
      </div>
    </div>
  )
}

export default PortfolioDetailPage