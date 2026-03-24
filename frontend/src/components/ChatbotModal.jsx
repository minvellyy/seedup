import React, { useState, useEffect, useRef } from 'react'
import { useAuth } from '../contexts/AuthContext'
import './ChatbotModal.css'

function MarkdownMessage({ text }) {
  const lines = text.split('\n')
  const elements = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    // 빈 줄
    if (line.trim() === '') {
      i++
      continue
    }

    // 제목
    const headingMatch = line.match(/^(#{1,3})\s+(.+)/)
    if (headingMatch) {
      const level = headingMatch[1].length
      const Tag = `h${level}`
      elements.push(<Tag key={i} className={`md-h${level}`}>{parseInline(headingMatch[2])}</Tag>)
      i++
      continue
    }

    // 구분선
    if (/^---+$/.test(line.trim())) {
      elements.push(<hr key={i} className="md-hr" />)
      i++
      continue
    }

    // 순서 없는 목록 수집
    if (/^[-*]\s/.test(line)) {
      const items = []
      while (i < lines.length && /^[-*]\s/.test(lines[i])) {
        items.push(<li key={i}>{parseInline(lines[i].replace(/^[-*]\s/, ''))}</li>)
        i++
      }
      elements.push(<ul key={`ul-${i}`} className="md-ul">{items}</ul>)
      continue
    }

    // 순서 있는 목록 수집
    if (/^\d+\.\s/.test(line)) {
      const items = []
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        items.push(<li key={i}>{parseInline(lines[i].replace(/^\d+\.\s/, ''))}</li>)
        i++
      }
      elements.push(<ol key={`ol-${i}`} className="md-ol">{items}</ol>)
      continue
    }

    // 일반 문단
    elements.push(<p key={i} className="md-p">{parseInline(line)}</p>)
    i++
  }

  return <div className="chat-markdown">{elements}</div>
}

function parseInline(text) {
  // 굵게 + 기울임
  const parts = []
  const regex = /(\*\*\*(.+?)\*\*\*)|(\*\*(.+?)\*\*)|(\*(.+?)\*)|(\[(.+?)\]\((.+?)\))|(`(.+?)`)/g
  let last = 0
  let match
  let key = 0

  while ((match = regex.exec(text)) !== null) {
    if (match.index > last) {
      parts.push(text.slice(last, match.index))
    }
    if (match[1]) {
      parts.push(<strong key={key++}><em>{match[2]}</em></strong>)
    } else if (match[3]) {
      parts.push(<strong key={key++}>{match[4]}</strong>)
    } else if (match[5]) {
      parts.push(<em key={key++}>{match[6]}</em>)
    } else if (match[7]) {
      parts.push(<a key={key++} href={match[9]} target="_blank" rel="noreferrer">{match[8]}</a>)
    } else if (match[10]) {
      parts.push(<code key={key++}>{match[11]}</code>)
    }
    last = match.index + match[0].length
  }

  if (last < text.length) {
    parts.push(text.slice(last))
  }

  return parts.length > 0 ? parts : text
}

const API_BASE_URL = ''

const BUTTON_SIZE = 56   // px
const BUTTON_MARGIN = 24  // 1.5rem
const MODAL_GAP = 8       // px between button and modal

