import React from 'react'
import { useNavigate } from 'react-router-dom'
import './Header.css'

function Header() {
  const navigate = useNavigate()

  const handleLogoClick = () => {
    navigate('/')
  }

  const handleNavClick = (path) => {
    navigate(path)
  }

  return (
    <header className="header">
      <div className="header-container">
        <div className="logo" onClick={handleLogoClick}>
          <span className="logo-text">SeedUp</span>
        </div>
        <nav className="nav-menu">
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
        </nav>
      </div>
    </header>
  )
}

export default Header
