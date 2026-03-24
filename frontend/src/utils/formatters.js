/**
 * 백분율 포맷팅 (예: 5.2%)
 */
export const fmtPct = (v) => (v == null ? '-' : `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`)

/**
 * 숫자 포맷팅 (한국어 로케일)
 */
export const fmtNum = (v) => (v == null ? '-' : new Intl.NumberFormat('ko-KR').format(Math.round(v)))

/**
 * 색상 팔레트 (자산 배분 시각화용)
 */
export const COLOR_PALETTE = [
  '#C2410C', '#EA580C', '#F97316', '#FB923C',
  '#FDBA74', '#FED7AA', '#FFEDD5', '#FFF4E6',
]

/**
 * 수익률 색상 결정 (양수=주황, 음수=파랑)
 */
export const getReturnColor = (value) => value >= 0 ? '#EA580C' : '#3B82F6'
