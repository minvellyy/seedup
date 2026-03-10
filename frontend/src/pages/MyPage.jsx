import React, { useState } from 'react'
import './MyPage.css'
import ProfileSection from './MyPageSections/ProfileSection'
import HoldingsSection from './MyPageSections/HoldingsSection'
import PortfolioSection from './MyPageSections/PortfolioSection'
import StrategyHistorySection from './MyPageSections/StrategyHistorySection'

const MyPage = () => {
  const [activeSection, setActiveSection] = useState('profile')

  const menuItems = [
    { key: 'profile', label: '개인정보 관리', icon: '👤' },
    { key: 'holdings', label: '보유 주식 내역 등록', icon: '📊' },
    { key: 'portfolio', label: '내 포트폴리오', icon: '💼' },
    { key: 'history', label: '추천 전략 히스토리', icon: '📋' },
  ]

  const renderSection = () => {
    switch (activeSection) {
      case 'profile':
        return <ProfileSection />
      case 'holdings':
        return <HoldingsSection />
      case 'portfolio':
        return <PortfolioSection />
      case 'history':
        return <StrategyHistorySection />
      default:
        return <ProfileSection />
    }
  }

  return (
    <div className="mypage">
      <div className="mypage-container">
        <div className="mypage-sidebar">
          <h2 className="sidebar-title">MyPage</h2>
          <nav className="sidebar-menu">
            {menuItems.map((item) => (
              <button
                key={item.key}
                className={`menu-item ${activeSection === item.key ? 'active' : ''}`}
                onClick={() => setActiveSection(item.key)}
              >
                <span className="menu-icon">{item.icon}</span>
                <span className="menu-label">{item.label}</span>
              </button>
            ))}
          </nav>
        </div>

        <div className="mypage-content">
          {renderSection()}
        </div>
      </div>
    </div>
  )
}

export default MyPage
