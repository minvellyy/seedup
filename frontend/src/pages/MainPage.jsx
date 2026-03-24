import React, { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import './MainPage.css'
import Hero from '../components/Hero/Hero'

// ----- Premium line SVG icons (no external libs) -----
const IconBase = ({ children, size = 56, strokeWidth = 2 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
    style={{ display: 'block' }}
  >
    <g stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round">
      {children}
    </g>
  </svg>
)

const SurveyIcon = (props) => (
  <IconBase {...props}>
    {/* clipboard */}
    <path d="M9 4h6" />
    <path d="M10 3h4a2 2 0 0 1 2 2v1H8V5a2 2 0 0 1 2-2Z" />
    <path d="M7 6h10a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2Z" />
    {/* check list */}
    <path d="M8.5 11.5l.8.8 1.7-1.7" />
    <path d="M12.5 11.5H16.5" />
    <path d="M8.5 15.5l.8.8 1.7-1.7" />
    <path d="M12.5 15.5H16.5" />
  </IconBase>
)

const AIIcon = (props) => (
  <IconBase {...props}>
    {/* brain-ish / circuit */}
    <path d="M9 8a3 3 0 0 1 6 0" />
    <path d="M7.5 10a2.5 2.5 0 0 1 1.5-2.3" />
    <path d="M16.5 10A2.5 2.5 0 0 0 15 7.7" />
    <path d="M8 10.5v1.5a2 2 0 0 0 2 2h.5" />
    <path d="M16 10.5v1.5a2 2 0 0 1-2 2h-.5" />
    <path d="M10.5 14v3" />
    <path d="M13.5 14v3" />
    <path d="M9.5 17h5" />
    {/* circuit nodes */}
    <path d="M6 12h-2" />
    <path d="M20 12h-2" />
    <path d="M4 12h0" />
    <path d="M20 12h0" />
  </IconBase>
)

const ChartIcon = (props) => (
  <IconBase {...props}>
    {/* axis */}
    <path d="M5 19V5" />
    <path d="M5 19h14" />
    {/* bars + line */}
    <path d="M8 16v-4" />
    <path d="M12 16v-7" />
    <path d="M16 16v-10" />
    <path d="M8 12l4-3 4 2 3-4" />
  </IconBase>
)

const TargetIcon = (props) => (
  <IconBase {...props}>
    <path d="M12 21a9 9 0 1 1 9-9" />
    <path d="M12 17a5 5 0 1 1 5-5" />
    <path d="M12 13a1 1 0 1 1 1-1" />
    <path d="M21 3l-6 6" />
    <path d="M17 3h4v4" />
  </IconBase>
)

// optional: smaller icon size for mockup cards
const SmallIconWrap = ({ children }) => (
  <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
    {children}
  </span>
)

function MainPage() {
  const navigate = useNavigate()
  const { isLoggedIn } = useAuth()

  // 로그인된 사용자는 대시보드로 리다이렉트
  useEffect(() => {
    if (isLoggedIn) {
      navigate('/dashboard')
    }
  }, [isLoggedIn, navigate])

  useEffect(() => {
    const handleScroll = () => {
      const cards = document.querySelectorAll('[data-scroll-card]')
      const fadeElements = document.querySelectorAll('[data-scroll-fade]')

      if (cards.length > 0) {
        cards.forEach((card) => {
          const rect = card.getBoundingClientRect()
          const windowHeight = window.innerHeight
          if (rect.top < windowHeight * 0.85 && rect.bottom > 0) {
            card.classList.add('fade-in-active')
          }
        })
      }

      fadeElements.forEach((element) => {
        const rect = element.getBoundingClientRect()
        const windowHeight = window.innerHeight
        if (rect.top < windowHeight * 0.85) {
          element.classList.add('fade-in-active')
        }
      })
    }

    setTimeout(() => handleScroll(), 300)

    window.addEventListener('scroll', handleScroll, { passive: true })
    window.addEventListener('resize', handleScroll, { passive: true })

    return () => {
      window.removeEventListener('scroll', handleScroll)
      window.removeEventListener('resize', handleScroll)
    }
  }, [])

  return (
    <main className="main-page">
      <Hero />

      {/* 맞춤형 설문 섹션 */}
      <section className="toss-section">
        <div className="toss-container">
          <div className="toss-text" data-scroll-fade>
            <h2>투자의 첫 단계,<br/>나를 아는 것부터</h2>
          </div>

          <div className="toss-visual" data-scroll-fade>
            <div className="feature-visual-card">
              <div className="visual-icon big-icon" aria-hidden="true">
                <SurveyIcon />
              </div>
              <h3>맞춤형 설문</h3>
              <p>당신의 투자 목표와<br/>성향을 파악하는<br/>개인화된 설문조사</p>
              <div className="visual-badge">
                <span>✓</span> 간편한 설문
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 폰 목업 섹션 */}
      <section className="toss-section alt">
        <div className="toss-container reverse">
          <div className="toss-visual" data-scroll-fade>
            <div className="phone-mockup">
              <div className="mockup-screen">
                <div className="mockup-header">
                  <span className="mockup-logo">SeedUP</span>
                </div>

                <div className="mockup-card card-1">
                  <div className="card-icon" aria-hidden="true">
                    <SmallIconWrap><ChartIcon size={22} strokeWidth={2} /></SmallIconWrap>
                  </div>
                  <div className="card-content">
                    <div className="card-title">포트폴리오 총액</div>
                    <div className="card-amount">5,120,000원</div>
                    <div className="card-change positive">+12.5%</div>
                  </div>
                </div>

                <div className="mockup-card card-2">
                  <div className="card-icon" aria-hidden="true">
                    <SmallIconWrap><TargetIcon size={22} strokeWidth={2} /></SmallIconWrap>
                  </div>
                  <div className="card-content">
                    <div className="card-title">추천 종목</div>
                    <div className="card-subtitle">삼성전자, 카카오뱅크</div>
                  </div>
                </div>

                <div className="mockup-card card-3">
                  <div className="card-icon" aria-hidden="true">
                    <SmallIconWrap><SurveyIcon size={22} strokeWidth={2} /></SmallIconWrap>
                  </div>
                  <div className="card-content">
                    <div className="card-title">맞춤형 분석</div>
                    <div className="card-subtitle">AI 기반 포트폴리오 제안</div>
                  </div>
                </div>

              </div>
            </div>
          </div>

          <div className="toss-text" data-scroll-fade>
            <h2>내 자산 관리,<br/>지출부터 투자까지<br/>똑똑하게</h2>
          </div>
        </div>
      </section>

      {/* AI 분석 섹션 */}
      <section className="toss-section">
        <div className="toss-container">
          <div className="toss-text" data-scroll-fade>
            <h2>AI 투자분석,<br/>데이터로 찾는 최적의 전략</h2>
          </div>

          <div className="toss-visual" data-scroll-fade>
            <div className="feature-visual-card">
              <div className="visual-icon big-icon" aria-hidden="true">
                <AIIcon />
              </div>
              <h3>AI 분석</h3>
              <p>입력 정보를 바탕으로<br/>AI가 분석하여<br/>최적의 포트폴리오 제안</p>
              <div className="visual-badge">
                <span>✓</span> 실시간 분석
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 실시간 추적 섹션 */}
      <section className="toss-section alt">
        <div className="toss-container reverse">
          <div className="toss-visual" data-scroll-fade>
            <div className="feature-visual-card">
              <div className="visual-icon big-icon" aria-hidden="true">
                <ChartIcon />
              </div>
              <h3>실시간 추적</h3>
              <p>포트폴리오의 성과를<br/>실시간으로<br/>모니터링하고 관리</p>
              <div className="visual-badge">
                <span>✓</span> 실시간 업데이트
              </div>
            </div>
          </div>

          <div className="toss-text" data-scroll-fade>
            <h2>내 투자 상태,<br/>지금 바로 확인해보세요</h2>
          </div>
        </div>
      </section>

      <section className="gallery-section">
        <div className="gallery-header" data-scroll-fade>
          <h2>SeedUP만의 특별함</h2>
          <p>더 나은 투자 경험을 위한 혁신</p>
        </div>

        <div className="image-gallery">
          <div className="gallery-card" data-scroll-card>
            <div className="gallery-image">
              <img src="/images/surveyper.png" alt="설문 조사" />
            </div>
            <div className="gallery-info">
              <h3>복잡한 투자, 한 번의 설문으로</h3>
              <p>당신의 투자 성향과 목표를 파악하는 맞춤형 설문</p>
            </div>
          </div>

          <div className="gallery-card" data-scroll-card>
            <div className="gallery-image">
              <img src="/images/ai.png" alt="AI 분석" />
            </div>
            <div className="gallery-info">
              <h3>전문가 수준의 AI 분석</h3>
              <p>최신 AI 기술로 최적의 포트폴리오를 제안합니다</p>
            </div>
          </div>

          <div className="gallery-card" data-scroll-card>
            <div className="gallery-image">
              <img src="/images/secu.png" alt="보안" />
            </div>
            <div className="gallery-info">
              <h3>개인정보 보호 최우선</h3>
              <p>철저한 보안으로 당신의 정보를 안전하게 보호합니다</p>
            </div>
          </div>

          <div className="gallery-card" data-scroll-card>
            <div className="gallery-image">
              <img src="/images/sett.png" alt="설정" />
            </div>
            <div className="gallery-info">
              <h3>언제든지 설정 변경 가능</h3>
              <p>투자 전략을 실시간으로 조정하고 관리하세요</p>
            </div>
          </div>
        </div>
      </section>
    </main>
  )
}

export default MainPage