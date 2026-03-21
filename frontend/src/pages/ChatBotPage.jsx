import React, { useState, useEffect, useRef } from 'react'
import { useAuth } from '../contexts/AuthContext'
import axios from 'axios'
import './ChatBotPage.css'

// 메시지 포맷팅 컴포넌트
const FormattedMessage = ({ content }) => {
  const formatText = (text) => {
    // 출처 블록 분리: 📰가 포함된 줄 이후를 출처 섹션으로 처리
    const sourcesIdx = text.search(/\n?---?\n?📰/)
    const altIdx = sourcesIdx === -1 ? text.indexOf('\n📰') : sourcesIdx
    const splitIdx = altIdx !== -1 ? altIdx : -1
    const mainText = splitIdx !== -1 ? text.slice(0, splitIdx) : text
    const sourcesRaw = splitIdx !== -1 ? text.slice(splitIdx) : ''
    // 앞뒤 --- 구분선 및 빈 줄 제거
    const sourcesText = sourcesRaw.replace(/^[\n\-]+/, '').replace(/[\n\-]+$/, '')

    const transform = (part) => part
      // 마크다운 링크 처리 ([텍스트](URL)) — 절대 URL(https://) 및 상대 경로(/api/...) 모두 처리
      .replace(/\[([^\]]+)\]\(((?:https?:\/\/|\/)[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="chat-link">$1</a>')
      // 제목 처리 (## 제목)
      .replace(/^##\s+(.+)$/gm, '<h3 class="chat-heading">$1</h3>')
      // 굵은 글자 처리 (**굵은 글자**)
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      // 불릿 포인트 처리 (- 항목 또는 • 항목)
      .replace(/^[•\-]\s+(.+)$/gm, '<div class="chat-bullet">• $1</div>')
      // 번호 목록 처리 (1. 항목)
      .replace(/^(\d+)\.\s+(.+)$/gm, '<div class="chat-numbered">$1. $2</div>')
      // 체크마크와 X 마크 처리
      .replace(/✅\s*([^"\n]*)/g, '<div class="chat-check">✅ $1</div>')
      .replace(/❌\s*([^"\n]*)/g, '<div class="chat-cross">❌ $1</div>')
      .replace(/⚠️\s*([^"\n]*)/g, '<div class="chat-warning">⚠️ $1</div>')
      // 별점 처리
      .replace(/⭐/g, '<span class="chat-star">⭐</span>')
      // 줄바꿈 처리
      .replace(/\n/g, '<br>')

    if (splitIdx !== -1) console.log('[출처블록]', JSON.stringify(sourcesText.slice(0, 200)))
    const mainHtml = transform(mainText)
    if (!sourcesText) return mainHtml

    // 출처 블록: 연속 빈 줄 제거 후 변환
    const sourcesHtml = transform(sourcesText.replace(/\n{2,}/g, '\n'))
    return mainHtml + `<div class="chat-sources">${sourcesHtml}</div>`
  }

  return (
    <div 
      className="formatted-message" 
      dangerouslySetInnerHTML={{ __html: formatText(content) }}
    />
  )
}

const ChatBotPage = () => {
  const { user, isLoggedIn } = useAuth()
  const [messages, setMessages] = useState([])
  const [inputValue, setInputValue] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isLoadingSessions, setIsLoadingSessions] = useState(false)  // 세션 로딩 상태 추가
  const [currentSessionId, setCurrentSessionId] = useState(null)
  const [sessions, setSessions] = useState([])
  const [error, setError] = useState(null)
  const messagesEndRef = useRef(null)

  // 상수 정의로 한글 문자열 분리
  const NEW_CHAT_TITLE = "새로운 대화"
  const LOADING_MESSAGE = "🔄 대화 기록 로딩 중..."
  const FIRST_CHAT_MESSAGE = "💬 첫 번째 대화를 시작해보세요!"
  const AUTO_SAVE_MESSAGE = "대화 내용이 자동으로 저장됩니다"
  const LOGIN_REQUIRED_MESSAGE = "🔑 로그인하면 대화 기록을 저장하고 관리할 수 있습니다"
  const LOCALE_KR = "ko-KR"

  // 디버깅: 사용자 상태 확인
  useEffect(() => {
    console.log('ChatBot - User:', user)
    console.log('ChatBot - IsLoggedIn:', isLoggedIn)
  }, [user, isLoggedIn])

  // 스크롤을 맨 아래로 이동
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  // 컴포넌트 마운트 시 마지막 세션 복원 (비활성화 - 항상 새로운 대화로 시작)
  useEffect(() => {
    // 초기 화면을 유지하기 위해 자동 복원 비활성화
    // if (isLoggedIn && user?.userId) {
    //   const lastSessionId = localStorage.getItem(`lastSessionId_${user.userId}`)
    //   if (lastSessionId) {
    //     setCurrentSessionId(lastSessionId)
    //     console.log('마지막 세션 복원:', lastSessionId)
    //   }
    // }
  }, [isLoggedIn, user?.userId])

  // 컴포넌트 마운트 시 세션 목록 로드 (메시지는 로드하지 않음)
  useEffect(() => {
    if (user?.userId) {  // user.userId 사용
      loadSessions(false) // autoLoadLatest = false - 초기 화면 유지
    }
  }, [user])

  // 세션 목록 로드
  const loadSessions = async (autoLoadLatest = false) => {
    try {
      setIsLoadingSessions(true)
      // 사용자 ID 결정
      let userId
      if (isLoggedIn && user?.userId) {
        userId = user.userId
      } else {
        userId = 999999 // 게스트 사용자
      }
      
      console.log('세션 목록 로드 요청:', { userId, user, isLoggedIn })
      const response = await axios.get(`/api/chat/sessions?user_id=${userId}`)
      console.log('세션 목록 API 응답:', response.data)
      
      if (response.data.success) {
        setSessions(response.data.sessions)
        console.log('세션 목록 로드 성공:', response.data.sessions.length + '개')
        console.log('세션 목록 내용:', response.data.sessions)
        
        // 가장 최근 세션 자동 로드
        if (autoLoadLatest && response.data.sessions.length > 0) {
          // 이미 복원된 세션이 있으면 그것을 우선, 없으면 가장 최근 세션
          const targetSessionId = currentSessionId || response.data.sessions[0].id
          const targetSession = response.data.sessions.find(s => s.id === targetSessionId) || response.data.sessions[0]
          if (!messages.length || currentSessionId !== targetSession.id) { // 메시지가 비어있거나 다른 세션인 경우만 로드
            console.log('세션 메시지 자동 로드:', targetSession.title)
            await loadSessionMessages(targetSession.id)
          }
        }
      } else {
        console.log('세션 목록 로드 실패:', response.data.message || 'No sessions available')
      }
    } catch (err) {
      console.error('세션 목록 로드 오류:', err)
      setError("세션 목록을 불러올 수 없습니다")
    } finally {
      setIsLoadingSessions(false)
    }
  }

  // 특정 세션의 메시지 로드
  const loadSessionMessages = async (sessionId) => {
    try {
      // 사용자 ID 결정
      let userId
      if (isLoggedIn && user?.userId) {
        userId = user.userId
      } else {
        userId = 999999 // 게스트 사용자
      }
      
      console.log('메시지 로드 요청:', { sessionId, userId })
      const response = await axios.get(`/api/chat/sessions/${sessionId}/messages?user_id=${userId}`)
      if (response.data.success) {
        setMessages(response.data.messages.map(msg => ({
          id: msg.id,
          role: msg.role,
          content: msg.content,
          timestamp: new Date(msg.created_at)
        })))
        setCurrentSessionId(sessionId)        
        // 로그인한 사용자의 마지막 세션 ID 저장
        if (isLoggedIn && user?.userId) {
          localStorage.setItem(`lastSessionId_${user.userId}`, sessionId)
        }        console.log('메시지 로드 성공:', response.data.messages.length)
      } else {
        console.log('메시지 로드:', response.data.message || 'No messages available')
        setMessages([])
      }
    } catch (err) {
      console.error('메시지 로드 오류:', err)
      setError("메시지를 불러올 수 없습니다")
    }
  }

  // 채팅 세션 삭제
  const deleteSession = async (e, sessionId) => {
    e.stopPropagation()
    if (!window.confirm('이 대화를 삭제하시겠습니까?')) return

    try {
      const userId = isLoggedIn && user?.userId ? user.userId : 999999
      await axios.delete(`/api/chat/session/${sessionId}?user_id=${userId}`)

      if (currentSessionId === sessionId) {
        setMessages([])
        setCurrentSessionId(null)
        if (isLoggedIn && user?.userId) {
          localStorage.removeItem(`lastSessionId_${user.userId}`)
        }
      }

      await loadSessions(false)
    } catch (err) {
      console.error('세션 삭제 오류:', err)
      setError('대화 삭제에 실패했습니다.')
    }
  }

  // 새 채팅 시작
  const startNewChat = () => {
    setMessages([])
    setCurrentSessionId(null)
    setError(null)
    
    // 로그인한 사용자의 마지막 세션 ID 삭제
    if (isLoggedIn && user?.userId) {
      localStorage.removeItem(`lastSessionId_${user.userId}`)
    }
  }

  // 메시지 전송
  const sendMessage = async (messageText = inputValue) => {
    if (!messageText.trim()) return

    // 사용자 정보 디버깅
    console.log('ChatBot - 메시지 전송:', {
      user,
      isLoggedIn,
      userId: user?.userId,  // user.userId 사용
      messageText
    })

    // 사용자 ID 결정 (로그인한 사용자는 실제 ID, 게스트는 999999)
    let userId
    if (isLoggedIn && user?.userId) {  // user.userId 사용
      userId = user.userId  // 로그인한 사용자의 실제 ID
      console.log('로그인한 사용자 ID:', userId)
    } else {
      userId = 999999   // 게스트 사용자 ID
      console.log('게스트 사용자 ID:', userId)
    }

    const userMessage = {
      id: Date.now() + Math.random(),
      role: 'user',
      content: messageText.trim(),
      timestamp: new Date()
    }

    setMessages(prev => [...prev, userMessage])
    setInputValue('')
    setIsLoading(true)
    setError(null)

    try {
      // 일반 채팅 API 호출 (비스트리밍) - POST body에 user_id 포함
      const response = await axios.post('/api/chat/send', {
        user_id: userId,  // POST body에 user_id 포함
        message: messageText.trim(),
        session_id: currentSessionId
      })

      const assistantMessage = {
        id: Date.now() + Math.random() + 1,
        role: 'assistant',
        content: response.data.message,
        timestamp: new Date()
      }

      setMessages(prev => [...prev, assistantMessage])
      
      // 세션 ID 업데이트 및 목록 새로고침
      if (!currentSessionId && response.data.session_id) {
        console.log('새 세션 생성됨:', response.data.session_id)
        setCurrentSessionId(response.data.session_id)
        // 로그인한 사용자의 마지막 세션 ID 저장
        if (isLoggedIn && user?.userId) {
          localStorage.setItem(`lastSessionId_${user.userId}`, response.data.session_id)
        }
      }
      
      // 로그인한 사용자는 항상 세션 목록 새로고침 (세션 업데이트 반영)
      if (isLoggedIn) {
        console.log('세션 목록 새로고침 시작...')
        setTimeout(() => {
          loadSessions(false) // 지연 후 세션 목록 새로고침
        }, 500) // 500ms 후 새로고침 (DB 저장 완료 대기)
      }

    } catch (err) {
      console.error('메시지 전송 오류:', err)
      setError("메시지 전송에 실패했습니다. 다시 시도해주세요.")
      
      // 오류 메시지 표시
      const errorMessage = {
        id: Date.now() + Math.random() + 1,
        role: 'assistant',
        content: err.response?.status === 404 ? 
          "로그인이 필요한 서비스입니다. 로그인 후 이용해주세요." : 
          "죄송합니다. 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
        timestamp: new Date(),
        isError: true
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }

  // 엔터키 처리
  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  // 날짜·시간 파싱 (MySQL "YYYY-MM-DD HH:MM:SS" 형식 대응)
  const parseDate = (timestamp) => {
    if (!timestamp) return null
    const date = new Date(
      typeof timestamp === 'string' ? timestamp.replace(' ', 'T') : timestamp
    )
    return isNaN(date.getTime()) ? null : date
  }

  // 시간 포맷팅 (날짜 + 시간)
  const formatTime = (timestamp) => {
    const date = parseDate(timestamp)
    if (!date) return ''
    return date.toLocaleString(LOCALE_KR, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  // 메시지 삭제
  const deleteMessage = async (messageId) => {
    if (!user?.userId) return
    try {
      await axios.delete(`/api/chat/message/${messageId}?user_id=${user.userId}`)
      setMessages(prev => prev.filter(m => m.id !== messageId))
    } catch (e) {
      console.error('메시지 삭제 실패:', e)
    }
  }

  // 빠른 질문 목록
  const quickQuestions = [
    "내 포트폴리오 수익률은 어떤가요?",
    "지금 어떤 종목을 매수하면 좋을까요?",
    "삼성전자 주가 전망을 알려주세요",
    "분산투자가 뭔가요?",
    "리밸런싱이 필요한지 알려주세요"
  ]

  return (
    <div className="chatbot-page">
      <div className="chatbot-sidebar">
        <div className="sidebar-header">
          <div className="bot-icon">
            <svg width="36" height="36" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M 50 75 Q 48 65, 47 55 Q 46 45, 48 38" fill="none" stroke="#5a9068" strokeWidth="6" strokeLinecap="round" />
              <path d="M 48 38 Q 35 35, 25 28 Q 18 23, 16 18 Q 16 15, 19 14 Q 23 14, 28 18 Q 38 25, 48 38" fill="#5a9068" fillOpacity="0.95" stroke="#5a9068" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M 48 38 Q 38 32, 30 26" fill="none" stroke="#4a7a58" strokeWidth="2" strokeLinecap="round" opacity="0.6" />
              <path d="M 48 38 Q 61 35, 71 28 Q 78 23, 80 18 Q 80 15, 77 14 Q 73 14, 68 18 Q 58 25, 48 38" fill="#5a9068" fillOpacity="0.95" stroke="#5a9068" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M 48 38 Q 58 32, 66 26" fill="none" stroke="#4a7a58" strokeWidth="2" strokeLinecap="round" opacity="0.6" />
              <ellipse cx="50" cy="78" rx="8" ry="3.5" fill="#5a9068" opacity="0.85" />
            </svg>
          </div>
          <span>SEED UP</span>
        </div>

        <button className="new-chat-btn" onClick={startNewChat}>
          ➕ 새 채팅
        </button>

        <div className="chat-sessions">
          {isLoggedIn ? (
            isLoadingSessions ? (
              <div className="session-placeholder" style={{
                padding: '20px',
                textAlign: 'center',
                color: '#666',
                fontSize: '14px'
              }}>
                {LOADING_MESSAGE}
              </div>
            ) : sessions.length > 0 ? (
              <ul className="session-list">
                {sessions.map((session) => (
                  <li
                    key={session.id}
                    className={`session-item ${currentSessionId === session.id ? 'active' : ''}`}
                    onClick={() => loadSessionMessages(session.id)}
                  >
                    <div className="session-item-content">
                      <div className="session-title">{session.title || NEW_CHAT_TITLE}</div>
                      <div className="session-item-footer">
                        <div className="session-time">
                          {session.updated_at ? new Date(session.updated_at).toLocaleDateString(LOCALE_KR) : "N/A"}
                        </div>
                        <button
                          className="session-delete-btn"
                          onClick={(e) => deleteSession(e, session.id)}
                          title="대화 삭제"
                        >✕</button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="session-placeholder" style={{
                padding: '20px',
                textAlign: 'center',
                color: '#666',
                fontSize: '14px'
              }}>
                {FIRST_CHAT_MESSAGE}<br />
                <small style={{ color: '#999' }}>{AUTO_SAVE_MESSAGE}</small>
              </div>
            )
          ) : (
            <div className="session-placeholder" style={{
              padding: '20px',
              textAlign: 'center',
              color: '#666',
              fontSize: '14px'
            }}>
              {LOGIN_REQUIRED_MESSAGE}
            </div>
          )}
        </div>
      </div>


      <div className="chatbot-main">
        <div className="chat-header">
          <div>
            <div className="chat-title">투자 전문 AI Assistant</div>
            <div className="chat-subtitle">개인화된 투자 상담 및 포트폴리오 관리</div>
          </div>
          
          <div className="user-info">
            <div className="status-dot"></div>
            <span>{user?.username || "게스트 사용자"}</span>
            {!isLoggedIn && <span style={{fontSize: '12px', color: '#666'}}>(체험하기)</span>}
          </div>
        </div>

        <div className="chat-messages">
          <div className="messages-container">
            {messages.length === 0 ? (
              <div className="empty-chat">
                <div className="empty-icon">💬</div>
                <div className="empty-title">안녕하세요! 투자 전문 AI입니다</div>
                <div className="empty-subtitle">
                  포트폴리오 분석, 종목 추천, 투자 조언 등<br />
                  무엇이든 물어보세요
                </div>
                
                <div className="quick-questions">
                  {quickQuestions.map((question, index) => (
                    <button
                      key={index}
                      className="quick-question-btn"
                      onClick={() => sendMessage(question)}
                      disabled={isLoading}
                    >
                      {question}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <>
                {messages.map((message) => (
                  <div key={message.id} className={`message ${message.role}`}>
                    <div className="message-avatar">
                      {message.role === 'user' ? (user?.username?.[0] || 'U') : (
                        <svg width="20" height="20" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
                          <path d="M 50 75 Q 48 65, 47 55 Q 46 45, 48 38" fill="none" stroke="currentColor" strokeWidth="6" strokeLinecap="round" />
                          <path d="M 48 38 Q 35 35, 25 28 Q 18 23, 16 18 Q 16 15, 19 14 Q 23 14, 28 18 Q 38 25, 48 38" fill="currentColor" fillOpacity="0.95" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
                          <path d="M 48 38 Q 38 32, 30 26" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" opacity="0.6" />
                          <path d="M 48 38 Q 61 35, 71 28 Q 78 23, 80 18 Q 80 15, 77 14 Q 73 14, 68 18 Q 58 25, 48 38" fill="currentColor" fillOpacity="0.95" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
                          <path d="M 48 38 Q 58 32, 66 26" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" opacity="0.6" />
                          <ellipse cx="50" cy="78" rx="8" ry="3.5" fill="currentColor" opacity="0.85" />
                        </svg>
                      )}
                    </div>
                    <div className="message-content">
                      {message.id && isLoggedIn && (
                        <button
                          className="message-delete-btn"
                          onClick={() => deleteMessage(message.id)}
                          title="메시지 삭제"
                        >✕</button>
                      )}
                      {message.role === 'assistant' ? (
                        <FormattedMessage content={message.content} />
                      ) : (
                        message.content
                      )}
                      <div className="message-time">
                        {formatTime(message.timestamp)}
                      </div>
                    </div>
                  </div>
                ))}
                
                {isLoading && (
                  <div className="message assistant">
                    <div className="message-avatar">
                      <svg width="20" height="20" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M 50 75 Q 48 65, 47 55 Q 46 45, 48 38" fill="none" stroke="currentColor" strokeWidth="6" strokeLinecap="round" />
                        <path d="M 48 38 Q 35 35, 25 28 Q 18 23, 16 18 Q 16 15, 19 14 Q 23 14, 28 18 Q 38 25, 48 38" fill="currentColor" fillOpacity="0.95" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
                        <path d="M 48 38 Q 38 32, 30 26" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" opacity="0.6" />
                        <path d="M 48 38 Q 61 35, 71 28 Q 78 23, 80 18 Q 80 15, 77 14 Q 73 14, 68 18 Q 58 25, 48 38" fill="currentColor" fillOpacity="0.95" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
                        <path d="M 48 38 Q 58 32, 66 26" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" opacity="0.6" />
                        <ellipse cx="50" cy="78" rx="8" ry="3.5" fill="currentColor" opacity="0.85" />
                      </svg>
                    </div>
                    <div className="message-content">
                      <div className="typing-indicator">
                        <div className="typing-dot"></div>
                        <div className="typing-dot"></div>
                        <div className="typing-dot"></div>
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        <div className="chat-input">
          <div className="input-container">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder={isLoggedIn ? "투자 관련 궁금한 것을 물어보세요..." : "로그인하면 개인화된 상담을 받을 수 있습니다"}
              disabled={isLoading}
            />
          </div>
          
          <button
            className="send-btn"
            onClick={() => sendMessage()}
            disabled={!inputValue.trim() || isLoading}
          >
            {isLoading ? '⏳' : '🚀'}
          </button>
        </div>

        {error && (
          <div className="error-message" style={{
            padding: '10px 20px',
            background: '#ffebee',
            color: '#c62828',
            textAlign: 'center'
          }}>
            {error}
          </div>
        )}
      </div>
    </div>
  )
}

export default ChatBotPage
