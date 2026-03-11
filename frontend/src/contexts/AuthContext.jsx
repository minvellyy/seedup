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

  // 컴포넌트 마운트 시 localStorage에서 사용자 정보 복원
  useEffect(() => {
    const storedUserId = localStorage.getItem('user_id')
    const storedEmail = localStorage.getItem('email')
    const storedUsername = localStorage.getItem('username')
    const storedInvestmentType = localStorage.getItem('investment_type')
    const storedName = localStorage.getItem('name')
    
    if (storedUserId && storedEmail) {
      setUser({
        userId: parseInt(storedUserId),
        email: storedEmail,
        username: storedUsername,
        investmentType: storedInvestmentType,
        name: storedName
      })
      setIsLoggedIn(true)
      console.log('localStorage에서 로그인 정보 복원:', {
        userId: storedUserId,
        email: storedEmail,
        username: storedUsername,
        name: storedName
      })
    }
  }, [])

  const login = (userData) => {
    const { user_id, email, username, investment_type, name } = userData
    localStorage.setItem('user_id', user_id)
    localStorage.setItem('email', email)
    if (username) {
      localStorage.setItem('username', username)
    }
    if (investment_type) {
      localStorage.setItem('investment_type', investment_type)
    }
    if (name) {
      localStorage.setItem('name', name)
    }
    setUser({ userId: user_id, email, username, investmentType: investment_type, name })
    setIsLoggedIn(true)
  }

  const logout = () => {
    localStorage.removeItem('user_id')
    localStorage.removeItem('email')
    localStorage.removeItem('username')
    localStorage.removeItem('investment_type')
    localStorage.removeItem('name')
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
