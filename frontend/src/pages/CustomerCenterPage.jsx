import React, { useState, useEffect } from 'react'
import { useAuth } from '../contexts/AuthContext'
import './CustomerCenterPage.css'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

// Mock Data
const FAQ_DATA = [
  {
    id: 1,
    question: '투자 경험이 없어도 이용할 수 있나요?',
    answer: '네, 가능합니다. SeedUP은 투자 경험이 많지 않은 사용자도 쉽게 이해할 수 있도록 투자 성향 설문과 추천 결과를 직관적으로 제공합니다.'
  },
  {
    id: 2,
    question: '추천 결과는 어떤 기준으로 제공되나요?',
    answer: '사용자의 투자 성향, 목표, 위험 선호도, 입력한 정보 등을 바탕으로 포트폴리오와 종목 추천 결과를 제공합니다.'
  },
  {
    id: 3,
    question: '포트폴리오 추천은 어떻게 이루어지나요?',
    answer: '투자 성향 설문 결과와 시장 데이터, 자산 분산 원칙 등을 종합적으로 반영해 포트폴리오 예시를 제공합니다.'
  },
  {
    id: 4,
    question: '투자 성향 설문을 다시 할 수 있나요?',
    answer: '네, 마이페이지에서 언제든지 투자 성향 설문을 다시 진행하실 수 있습니다. 투자 성향이 변경되면 새로운 추천 결과를 받아보실 수 있습니다.'
  },
  {
    id: 5,
    question: 'AI 추천은 어떤 데이터를 기반으로 하나요?',
    answer: '사용자 입력 정보, 시장 데이터, 종목 특성, 포트폴리오 구성 원칙 등 서비스 정책에 맞는 다양한 데이터를 기반으로 AI 추천이 제공됩니다.'
  },
  {
    id: 6,
    question: '개인정보는 안전하게 보호되나요?',
    answer: '네, SeedUP은 최신 보안 기술을 사용하여 개인정보를 암호화하고 안전하게 보호합니다. 관련 법규를 철저히 준수하고 있습니다.'
  },
  {
    id: 7,
    question: '실시간 주가 정보는 어떻게 제공되나요?',
    answer: '한국투자증권 KIS API를 통해 실시간 주가 정보를 제공하고 있습니다. 시세 지연 없이 최신 정보를 확인하실 수 있습니다.'
  },
  {
    id: 8,
    question: '추천받은 종목을 실제로 매매할 수 있나요?',
    answer: 'SeedUP은 투자 추천 서비스로, 실제 매매는 증권사 계좌를 통해 진행하셔야 합니다. 추천 정보를 참고하여 투자 결정을 내리실 수 있습니다.'
  }
]

const INQUIRY_DATA = [
  {
    id: 1,
    type: '포트폴리오',
    title: '포트폴리오 추천 결과가 이상해요',
    content: '추천 결과가 맞는건지 잘 모르겠어요. 분석이 잘 된건가요?',
    date: '2026.02.10',
    status: 'pending',
    answer: null
  },
  {
    id: 2,
    type: '계정/로그인',
    title: '로그인이 되지 않습니다',
    content: '비밀번호를 정확히 입력했는데도 로그인이 되지 않아요.',
    date: '2026.02.08',
    status: 'completed',
    answer: '비밀번호 재설정 링크를 이메일로 발송해드렸습니다. 이메일을 확인하시고 비밀번호를 재설정해주세요. 추가 문제가 있으시면 고객센터로 연락 부탁드립니다.'
  },
  {
    id: 3,
    type: '설문조사',
    title: '투자 성향 설문 결과 변경',
    content: '설문 결과를 다시 받고 싶은데 어떻게 하나요?',
    date: '2026.02.05',
    status: 'completed',
    answer: '마이페이지 > 개인정보 관리 메뉴에서 투자 성향 설문을 다시 진행하실 수 있습니다. 새로운 결과에 따라 추천이 업데이트됩니다.'
  },
  {
    id: 4,
    type: '서비스 이용',
    title: '대시보드 화면이 로딩되지 않아요',
    content: '대시보드 페이지에 접속하면 계속 로딩만 되고 화면이 나타나지 않습니다.',
    date: '2026.02.03',
    status: 'completed',
    answer: '일시적인 서버 문제로 인한 현상이었습니다. 현재는 정상적으로 서비스가 제공되고 있습니다. 이용에 불편을 드려 죄송합니다.'
  }
]

// StatusBadge Component
const StatusBadge = ({ status }) => {
  const statusConfig = {
    pending: { text: '답변 대기', className: 'status-pending' },
    completed: { text: '답변 완료', className: 'status-completed' }
  }
  
  const config = statusConfig[status] || statusConfig.pending
  
  return (
    <span className={`status-badge ${config.className}`}>
      {config.text}
    </span>
  )
}

