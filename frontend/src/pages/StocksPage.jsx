import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import './StocksPage.css'

const PERIOD_OPTIONS = [
  { value: 'realtime', label: '실시간' },
  { value: '1d', label: '1일' },
  { value: '1w', label: '1주일' },
  { value: '1m', label: '1개월' },
  { value: '3m', label: '3개월' },
  { value: '6m', label: '6개월' },
]

// 종목코드 -> 종목명 매핑 (주요 종목)
const STOCK_NAME_MAP = {
  '005930': '삼성전자',
  '373220': 'LG에너지솔루션',
  '000660': 'SK하이닉스',
  '207940': '삼성바이오로직스',
  '005935': '삼성전자우',
  '051910': 'LG화학',
  '006400': '삼성SDI',
  '005380': '현대차',
  '336260': '두산퓨얼셀',
  '000270': '기아',
  '068270': '셀트리온',
  '035420': 'NAVER',
  '105560': 'KB금융',
  '055550': '신한지주',
  '035720': '카카오',
  '012330': '현대모비스',
  '028260': '삼성물산',
  '066570': 'LG전자',
  '003670': '포스코퓨처엠',
  '096770': 'SK이노베이션',
  '017670': 'SK텔레콤',
  '009150': '삼성전기',
  '032830': '삼성생명',
  '018260': '삼성에스디에스',
  '033780': 'KT&G',
  '003550': 'LG',
  '015760': '한국전력',
  '010130': '고려아연',
  '047050': '포스코인터내셔널',
  '086790': '하나금융지주',
  '034730': 'SK',
  '030200': 'KT',
  '323410': '카카오뱅크',
  '251270': '넷마블',
  '036570': '엔씨소프트',
  '259960': '크래프톤',
  '047810': '한국항공우주',
  '402340': 'SK스퀘어',
  '042700': '한미반도체',
  '011200': 'HMM',
  '352820': '하이브',
  '003490': '대한항공',
  '009540': 'HD한국조선해양',
  '010950': 'S-Oil',
  '000810': '삼성화재',
  '086280': '현대글로비스',
  '138040': '메리츠금융지주',
  '316140': '우리금융지주',
  '024110': '기업은행',
  '161390': '한국타이어앤테크놀로지',
  '011070': 'LG이노텍',
  '329180': '현대에너지솔루션',
  '010140': '삼성중공업',
  '267250': 'HD현대',
  '377300': '카카오페이',
  '004020': '현대제철',
  '034020': '두산에너빌리티',
  '271560': '오리온',
  '241560': '두산밥캣',
  '003540': '대신증권',
  '004170': '신세계',
  '012450': '한화에어로스페이스',
  '361610': 'SK아이이테크놀로지',
  '139480': '이마트',
  '018880': '한온시스템',
  '081660': '휠라홀딩스',
  '128940': '한미약품',
  '097950': 'CJ제일제당',
  '000720': '현대건설',
  '078930': 'GS',
  '004990': '롯데칠성',
  '006260': 'LS',
  '004370': '농심',
  '006800': '미래에셋증권',
  '071050': '한국금융지주',
  '000100': '유한양행',
  '005940': 'NH투자증권',
  '043260': '성호전자',
  '348210': '넥스틴',
  '263750': '펄어비스',
  '293490': '카카오게임즈',
  '282330': 'BGF리테일',
  '001230': '동국제강',
  '005490': 'POSCO홀딩스',
  '009830': '한화솔루션',
  '002380': 'KCC',
  '088350': '한화생명',
  '064350': '현대로템',
  '009970': '영원무역홀딩스',
  '003620': 'KG모빌리티',
  '004000': '롯데정밀화학',
  '298020': '효성티앤씨',
  '298050': '효성첨단소재',
  '298040': '효성중공업',
  '051900': 'LG생활건강',
  '180640': '한진칼',
  '000120': 'CJ대한통운',
  '108670': 'LX세미콘',
  '145020': '휴젤',
}

const INFINITE_SCROLL_STEP = 20
const INFINITE_SCROLL_MAX  = 50

