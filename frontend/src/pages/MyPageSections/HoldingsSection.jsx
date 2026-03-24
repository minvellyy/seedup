import React, { useState, useEffect } from 'react'
import { useAuth } from '../../contexts/AuthContext'

const HoldingsSection = () => {
  const { user } = useAuth()
  
  const [formData, setFormData] = useState({
    broker: '',
    account: '',
    stockName: '',
    stockCode: '',
    shares: '',
    purchasePrice: '',
    purchaseDate: '',
  })

  const [holdings, setHoldings] = useState([])
  const [summary, setSummary] = useState({
    totalValue: 0,
    dailyChangeValue: 0,
    dailyChangeRate: 0,
  })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [imageUploading, setImageUploading] = useState(false)
  const [showManualForm, setShowManualForm] = useState(false)

  // 보유 주식 요약 데이터 조회
  useEffect(() => {
    if (!user?.userId) {
      setLoading(false)
      setHoldings([])
      setSummary({
        totalValue: 0,
        dailyChangeValue: 0,
        dailyChangeRate: 0,
      })
      return
    }
    
    const fetchHoldingsSummary = async () => {
      try {
        setLoading(true)
        setError(null)
        
        const response = await fetch(`http://localhost:8000/api/holdings/${user.userId}/summary`)
        if (!response.ok) {
          throw new Error('보유 주식 조회에 실패했습니다')
        }
        
        const data = await response.json()
        
        const formattedHoldings = data.holdings.map(h => ({
          id: h.id,
          name: h.stock_name,
          code: h.stock_code,
          value: h.current_value || (h.purchase_price * h.shares),
          returnRate: h.return_rate || 0,
          shares: h.shares,
        }))
        
        setHoldings(formattedHoldings)
        setSummary({
          totalValue: data.total_current_value,
          dailyChangeValue: data.total_return_amount,
          dailyChangeRate: data.total_return_rate,
        })
        
      } catch (err) {
        console.error('보유 주식 조회 실패:', err)
        setError(err.message)
        setHoldings([])
        setSummary({
          totalValue: 0,
          dailyChangeValue: 0,
          dailyChangeRate: 0,
        })
      } finally {
        setLoading(false)
      }
    }
    
    fetchHoldingsSummary()
  }, [user])

  const handleChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({
      ...prev,
      [name]: value
    }))
  }

  const handleImageUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return

    if (!file.type.startsWith('image/')) {
      alert('이미지 파일만 업로드 가능합니다')
      return
    }

    try {
      setImageUploading(true)

      const formDataObj = new FormData()
      formDataObj.append('file', file)

      const response = await fetch('http://localhost:8000/api/holdings/parse-mts-image', {
        method: 'POST',
        body: formDataObj,
      })

      if (!response.ok) {
        throw new Error('이미지 분석에 실패했습니다')
      }

      const result = await response.json()
      
      if (!result.success) {
        throw new Error(result.error || '이미지에서 정보를 추출할 수 없습니다')
      }

      if (result.holdings && result.holdings.length > 0) {
        const holding = result.holdings[0]
        setFormData(prev => ({
          ...prev,
          stockName: holding.stock_name || '',
          stockCode: holding.stock_code || '',
          shares: holding.shares?.toString() || '',
          purchasePrice: holding.purchase_price?.toString() || '',
        }))
        
        alert(`${result.holdings.length}개의 종목 정보를 찾았습니다. 첫 번째 종목이 입력되었습니다.`)
      } else {
        alert('이미지에서 주식 정보를 찾을 수 없습니다')
      }

    } catch (err) {
      console.error('이미지 업로드 실패:', err)
      alert(err.message || '이미지 분석에 실패했습니다')
    } finally {
      setImageUploading(false)
      e.target.value = ''
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    
    if (!user?.userId) {
      alert('로그인이 필요합니다')
      return
    }
    
    try {
      const response = await fetch('http://localhost:8000/api/holdings', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: user.userId,
          stock_code: formData.stockCode,
          stock_name: formData.stockName,
          broker: formData.broker,
          account_number: formData.account,
          shares: parseInt(formData.shares),
          purchase_price: parseFloat(formData.purchasePrice),
          purchase_date: formData.purchaseDate || null,
        }),
      })
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: '알 수 없는 오류' }))
        throw new Error(errorData.detail || `주식 등록에 실패했습니다 (${response.status})`)
      }
      
      alert('주식 내역이 등록되었습니다')
      
      setFormData({
        broker: '',
        account: '',
        stockName: '',
        stockCode: '',
        shares: '',
        purchasePrice: '',
        purchaseDate: '',
      })
      
      const summaryResponse = await fetch(`http://localhost:8000/api/holdings/${user.userId}/summary`)
      if (summaryResponse.ok) {
        const data = await summaryResponse.json()
        
        const formattedHoldings = data.holdings.map(h => ({
          id: h.id,
          name: h.stock_name,
          code: h.stock_code,
          value: h.current_value || (h.purchase_price * h.shares),
          returnRate: h.return_rate || 0,
          shares: h.shares,
        }))
        
        setHoldings(formattedHoldings)
        setSummary({
          totalValue: data.total_current_value,
          dailyChangeValue: data.total_return_amount,
          dailyChangeRate: data.total_return_rate,
        })
      }
      
    } catch (err) {
      console.error('주식 등록 실패:', err)
      alert(err.message || '주식 등록에 실패했습니다')
    }
  }

  const handleDelete = async (holdingId, stockName) => {
    if (!window.confirm(`${stockName} 종목을 삭제하시겠습니까?`)) {
      return
    }
    
    try {
      const response = await fetch(`http://localhost:8000/api/holdings/${holdingId}`, {
        method: 'DELETE',
      })
      
      if (!response.ok) {
        throw new Error('삭제에 실패했습니다')
      }
      
      alert(`${stockName} 종목이 삭제되었습니다`)
      
      const summaryResponse = await fetch(`http://localhost:8000/api/holdings/${user.userId}/summary`)
      if (summaryResponse.ok) {
        const data = await summaryResponse.json()
        
        const formattedHoldings = data.holdings.map(h => ({
          id: h.id,
          name: h.stock_name,
          code: h.stock_code,
          value: h.current_value || (h.purchase_price * h.shares),
          returnRate: h.return_rate || 0,
          shares: h.shares,
        }))
        
        setHoldings(formattedHoldings)
        setSummary({
          totalValue: data.total_current_value,
          dailyChangeValue: data.total_return_amount,
          dailyChangeRate: data.total_return_rate,
        })
      }
      
    } catch (err) {
      console.error('종목 삭제 실패:', err)
      alert(err.message || '종목 삭제에 실패했습니다')
    }
  }

  const formatNumber = (num) => {
    return new Intl.NumberFormat('ko-KR').format(num)
  }

  const formatPercent = (num) => {
    const sign = num >= 0 ? '+' : ''
    return `${sign}${num.toFixed(2)}%`
  }

  return (
    <div className="section-content">
      <h2 className="section-title">보유 주식 내역 등록</h2>
      
      {error && !loading && (
        <div style={{
          background: '#fef2f2',
          border: '1px solid #fecaca',
          borderRadius: '8px',
          padding: '1rem',
          marginBottom: '1rem',
          color: '#dc2626'
        }}>
          ⚠️ {error}
        </div>
      )}
      
      <div className="holdings-layout">
        <div className="holdings-summary">
          {loading ? (
            <div style={{ textAlign: 'center', padding: '2rem' }}>
              <p>보유 주식 정보를 불러오는 중...</p>
            </div>
          ) : (
            <>
              <div className="summary-card total">
                <h3>총 보유 금액</h3>
                <p className="amount">{formatNumber(summary.totalValue)}원</p>
              </div>

              <div className="summary-card change">
                <h3>전일 대비</h3>
                <div className={`change-info ${summary.dailyChangeRate >= 0 ? 'positive' : 'negative'}`}>
                  <p className="amount">{formatNumber(summary.dailyChangeValue)}원</p>
                  <p className="rate">{formatPercent(summary.dailyChangeRate)}</p>
                </div>
              </div>

              <div className="holdings-list-card">
                <h3>보유 종목</h3>
                <div className="holdings-list">
                  {holdings.length === 0 ? (
                    <div className="empty-state">
                      <p>보유 종목이 없습니다</p>
                      <p className="empty-hint">우측 폼에서 종목을 등록해주세요</p>
                    </div>
                  ) : (
                    holdings.map(stock => (
                      <div key={stock.id} className="holding-item">
                        <div className="holding-info">
                          <h4>{stock.name}</h4>
                          <p className="stock-code">{stock.code}</p>
                        </div>
                        <div className="holding-value">
                          <p className="amount">{formatNumber(stock.value)}원</p>
                          <p className={`return ${stock.returnRate >= 0 ? 'positive' : 'negative'}`}>
                            {formatPercent(stock.returnRate)}
                          </p>
                        </div>
                        <button 
                          className="btn-delete-holding"
                          onClick={() => handleDelete(stock.id, stock.name)}
                          title="삭제"
                        >
                          ✕
                        </button>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </>
          )}
        </div>

        <div className="holdings-form-wrapper">
          <div className="holdings-form-card">
            <h3>보유 내역 등록</h3>
            
            <div className="input-method-toggle">
              <button
                type="button"
                className={`toggle-btn ${!showManualForm ? 'active' : ''}`}
                onClick={() => setShowManualForm(false)}
              >
                📸 보유 주식 내역 캡처
              </button>
              <button
                type="button"
                className={`toggle-btn ${showManualForm ? 'active' : ''}`}
                onClick={() => setShowManualForm(true)}
              >
                ✍️ 직접 입력
              </button>
            </div>

            {!showManualForm && (
              <div className="image-upload-section">
                <div className="image-upload-box">
                  <input
                    type="file"
                    id="mts-image"
                    accept="image/*"
                    onChange={handleImageUpload}
                    disabled={imageUploading}
                    style={{ display: 'none' }}
                  />
                  <label htmlFor="mts-image" className="image-upload-label">
                    {imageUploading ? (
                      <div className="uploading">
                        <div className="spinner"></div>
                        <p>이미지 분석 중...</p>
                      </div>
                    ) : (
                      <>
                        <div className="upload-icon">📷</div>
                        <p className="upload-title">보유 주식 내역을 캡처하여 올려주세요</p>
                        <p className="upload-hint">보유 종목 정보가 자동으로 입력됩니다</p>
                      </>
                    )}
                  </label>
                </div>
                <div className="image-guide">
                  <p className="guide-title">💡 촬영 가이드</p>
                  <ul>
                    <li>종목명, 종목코드가 선명하게 보이도록 촬영해주세요</li>
                    <li>보유 수량과 매입가 정보를 포함해주세요</li>
                    <li>여러 종목이 있을 경우 첫 번째 종목이 입력됩니다</li>
                  </ul>
                </div>
              </div>
            )}

            <form onSubmit={handleSubmit} className="holdings-form">
              <div className="form-group">
                <label htmlFor="broker">증권사 <span className="required">*</span></label>
                <select
                  id="broker"
                  name="broker"
                  value={formData.broker}
                  onChange={handleChange}
                  className="form-input"
                  required
                >
                  <option value="">증권사를 선택하세요</option>
                  <option value="kis">한국투자증권</option>
                  <option value="samsung">삼성증권</option>
                  <option value="mirae">미래에셋증권</option>
                  <option value="kb">KB증권</option>
                  <option value="nhqv">NH투자증권</option>
                  <option value="kiwoom">키움증권</option>
                  <option value="hana">하나증권</option>
                </select>
              </div>

              <div className="form-group">
                <label htmlFor="account">계좌번호 <span className="required">*</span></label>
                <input
                  type="text"
                  id="account"
                  name="account"
                  value={formData.account}
                  onChange={handleChange}
                  className="form-input"
                  placeholder="계좌번호를 입력하세요"
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="stockName">종목명 <span className="required">*</span></label>
                <input
                  type="text"
                  id="stockName"
                  name="stockName"
                  value={formData.stockName}
                  onChange={handleChange}
                  className="form-input"
                  placeholder="예: 삼성전자"
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="stockCode">종목코드</label>
                <input
                  type="text"
                  id="stockCode"
                  name="stockCode"
                  value={formData.stockCode}
                  onChange={handleChange}
                  className="form-input"
                  placeholder="예: 005930"
                />
              </div>

              <div className="form-group">
                <label htmlFor="shares">수량 <span className="required">*</span></label>
                <input
                  type="number"
                  id="shares"
                  name="shares"
                  value={formData.shares}
                  onChange={handleChange}
                  className="form-input"
                  placeholder="보유 수량"
                  min="1"
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="purchasePrice">매수가 (평균단가) <span className="required">*</span></label>
                <input
                  type="number"
                  id="purchasePrice"
                  name="purchasePrice"
                  value={formData.purchasePrice}
                  onChange={handleChange}
                  className="form-input"
                  placeholder="원"
                  min="0"
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="purchaseDate">매입일</label>
                <input
                  type="date"
                  id="purchaseDate"
                  name="purchaseDate"
                  value={formData.purchaseDate}
                  onChange={handleChange}
                  className="form-input"
                />
              </div>

              <button type="submit" className="btn btn-primary btn-full">
                등록하기
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}

export default HoldingsSection
