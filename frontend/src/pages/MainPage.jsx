import React from 'react'
import { useNavigate } from 'react-router-dom'
import './MainPage.css'

function MainPage() {
  const navigate = useNavigate()

  return (
    <main className="main-page">
      <div className="hero-section">
        <div className="hero-content">
          <h1 className="hero-title">나에게 맞는 투자 설계</h1>
          <p className="hero-subtitle">
            개인의 금융 목표와 성향에 맞춘<br />
            맞춤형 투자 설계 서비스
          </p>
          
          <div className="cta-buttons">
            <button 
              className="btn btn-primary"
              onClick={() => navigate('/signup')}
            >
              회원가입하기
            </button>
            <button 
              className="btn btn-secondary"
              onClick={() => navigate('/login')}
            >
              이미 계정이 있으신가요? 로그인
            </button>
          </div>
        </div>
      </div>

      <div className="features-section">
        <h2>주요 기능</h2>
        <div className="features-grid">
          <div className="feature-card">
            <div className="feature-icon">📋</div>
            <h3>맞춤형 설문</h3>
            <p>당신의 투자 목표와 성향을 파악하는 개인화된 설문조사</p>
          </div>
          <div className="feature-card">
            <div className="feature-icon">🎯</div>
            <h3>AI 분석</h3>
            <p>입력 정보를 바탕으로 AI가 분석하여 최적의 포트폴리오 제안</p>
          </div>
          <div className="feature-card">
            <div className="feature-icon">📊</div>
            <h3>실시간 추적</h3>
            <p>포트폴리오의 성과를 실시간으로 모니터링하고 관리</p>
          </div>
        </div>
      </div>

      <div className="info-section">
        <h2>SeedUp만의 특별함</h2>
        <ul className="info-list">
          <li>✓ 복잡한 투자, 한 번의 설문으로 시작하세요</li>
          <li>✓ 전문가 수준의 AI 분석 기술 적용</li>
          <li>✓ 개인정보 보호 최우선</li>
          <li>✓ 언제든지 설정 변경 가능</li>
        </ul>
      </div>
    </main>
  )
}

export default MainPage
