import React from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import './Header.css'

function Header() {
  const navigate = useNavigate()
  const location = useLocation()
  const { isLoggedIn, logout, user } = useAuth()

  // 개인화 설문 페이지에서는 비활성화된 새로운 네비게이션 바
  const showDisabledNav = location.pathname === '/survey' || location.pathname === '/survey/investment'
  // 로그인 후 홈 화면과 대시보드, 추천 페이지 등에서는 활성화된 새로운 네비게이션 바
  const showActiveNav = isLoggedIn && (
    location.pathname === '/' || 
    location.pathname === '/dashboard' || 
    location.pathname === '/recommendations' ||
    location.pathname === '/mypage' ||
    location.pathname === '/chat' ||
    location.pathname === '/support' ||
    location.pathname === '/stocks' ||
    location.pathname.startsWith('/stock/') ||
    location.pathname.startsWith('/etf/') ||
    location.pathname.startsWith('/portfolio/')
  )
  
  const handleLogoClick = () => {
    if (isLoggedIn) {
      navigate('/dashboard')
    } else {
      navigate('/')
    }
  }

  const handleNavClick = (path) => {
    navigate(path)
  }

  const handleLogout = () => {
    logout()
    navigate('/')
  }

  // 개인화 설문 페이지용 네비게이션 바 (비활성화)
  if (showDisabledNav) {
    return (
      <header className="header">
        <div className="header-container">
          <div className="logo" onClick={handleLogoClick}>
            <span className="logo-text">SeedUp</span>
          </div>
          <nav className="nav-menu">
            <div className="nav-left">
              <button className="nav-item disabled" disabled>홈</button>
              <button className="nav-item disabled" disabled>포트폴리오</button>
              <button className="nav-item disabled" disabled>개별종목</button>
              <button className="nav-item disabled" disabled>챗봇</button>
              <button className="nav-item disabled" disabled>고객센터</button>
            </div>
            <div className="nav-right">
              <button className="nav-item disabled" disabled>로그아웃</button>
              <button className="nav-item disabled" disabled>마이페이지</button>
            </div>
          </nav>
        </div>
      </header>
    )
  }

  // 로그인 후 홈 화면용 네비게이션 바 (활성화)
  if (showActiveNav) {
    return (
      <header className="header">
        <div className="header-container">
          <div className="logo" onClick={handleLogoClick}>
            <span className="logo-text">SeedUp</span>
          </div>
          <nav className="nav-menu">
            <div className="nav-left">
              <button className="nav-item" onClick={() => handleNavClick('/')}>홈</button>
              <button className="nav-item" onClick={() => handleNavClick('/recommendations')}>포트폴리오</button>
              <button className="nav-item" onClick={() => handleNavClick('/stocks')}>개별종목</button>
              <button className="nav-item" onClick={() => handleNavClick('/chat')}>챗봇</button>
              <button className="nav-item" onClick={() => handleNavClick('/support')}>고객센터</button>
            </div>
            <div className="nav-right">
              <button className="nav-item logout-btn" onClick={handleLogout}>로그아웃</button>
              <button className="nav-item" onClick={() => handleNavClick('/mypage')}>마이페이지</button>
            </div>
          </nav>
        </div>
      </header>
    )
  }

  // 기본 네비게이션 바 (로그인 전)
  return (
    <header className="header">
      <div className="header-container">
        <div className="logo" onClick={handleLogoClick}>
          <span className="logo-text">SeedUp</span>
        </div>
        <nav className="nav-menu">
          <div className="nav-left">
            <button 
              className="nav-item"
              onClick={() => handleNavClick('/about')}
            >
              서비스 소개
            </button>
            <button 
              className="nav-item"
              onClick={() => handleNavClick('/support')}
            >
              고객센터
            </button>
          </div>
          <div className="nav-right">
            {isLoggedIn ? (
              <>
                <button 
                  className="nav-item logout-btn"
                  onClick={handleLogout}
                >
                  로그아웃
                </button>
              </>
            ) : (
              <>
                <button 
                  className="nav-item"
                  onClick={() => handleNavClick('/login')}
                >
                  로그인
                </button>
                <button 
                  className="nav-item"
                  onClick={() => handleNavClick('/signup')}
                >
                  회원가입
                </button>
              </>
            )}
          </div>
        </nav>
      </div>
    </header>
  )
}

export default Header
