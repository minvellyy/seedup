import React from 'react'
import { useNavigate } from 'react-router-dom'
import './Header.css'

function Header({ currentPath }) {
  const navigate = useNavigate()

  const handleLogoClick = () => {
    navigate('/')
  }

  const handleNavClick = (path) => {
    navigate(path)
  }

  // 투자성향 페이지부터는 다른 메뉴를 보여줌
  const isInvestTypePage = currentPath && currentPath.startsWith('/survey/invest-type')

  return (
    <header className="header">
      <div className="header-container">
        <div className="logo" onClick={handleLogoClick}>
          <span className="logo-text">SeedUp</span>
        </div>
        <nav className="nav-menu">
          {isInvestTypePage ? (
            <>
              <button 
                className="nav-item"
                onClick={() => handleNavClick('/')}
              >
                홈
              </button>
              <button 
                className="nav-item"
                onClick={() => handleNavClick('/portfolio')}
              >
                포트폴리오
              </button>
              <button 
                className="nav-item"
                onClick={() => handleNavClick('/investment')}
              >
                개별종목
              </button>
              <button 
                className="nav-item"
                onClick={() => handleNavClick('/chatbot')}
              >
                챗봇
              </button>
              <button 
                className="nav-item"
                onClick={() => handleNavClick('/support')}
              >
                고객센터
              </button>
              <button 
                className="nav-item"
                onClick={() => handleNavClick('/mypage')}
              >
                마이페이지
              </button>
            </>
          ) : (
            <>
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
        </nav>
      </div>
    </header>
  )
}

export default Header
