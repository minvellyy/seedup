import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import axios from 'axios'

const ProfileSection = () => {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [loading, setLoading] = useState(true)
  const [formData, setFormData] = useState({
    name: '',
    phone: '',
    email: '',
    lumpSumAmount: '',
    currentPassword: '',
    newPassword: '',
    confirmPassword: '',
  })

  const [errors, setErrors] = useState({})

  // 사용자 정보 가져오기
  useEffect(() => {
    const fetchUserData = async () => {
      if (!user?.userId) {
        console.log('[ProfileSection] user.userId가 없음:', user)
        setLoading(false)
        return
      }

      try {
        console.log('[ProfileSection] API 호출:', `http://localhost:8000/api/users/${user.userId}`)
        const response = await fetch(`http://localhost:8000/api/users/${user.userId}`)
        const data = await response.json()
        
        console.log('[ProfileSection] API 응답:', data)
        
        if (data.success && data.user) {
          const userData = {
            name: data.user.name || data.user.username || '',
            phone: data.user.phone || '',
            email: data.user.email || '',
            lumpSumAmount: data.user.lump_sum_amount != null ? String(data.user.lump_sum_amount) : '',
          }
          console.log('[ProfileSection] 설정할 데이터:', userData)
          
          setFormData(prev => ({
            ...prev,
            ...userData
          }))
        }
      } catch (error) {
        console.error('사용자 정보 조회 실패:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchUserData()
  }, [user?.userId])

  const handleChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({
      ...prev,
      [name]: value
    }))
    // 에러 초기화
    if (errors[name]) {
      setErrors(prev => ({
        ...prev,
        [name]: ''
      }))
    }
  }

  const validateForm = () => {
    const newErrors = {}

    if (!formData.phone) {
      newErrors.phone = '전화번호를 입력해주세요'
    } else if (!/^010-\d{4}-\d{4}$/.test(formData.phone)) {
      newErrors.phone = '올바른 전화번호 형식이 아닙니다 (예: 010-1234-5678)'
    }

    if (!formData.email) {
      newErrors.email = '이메일을 입력해주세요'
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      newErrors.email = '올바른 이메일 형식이 아닙니다'
    }

    if (formData.newPassword && formData.newPassword !== formData.confirmPassword) {
      newErrors.confirmPassword = '비밀번호가 일치하지 않습니다'
    }

    if (formData.newPassword && formData.newPassword.length < 8) {
      newErrors.newPassword = '비밀번호는 최소 8자 이상이어야 합니다'
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!validateForm()) {
      return
    }

    if (!user?.userId) {
      alert('로그인이 필요합니다.')
      return
    }

    try {
      const updateData = {
        name: formData.name,
        phone: formData.phone,
        email: formData.email,
      }

      if (formData.lumpSumAmount !== '') {
        const parsed = Number(formData.lumpSumAmount.replace(/,/g, ''))
        if (!isNaN(parsed)) updateData.lump_sum_amount = parsed
      }

      // 비밀번호 변경이 있는 경우에만 추가
      if (formData.newPassword) {
        updateData.newPassword = formData.newPassword
      }

      const url = `http://localhost:8000/api/users/${user.userId}`
      console.log('[UPDATE] 요청 데이터:', updateData)
      console.log('[UPDATE] API URL:', url)

      const response = await axios.put(url, updateData)
      const data = response.data

      console.log('[UPDATE] 응답 상태:', response.status)
      console.log('[UPDATE] 응답 데이터:', data)

      if (data.success) {
        console.log('[UPDATE] 성공')
        // 일시투자금 변경 시 대시보드 포트폴리오 캐시 무효화
        if (updateData.lump_sum_amount !== undefined) {
          try {
            sessionStorage.removeItem(`pf_recs_${user.userId}`)
          } catch {}
        }
        alert('개인정보가 수정되었습니다.')
        // 비밀번호 필드 초기화
        setFormData(prev => ({
          ...prev,
          currentPassword: '',
          newPassword: '',
          confirmPassword: '',
        }))
      } else {
        console.error('[UPDATE] 실패:', data.message || data)
        alert(data.message || '개인정보 수정에 실패했습니다.')
      }
    } catch (error) {
      console.error('[UPDATE] 예외 발생:', error?.response?.data || error?.message || error)
      alert('서버 요청 중 오류가 발생했습니다.')
    }
  }

  const handleRetakeSurvey = () => {
    navigate('/invest-type-survey')
  }

  if (loading) {
    return (
      <div className="section-content">
        <h2 className="section-title">개인정보 관리</h2>
        <div className="profile-card">
          <p>로딩 중...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="section-content">
      <h2 className="section-title">개인정보 관리</h2>
      <div className="profile-card">
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="name">이름</label>
            <input
              type="text"
              id="name"
              name="name"
              value={formData.name}
              onChange={handleChange}
              disabled
              className="form-input disabled"
            />
            <p className="form-helper">이름은 수정할 수 없습니다</p>
          </div>

          <div className="form-group">
            <label htmlFor="phone">전화번호 <span className="required">*</span></label>
            <input
              type="tel"
              id="phone"
              name="phone"
              value={formData.phone}
              onChange={handleChange}
              className={`form-input ${errors.phone ? 'error' : ''}`}
              placeholder="010-1234-5678"
            />
            {errors.phone && <p className="form-error">{errors.phone}</p>}
          </div>

          <div className="form-group">
            <label htmlFor="email">이메일 주소 <span className="required">*</span></label>
            <input
              type="email"
              id="email"
              name="email"
              value={formData.email}
              onChange={handleChange}
              className={`form-input ${errors.email ? 'error' : ''}`}
              placeholder="example@email.com"
            />
            {errors.email && <p className="form-error">{errors.email}</p>}
          </div>

          <div className="form-group">
            <label htmlFor="lumpSumAmount">일시투자금</label>
            <p className="form-helper">
              현재:{' '}
              {formData.lumpSumAmount
                ? `${Number(formData.lumpSumAmount).toLocaleString('ko-KR')}원`
                : '설정된 금액이 없습니다'}
            </p>
            <input
              type="number"
              id="lumpSumAmount"
              name="lumpSumAmount"
              value={formData.lumpSumAmount}
              onChange={handleChange}
              className="form-input"
              placeholder="새 금액 입력 (원)"
              min="0"
            />
          </div>

          <div className="form-divider"></div>

          <div className="form-group">
            <label htmlFor="currentPassword">현재 비밀번호</label>
            <input
              type="password"
              id="currentPassword"
              name="currentPassword"
              value={formData.currentPassword}
              onChange={handleChange}
              className="form-input"
              placeholder="현재 비밀번호"
            />
            <p className="form-helper">비밀번호를 변경하려면 현재 비밀번호를 입력하세요</p>
          </div>

          <div className="form-group">
            <label htmlFor="newPassword">새 비밀번호</label>
            <input
              type="password"
              id="newPassword"
              name="newPassword"
              value={formData.newPassword}
              onChange={handleChange}
              className={`form-input ${errors.newPassword ? 'error' : ''}`}
              placeholder="새 비밀번호 (최소 8자)"
            />
            {errors.newPassword && <p className="form-error">{errors.newPassword}</p>}
          </div>

          <div className="form-group">
            <label htmlFor="confirmPassword">새 비밀번호 확인</label>
            <input
              type="password"
              id="confirmPassword"
              name="confirmPassword"
              value={formData.confirmPassword}
              onChange={handleChange}
              className={`form-input ${errors.confirmPassword ? 'error' : ''}`}
              placeholder="새 비밀번호 확인"
            />
            {errors.confirmPassword && <p className="form-error">{errors.confirmPassword}</p>}
          </div>

          <div className="form-actions">
            <button type="submit" className="btn btn-primary">
              수정 완료
            </button>
            <button type="button" className="btn btn-secondary" onClick={handleRetakeSurvey}>
              투자 성향 재진단하기
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default ProfileSection