function ChatbotModal() {
  const { user } = useAuth()
  const [showChatbot, setShowChatbot] = useState(false)
  const [chatMessages, setChatMessages] = useState([])
  const [chatInput, setChatInput] = useState('')
  const [bottomOffset, setBottomOffset] = useState(BUTTON_MARGIN)
  const chatMessagesEndRef = useRef(null)

  useEffect(() => {
    if (chatMessagesEndRef.current) {
      chatMessagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [chatMessages])

  useEffect(() => {
    const footer = document.querySelector('.footer')
    if (!footer) return

    const updatePosition = () => {
      const footerRect = footer.getBoundingClientRect()
      const viewportHeight = window.innerHeight
      const footerVisibleHeight = Math.max(0, viewportHeight - footerRect.top)
      setBottomOffset(footerVisibleHeight + BUTTON_MARGIN)
    }

    updatePosition()
    window.addEventListener('scroll', updatePosition, { passive: true })
    window.addEventListener('resize', updatePosition)
    return () => {
      window.removeEventListener('scroll', updatePosition)
      window.removeEventListener('resize', updatePosition)
    }
  }, [])

  const handleSendMessage = async () => {
    if (!chatInput.trim()) return

    const userMessage = {
      id: Date.now(),
      text: chatInput,
      sender: 'user',
      timestamp: new Date()
    }

    setChatMessages(prev => [...prev, userMessage])
    const currentMessage = chatInput
    setChatInput('')

    const loadingMessage = {
      id: Date.now() + 1,
      text: '답변을 생성하는 중...',
      sender: 'bot',
      timestamp: new Date(),
      loading: true
    }
    setChatMessages(prev => [...prev, loadingMessage])

    try {
      const response = await fetch(`${API_BASE_URL}/api/chat/send`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: user?.userId || 999999,
          message: currentMessage,
          session_id: null
        })
      })

      if (!response.ok) {
        const errorText = await response.text()
        console.error('[챗봇] API 오류 응답:', errorText)
        throw new Error(`챗봇 응답 실패: ${response.status}`)
      }

      const data = await response.json()

      setChatMessages(prev => {
        const filtered = prev.filter(msg => !msg.loading)
        return [...filtered, {
          id: Date.now(),
          text: data.message || data.response || '응답을 받았지만 내용이 비어있습니다.',
          sender: 'bot',
          timestamp: new Date()
        }]
      })
    } catch (error) {
      console.error('[챗봇] 오류 발생:', error)
      setChatMessages(prev => {
        const filtered = prev.filter(msg => !msg.loading)
        return [...filtered, {
          id: Date.now(),
          text: `죄송합니다. 오류가 발생했습니다: ${error.message}`,
          sender: 'bot',
          timestamp: new Date(),
          error: true
        }]
      })
    }
  }

  return (
    <>
      {/* 플로팅 챗봇 버튼 */}
      <button
        className="chatbot-float-button"
        style={{ bottom: bottomOffset }}
        onClick={() => setShowChatbot(!showChatbot)}
        aria-label="챗봇 열기"
      >
        <svg width="46" height="46" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
          {/* 줄기 */}
          <path
            d="M 50 75 Q 48 65, 47 55 Q 46 45, 48 38"
            fill="none"
            stroke="#ffffff"
            strokeWidth="6"
            strokeLinecap="round"
          />
          {/* 왼쪽 잎 */}
          <path
            d="M 48 38 Q 35 35, 25 28 Q 18 23, 16 18 Q 16 15, 19 14 Q 23 14, 28 18 Q 38 25, 48 38"
            fill="#ffffff"
            fillOpacity="0.95"
            stroke="#ffffff"
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {/* 왼쪽 잎 중심맥 */}
          <path
            d="M 48 38 Q 38 32, 30 26"
            fill="none"
            stroke="#6FBF8F"
            strokeWidth="2"
            strokeLinecap="round"
            opacity="0.6"
          />
          {/* 오른쪽 잎 */}
          <path
            d="M 48 38 Q 61 35, 71 28 Q 78 23, 80 18 Q 80 15, 77 14 Q 73 14, 68 18 Q 58 25, 48 38"
            fill="#ffffff"
            fillOpacity="0.95"
            stroke="#ffffff"
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {/* 오른쪽 잎 중심맥 */}
          <path
            d="M 48 38 Q 58 32, 66 26"
            fill="none"
            stroke="#6FBF8F"
            strokeWidth="2"
            strokeLinecap="round"
            opacity="0.6"
          />
          {/* 줄기 하단 */}
          <ellipse
            cx="50"
            cy="78"
            rx="8"
            ry="3.5"
            fill="#ffffff"
            opacity="0.85"
          />
        </svg>
      </button>

      {/* 챗봇 모달 */}
      {showChatbot && (
        <div className="chatbot-modal" style={{ bottom: bottomOffset + BUTTON_SIZE + MODAL_GAP }}>
          <div className="chatbot-header">
            <h3>투자 도우미 챗봇</h3>
            <button onClick={() => setShowChatbot(false)} className="chatbot-close-button">
              ✕
            </button>
          </div>
          <div className="chatbot-messages">
            {chatMessages.length === 0 ? (
              <div className="chatbot-welcome">
                <p>안녕하세요! 투자 관련 질문이 있으시면 언제든지 물어보세요.</p>
              </div>
            ) : (
              <>
                {chatMessages.map((msg) => (
                  <div key={msg.id} className={`chat-message ${msg.sender} ${msg.loading ? 'loading' : ''} ${msg.error ? 'error' : ''}`}>
                    {msg.sender === 'bot' && !msg.loading
                      ? <MarkdownMessage text={msg.text} />
                      : <p>{msg.text}</p>
                    }
                  </div>
                ))}
                <div ref={chatMessagesEndRef} />
              </>
            )}
          </div>
          <div className="chatbot-input">
            <input
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
              placeholder="질문을 입력하세요..."
            />
            <button onClick={handleSendMessage}>전송</button>
          </div>
        </div>
      )}
    </>
  )
}

export default ChatbotModal
