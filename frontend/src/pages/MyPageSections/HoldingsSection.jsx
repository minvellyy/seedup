import React, { useState } from 'react'

// Mock data
const mockHoldingsSummary = {
  totalValue: 32134087,
  dailyChangeValue: -656190,
  dailyChangeRate: -2.03,
}

const mockHoldingStocks = [
  { id: 1, name: '티솔라', code: '123456', value: 13899090, returnRate: -20.79, shares: 100 },
  { id: 2, name: '퀀타로', code: '234567', value: 3460990, returnRate: -16.67, shares: 50 },
  { id: 3, name: '엠테디아', code: '345678', value: 2010000, returnRate: 0.0, shares: 30 },
  { id: 4, name: '삼성전자', code: '005930', value: 5764007, returnRate: 5.23, shares: 80 },
  { id: 5, name: 'SK하이닉스', code: '000660', value: 7000000, returnRate: 3.45, shares: 60 },
]

const HoldingsSection = () => {
  const [formData, setFormData] = useState({
    broker: '',
    account: '',
    stockName: '',
    stockCode: '',
    shares: '',
    purchasePrice: '',
    purchaseDate: '',
  })

  const [holdings, setHoldings] = useState(mockHoldingStocks)
  const [summary, setSummary] = useState(mockHoldingsSummary)

  const handleChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({
      ...prev,
      [name]: value
    }))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    alert('주식 내역이 등록되었습니다')
    console.log('등록된 주식 정보:', formData)
    // 여기서 실제로는 API 호출하여 등록
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
      
      <div className="holdings-layout">
        {/* 좌측: 보유 주식 요약 */}
        <div className="holdings-summary">
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
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* 우측: 등록 폼 */}
        <div className="holdings-form-wrapper">
          <div className="holdings-form-card">
            <h3>보유 내역 등록</h3>
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
                <label htmlFor="purchaseDate">매입일 <span className="required">*</span></label>
                <input
                  type="date"
                  id="purchaseDate"
                  name="purchaseDate"
                  value={formData.purchaseDate}
                  onChange={handleChange}
                  className="form-input"
                  required
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
