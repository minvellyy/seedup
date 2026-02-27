import React, { useState } from 'react'
import './SurveyPage.css'
import axios from 'axios'

function formatNumberWithCommas(num) {
  if (!num) return '';
  return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

function SurveyPage() {
  // 페이지 로드 시 localStorage 확인
  React.useEffect(() => {
    const storedUserId = localStorage.getItem('user_id');
    const storedEmail = localStorage.getItem('email');
    console.log('=== SurveyPage 로드 시 localStorage 확인 ===');
    console.log('저장된 user_id:', storedUserId);
    console.log('저장된 email:', storedEmail);
    console.log('localStorage 전체:', Object.keys(localStorage).map(key => `${key}: ${localStorage.getItem(key)}`));
  }, []);

  const [answers, setAnswers] = useState({
    investmentGoal: '',
    targetDate: '',
    targetAmount: '',
    investmentMethod: '',
    lumpSum: '',
    installment: '',
    maxStocks: '',
    dividendPreference: '',
    accountType: ''
  })

  const [showModal, setShowModal] = useState(false)

  const handleInputChange = (e) => {
    const { name, value } = e.target
    setAnswers(prev => ({
      ...prev,
      [name]: value
    }))
  }

  const handleRadioChange = (e, field) => {
    setAnswers(prev => ({
      ...prev,
      [field]: e.target.value
    }))
  }

  const handleNumberInput = (e) => {
    const { name, value } = e.target;
    // 숫자만 입력 가능, 콤마 제거
    const raw = value.replace(/,/g, '');
    if (raw === '' || /^\d+$/.test(raw)) {
      setAnswers(prev => ({
        ...prev,
        [name]: raw
      }));
    }
  }  

  const isRequiredFieldsFilled = () => {
    const requiredFields = [
      answers.investmentGoal,
      answers.targetDate,
      answers.investmentMethod,
      answers.maxStocks,
      answers.dividendPreference,
      answers.accountType
    ]

    // investmentMethod에 따른 조건부 필수 필드
    if (answers.investmentMethod === 'lumpSum' && !answers.lumpSum) {
      return false
    }
    if (answers.investmentMethod === 'installment' && !answers.installment) {
      return false
    }

    return requiredFields.every(field => field)
  }

  const handleSubmit = async () => {
    if (isRequiredFieldsFilled()) {
      try {
        // 프론트엔드 필드명을 question_id로 매핑
        const fieldToQuestionMapping = {
          investmentGoal: { id: 1, type: 'TEXT' },
          targetDate: { id: 2, type: 'TEXT' },
          targetAmount: { id: 3, type: 'NUMBER' },
          investmentMethod: { id: 4, type: 'SINGLE_CHOICE' },
          lumpSum: { id: 5, type: 'NUMBER' },
          installment: { id: 6, type: 'NUMBER' },
          maxStocks: { id: 7, type: 'NUMBER' },
          dividendPreference: { id: 8, type: 'SINGLE_CHOICE' },
          accountType: { id: 9, type: 'TEXT' }
        };

        // 프론트엔드 값을 백엔드 형식으로 변환
        const valueMapping = {
          investmentMethod: {
            'lumpSum': 'LUMP_SUM',
            'installment': 'DCA'
          },
          dividendPreference: {
            'high': 'HIGH',
            'medium': 'MID',
            'low': 'LOW'
          }
        };

        // 답변 데이터를 백엔드가 기대하는 형식으로 변환
        const formattedAnswers = [];
        for (const [fieldName, value] of Object.entries(answers)) {
          if (!value) continue; // 빈 값은 건너뛰기
          
          const mapping = fieldToQuestionMapping[fieldName];
          if (!mapping) continue;

          const answer = { question_id: mapping.id };
          
          let finalValue = value;
          // 값 변환이 필요한 경우
          if (valueMapping[fieldName] && valueMapping[fieldName][value]) {
            finalValue = valueMapping[fieldName][value];
          }
          
          if (mapping.type === 'TEXT') {
            answer.value_text = finalValue;
          } else if (mapping.type === 'NUMBER') {
            // 콤마 제거 후 숫자로 변환
            const cleanedValue = finalValue.toString().replace(/,/g, '');
            answer.value_number = parseFloat(cleanedValue);
          } else if (mapping.type === 'SINGLE_CHOICE') {
            answer.value_choice = finalValue;
          }
          
          formattedAnswers.push(answer);
        }

        // localStorage에서 user_id 가져오기
        const userId = localStorage.getItem('user_id');
        console.log('localStorage의 user_id:', userId);
        console.log('localStorage 전체:', { ...localStorage });
        
        if (!userId) {
          alert('로그인이 필요합니다.');
          window.location.href = '/login';
          return;
        }

        const userIdNumber = parseInt(userId);
        console.log('변환된 user_id (숫자):', userIdNumber);
        console.log('전송할 데이터:', { user_id: userIdNumber, answers: formattedAnswers });

        const response = await axios.post('http://localhost:8000/api/survey', {
          user_id: userIdNumber,
          answers: formattedAnswers
        });

        if (response.data.success) {
          setShowModal(true);
          console.log('설문 답변 제출 성공:', response.data);
        } else {
          alert('설문 제출에 실패했습니다. 다시 시도해주세요.');
        }
      } catch (error) {
        console.error('설문 제출 중 오류:', error);
        const errorMessage = error.response?.data?.detail?.message || '설문 제출 중 오류가 발생했습니다.';
        alert(errorMessage);
      }
    }
  }

  return (
    <main className="survey-page">
      <div className="survey-container">
        <div className="survey-header">
          <h1>나에게 맞는 투자 설계하기</h1>
          <p className="survey-subtitle">
            입력하신 정보는 개인 맞춤 분석에 활용되며, 구체적일수록 추천의 정확도가 높아집니다.
          </p>
        </div>

        <div className="survey-form">
          {/* 1. 투자 목적 */}
          <div className="survey-section">
            <label className="required">1. 투자 목적은 무엇인가요? *</label>
            <input
              type="text"
              name="investmentGoal"
              placeholder="자산증식 / 목돈 / 주택 / 결혼 / 은퇴 / 학자금"
              value={answers.investmentGoal}
              onChange={handleInputChange}
              className="form-input"
            />
          </div>

          {/* 2. 목표 시점 */}
          <div className="survey-section">
            <label className="required">2. 목표 시점은 언제인가요? *</label>
            <input
              type="text"
              name="targetDate"
              placeholder="예: 2025년 12월, 5년 후"
              value={answers.targetDate}
              onChange={handleInputChange}
              className="form-input"
            />
          </div>

          {/* 3. 목표 금액 */}
          <div className="survey-section">
            <label className="optional">3. 목표 금액은 얼마인가요?</label>
            <div className="input-group">
              <input
                type="text"
                name="targetAmount"
                placeholder="0"
                value={answers.targetAmount ? formatNumberWithCommas(answers.targetAmount) : ''}
                onChange={handleNumberInput}
                className="form-input number-input"
                inputMode="numeric"
                autoComplete="off"
              />
              <span className="input-suffix">원</span>
            </div>
          </div>

          {/* 4. 선호 투자 방식 */}
          <div className="survey-section">
            <label className="required">4. 선호하는 투자 방식은? *</label>
            <div className="radio-group">
              <div className="radio-item">
                <input
                  type="radio"
                  id="lumpSum"
                  name="investmentMethod"
                  value="lumpSum"
                  checked={answers.investmentMethod === 'lumpSum'}
                  onChange={(e) => handleRadioChange(e, 'investmentMethod')}
                />
                <label htmlFor="lumpSum">일시금</label>
              </div>
              <div className="radio-item">
                <input
                  type="radio"
                  id="installment"
                  name="investmentMethod"
                  value="installment"
                  checked={answers.investmentMethod === 'installment'}
                  onChange={(e) => handleRadioChange(e, 'investmentMethod')}
                />
                <label htmlFor="installment">적립식</label>
              </div>
            </div>

            {answers.investmentMethod === 'lumpSum' && (
              <div className="conditional-section">
                <label className="required">일시금 금액 *</label>
                <div className="input-group">
                  <input
                    type="text"
                    name="lumpSum"
                    placeholder="0"
                    value={answers.lumpSum ? formatNumberWithCommas(answers.lumpSum) : ''}
                    onChange={handleNumberInput}
                    className="form-input number-input"
                    inputMode="numeric"
                    autoComplete="off"
                  />
                  <span className="input-suffix">원</span>
                </div>
              </div>
            )}

            {answers.investmentMethod === 'installment' && (
              <div className="conditional-section">
                <label className="required">월 투자 가능 금액 *</label>
                <div className="input-group">
                  <input
                    type="text"
                    name="installment"
                    placeholder="0"
                    value={answers.installment ? formatNumberWithCommas(answers.installment) : ''}
                    onChange={handleNumberInput}
                    className="form-input number-input"
                    inputMode="numeric"
                    autoComplete="off"
                  />
                  <span className="input-suffix">원</span>
                </div>
              </div>
            )}
          </div>

          {/* 5. 최대 보유 종목 수 */}
          <div className="survey-section">
            <label className="required">5. 최대 몇 개의 종목을 보유하고 싶으신가요? *</label>
            <input
              type="text"
              name="maxStocks"
              placeholder="5개 / 10개 / 20개 이상"
              value={answers.maxStocks}
              onChange={handleInputChange}
              className="form-input"
            />
          </div>

          {/* 6. 배당 선호도 */}
          <div className="survey-section">
            <label className="required">6. 배당금 선호도는? *</label>
            <div className="radio-group">
              <div className="radio-item">
                <input
                  type="radio"
                  id="dividendHigh"
                  name="dividendPreference"
                  value="high"
                  checked={answers.dividendPreference === 'high'}
                  onChange={(e) => handleRadioChange(e, 'dividendPreference')}
                />
                <label htmlFor="dividendHigh">높음 (배당금 수익 중시)</label>
              </div>
              <div className="radio-item">
                <input
                  type="radio"
                  id="dividendMedium"
                  name="dividendPreference"
                  value="medium"
                  checked={answers.dividendPreference === 'medium'}
                  onChange={(e) => handleRadioChange(e, 'dividendPreference')}
                />
                <label htmlFor="dividendMedium">중간</label>
              </div>
              <div className="radio-item">
                <input
                  type="radio"
                  id="dividendLow"
                  name="dividendPreference"
                  value="low"
                  checked={answers.dividendPreference === 'low'}
                  onChange={(e) => handleRadioChange(e, 'dividendPreference')}
                />
                <label htmlFor="dividendLow">낮음 (성장성 중시)</label>
              </div>
            </div>
          </div>

          {/* 7. 계좌 유형 */}
          <div className="survey-section">
            <label className="required">7. 계좌 유형은? *</label>
            <input
              type="text"
              name="accountType"
              placeholder="일반 / ISA / 연금 / 없음 / 복수 가능"
              value={answers.accountType}
              onChange={handleInputChange}
              className="form-input"
            />
          </div>
        </div>

        <button 
          className={`submit-button ${isRequiredFieldsFilled() ? 'enabled' : 'disabled'}`}
          onClick={handleSubmit}
          disabled={!isRequiredFieldsFilled()}
        >
          제출하기
        </button>
      </div>

      {showModal && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div className="modal-icon">🎉</div>
            <h2>설문 제출이 완료되었습니다!</h2>
            <p>입력하신 정보로 맞춤형 투자 설계를 분석 중입니다.</p>
            <button 
              className="modal-button"
              onClick={() => setShowModal(false)}
            >
              확인
            </button>
          </div>
        </div>
      )}
    </main>
  )
}

export default SurveyPage
