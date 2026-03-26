import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import './Header.css'

function Header() {
  const navigate = useNavigate()
  const location = useLocation()
  const { isLoggedIn, logout } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)

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
    setMenuOpen(false)
  }

  const handleNavClick = (path) => {
    navigate(path)
    setMenuOpen(false)
  }

  const handleLogout = () => {
    logout()
    navigate('/')
    setMenuOpen(false)
  }

  const toggleMenu = () => setMenuOpen(prev => !prev)

  const HamburgerBtn = () => (
    <button
      className={`hamburger-btn${menuOpen ? ' open' : ''}`}
      onClick={toggleMenu}
      aria-label="메뉴 열기"
    >
      <span />
      <span />
      <span />
    </button>
  )

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
          <HamburgerBtn />
        </div>
        {menuOpen && (
          <div className="mobile-menu">
            <button className="mobile-nav-item" disabled>Home</button>
            <button className="mobile-nav-item" disabled>Portfolio</button>
            <button className="mobile-nav-item" disabled>Stocks</button>
            <button className="mobile-nav-item" disabled>Chatbot</button>
            <button className="mobile-nav-item" disabled>Support</button>
          </div>
        )}
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
          <div className="mobile-header-actions">
            <button
              className="mobile-support-btn"
              onClick={() => handleNavClick('/support')}
              aria-label="고객센터"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                {/* 헤드폰 밴드 + 이어컵 */}
                <path d="M3 10a9 9 0 0 1 18 0"/>
                <rect x="1" y="10" width="3.5" height="5.5" rx="1.5"/>
                <rect x="19.5" y="10" width="3.5" height="5.5" rx="1.5"/>
                {/* 말풍선 (채팅) */}
                <rect x="7" y="6.5" width="10" height="7.5" rx="1.8"/>
                <path d="M9.5 17l1.5-3h3"/>
                {/* 말풍선 점 3개 */}
                <circle cx="10" cy="10.5" r="0.7" fill="currentColor" stroke="none"/>
                <circle cx="12" cy="10.5" r="0.7" fill="currentColor" stroke="none"/>
                <circle cx="14" cy="10.5" r="0.7" fill="currentColor" stroke="none"/>
                {/* 하단 마이크 연결선 + 캡슐 */}
                <path d="M21 15.5v1.5a2 2 0 0 1-2 2h-3"/>
                <rect x="10.5" y="18" width="4" height="2.2" rx="1.1"/>
              </svg>
            </button>
            <button
              className="mobile-logout-btn"
              onClick={handleLogout}
              aria-label="로그아웃"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                <polyline points="16 17 21 12 16 7"/>
                <line x1="21" y1="12" x2="9" y2="12"/>
              </svg>
            </button>
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
          <HamburgerBtn />
        </div>
        {menuOpen && (
          <div className="mobile-menu">
            <button className="mobile-nav-item" onClick={() => handleNavClick('/')}>Home</button>
            <button className="mobile-nav-item" onClick={() => handleNavClick('/recommendations')}>Portfolio</button>
            <button className="mobile-nav-item" onClick={() => handleNavClick('/stocks')}>Stocks</button>
            <button className="mobile-nav-item" onClick={() => handleNavClick('/chat')}>Chatbot</button>
            <button className="mobile-nav-item" onClick={() => handleNavClick('/support')}>Support</button>
            <button className="mobile-nav-item" onClick={() => handleNavClick('/mypage')}>My Page</button>
            <button className="mobile-nav-item mobile-logout" onClick={handleLogout}>Logout</button>
          </div>
        )}
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
        <HamburgerBtn />
      </div>
      {menuOpen && (
        <div className="mobile-menu">
          <button className="mobile-nav-item" onClick={() => handleNavClick('/support')}>Support</button>
          {isLoggedIn ? (
            <button className="mobile-nav-item mobile-logout" onClick={handleLogout}>Logout</button>
          ) : (
            <>
              <button className="mobile-nav-item" onClick={() => handleNavClick('/login')}>Login</button>
              <button className="mobile-nav-item" onClick={() => handleNavClick('/signup')}>Sign Up</button>
            </>
          )}
        </div>
      )}
    </header>
  )
}

export default Header
