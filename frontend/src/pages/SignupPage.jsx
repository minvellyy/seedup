import React, { useState } from 'react'
import TermsCheckbox from '../components/TermsCheckbox'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import './SignupPage.css'

function SignupPage() {
  const navigate = useNavigate()
  const { login } = useAuth()
  const [formData, setFormData] = useState({
    name: '',
    phone: '',
    username: '',
    email: '',
    password: '',
    confirmPassword: '',
    dob: ''
  })
  const [errors, setErrors] = useState({})
  const [isLoading, setIsLoading] = useState(false)
  const [showModal, setShowModal] = useState(false)
  const [showTermsPopup, setShowTermsPopup] = useState(false)
  const [checkedTerms, setCheckedTerms] = useState({
    'service-terms': false,
    'privacy-policy': false,
    'marketing': false,
    'personalized-service': false
  })
  const TERMS_DATA = [
    {
      id: 'service-terms',
      type: '필수',
      title: '서비스 이용약관 동의',
      content: `제 1 조 (목적)

본 약관은 Seedup가 제공하는 투자정보서비스(이하 “본 서비스”라 합니다)를 고객이 이용함에 있어서 필요한 사항을 정함을 목적으로 합니다.

제 2 조 (용어의 정의)

본 약관에서 사용하는 용어의 정의는 다음 각 호와 같습니다.

“Seedup웹”이란 회사가 고객에 대하여 증권매매거래 기타 서비스를 제공함에 있어서 이용하는 웹사이트를 의미합니다.
“WTS”란 회사가 고객에 대하여 증권매매거래 기타 서비스를 제공함에 있어서 이용하는 웹트레이딩시스템을 의미합니다.
“투자정보”란 금융투자에 관련된 지식 또는 정보로서 다음 각 목의 것을 포함하며, 본 서비스의 이용고객에게 송신, 배포, 게재할 목적으로 회사가 작성 또는 촬영, 이용권한 확보, 수집, 발췌, 편집, 배열, 구성, 결합, 번역 등을 한 것(글, 그림, 동영상 등 형태를 불문합니다)을 말합니다.
            가. 국내∙외 경제상황 또는 경제전망(주요국 경제 정책, 국제정세, 산업구조 변화 등에 관한 정보를 포함하고 이에 한정하지 않음)

            나. 국내∙외 금융투자상품시장의 상황 또는 전망(시장의 개폐, 시가총액, 거래량, 주가지수 등에 관한 정보를 포함하고 이에 한정하지 않음)

            다. 특정산업의 상황 및 전망

            라. 특정종목에 관련된 상황 및 전망(발행회사의 실적, 주요 뉴스 및 공시, 가격 변동, 시가총액, 거래량, 외국인∙기관 매매, 차입∙공매도, 기본적∙기술적 분석 및 지표, 투자유의 등에 관한 정보를 포함하고 이에 한정하지 않음)

            마. 금융투자에 관련된 법규정보, 이론 또는 가설 등 지식

            바. 금융투자에 관련된 통계적 기록, 금융투자에 관련된 역사적 사건에 관한 서술 또는 논평

            사. 그 밖에 금융투자에 관련된 지식 또는 정보

4. “투자정보서비스”란 투자정보를 Seedup의 일부 화면, 이메일, 휴대전화 문자메세지, 카카오톡 메시지, Seedup의 푸쉬 메시지, Seedup의 알림 화면, WTS 등의 매체를 통하여 주기적 또는 비주기적으로 송신하는 서비스를 말합니다.

... (이하 plan.md 내 약관 전체 본문을 그대로 이어서 삽입) ...`
    },
    {
      id: 'privacy-policy',
      type: '필수',
      title: '개인정보 처리방침 동의',
      content: `개인정보 수집·이용 동의(투자정보서비스)
Seedup은 「개인정보 보호법」, 「신용정보의 이용 및 보호에 관한 법률」 등 관련 법령에 따라 고객님께 아래와 같은 '수집이용 목적, 수집이용 항목, 이용 및 보유기간, 동의 거부권 및 동의 거부 시 불이익에 관한 사항'을 안내 드리고 개인정보 수집▪이용 동의를 받고자 합니다.

수집이용 목적	투자정보서비스 제공
수집이용 항목
이름, 고객식별값, 휴대폰번호
이용 및 보유기간
서비스 해지·취소 시 또는 회원탈퇴 시 까지(단, 관련 법령에 따라 보존할 필요가 있는 경우는 해당 보존기간)

동의를 거부하는 경우에 대한 안내:
고객님께서는 개인정보 수집·이용 동의를 거부할 권리가 있습니다. 동의 거부 시 수집·이용 목적에 따른 투자정보서비스를 이용할 수 없습니다.`
    },
    {
      id: 'marketing',
      type: '선택',
      title: '마케팅 정보 수신 동의',
      content: `마케팅 정보 수신에 동의하시면 새로운 서비스 및 이벤트 정보를 받아보실 수 있습니다.

마케팅 정보는 이메일, SMS, 카카오톡 메시지, 푸쉬 알림 등의 방법으로 발송됩니다.

고객님께서는 언제든지 수신 거부 의사를 표시할 수 있으며, 수신 거부 후에도 서비스 이용에는 제한이 없습니다.

개인정보는 마케팅 목적으로만 사용되며, 제3자에게 제공되지 않습니다.`
    },
    {
      id: 'personalized-service',
      type: '선택',
      title: '맞춤형 서비스 개인(신용)정보 수집·이용 동의',
      content: `맞춤형 서비스 개인(신용)정보 수집·이용 요약동의

Seedup은 고객님의 Seedup 내 서비스 방문 이력, 활동 및 검색 이력 등을 이용하여 고객님께 맞춤형 서비스를 제공하기 위하여 개인(신용)정보를 다음과 같이 수집·이용하는 것에 동의를 받고자 합니다.

1. 수집·이용에 관한 사항

수집·이용 목적: Seedup의 상품·서비스에 대한 맞춤형 서비스(광고, 컨텐츠, UI/UX 등)를 제공하기 위함

보유 및 이용기간: 동의 철회 또는 회원 탈퇴 시까지
※ 위 보유 기간에서의 동의철회란 "고객님께서 Seedup의 상품·서비스에 대한 맞춤형 서비스 제공 동의 철회"를 말합니다.

거부 권리 및 불이익: 고객님은 맞춤형 서비스 개인(신용)정보 수집·이용 동의를 거부할 권리가 있으며, 이용목적을 위한 선택적 사항이므로 동의하지 않더라도 Seedup의 다른 서비스 이용에는 제한이 없습니다. 다만, 동의하지 않을 경우 이용목적에 따른 맞춤형 서비스를 제공받지 못할 수 있습니다.

2. 수집·이용 항목

개인(신용)정보 (31개): 행태정보 및 기타 정보 수집으로 맞춤형 광고 및 서비스 제공

※ 만 14세 미만자의 행태정보 보호 안내:
Seedup은 만 14세 미만 아동의 행태정보는 맞춤형 광고에 활용하지 않으며, 이들에게는 맞춤형 광고를 제공하지 않습니다.`
    }
  ]
  const [usernameAvailable, setUsernameAvailable] = useState(null)

  const handleChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({
      ...prev,
      [name]: value
    }))
    // 입력 시 해당 필드의 에러 제거
    if (errors[name]) {
      setErrors(prev => ({
        ...prev,
        [name]: ''
      }))
    }
  }

  const validateForm = () => {
    const newErrors = {}

    if (!formData.name) {
      newErrors.name = '이름을 입력해주세요.'
    }

    if (!formData.phone) {
      newErrors.phone = '전화번호를 입력해주세요.'
    }

    if (!formData.username) {
      newErrors.username = 'ID를 입력해주세요.'
    } else if (usernameAvailable === false) {
      newErrors.username = '이미 사용 중인 ID입니다.'
    }

    if (!formData.email) {
      newErrors.email = '이메일을 입력해주세요.'
    } else if (!formData.email.includes('@')) {
      newErrors.email = '유효한 이메일을 입력해주세요.'
    }

    if (!formData.password) {
      newErrors.password = '비밀번호를 입력해주세요.'
    } else if (formData.password.length < 6) {
      newErrors.password = '비밀번호는 6자 이상이어야 합니다.'
    }

    if (!formData.confirmPassword) {
      newErrors.confirmPassword = '비밀번호 확인을 입력해주세요.'
    } else if (formData.password !== formData.confirmPassword) {
      newErrors.confirmPassword = '비밀번호가 일치하지 않습니다.'
    }

    return newErrors
  }

  const checkUsernameExists = async (value) => {
    if (!value) return
    try {
      const res = await fetch(`/api/check_username?username=${encodeURIComponent(value)}`)
      const data = await res.json()
      if (res.ok) {
        setUsernameAvailable(!data.exists)
        setErrors(prev => ({ ...prev, username: data.exists ? '이미 사용 중인 ID입니다.' : '' }))
      }
    } catch (e) {
      // ignore network errors for availability
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    const newErrors = validateForm()
    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors)
      return
    }
    setShowTermsPopup(true)
  }

  const handleTermsChange = (termId) => {
    setCheckedTerms(prev => ({
      ...prev,
      [termId]: !prev[termId]
    }))
  }

  const requiredTermsChecked = checkedTerms['service-terms'] && checkedTerms['privacy-policy']

  const handleTermsConfirm = async () => {
    if (!requiredTermsChecked) return
    setShowTermsPopup(false)
    setIsLoading(true)
    try {
      const response = await fetch('/api/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: formData.name,
          phone: formData.phone,
          username: formData.username,
          email: formData.email,
          password: formData.password,
          dob: formData.dob
        })
      })
      const data = await response.json()
      if (response.ok) {
        // 회원가입 성공 시 자동 로그인 처리
        console.log('회원가입 성공 응답:', data);
        console.log('회원가입 성공 - user_id:', data.user_id, 'email:', data.email, 'username:', data.username);
        
        // 로그인 정보 저장
        login(data)
        
        // localStorage에 제대로 저장되었는지 확인
        setTimeout(() => {
          console.log('로그인 후 localStorage 확인:', {
            user_id: localStorage.getItem('user_id'),
            email: localStorage.getItem('email'),
            username: localStorage.getItem('username')
          });
        }, 100);
        
        console.log('로그인 상태 업데이트 완료');
        setShowModal(true)
      } else {
        setErrors({ submit: data.message || '회원가입에 실패했습니다.' })
      }
    } catch (err) {
      setErrors({ submit: '서버에 연결할 수 없습니다. 나중에 다시 시도해주세요.' })
    } finally {
      setIsLoading(false)
    }
  }

  const handleModalClose = () => {
    setShowModal(false)
    
    // 로그인 정보 확인 후 페이지 이동
    const userId = localStorage.getItem('user_id')
    console.log('설문 페이지 이동 전 user_id 확인:', userId)
    
    if (!userId) {
      console.error('user_id가 저장되지 않았습니다!')
      alert('로그인 정보를 확인할 수 없습니다. 다시 로그인해주세요.')
      navigate('/login')
      return
    }
    
    navigate('/survey')
  }

  return (
    <main className="signup-page">
      <div className="signup-container">
        <div className="signup-card">
          <h1>회원가입</h1>
          <p className="signup-subtitle">SeedUp 계정을 생성하세요</p>

          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label htmlFor="name">이름</label>
              <input
                type="text"
                id="name"
                name="name"
                placeholder="이름을 입력하세요"
                value={formData.name}
                onChange={handleChange}
                disabled={isLoading}
                className={errors.name ? 'error' : ''}
              />
              {errors.name && <span className="error-text">{errors.name}</span>}
            </div>

            <div className="form-group">
              <label htmlFor="phone">전화번호</label>
              <input
                type="text"
                id="phone"
                name="phone"
                placeholder="010-1234-5678"
                value={formData.phone}
                onChange={handleChange}
                disabled={isLoading}
                className={errors.phone ? 'error' : ''}
              />
              {errors.phone && <span className="error-text">{errors.phone}</span>}
            </div>

            <div className="form-group">
              <label htmlFor="username">ID</label>
              <input
                type="text"
                id="username"
                name="username"
                placeholder="사용할 ID를 입력하세요"
                value={formData.username}
                onChange={(e) => { handleChange(e); setUsernameAvailable(null) }}
                onBlur={(e) => checkUsernameExists(e.target.value)}
                disabled={isLoading}
                className={errors.username ? 'error' : ''}
              />
              {usernameAvailable === true && <span className="success-text">사용 가능한 ID입니다.</span>}
              {errors.username && <span className="error-text">{errors.username}</span>}
            </div>

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
                className={errors.email ? 'error' : ''}
              />
              {errors.email && <span className="error-text">{errors.email}</span>}
            </div>

            <div className="form-group">
              <label htmlFor="password">비밀번호</label>
              <input
                type="password"
                id="password"
                name="password"
                placeholder="6자 이상의 비밀번호"
                value={formData.password}
                onChange={handleChange}
                disabled={isLoading}
                className={errors.password ? 'error' : ''}
              />
              {errors.password && <span className="error-text">{errors.password}</span>}
            </div>

            <div className="form-group">
              <label htmlFor="confirmPassword">비밀번호 확인</label>
              <input
                type="password"
                id="confirmPassword"
                name="confirmPassword"
                placeholder="비밀번호를 다시 입력하세요"
                value={formData.confirmPassword}
                onChange={handleChange}
                disabled={isLoading}
                className={errors.confirmPassword ? 'error' : ''}
              />
              {errors.confirmPassword && <span className="error-text">{errors.confirmPassword}</span>}
            </div>

            <div className="form-group">
              <label htmlFor="dob">생년월일</label>
              <input
                type="date"
                id="dob"
                name="dob"
                value={formData.dob}
                onChange={handleChange}
                disabled={isLoading}
              />
            </div>

            {errors.submit && <div className="error-message">{errors.submit}</div>}

            <button 
              type="submit" 
              className="submit-button"
              disabled={isLoading}
            >
              {isLoading ? '가입 중...' : '회원가입'}
            </button>
          </form>

          <div className="divider">이미 계정이 있으신가요?</div>

          <button 
            type="button"
            className="login-link"
            onClick={() => navigate('/login')}
          >
            <span>로그인</span>
          </button>
        </div>
      </div>

      {showModal && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div className="modal-icon">✓</div>
            <h2>회원가입이 완료되었습니다!</h2>
            <p>이제 맞춤형 설문조사를 시작하세요.</p>
            <button 
              className="modal-button"
              onClick={handleModalClose}
            >
              설문 시작하기
            </button>
          </div>
        </div>
      )}

      {showTermsPopup && (
        <div className="modal-overlay">
          <div className="modal-content terms-popup">
            <h2>약관 동의</h2>
            <p>SeedUp 서비스를 이용하려면 필수 약관에 동의해야 합니다.</p>
            <div className="terms-list">
              {TERMS_DATA.map(term => (
                <TermsCheckbox
                  key={term.id}
                  id={term.id}
                  type={term.type}
                  title={term.title}
                  content={term.content}
                  checked={checkedTerms[term.id]}
                  onChange={() => handleTermsChange(term.id)}
                />
              ))}
            </div>
            <div className="terms-info">
              <p>필수 약관에 동의하셔야 회원가입이 진행됩니다.</p>
            </div>
            <button
              className={`submit-button ${requiredTermsChecked ? 'enabled' : 'disabled'}`}
              onClick={handleTermsConfirm}
              disabled={!requiredTermsChecked || isLoading}
            >
              {isLoading ? '가입 중...' : '회원가입 계속'}
            </button>
            <button
              className="modal-button cancel"
              onClick={() => setShowTermsPopup(false)}
              disabled={isLoading}
            >
              취소
            </button>
          </div>
        </div>
      )}
    </main>
  )
}

export default SignupPage
