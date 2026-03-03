import React, { createContext, useContext, useState, useEffect } from 'react'

const AuthContext = createContext()

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null)
  const [isLoggedIn, setIsLoggedIn] = useState(false)

  // 컴포넌트 마운트 시 localStorage 초기화 (항상 로그아웃 상태로 시작)
  useEffect(() => {
    localStorage.removeItem('user_id')
    localStorage.removeItem('email')
    localStorage.removeItem('username')
  }, [])

  const login = (userData) => {
    const { user_id, email, username } = userData
    localStorage.setItem('user_id', user_id)
    localStorage.setItem('email', email)
    if (username) {
      localStorage.setItem('username', username)
    }
    setUser({ userId: user_id, email, username })
    setIsLoggedIn(true)
  }

  const logout = () => {
    localStorage.removeItem('user_id')
    localStorage.removeItem('email')
    localStorage.removeItem('username')
    setUser(null)
    setIsLoggedIn(false)
  }

  const value = {
    user,
    isLoggedIn,
    login,
    logout
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}
