import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import './LoginPage.css'

function LoginPage() {
  const navigate = useNavigate()
  const [formData, setFormData] = useState({
    email: '',
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
    if (!formData.email || !formData.password) {
      setError('이메일과 비밀번호를 입력해주세요.')
      setIsLoading(false)
      return
    }

    try {
      const response = await fetch('http://localhost:5000/api/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email: formData.email,
          password: formData.password
        })
      })

      const data = await response.json()

      if (response.ok) {
        // 사용자 ID 저장 (필요한 경우)
        localStorage.setItem('user_id', data.user_id)
        localStorage.setItem('email', data.email)
        navigate('/survey')
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
          <p className="login-subtitle">SeedUp 계정으로 로그인하세요</p>

          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label htmlFor="email">이메일</label>
              <input
                type="email"
                id="email"
                name="email"
                placeholder="your@email.com"
                value={formData.email}
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
