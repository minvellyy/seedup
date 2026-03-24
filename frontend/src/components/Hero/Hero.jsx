import React from 'react'
import { useNavigate } from 'react-router-dom'
import './hero.css'

export default function Hero() {
  const navigate = useNavigate()

  return (
    <section className="hero">
      <div className="hero-container">
        <div className="hero-content">
          <div className="hero-label">SeedUP</div>
          <h1 className="hero-title">
            나에게 맞는<br />
            투자 설계
          </h1>
          <p className="hero-description">
            개인의 금융 목표와 성향에 맞춘 맞춤형 투자 설계 서비스
          </p>

          <div className="hero-actions">
            <button className="btn-primary" onClick={() => navigate('/signup')}>
              Sign Up
            </button>
            <button className="btn-secondary" onClick={() => navigate('/login')}>
              Login
            </button>
          </div>
        </div>
        
        <div className="hero-visual">
          <div className="visual-circle visual-circle-1"></div>
          <div className="visual-circle visual-circle-2"></div>
          <div className="visual-circle visual-circle-3"></div>
        </div>
      </div>
    </section>
  )
}
