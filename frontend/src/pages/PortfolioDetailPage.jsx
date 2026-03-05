import React from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import './PortfolioDetailPage.css'

// 주황색 계열 팔레트
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

  if (!portfolioData) {
    return (
      <div className="portfolio-detail-page">
        <div className="pd-error-box">
          <p>포트폴리오 데이터를 불러올 수 없습니다. 추천 목록에서 다시 접근해 주세요.</p>
          <button onClick={() => navigate('/recommendations')} className="pd-back-btn">
            ← 추천 목록으로
          </button>
        </div>
      </div>
    )
  }

  const {
    risk_tier, risk_grade, overall_summary,
    portfolio_items = [], buy_plan = [],
    performance_3y, monte_carlo_1y,
    investable_amount_krw, total_invested_krw, leftover_krw,
  } = portfolioData

  const sortedItems = [...portfolio_items].sort((a, b) => b.weight_pct - a.weight_pct)

  return (
    <div className="portfolio-detail-page">
      <div className="portfolio-detail-container">

        <button onClick={() => navigate('/recommendations')} className="pd-back-btn">
          ← 추천 목록으로
        </button>

        {/* 헤더 */}
        <div className="portfolio-detail-header">
          <div className="pd-header-badges">
            <span className="pd-risk-grade">{risk_grade}</span>
            <span className="pd-risk-tier">{risk_tier}</span>
          </div>
          <h1 className="portfolio-detail-name">나의 맞춤 포트폴리오</h1>
          {overall_summary && (
            <p className="portfolio-summary">{overall_summary}</p>
          )}
        </div>

        {/* 투자 금액 요약 */}
        {investable_amount_krw != null && (
          <section className="pd-section pd-amount-section">
            <h2 className="pd-section-heading">투자 금액 요약</h2>
            <div className="pd-amount-grid">
              <div className="pd-amount-card">
                <div className="pd-amount-label">투자 가능 금액</div>
                <div className="pd-amount-value">{fmtNum(investable_amount_krw)}원</div>
              </div>
              <div className="pd-amount-card pd-amount-card--invested">
                <div className="pd-amount-label">실제 투자 금액</div>
                <div className="pd-amount-value">{fmtNum(total_invested_krw)}원</div>
              </div>
              <div className="pd-amount-card">
                <div className="pd-amount-label">잔여 금액</div>
                <div className="pd-amount-value">{fmtNum(leftover_krw)}원</div>
              </div>
            </div>
          </section>
        )}

        {/* 구성 비중 바 */}
        <section className="pd-section composition-section">
          <h2 className="pd-section-heading">종목 구성 비중</h2>
          <div className="composition-bar">
            {sortedItems.map((item, idx) => (
              <div
                key={item.ticker}
                className="composition-segment"
                style={{
                  width: `${item.weight_pct}%`,
                  backgroundColor: COLOR_PALETTE[idx % COLOR_PALETTE.length],
                }}
                title={`${item.name}: ${item.weight_pct.toFixed(1)}%`}
              />
            ))}
          </div>
          <div className="composition-legend">
            {sortedItems.map((item, idx) => (
              <div key={item.ticker} className="legend-item">
                <span className="legend-color" style={{ backgroundColor: COLOR_PALETTE[idx % COLOR_PALETTE.length] }} />
                <span className="legend-name">{item.name}</span>
                <span className="legend-code">{item.ticker}</span>
                <span className="legend-type">{item.asset_type}</span>
                <span className="legend-percent">{item.weight_pct.toFixed(1)}%</span>
              </div>
            ))}
          </div>

          {/* 편입 이유 */}
          <div className="pd-items-detail">
            {sortedItems.map((item) => (
              item.selection_reason && (
                <div key={item.ticker} className="pd-item-reason">
                  <strong>{item.name}</strong>
                  <span>{item.selection_reason}</span>
                </div>
              )
            ))}
          </div>
        </section>

        {/* 매수 계획 */}
        {buy_plan.length > 0 && (
          <section className="pd-section">
            <h2 className="pd-section-heading">매수 계획</h2>
            <div className="pd-table-wrap">
              <table className="pd-buy-table">
                <thead>
                  <tr>
                    <th>종목</th>
                    <th>현재가</th>
                    <th>수량</th>
                    <th>투자금액</th>
                    <th>1년 기대수익</th>
                    <th>근거</th>
                  </tr>
                </thead>
                <tbody>
                  {buy_plan.map((bp) => (
                    <tr key={bp.ticker}>
                      <td>
                        <div className="pd-bp-name">{bp.name}</div>
                        <div className="pd-bp-code">{bp.ticker}</div>
                      </td>
                      <td>{fmtNum(bp.price_krw)}원</td>
                      <td>{bp.shares}주</td>
                      <td>{fmtNum(bp.allocated_budget_krw)}원</td>
                      <td>
                        <span className={bp.expected_return_1y_pct >= 0 ? 'pd-pos' : 'pd-neg'}>
                          {fmtPct(bp.expected_return_1y_pct)}
                        </span>
                      </td>
                      <td className="pd-rationale">{bp.rationale}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* 3년 백테스트 성과 */}
        {performance_3y && (
          <section className="pd-section">
            <h2 className="pd-section-heading">3년 백테스트 분석</h2>
            {performance_3y.period && (
              <p className="pd-period">{performance_3y.period}</p>
            )}
            <div className="pd-perf-grid">
              <div className="pd-perf-card pd-perf-card--ret">
                <div className="pd-perf-label">연환산 수익률</div>
                <div className="pd-perf-value">{fmtPct(performance_3y.ann_return_pct)}</div>
              </div>
              <div className="pd-perf-card">
                <div className="pd-perf-label">연간 변동성</div>
                <div className="pd-perf-value pd-vol">{fmtPct(performance_3y.ann_vol_pct, false)}</div>
              </div>
              <div className="pd-perf-card">
                <div className="pd-perf-label">최대 낙폭 (MDD)</div>
                <div className="pd-perf-value pd-mdd">{fmtPct(performance_3y.mdd_pct, false)}</div>
              </div>
              <div className="pd-perf-card">
                <div className="pd-perf-label">샤프 지수</div>
                <div className="pd-perf-value">{performance_3y.sharpe?.toFixed(2) ?? '-'}</div>
              </div>
            </div>
            {performance_3y.interpretation && (
              <div className="pd-interpretation">{performance_3y.interpretation}</div>
            )}
          </section>
        )}

        {/* 몬테카를로 시뮬레이션 */}
        {monte_carlo_1y && (
          <section className="pd-section">
            <h2 className="pd-section-heading">1년 수익률 시나리오 (몬테카를로)</h2>
            <div className="pd-mc-grid">
              <div className="pd-mc-card pd-mc-bear">
                <div className="pd-mc-label">하락 시나리오 (10%)</div>
                <div className="pd-mc-value">{fmtPct(monte_carlo_1y.p10_pct)}</div>
              </div>
              <div className="pd-mc-card pd-mc-base">
                <div className="pd-mc-label">기준 시나리오 (50%)</div>
                <div className="pd-mc-value">{fmtPct(monte_carlo_1y.p50_pct)}</div>
              </div>
              <div className="pd-mc-card pd-mc-bull">
                <div className="pd-mc-label">상승 시나리오 (90%)</div>
                <div className="pd-mc-value">{fmtPct(monte_carlo_1y.p90_pct)}</div>
              </div>
            </div>
            {monte_carlo_1y.interpretation && (
              <div className="pd-interpretation">{monte_carlo_1y.interpretation}</div>
            )}
          </section>
        )}

        {/* 투자 유의사항 */}
        <section className="pd-section pd-notice-section">
          <h2 className="pd-section-heading">투자 유의사항</h2>
          <ul className="pd-notice-list">
            <li>본 포트폴리오는 AI가 생성한 참고용 추천이며, 투자 결정의 책임은 투자자 본인에게 있습니다.</li>
            <li>과거 수익률이 미래 수익을 보장하지 않으며, 시장 상황에 따라 손실이 발생할 수 있습니다.</li>
            <li>투자 전 개인의 투자 성향과 재무 상태를 고려하여 신중히 결정하시기 바랍니다.</li>
            <li>정기적인 리밸런싱을 통해 목표 자산 배분을 유지하는 것이 중요합니다.</li>
          </ul>
        </section>

      </div>
    </div>
  )
}

export default PortfolioDetailPage