// FAQ Section Component
const FaqSection = () => {
  const [searchKeyword, setSearchKeyword] = useState('')
  const [openFaqId, setOpenFaqId] = useState(null)

  const filteredFaqs = FAQ_DATA.filter(faq =>
    faq.question.toLowerCase().includes(searchKeyword.toLowerCase()) ||
    faq.answer.toLowerCase().includes(searchKeyword.toLowerCase())
  )

  const toggleFaq = (id) => {
    setOpenFaqId(openFaqId === id ? null : id)
  }

  return (
    <div className="cs-content-section">
      <div className="cs-section-header">
        <h2 className="cs-section-title">FAQ</h2>
        <p className="cs-section-description">자주 묻는 질문을 확인해보세요</p>
      </div>

      <div className="faq-search-bar">
        <svg className="search-icon" width="20" height="20" viewBox="0 0 20 20" fill="none">
          <path d="M9 17A8 8 0 1 0 9 1a8 8 0 0 0 0 16zM18 18l-4.35-4.35" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        <input
          type="text"
          placeholder="궁금한 내용을 검색해보세요"
          value={searchKeyword}
          onChange={(e) => setSearchKeyword(e.target.value)}
          className="faq-search-input"
        />
      </div>

      <div className="faq-list">
        {filteredFaqs.length > 0 ? (
          filteredFaqs.map((faq) => (
            <div
              key={faq.id}
              className={`faq-item ${openFaqId === faq.id ? 'open' : ''}`}
            >
              <button
                className="faq-question"
                onClick={() => toggleFaq(faq.id)}
              >
                <span className="faq-q-label">Q</span>
                <span className="faq-q-text">{faq.question}</span>
                <svg
                  className="faq-toggle-icon"
                  width="20"
                  height="20"
                  viewBox="0 0 20 20"
                  fill="none"
                >
                  <path
                    d="M5 7.5L10 12.5L15 7.5"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
              {openFaqId === faq.id && (
                <div className="faq-answer">
                  <span className="faq-a-label">A</span>
                  <p className="faq-a-text">{faq.answer}</p>
                </div>
              )}
            </div>
          ))
        ) : (
          <div className="empty-state">
            <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
              <circle cx="32" cy="32" r="32" fill="#F3F4F6"/>
              <path d="M32 20v24M32 48h.02" stroke="#9CA3AF" strokeWidth="3" strokeLinecap="round"/>
            </svg>
            <p className="empty-message">검색 결과가 없습니다</p>
            <p className="empty-description">다른 키워드로 검색해보세요</p>
          </div>
        )}
      </div>
    </div>
  )
}

