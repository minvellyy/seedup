import React, { useState } from 'react'
import './MyPage.css'
import ProfileSection from './MyPageSections/ProfileSection'
import HoldingsSection from './MyPageSections/HoldingsSection'
import PortfolioSection from './MyPageSections/PortfolioSection'
import StrategyHistorySection from './MyPageSections/StrategyHistorySection'

const MyPage = () => {
  const [activeSection, setActiveSection] = useState('profile')

  const menuItems = [
    {
      key: 'profile', label: '개인정보 관리',
      icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
    },
    {
      key: 'holdings', label: '보유 주식 내역 등록',
      icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>
    },
    {
      key: 'portfolio', label: '내 포트폴리오',
      icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21.21 15.89A10 10 0 1 1 8 2.83"/><path d="M22 12A10 10 0 0 0 12 2v10z"/></svg>
    },
    {
      key: 'history', label: '추천 전략 히스토리',
      icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
    },
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
          <p className="sidebar-category">CATEGORIES</p>
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
