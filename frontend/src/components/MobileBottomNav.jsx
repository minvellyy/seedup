import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import './MobileBottomNav.css'

const NAV_ITEMS = [
  {
    label: 'Home',
    path: '/',
    exact: true,
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 9.5L12 3l9 6.5V20a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9.5z" />
        <polyline points="9 21 9 13 15 13 15 21" />
      </svg>
    ),
  },
  {
    label: 'Portfolio',
    path: '/recommendations',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="18" y1="20" x2="18" y2="10" />
        <line x1="12" y1="20" x2="12" y2="4" />
        <line x1="6" y1="20" x2="6" y2="14" />
      </svg>
    ),
  },
  {
    label: 'Stocks',
    path: '/stocks',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
        <polyline points="16 7 22 7 22 13" />
      </svg>
    ),
  },
  {
    label: 'Chat',
    path: '/chat',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    ),
  },
  {
    label: 'My',
    path: '/mypage',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="8" r="4" />
        <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" />
      </svg>
    ),
  },
]

const SHOW_ON_PATHS = ['/', '/dashboard', '/recommendations', '/mypage', '/chat', '/support', '/stocks']

function MobileBottomNav() {
  const navigate = useNavigate()
  const location = useLocation()
  const { isLoggedIn } = useAuth()

  const shouldShow = isLoggedIn && (
    SHOW_ON_PATHS.includes(location.pathname) ||
    location.pathname.startsWith('/stock/') ||
    location.pathname.startsWith('/etf/') ||
    location.pathname.startsWith('/portfolio/')
  )

  if (!shouldShow) return null

  const isActive = (item) => {
    if (item.exact) return location.pathname === item.path
    return location.pathname === item.path || location.pathname.startsWith(item.path + '/')
  }

  return (
    <nav className="mobile-bottom-nav">
      {NAV_ITEMS.map((item) => (
        <button
          key={item.path}
          className={`mobile-bottom-nav__item${isActive(item) ? ' active' : ''}`}
          onClick={() => navigate(item.path)}
        >
          <span className="mobile-bottom-nav__icon">{item.icon}</span>
          <span className="mobile-bottom-nav__label">{item.label}</span>
        </button>
      ))}
    </nav>
  )
}

export default MobileBottomNav
