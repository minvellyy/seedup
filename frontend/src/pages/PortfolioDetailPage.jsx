import React, { useState, useRef, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import html2pdf from 'html2pdf.js'
import './PortfolioDetailPage.css'

const COLOR_PALETTE = [
  '#C2410C', '#EA580C', '#F97316', '#FB923C',
  '#FDBA74', '#FED7AA', '#FFEDD5', '#FFF4E6',
]

const fmtNum = (v) =>
  v == null ? '-' : new Intl.NumberFormat('ko-KR').format(Math.round(v))
const fmtPct = (v, plus = true) =>
  v == null ? '-' : `${plus && v >= 0 ? '+' : ''}${v.toFixed(1)}%`

function PortfolioDetailPage() {
  const navigate = useNavigate()
  const { state } = useLocation()
  const portfolioData = state?.portfolioData

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

  const handlePdf = () => {
    const el = cardRef.current
    if (!el) return
    html2pdf().set({
      margin: [10, 10, 10, 10],
      filename: `portfolio_${risk_tier || 'result'}.pdf`,
      image: { type: 'jpeg', quality: 0.98 },
      html2canvas: { scale: 2, useCORS: true, logging: false },
      jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
    }).from(el).save()
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
      const res = await fetch('/api/dashboard/portfolio-ai-enrich', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tickers, mode: 'fin' }),
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
            {overall_summary && (
              <div className="pd-summary-text">💬 {overall_summary}</div>
            )}
          </div>

          <div className="pd-divider" />

          {/* 구성비율 */}
          <div className="pd-section-row">
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
                    <p className="pd-status-msg">⏳ AI 리스크 분석 중...</p>
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
                  <div className="pd-interpretation">{monte_carlo_1y.interpretation}</div>
                )}
              </div>
              <div className="pd-divider" />
            </>
          )}

          {/* 종목별 분석 */}
          <div className="pd-section-row">
            <div className="pd-section-label">종목별 분석</div>

            {aiStatus !== 'done' && (
              <div style={{ marginBottom: 12 }}>
                <button onClick={runAiEnrich} disabled={aiStatus === 'loading'} className="pd-ai-btn">
                  {aiStatus === 'loading' ? '⏳ AI 분석 중...' : '✨ AI 분석 실행'}
                </button>
                {aiStatus === 'error' && <p className="pd-status-msg pd-status-err">AI 분석에 실패했습니다.</p>}
                {aiStatus === 'timeout' && <p className="pd-status-msg pd-status-warn">3분을 초과하여 중단했습니다. 잠시 후 다시 시도해 주세요.</p>}
              </div>
            )}

            <div className="pd-stock-list">
              {sortedItems.map((item, idx) => {
                const ai = aiData[item.ticker]
                const reason = ai?.selection_reason || item.selection_reason
                const grade = ai?.fin_grade || item.ai_fin_grade
                const strengths = ai?.strengths || item.ai_strengths || []
                const weaknesses = ai?.weaknesses || item.ai_weaknesses || []
                return (
                  <div key={item.ticker} className="pd-stock-row">
                    <div className="pd-stock-left">
                      <span className="pd-stock-dot" style={{ background: COLOR_PALETTE[idx % COLOR_PALETTE.length] }} />
                      <strong className="pd-stock-name">{item.name}</strong>
                      <span className="pd-stock-code">{item.ticker}</span>
                      {grade && (
                        <span className={`pd-grade-badge pd-grade-${grade}`}>{grade}</span>
                      )}
                      {(ai || item.ai_fin_grade) && (
                        <span className="pd-ai-badge">✨ AI</span>
                      )}
                    </div>
                    <div className="pd-stock-right">
                      {reason && <p className="pd-stock-reason">{reason}</p>}
                      <div className="pd-stock-tags">
                        {strengths.map((s, i) => (
                          <span key={i} className="pd-tag pd-tag-pos">✓ {s}</span>
                        ))}
                        {weaknesses.map((w, i) => (
                          <span key={i} className="pd-tag pd-tag-neg"> {w}</span>
                        ))}
                      </div>
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
  )
}

export default PortfolioDetailPage