function StocksPage() {
  const navigate = useNavigate()
  const [period, setPeriod] = useState('realtime')
  const [topStocks, setTopStocks] = useState([])
  const [visibleCount, setVisibleCount] = useState(INFINITE_SCROLL_STEP)
  const [selectedStockCode, setSelectedStockCode] = useState(null)
  const [searchKeyword, setSearchKeyword] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [showSearchResults, setShowSearchResults] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // 무한 스크롤 — 리스트 컨테이너 & 하단 sentinel refs
  const listRef      = useRef(null)
  const sentinelRef  = useRef(null)

  // SSE 연결 관리
  const esRef = useRef(null)
  const subscribedCodesRef = useRef('')

  // 거래대금 Top 100 데이터 가져오기
  const fetchTopStocks = async (selectedPeriod) => {
    try {
      setLoading(true)
      setError(null)
      const response = await fetch(`/api/v1/stocks/top?period=${selectedPeriod}`)
      
      if (!response.ok) {
        throw new Error(`API 요청 실패: ${response.status}`)
      }
      
      const data = await response.json()
      
      // 데이터 포맷 변환 (API 응답 형식에 따라 조정)
      const formattedData = data.map((stock, index) => {
        const stockCode = stock.stock_code || stock.code
        // API에서 받은 종목명이 있고, 종목코드와 다르면 사용
        let stockName = stock.stock_name || stock.name || ''
        
        // API 종목명이 없거나 종목코드와 같으면 매핑 테이블 사용
        if (!stockName || stockName === stockCode) {
          stockName = STOCK_NAME_MAP[stockCode] || stockCode
        }
        
        return {
          rank: index + 1,
          code: stockCode,
          name: stockName,
          market: stock.market || 'KOSPI',
          price: stock.current_price || stock.price || 0,
          changeRate: stock.change_rate || stock.changeRate || 0,
          volume: stock.volume || 0,
          isFavorite: false, // 추후 사용자 관심종목 API 연동 시 업데이트
        }
      })
      
      setTopStocks(formattedData)
    } catch (err) {
      console.error('거래대금 Top 100 조회 오류:', err)
      setError(err.message)
      // 오류 시 빈 배열로 초기화
      setTopStocks([])
    } finally {
      setLoading(false)
    }
  }

  // 실시간 주가 업데이트 SSE 연결
  const connectSSE = useCallback((stockCodes) => {
    if (!stockCodes || stockCodes.length === 0) return
    
    const codeStr = stockCodes.join(',')
    
    // 이미 같은 종목들을 구독 중이면 재연결 안 함
    if (codeStr === subscribedCodesRef.current) return
    
    subscribedCodesRef.current = codeStr
    
    // 기존 연결 종료
    if (esRef.current) {
      esRef.current.close()
    }
    
    // 새로운 SSE 연결
    const es = new EventSource(`/api/stream/prices?codes=${codeStr}`)
    esRef.current = es
    
    es.onmessage = (e) => {
      try {
        const updates = JSON.parse(e.data)
        
        // 받은 업데이트로 topStocks 상태 업데이트
        setTopStocks(prevStocks =>
          prevStocks.map(stock => {
            const update = updates[stock.code]
            if (!update) return stock
            
            return {
              ...stock,
              price: update.current_price || stock.price,
              changeRate: update.change_rate || stock.changeRate,
              volume: update.volume || stock.volume,
            }
          })
        )
      } catch (err) {
        console.warn('SSE 메시지 파싱 오류:', err)
      }
    }
    
    es.onerror = (err) => {
      console.warn('SSE 연결 오류:', err)
      // EventSource는 자동으로 재연결 시도함
    }
  }, [])

  // 기간 변경 시 데이터 다시 가져오기 + visibleCount 초기화
  useEffect(() => {
    setVisibleCount(INFINITE_SCROLL_STEP)
    fetchTopStocks(period)
  }, [period])

  // 무한 스크롤 — sentinel이 리스트 내 viewport에 들어오면 visibleCount 증가
  useEffect(() => {
    if (!sentinelRef.current || !listRef.current) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          setVisibleCount(prev => Math.min(prev + INFINITE_SCROLL_STEP, INFINITE_SCROLL_MAX))
        }
      },
      { root: listRef.current, threshold: 0.1 }
    )
    observer.observe(sentinelRef.current)
    return () => observer.disconnect()
  }, [loading])

  // topStocks 업데이트 시 SSE 재연결
  useEffect(() => {
    if (topStocks.length > 0) {
      const codes = topStocks.map(stock => stock.code)
      connectSSE(codes)
    }
    
    // cleanup: 컴포넌트 언마운트 시 연결 종료
    return () => {
      if (esRef.current) {
        esRef.current.close()
        esRef.current = null
      }
    }
  }, [topStocks.length, connectSSE])

  // 검색어 변경 시 자동완성
  useEffect(() => {
    if (searchKeyword.trim() === '') {
      setSearchResults([])
      setShowSearchResults(false)
      return
    }

    // Debounce를 위한 타이머
    const timer = setTimeout(async () => {
      try {
        // API로 검색 요청
        const response = await fetch(`/api/v1/stocks/search?q=${encodeURIComponent(searchKeyword)}`)
        
        if (response.ok) {
          const data = await response.json()
          const formattedResults = data.map(stock => {
            const stockCode = stock.stock_code || stock.code
            const stockName = STOCK_NAME_MAP[stockCode] || stock.stock_name || stock.name || stockCode
            return {
              code: stockCode,
              name: stockName,
              market: stock.market || 'KOSPI',
              price: stock.current_price || stock.price || 0,
              changeRate: stock.change_rate || stock.changeRate || 0,
            }
          })
          setSearchResults(formattedResults)
        } else {
          // API 실패 시 topStocks에서 로컬 검색
          const filtered = topStocks.filter(stock => 
            stock.name.toLowerCase().includes(searchKeyword.toLowerCase()) ||
            stock.code.includes(searchKeyword)
          ).slice(0, 10)
          setSearchResults(filtered)
        }
        
        setShowSearchResults(true)
      } catch (err) {
        console.warn('검색 API 오류, 로컬 검색 사용:', err)
        // API 오류 시 topStocks에서 로컬 검색
        const filtered = topStocks.filter(stock => 
          stock.name.toLowerCase().includes(searchKeyword.toLowerCase()) ||
          stock.code.includes(searchKeyword)
        ).slice(0, 10)
        setSearchResults(filtered)
        setShowSearchResults(true)
      }
    }, 300)

    return () => clearTimeout(timer)
  }, [searchKeyword, topStocks])

  // 관심종목 토글
  const toggleFavorite = (stockCode) => {
    setTopStocks(prevStocks => 
      prevStocks.map(stock => 
        stock.code === stockCode 
          ? { ...stock, isFavorite: !stock.isFavorite }
          : stock
      )
    )
  }

  // 종목 선택
  const handleStockClick = (stockCode) => {
    setSelectedStockCode(stockCode)
    navigate(`/stock/${stockCode}`)
  }

  // 검색 결과 선택
  const handleSearchResultClick = (stock) => {
    setSearchKeyword('')
    setShowSearchResults(false)
    handleStockClick(stock.code)
  }

  // 가격 포맷팅
  const formatPrice = (price) => {
    return new Intl.NumberFormat('ko-KR').format(price)
  }

  // 등락률 포맷팅
  const formatChangeRate = (rate) => {
    const sign = rate > 0 ? '+' : ''
    return `${sign}${rate.toFixed(2)}%`
  }

  // 거래량 포맷팅
  const formatVolume = (volume) => {
    if (volume >= 1000000) {
      return `${(volume / 1000000).toFixed(1)}M`
    } else if (volume >= 1000) {
      return `${(volume / 1000).toFixed(1)}K`
    }
    return volume.toLocaleString()
  }

  // 종목별 고유 색상 생성
  const getStockColor = (code) => {
    const colors = [
      { bg: '#3B82F6', text: '#FFFFFF' }, // 파랑
      { bg: '#DC2626', text: '#FFFFFF' }, // 빨강
      { bg: '#F59E0B', text: '#FFFFFF' }, // 주황
      { bg: '#10B981', text: '#FFFFFF' }, // 초록
      { bg: '#8B5CF6', text: '#FFFFFF' }, // 보라
      { bg: '#EC4899', text: '#FFFFFF' }, // 핑크
      { bg: '#14B8A6', text: '#FFFFFF' }, // 청록
      { bg: '#F97316', text: '#FFFFFF' }, // 진한 주황
      { bg: '#6366F1', text: '#FFFFFF' }, // 인디고
      { bg: '#EF4444', text: '#FFFFFF' }, // 밝은 빨강
    ]
    const hash = code.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0)
    return colors[hash % colors.length]
  }

  return (
    <div className="stocks-page">
      {/* 페이지 헤더 */}
      <div className="stocks-page-header">
        <div className="header-content">
          <h1 className="page-title">실시간 조회</h1>
          <p className="page-description">실시간으로 거래가 활발한 종목을 확인하고 원하는 종목을 검색해보세요.</p>
        </div>
      </div>

      {/* 메인 컨텐츠 */}
      <div className="stocks-page-body">
        {/* 좌측: 거래대금 Top 100 섹션 */}
        <div className="top-stocks-section">
          <div className="section-card">
            <div className="section-header">
              <h2 className="section-title">거래대금 Top 100</h2>
              <div className="update-time">실시간 업데이트</div>
            </div>

            {/* 종목 리스트 */}
            <div className="stocks-list" ref={listRef}>
              {loading ? (
                <div className="loading-state">
                  {[...Array(10)].map((_, i) => (
                    <div key={i} className="skeleton-row"></div>
                  ))}
                </div>
              ) : error ? (
                <div className="empty-state">
                  <div className="empty-icon">⚠️</div>
                  <p>{error}</p>
                  <button 
                    className="retry-btn"
                    onClick={() => fetchTopStocks(period)}
                  >
                    다시 시도
                  </button>
                </div>
              ) : topStocks.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-icon">📊</div>
                  <p>조회 가능한 종목이 없습니다.</p>
                </div>
              ) : (
                topStocks.slice(0, visibleCount).map(stock => {
                  const stockColor = getStockColor(stock.code)
                  const displayName = stock.name
                  const logoText = displayName.length <= 3 ? displayName : displayName.substring(0, 3)
                  return (
                  <div
                    key={stock.code}
                    className={`stock-item ${selectedStockCode === stock.code ? 'selected' : ''}`}
                    onClick={() => handleStockClick(stock.code)}
                  >
                    <div className="stock-rank">{stock.rank}</div>
                    
                    <div className="stock-logo">
                      <div 
                        className="logo-placeholder"
                        style={{ 
                          background: stockColor.bg,
                          color: stockColor.text
                        }}
                      >
                        {logoText}
                      </div>
                    </div>

                    <div className="stock-info">
                      <div className="stock-name-row">
                        <span className="stock-name">{displayName}</span>
                        <span className={`market-badge ${stock.market.toLowerCase()}`}>
                          {stock.market}
                        </span>
                      </div>
                      <div className="stock-code">{stock.code}</div>
                    </div>

                    <div className="stock-price-info">
                      <div className="stock-price">{formatPrice(stock.price)}원</div>
                      <div className={`stock-change ${stock.changeRate >= 0 ? 'positive' : 'negative'}`}>
                        {formatChangeRate(stock.changeRate)}
                      </div>
                    </div>
                  </div>
                  )
                })
              )}
              {/* 무한 스크롤 sentinel */}
              {!loading && !error && topStocks.length > 0 && (
                <>
                  <div ref={sentinelRef} style={{ height: 1 }} />
                  {visibleCount < topStocks.length && visibleCount < INFINITE_SCROLL_MAX && (
                    <div className="scroll-load-hint">아래로 스크롤하면 더 보기</div>
                  )}
                  {(visibleCount >= topStocks.length || visibleCount >= INFINITE_SCROLL_MAX) && (
                    <div className="scroll-load-hint">
                      {topStocks.length <= INFINITE_SCROLL_MAX
                        ? `전체 ${topStocks.length}개 종목`
                        : `Top ${INFINITE_SCROLL_MAX} 까지 표시됩니다`}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>

        {/* 우측: 검색 섹션 */}
        <div className="stock-search-section">
          <div className="section-card">
            <div className="section-header">
              <h2 className="section-title">종목 검색</h2>
            </div>

            {/* 검색 입력창 */}
            <div className="search-container">
              <div className="search-input-wrapper">
                <svg className="search-icon" width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M9 17A8 8 0 1 0 9 1a8 8 0 0 0 0 16zM19 19l-4.35-4.35" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                <input
                  type="text"
                  className="search-input"
                  placeholder="종목명 또는 종목코드를 검색해보세요"
                  value={searchKeyword}
                  onChange={(e) => setSearchKeyword(e.target.value)}
                  onFocus={() => searchResults.length > 0 && setShowSearchResults(true)}
                />
                {searchKeyword && (
                  <button
                    className="clear-btn"
                    onClick={() => {
                      setSearchKeyword('')
                      setShowSearchResults(false)
                    }}
                    aria-label="검색어 지우기"
                  >
                    ✕
                  </button>
                )}
              </div>

              {/* 검색 결과 드롭다운 */}
              {showSearchResults && searchResults.length > 0 && (
                <div className="search-results-dropdown">
                  {searchResults.map(stock => {
                    const stockColor = getStockColor(stock.code)
                    const displayName = stock.name
                    const logoText = displayName.length <= 3 ? displayName : displayName.substring(0, 3)
                    return (
                    <div
                      key={stock.code}
                      className="search-result-item"
                      onClick={() => handleSearchResultClick(stock)}
                    >
                      <div 
                        className="result-logo"
                        style={{ 
                          background: stockColor.bg,
                          color: stockColor.text
                        }}
                      >
                        {logoText}
                      </div>
                      <div className="result-info">
                        <div className="result-name-row">
                          <span className="result-name">{displayName}</span>
                          <span className={`market-badge ${stock.market.toLowerCase()}`}>
                            {stock.market}
                          </span>
                        </div>
                        <div className="result-code">{stock.code}</div>
                      </div>
                      <div className="result-price-info">
                        <div className="result-price">{formatPrice(stock.price)}원</div>
                        <div className={`result-change ${stock.changeRate >= 0 ? 'positive' : 'negative'}`}>
                          {formatChangeRate(stock.changeRate)}
                        </div>
                      </div>
                    </div>
                    )
                  })}
                </div>
              )}

              {/* 검색 결과 없음 */}
              {showSearchResults && searchResults.length === 0 && searchKeyword && (
                <div className="search-results-dropdown">
                  <div className="no-results">
                    <div className="no-results-icon">🔍</div>
                    <p>검색 결과가 없습니다.</p>
                    <span>다른 검색어를 입력해보세요.</span>
                  </div>
                </div>
              )}
            </div>

            {/* 초기 안내 영역 */}
            {!searchKeyword && (
              <div className="search-guide">
                <div className="guide-icon">
                  <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
                    <circle cx="32" cy="32" r="30" fill="#E8F5EE"/>
                    <path d="M28 42a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM44 44l-5.4-5.4" stroke="#2E7D5B" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </div>
                <p className="guide-description">
                  종목명 또는 종목코드를 입력하면<br />
                  실시간 검색 결과를 확인할 수 있습니다.
                </p>
                
                {/* 인기 검색어 */}
                <div className="popular-searches">
                  <h4 className="popular-title">인기 검색어</h4>
                  <div className="popular-tags">
                    {['삼성전자', 'SK하이닉스', 'NAVER', '카카오', '현대차'].map((keyword, index) => (
                      <button
                        key={index}
                        className="popular-tag"
                        onClick={() => setSearchKeyword(keyword)}
                      >
                        {keyword}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default StocksPage
