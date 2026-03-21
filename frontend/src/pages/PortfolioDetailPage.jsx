import React, { useState, useRef, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import html2pdf from 'html2pdf.js'
import { useAuth } from '../contexts/AuthContext'
import './PortfolioDetailPage.css'
import { TermText, DynamicTermProvider } from '../components/TermTooltip'

const COLOR_PALETTE = [
  '#C2410C', '#EA580C', '#F97316', '#FB923C',
  '#FDBA74', '#FED7AA', '#FFEDD5', '#FFF4E6',
]

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
  const [dynamicTerms, setDynamicTerms] = useState({})
  const cardRef = useRef(null)

  // 페이지 로딩 시 portfolioData 텍스트로 LLM 용어 추출
  useEffect(() => {
    if (!portfolioData) return
    const texts = [
      ...(portfolioData.portfolio_items || []).map(i => i.selection_reason).filter(Boolean),
      portfolioData.overall_summary,
      portfolioData.portfolio_summary,
    ].filter(Boolean)
    const combined = texts.join('\n')
    if (combined.length < 30) return
    fetch('/api/v1/terms/extract', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: combined }),
    })
      .then(r => r.json())
      .then(d => setDynamicTerms(prev => ({ ...prev, ...(d.terms || {}) })))
      .catch(() => {})
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // 데이터가 없을 때 3초 후에 로딩을 멈추고 에러 표시
  useEffect(() => {
    if (!portfolioData) {
      const timer = setTimeout(() => {
        setIsLoading(false)
      }, 3000)
      return () => clearTimeout(timer)
    }
  }, [portfolioData])

  const handlePdf = () => {
    const el = cardRef.current
    if (!el) return
    const footer = el.querySelector('.pd-footer')
    if (footer) footer.style.display = 'none'
    html2pdf().set({
      margin: [10, 10, 10, 10],
      filename: `${new Date().toISOString().slice(0,10)}_${portfolioRank ? `TOP${portfolioRank}_` : ''}${risk_tier || '포트폴리오'}_${user?.name || user?.userId || 'user'}.pdf`,
      image: { type: 'jpeg', quality: 0.98 },
      html2canvas: { scale: 2, useCORS: true, logging: false },
      jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
      pagebreak: { mode: ['css', 'legacy'] },
    }).from(el).save().then(() => {
      if (footer) footer.style.display = ''
    })
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
      const aiResult = await res.json()
      setAiData(aiResult)
      setAiStatus('done')
      // AI narrative 텍스트로 추가 용어 추출
      const aiTexts = Object.values(aiResult)
        .flatMap(v => [v?.narrative, v?.selection_reason, ...(v?.strengths || []), ...(v?.weaknesses || [])])
        .filter(Boolean)
      const aiCombined = aiTexts.join('\n')
      if (aiCombined.length >= 30) {
        fetch('/api/v1/terms/extract', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: aiCombined }),
        })
          .then(r => r.json())
          .then(d => setDynamicTerms(prev => ({ ...prev, ...(d.terms || {}) })))
          .catch(() => {})
      }
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
      setRiskAnalysis(await res.json())
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
    <DynamicTermProvider extraDict={dynamicTerms}>
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
              return oneLiner ? <div className="pd-tier-summary"><TermText text={oneLiner} /></div> : null
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
            <div className="pd-labeled-bar">
              {sortedItems.map((item, idx) => (
                <div
                  key={item.ticker}
                  className="pd-bar-segment"
                  style={{ width: `${item.weight_pct}%`, background: COLOR_PALETTE[idx % COLOR_PALETTE.length] }}
                  title={`${item.name} ${item.weight_pct.toFixed(1)}%`}
                >
                  <span className="pd-bar-label">
                    {item.name}({item.weight_pct.toFixed(0)}%)
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="pd-divider" />

          {/* 단기 방향성 / 중장기 기대수익률 / 리스크 */}
          {quant_signals && (
            <>
              <div className="pd-section-row pd-two-col">
                {/* 왼쪽: 단기 + 중장기 */}
                <div className="pd-col">
                  <div className="pd-section-label">(단기) 20일 후 예상 수익률</div>
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

                  <div className="pd-section-label pd-section-label-mt">(중장기) 기대수익률 (CAPM 기반)</div>
                  {quant_signals.medium_term?.weighted_ret_12m_pct != null ? (
                    <>
                      <div className={`pd-big-value ${quant_signals.medium_term.weighted_ret_12m_pct >= 0 ? 'pd-pos' : 'pd-neg'}`}>
                        {quant_signals.medium_term.weighted_ret_12m_pct >= 0 ? '+' : ''}
                        {quant_signals.medium_term.weighted_ret_12m_pct.toFixed(1)}%
                        <span className="pd-big-value-sub"> (12M 과거 수익률 기반)</span>
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

                {/* 오른쪽: 리스크 */}
                <div className="pd-col">
                  <div className="pd-section-label">리스크</div>
                  {riskStatus === 'loading' && (
                    <p className="pd-status-msg">⏳ AI 리스크 분석 중...</p>
                  )}
                  {riskStatus === 'done' && riskAnalysis ? (
                    <>
                      <div className="pd-risk-summary"><TermText text={riskAnalysis.risk_summary} /></div>
                      <div className="pd-signal-items">
                        {(riskAnalysis.per_stock || []).map(ps => (
                          <div key={ps.ticker} className="pd-signal-item pd-risk-item">
                            <span className="pd-signal-name">{ps.name}</span>
                            <span className="pd-risk-text pd-neg"><TermText text={ps.risk_text} /></span>
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
                    <div className="pd-interpretation"><TermText text={performance_3y.interpretation} /></div>
                  )}
                </div>
                <div className="pd-col">
                  <div className="pd-section-label">리스크</div>
                  {riskStatus === 'loading' && (
                    <p className="pd-status-msg">⏳ AI 리스크 분석 중...</p>
                  )}
                  {riskStatus === 'done' && riskAnalysis ? (
                    <div className="pd-risk-summary"><TermText text={riskAnalysis.risk_summary} /></div>
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

          {/* 몬테카를로 시뮬레이션 */}
          {monte_carlo_1y && (
            <>
              <div className="pd-section-row">
                <div className="pd-section-label">(몬테카를로) 향후 1년 수익률 (현재 가격 기준)</div>
                <div className="pd-mc-row">
                  <div className="pd-mc-box pd-mc-bear">
                    <div className="pd-mc-label">약세 (10%)</div>
                    <div className="pd-mc-value">{fmtPct(monte_carlo_1y.p10_pct)}</div>
                  </div>
                  <div className="pd-mc-box pd-mc-base">
                    <div className="pd-mc-label">기준 (50%)</div>
                    <div className="pd-mc-value">{fmtPct(monte_carlo_1y.p50_pct)}</div>
                  </div>
                  <div className="pd-mc-box pd-mc-bull">
                    <div className="pd-mc-label">강세 (90%)</div>
                    <div className="pd-mc-value">{fmtPct(monte_carlo_1y.p90_pct)}</div>
                  </div>
                </div>
                {monte_carlo_1y.interpretation && (
                  <div className="pd-interpretation"><TermText text={monte_carlo_1y.interpretation} /></div>
                )}
              </div>
              <div className="pd-divider" />
            </>
          )}


          {/* 종목별 분석 */}
          <div className="pd-section-row pdf-page-break">
            <div className="pd-section-label">종목별 분석</div>

            {aiStatus !== 'done' && (
              <div style={{ marginBottom: 12 }}>
                <button onClick={runAiEnrich} disabled={aiStatus === 'loading'} className="pd-ai-btn">
                  {aiStatus === 'loading' ? '뉴스 분석 중...' : '뉴스 기반 선정 근거 분석'}
                </button>
                {aiStatus === 'error' && <p className="pd-status-msg pd-status-err">AI 분석에 실패했습니다.</p>}
                {aiStatus === 'timeout' && <p className="pd-status-msg pd-status-warn">3분을 초과하여 중단했습니다. 잠시 후 다시 시도해 주세요.</p>}
              </div>
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
                      {narrative && <p className="pd-stock-reason"><TermText text={narrative} /></p>}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="pd-divider" />

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
    </DynamicTermProvider>
  )
}

export default PortfolioDetailPage