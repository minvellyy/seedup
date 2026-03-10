import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'

const ProfileSection = () => {
  const navigate = useNavigate()
  const [formData, setFormData] = useState({
    name: '홍길동',
    phone: '010-1234-5678',
    email: 'seedup@example.com',
    currentPassword: '',
    newPassword: '',
    confirmPassword: '',
  })

  const [errors, setErrors] = useState({})

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

  const handleSubmit = (e) => {
    e.preventDefault()
    if (validateForm()) {
      alert('개인정보가 수정되었습니다')
      console.log('수정된 정보:', formData)
    }
  }

  const handleRetakeSurvey = () => {
    navigate('/invest-type-survey')
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