// Inquiry Form Modal Component
const InquiryFormModal = ({ isOpen, onClose, onSubmit }) => {
  const [formData, setFormData] = useState({
    type: '서비스 이용',
    title: '',
    content: ''
  })

  const handleChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!formData.title.trim() || !formData.content.trim()) {
      alert('제목과 내용을 모두 입력해주세요.')
      return
    }
    onSubmit(formData)
    setFormData({ type: '서비스 이용', title: '', content: '' })
  }

  if (!isOpen) return null

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3 className="modal-title">새 문의 작성</h3>
          <button className="modal-close" onClick={onClose}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
          </button>
        </div>

        <form className="inquiry-form" onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="type" className="form-label">문의 유형</label>
            <select
              id="type"
              name="type"
              value={formData.type}
              onChange={handleChange}
              className="form-select"
            >
              <option value="서비스 이용">서비스 이용</option>
              <option value="포트폴리오">포트폴리오</option>
              <option value="계정/로그인">계정/로그인</option>
              <option value="설문조사">설문조사</option>
              <option value="결제/환불">결제/환불</option>
              <option value="기타">기타</option>
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="title" className="form-label">문의 제목</label>
            <input
              id="title"
              name="title"
              type="text"
              value={formData.title}
              onChange={handleChange}
              placeholder="문의 제목을 입력해주세요"
              className="form-input"
              maxLength={100}
            />
          </div>

          <div className="form-group">
            <label htmlFor="content" className="form-label">문의 내용</label>
            <textarea
              id="content"
              name="content"
              value={formData.content}
              onChange={handleChange}
              placeholder="문의 내용을 상세히 입력해주세요"
              className="form-textarea"
              rows={8}
              maxLength={1000}
            />
            <div className="char-count">{formData.content.length}/1000</div>
          </div>

          <div className="form-actions">
            <button type="button" className="btn-cancel" onClick={onClose}>
              취소
            </button>
            <button type="submit" className="btn-submit">
              문의 등록
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// Inquiry Section Component
const InquirySection = () => {
  const { user } = useAuth()
  const [inquiryData, setInquiryData] = useState([])
  const [selectedInquiryId, setSelectedInquiryId] = useState(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)

  const selectedInquiry = inquiryData.find(inquiry => inquiry.id === selectedInquiryId)
  const completedAnswerFallback = '문의해주신 내용 확인되었습니다. 요청하신 사항에 대한 조치를 완료했으며 현재 정상 이용 가능합니다. 추가로 불편한 점이 있으시면 같은 문의에서 다시 남겨주세요.'
  const selectedAnswer = selectedInquiry
    ? ((selectedInquiry.answer ?? '').trim() || (selectedInquiry.status === 'completed' ? completedAnswerFallback : ''))
    : ''

  // 디버깅: 선택된 문의 확인
  useEffect(() => {
    if (selectedInquiry) {
      console.log('🔍 선택된 문의:', selectedInquiry)
      console.log('💬 답변 데이터:', selectedInquiry.answer)
      console.log('📊 상태:', selectedInquiry.status)
    }
  }, [selectedInquiry])

  // 문의 목록 불러오기
  useEffect(() => {
    const fetchInquiries = async () => {
      if (!user?.userId) {
        setIsLoading(false)
        return
      }

      try {
        setIsLoading(true)
        setError(null)
        const response = await fetch(`${API_BASE_URL}/api/inquiries?user_id=${user.userId}`)
        
        if (!response.ok) {
          throw new Error('문의 목록을 불러오는데 실패했습니다')
        }

        const data = await response.json()
        
        console.log('📋 문의 API 응답:', data)
        
        // API 응답 데이터를 프론트엔드 형식으로 변환
        const formattedData = data.map(item => ({
          id: item.id,
          type: item.inquiry_type,
          title: item.title,
          content: item.content,
          date: new Date(item.created_at).toISOString().split('T')[0].replace(/-/g, '.').slice(2),
          status: item.status,
          answer: item.answer
        }))

        console.log('✅ 변환된 문의 데이터:', formattedData)

        setInquiryData(formattedData)
        
        // 첫 번째 문의 자동 선택
        if (formattedData.length > 0 && !selectedInquiryId) {
          setSelectedInquiryId(formattedData[0].id)
        }
      } catch (err) {
        console.error('Error fetching inquiries:', err)
        setError(err.message)
      } finally {
        setIsLoading(false)
      }
    }

    fetchInquiries()
  }, [user])

  const handleCreateInquiry = async (formData) => {
    if (!user?.userId) {
      alert('로그인이 필요합니다.')
      return
    }

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/inquiries`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            user_id: user.userId,
            inquiry_type: formData.type,
            title: formData.title,
            content: formData.content
          })
        }
      )

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || '문의 등록에 실패했습니다')
      }

      const newInquiry = await response.json()
      
      // 프론트엔드 형식으로 변환
      const formattedInquiry = {
        id: newInquiry.id,
        type: newInquiry.inquiry_type,
        title: newInquiry.title,
        content: newInquiry.content,
        date: new Date(newInquiry.created_at).toISOString().split('T')[0].replace(/-/g, '.').slice(2),
        status: newInquiry.status,
        answer: newInquiry.answer
      }

      setInquiryData([formattedInquiry, ...inquiryData])
      setSelectedInquiryId(formattedInquiry.id)
      setIsModalOpen(false)
      alert('문의가 등록되었습니다. 빠른 시일 내에 답변드리겠습니다.')
    } catch (err) {
      console.error('Error creating inquiry:', err)
      alert(err.message || '문의 등록에 실패했습니다.')
    }
  }

  const pendingCount = inquiryData.filter(i => i.status === 'pending').length
  const resolvedCount = inquiryData.filter(i => i.status === 'completed').length

  const getTypeConfig = (type) => {
    const map = {
      '포트폴리오': { label: 'INVESTMENT' },
      '계정/로그인': { label: 'ACCOUNT/LOGIN' },
      '설문조사': { label: 'SURVEY' },
      '서비스 이용': { label: 'SERVICE' },
      '결제/환불': { label: 'PAYMENT' },
      '기타': { label: 'OTHER' },
    }
    return map[type] || { label: type.toUpperCase() }
  }

  const displayName = user?.name || user?.email?.split('@')[0] || 'User'

  return (
    <div className="cs-content-section inq-wrapper">
      {isLoading ? (
        <div className="loading-state"><div className="spinner"></div><p>문의 내역을 불러오는 중...</p></div>
      ) : error ? (
        <div className="error-state"><p className="error-message">{error}</p></div>
      ) : (
        <div className="inq-layout">
          {/* ── Left: greeting + detail ── */}
          <div className="inq-main">
            <div className="inq-greeting">
              <h2 className="inq-greeting-title">Hello, {displayName}.</h2>
              <p className="inq-greeting-sub">
                Welcome to your personal 1:1 inquiry portal. Here you can track the progress of your financial consultations and technical support requests.
              </p>
            </div>

            {selectedInquiry ? (
              <div className="inq-detail-box">
                <div className="inq-detail-topbar">
                  <div className="inq-detail-meta">
                    <span className="inq-type-badge">{getTypeConfig(selectedInquiry.type).label}</span>
                    <span className="inq-detail-date">{selectedInquiry.date}</span>
                  </div>
                  <StatusBadge status={selectedInquiry.status} />
                </div>
                <h3 className="inq-detail-title">{selectedInquiry.title}</h3>
                <p className="inq-detail-content">{selectedInquiry.content}</p>

                {selectedAnswer ? (
                  <div className="inq-support-reply">
                    <div className="inq-support-avatar">S</div>
                    <div className="inq-support-body">
                      <div className="inq-support-name">SeedUP Support Team</div>
                      <p className="inq-support-text">{selectedAnswer}</p>
                    </div>
                  </div>
                ) : (
                  <div className="inq-pending-notice">
                    <span>⏳</span> 담당자에게 배정되었습니다. 빠른 시일 내에 답변드리겠습니다.
                  </div>
                )}
              </div>
            ) : (
              <div className="inq-empty">
                <p>오른쪽 목록에서 문의를 선택해주세요</p>
              </div>
            )}
          </div>

          {/* ── Right: stats + list + button ── */}
          <div className="inq-sidebar">
            <div className="inq-stats">
              <div className="inq-stat-item">
                <span className="inq-stat-num">{String(pendingCount).padStart(2, '0')}</span>
                <span className="inq-stat-label">PENDING</span>
              </div>
              <div className="inq-stat-divider" />
              <div className="inq-stat-item">
                <span className="inq-stat-num">{String(resolvedCount).padStart(2, '0')}</span>
                <span className="inq-stat-label">RESOLVED</span>
              </div>
            </div>

            <div className="inq-list-header">
              <span className="inq-list-title">문의 내역</span>
              <span className="inq-list-all">View All →</span>
            </div>

            <div className="inq-list">
              {inquiryData.length > 0 ? inquiryData.map(inquiry => (
                <button
                  key={inquiry.id}
                  className={`inq-list-item ${selectedInquiryId === inquiry.id ? 'active' : ''}`}
                  onClick={() => setSelectedInquiryId(inquiry.id)}
                >
                  <div className="inq-list-item-top">
                    <span className="inq-type-badge">{getTypeConfig(inquiry.type).label}</span>
                    <span className={`inq-dot-status ${inquiry.status}`}>
                      {inquiry.status === 'pending' ? 'PENDING' : 'COMPLETED'}
                    </span>
                  </div>
                  <p className="inq-list-item-title">{inquiry.title}</p>
                  <span className="inq-list-item-date">{inquiry.date}</span>
                </button>
              )) : (
                <p className="inq-list-empty">등록된 문의가 없습니다</p>
              )}
            </div>

            <button className="inq-write-btn" onClick={() => setIsModalOpen(true)}>
              ✏ &nbsp;문의 작성
            </button>
          </div>
        </div>
      )}

      <InquiryFormModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSubmit={handleCreateInquiry}
      />
    </div>
  )
}

// Main CustomerCenter Component
const CustomerCenterPage = () => {
  const [activeTab, setActiveTab] = useState('faq')

  const menuItems = [
    {
      key: 'faq', label: 'FAQ',
      icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3M12 17h.01"/></svg>
    },
    {
      key: 'inquiry', label: '1:1 문의',
      icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
    }
  ]

  return (
    <div className="customer-center">
      <div className="cs-container">
        <aside className="cs-sidebar">
          <p className="cs-sidebar-category">CATEGORIES</p>
          <nav className="cs-menu">
            {menuItems.map((item) => (
              <button
                key={item.key}
                className={`cs-menu-item ${activeTab === item.key ? 'active' : ''}`}
                onClick={() => setActiveTab(item.key)}
              >
                <span className="menu-icon">{item.icon}</span>
                <span className="menu-label">{item.label}</span>
              </button>
            ))}
          </nav>
        </aside>

        <main className="cs-main-content">
          {activeTab === 'faq' ? <FaqSection /> : <InquirySection />}
        </main>
      </div>
    </div>
  )
}

export default CustomerCenterPage
