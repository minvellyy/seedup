import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import './LoginPage.css'

function LoginPage() {
  const navigate = useNavigate()
  const { login } = useAuth()
  const [formData, setFormData] = useState({
    username: '',
    password: ''
  })
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const handleChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({
      ...prev,
      [name]: value
    }))
    setError('')
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setIsLoading(true)

    // 간단한 검증
    if (!formData.username || !formData.password) {
      setError('ID와 비밀번호를 입력해주세요.')
      setIsLoading(false)
      return
    }

    try {
      const response = await fetch('/api/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          username: formData.username,
          password: formData.password
        })
      })

      const data = await response.json()

      if (response.ok) {
        // AuthContext를 통해 로그인 상태 업데이트
        console.log('로그인 성공 - 저장할 user_id:', data.user_id);
        login(data)
        console.log('로그인 상태 업데이트 완료');
        navigate('/dashboard')
      } else {
        setError(data.message || '로그인에 실패했습니다.')
      }
    } catch (err) {
      setError('서버에 연결할 수 없습니다. 나중에 다시 시도해주세요.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <main className="login-page">
      <div className="login-container">
        <div className="login-card">
          <h1>로그인</h1>
          <p className="login-subtitle">SeedUP 계정으로 로그인하세요</p>

          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label htmlFor="username">ID</label>
              <input
                type="text"
                id="username"
                name="username"
                placeholder="아이디를 입력하세요"
                value={formData.username}
                onChange={handleChange}
                disabled={isLoading}
              />
            </div>

            <div className="form-group">
              <label htmlFor="password">비밀번호</label>
              <input
                type="password"
                id="password"
                name="password"
                placeholder="비밀번호를 입력하세요"
                value={formData.password}
                onChange={handleChange}
                disabled={isLoading}
              />
            </div>

            {error && <div className="error-message">{error}</div>}

            <button 
              type="submit" 
              className="submit-button"
              disabled={isLoading}
            >
              {isLoading ? '로그인 중...' : '로그인'}
            </button>
          </form>

          <div className="divider">또는</div>

          <button 
            type="button"
            className="signup-link"
            onClick={() => navigate('/signup')}
          >
            아직 계정이 없으신가요? <span>회원가입</span>
          </button>
        </div>
      </div>
    </main>
  )
}

export default LoginPage
