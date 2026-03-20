/**
 * TermTooltip / TermText / DynamicTermProvider
 *
 * - <TermTooltip term="OPM">OPM</TermTooltip>
 *   : 단어 하나를 말풍선 툴팁으로 래핑
 *
 * - <TermText text="...OPM, PER 등이 포함된 AI 분석 텍스트..." />
 *   : 텍스트 문자열에서 금융 용어를 자동 감지해 툴팁으로 치환
 *
 * - <DynamicTermProvider extraDict={{ 용어: "설명", ... }}>
 *   : 페이지 단위로 LLM이 추출한 동적 용어를 주입. 하위 모든 TermText에 적용.
 */

import React, { useState, useRef, useMemo, useContext } from 'react'
import './TermTooltip.css'

// ── 정적 금융 용어 사전 ────────────────────────────────────────────────────
export const TERM_DICT = {
  'OPM':    '영업이익률 — 매출에서 실제 영업으로 벌어들인 이익의 비율. 높을수록 수익성이 좋습니다.',
  'ROA':    '총자산이익률 — 보유한 자산으로 얼마나 이익을 냈는지를 나타냅니다. 높을수록 자산을 효율적으로 활용하는 기업입니다.',
  'PER':    '주가수익비율 — 현재 주가가 이익에 비해 비싼지 싼지를 나타내는 수치. 낮을수록 상대적으로 저렴하게 거래되고 있습니다.',
  'PBR':    '주가순자산비율 — 회사 장부상 자산 가치 대비 주가 수준. 1 미만이면 자산 가치보다 싸게 거래되는 것입니다.',
  'FCF':    '잉여현금흐름 — 사업 운영과 투자 후 실제로 남는 현금. 배당·투자 여력을 보여주는 지표입니다.',
  'CFO':    '영업현금흐름 — 영업 활동으로 실제 발생한 현금 흐름. 순이익과 달리 실제 현금 유입·유출을 반영합니다.',
  'CDMO':   '바이오의약품 위탁 개발·생산 서비스 — 제약사 대신 의약품을 개발·생산해 주는 사업입니다.',
  'HBM':    '고대역폭메모리 — AI 연산에 특화된 고성능 반도체 메모리. AI 서버 수요가 늘수록 HBM 수요도 증가합니다.',
  'ETF':    '상장지수펀드 — 여러 종목을 묶어 주식처럼 거래소에서 사고팔 수 있는 펀드입니다.',
  'ESG':    '환경·사회·지배구조 — 기업의 비재무적 지속 가능성을 평가하는 기준입니다.',
  'YoY':    '전년 동기 대비 — 작년 같은 기간과 비교한 성장률입니다.',
  'TTM':    '최근 12개월 합산 — 현재 기준 직전 1년 누적 데이터를 기반으로 계산한 지표입니다.',
  'BUY':    '매수 추천 — 이 종목을 사는 것이 유리하다는 AI 분석 의견입니다.',
  'HOLD':   '보유 추천 — 현재 보유 상태를 유지하는 것이 좋다는 AI 분석 의견입니다.',
  'SELL':   '매도 추천 — 이 종목을 파는 것이 유리하다는 AI 분석 의견입니다.',
  '부채비율':  '자기 자본 대비 빌린 돈의 비율. 낮을수록 재무적으로 안정적인 기업입니다.',
  '유동비율':  '단기 부채를 갚을 수 있는 여유 자금 수준. 높을수록 단기 채무 상환 능력이 좋습니다.',
  '밸류체인':  '제품이 원자재에서 최종 소비자에게 전달되기까지의 전체 공급·생산 과정입니다.',
  '업사이클':  '산업이 침체기를 벗어나 호황 국면에 진입하는 시기를 뜻합니다.',
  '다운사이클': '산업이 호황에서 침체 국면으로 접어드는 시기를 뜻합니다.',
  '레짐':    '시장 흐름의 국면. 상승(bull) 또는 하락(bear) 장세 등 시장의 큰 방향성을 나타냅니다.',
  'RAG':    '검색 증강 생성 — 관련 문서를 검색해 AI 답변 품질을 높이는 기술입니다.',
  'NLG':    '자연어 생성 — AI가 데이터를 사람이 읽기 쉬운 문장으로 변환하는 기술입니다.',
  'LLM':    '대형 언어 모델 — GPT 등 대규모 텍스트로 학습된 AI 언어 모델입니다.',
  '시가총액':  '현재 주가 × 발행 주식 수. 기업의 시장 전체 가치를 나타냅니다.',
  '영업이익률': 'OPM과 같은 의미. 매출에서 실제 영업으로 벌어들인 이익의 비율입니다.',
  '총자산이익률': 'ROA와 같은 의미. 보유 자산으로 얼마나 이익을 냈는지를 나타냅니다.',
}

