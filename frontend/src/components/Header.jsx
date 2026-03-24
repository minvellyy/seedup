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
            <span className="logo-text">SeedUP</span>
          </div>
          <nav className="nav-menu">
            <div className="nav-left">
              <button className="nav-item disabled" disabled>Home</button>
              <button className="nav-item disabled" disabled>Portfolio</button>
              <button className="nav-item disabled" disabled>Stocks</button>
              <button className="nav-item disabled" disabled>Chatbot</button>
              <button className="nav-item disabled" disabled>Support</button>
            </div>
            <div className="nav-right">
              <button className="nav-item disabled" disabled>Logout</button>
              <button className="nav-item nav-avatar disabled" disabled>
                <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>
              </button>
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
            <span className="logo-text">SeedUP</span>
          </div>
          <nav className="nav-menu">
            <div className="nav-left">
              <button className="nav-item" onClick={() => handleNavClick('/')}>Home</button>
              <button className="nav-item" onClick={() => handleNavClick('/recommendations')}>Portfolio</button>
              <button className="nav-item" onClick={() => handleNavClick('/stocks')}>Stocks</button>
              <button className="nav-item" onClick={() => handleNavClick('/chat')}>Chatbot</button>
              <button className="nav-item" onClick={() => handleNavClick('/support')}>Support</button>
            </div>
            <div className="nav-right">
              <button className="nav-item logout-btn" onClick={handleLogout}>Logout</button>
              <button className="nav-item nav-avatar" onClick={() => handleNavClick('/mypage')}>
                <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>
              </button>
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
          <span className="logo-text">SeedUP</span>
        </div>
        <nav className="nav-menu">
          <div className="nav-left">
            <button 
              className="nav-item"
              onClick={() => handleNavClick('/about')}
            >
              About
            </button>
            <button 
              className="nav-item"
              onClick={() => handleNavClick('/support')}
            >
              Support
            </button>
          </div>
          <div className="nav-right">
            {isLoggedIn ? (
              <>
                <button 
                  className="nav-item logout-btn"
                  onClick={handleLogout}
                >
                  Logout
                </button>
              </>
            ) : (
              <>
                <button 
                  className="nav-item"
                  onClick={() => handleNavClick('/login')}
                >
                  Login
                </button>
                <button 
                  className="nav-item"
                  onClick={() => handleNavClick('/signup')}
                >
                  Sign Up
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
