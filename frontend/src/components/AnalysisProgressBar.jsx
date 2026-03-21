import { useEffect, useState, useRef } from 'react'
import './AnalysisProgressBar.css'

const DEFAULT_STEPS = [
  { label: '투자 원칙 적합도 분석', icon: '📋' },
  { label: '기업 재무 데이터 검토', icon: '🏢' },
  { label: '산업 동향 파악', icon: '📊' },
  { label: 'AI 리포트 생성', icon: '✍️' },
]

export default function AnalysisProgressBar({ loading, steps }) {
  const STEPS = steps || DEFAULT_STEPS
  const [progress, setProgress] = useState(0)
  const [stepIdx, setStepIdx] = useState(0)
  const progressRef = useRef(0)
  const intervalRef = useRef(null)
  const stepIntervalRef = useRef(null)

  useEffect(() => {
    if (loading) {
      setProgress(0)
      setStepIdx(0)
      progressRef.current = 0

      // easing: 남은 거리의 2.5%씩 200ms마다 증가 → 초반 빠르고 85%에 가까울수록 느려짐
      // 0%→50% ≈ 5s, 50%→75% ≈ 10s, 75%→85% ≈ 20s (총 약 35s)
      intervalRef.current = setInterval(() => {
        const remaining = 85 - progressRef.current
        const increment = Math.max(0.15, remaining * 0.025)
        progressRef.current = Math.min(progressRef.current + increment, 85)
        setProgress(progressRef.current)
        if (progressRef.current >= 85) clearInterval(intervalRef.current)
      }, 200)

      // 단계 메시지 순환 — 총 예상 35s 기준으로 분배
      stepIntervalRef.current = setInterval(() => {
        setStepIdx(prev => Math.min(prev + 1, STEPS.length - 1))
      }, Math.floor(35000 / STEPS.length))
    } else {
      clearInterval(intervalRef.current)
      clearInterval(stepIntervalRef.current)
      setProgress(100)
      setStepIdx(STEPS.length - 1)
    }

    return () => {
      clearInterval(intervalRef.current)
      clearInterval(stepIntervalRef.current)
    }
  }, [loading])

  return (
    <div className="apb-container">
      <div className="apb-bar-wrap">
        <div className="apb-bar" style={{ width: `${progress}%` }} />
      </div>
      <div className="apb-meta">
        <span className="apb-label">
          {loading
            ? `${STEPS[stepIdx].icon} ${STEPS[stepIdx].label} 중...`
            : '✅ 분석 완료'}
        </span>
        <span className="apb-percent">{Math.round(progress)}%</span>
      </div>
      <div className="apb-steps">
        {STEPS.map((s, i) => (
          <div
            key={i}
            className={`apb-step ${i < stepIdx ? 'done' : i === stepIdx && loading ? 'active' : i === stepIdx && !loading ? 'done' : ''}`}
          >
            <span className="apb-step-dot" />
            <span className="apb-step-text">{s.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