// 정적 사전만으로 만든 기본 정규식 (동적 항목 없을 때 재사용)
const _buildRegex = (terms) => {
  if (terms.length === 0) return null
  const escaped = terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  return new RegExp(`(${escaped.join('|')})`, 'g')
}
const STATIC_SORTED = Object.keys(TERM_DICT).sort((a, b) => b.length - a.length)
const STATIC_REGEX   = _buildRegex(STATIC_SORTED)

// ── 동적 용어 Context ──────────────────────────────────────────────────────
const DynamicTermContext = React.createContext({})

/**
 * 페이지 최상위에 배치. extraDict에 LLM이 추출한 { 용어: 설명 } 을 전달하면
 * 하위 모든 TermText 컴포넌트에서 자동으로 툴팁이 활성화됩니다.
 */
export function DynamicTermProvider({ children, extraDict = {} }) {
  return (
    <DynamicTermContext.Provider value={extraDict}>
      {children}
    </DynamicTermContext.Provider>
  )
}

// ── 단일 툴팁 컴포넌트 ────────────────────────────────────────────────────
/**
 * definition prop 을 우선 사용. 없으면 정적 TERM_DICT → Context 순으로 폴백.
 */
export function TermTooltip({ term, definition, children }) {
  const [visible, setVisible] = useState(false)
  const [pos, setPos] = useState({ top: true })
  const wrapRef = useRef(null)
  const dynamicDict = useContext(DynamicTermContext)

  const def = definition ?? TERM_DICT[term] ?? dynamicDict[term]
  if (!def) return <>{children}</>

  const handleMouseEnter = () => {
    if (wrapRef.current) {
      const rect = wrapRef.current.getBoundingClientRect()
      setPos({ top: rect.top > 120 })
    }
    setVisible(true)
  }

  return (
    <span
      className="term-tooltip-wrap"
      ref={wrapRef}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={() => setVisible(false)}
    >
      <span className="term-highlight">{children}</span>
      {visible && (
        <span className={`term-bubble ${pos.top ? 'bubble-top' : 'bubble-bottom'}`}>
          <strong className="term-bubble-term">{term}</strong>
          <span className="term-bubble-def">{def}</span>
        </span>
      )}
    </span>
  )
}

// ── 텍스트 자동 파싱 컴포넌트 ─────────────────────────────────────────────
/**
 * text 문자열 내 용어를 자동으로 감지해 <TermTooltip>으로 치환합니다.
 * DynamicTermProvider 안에 있으면 LLM 추출 용어도 함께 인식합니다.
 */
export function TermText({ text, className }) {
  const dynamicDict = useContext(DynamicTermContext)

  // 동적 용어가 있을 때만 정규식을 재계산 (성능 최적화)
  const { mergedDict, termRegex } = useMemo(() => {
    const hasDynamic = Object.keys(dynamicDict).length > 0
    if (!hasDynamic) {
      return { mergedDict: TERM_DICT, termRegex: STATIC_REGEX }
    }
    const merged = { ...TERM_DICT, ...dynamicDict }
    const sorted = Object.keys(merged).sort((a, b) => b.length - a.length)
    return { mergedDict: merged, termRegex: _buildRegex(sorted) }
  }, [dynamicDict])

  if (!text || !termRegex) return <span className={className}>{text}</span>

  const parts = text.split(termRegex)

  return (
    <span className={className}>
      {parts.map((part, i) => {
        const def = mergedDict[part]
        if (def) {
          return (
            <TermTooltip key={i} term={part} definition={def}>
              {part}
            </TermTooltip>
          )
        }
        return <React.Fragment key={i}>{part}</React.Fragment>
      })}
    </span>
  )
}

export default TermTooltip

