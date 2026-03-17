import React, { useState } from "react";
import { useNavigate } from 'react-router-dom';
import { useAuth } from "../contexts/AuthContext";
import "./SurveyPage.css";
import "../App.css";

const questions = [
  {
    key: "q1",
    text: "1. 향후 수입을 어떻게 예상하시나요?",
    type: "radio",
    options: [
      "현재 일정한 수입이 발생하고 있으며, 향후 전체 수준을 유지하거나 증가할 것 같아요.",
      "현재 일정한 수입이 발생하고 있으나, 향후 감소하거나 불안정할 것 같아요.",
      "현재 일정한 수입이 없으며, 현금이 주 수입원이에요.",
    ],
    score: [5, 3, 1],
  },
  {
    key: "q2",
    text: "2. 기존 보유하고 계신 총자산 대비 금융자산의 비중은 어느 정도인가요?",
    type: "radio",
    options: ["5% 이하", "10% 이하", "20% 이하", "30% 이하", "30% 초과"],
    score: [1, 2, 3, 4, 5],
  },
  {
    key: "q3",
    text: "3. 투자한 경험이 있는 항목을 모두 선택해주세요. (중복 가능)",
    type: "nested-checkbox",
    options: [
      { text: "금융투자상품에 투자해 본 경험이 없음", subOptions: [] },
      {
        text: "주식신용거래, 선물/옵션, ELW, 원금비보장형 ELS/DLS/ELF",
        subOptions: ["1년 미만", "1년 이상 3년 미만", "3년 이상"],
      },
      {
        text: "주식, 주식형펀드, 해외펀드, 원금보장형 ELS/DLS/ELF, 투자자문/일임(Wrap), 외화증권",
        subOptions: ["1년 미만", "1년 이상 3년 미만", "3년 이상"],
      },
      {
        text: "채권/혼합형 펀드, 신탁, 채권",
        subOptions: ["1년 미만", "1년 이상 3년 미만", "3년 이상"],
      },
    ],
    // 중복 선택 시 최댓값만 사용 (합산X)
    // 옵션점수 + 기간점수: ①0점, ②6점, ③3점, ④1점 + 기간(①1점, ②3점, ③5점)
    score: [
      [0],        // 옵션①: 경험없음 (0점)
      [7, 9, 11], // 옵션②: 6점 + 기간(1점, 3점, 5점) = 7, 9, 11점
      [4, 6, 8],  // 옵션③: 3점 + 기간(1점, 3점, 5점) = 4, 6, 8점
      [2, 4, 6],  // 옵션④: 1점 + 기간(1점, 3점, 5점) = 2, 4, 6점
    ],
  },
  {
    key: "q4",
    text: "4. 어떤 목적으로 투자하시나요?",
    type: "radio",
    options: [
      "투자 수익보다 원금 보존이 더 중요해요.",
      "원금 보존 가능성을 조금 포기하더라도 투자 수익을 낼 수 있으면 좋겠어요.",
      "원금 손실 위험이 있어도 높은 투자 수익을 원해요.",
    ],
    score: [1, 3, 5],
  },
  {
    key: "q5",
    text: "5. 고객님께서 감내하실 수 있는 투자수익 및 위험수준은 어느 정도인가요?",
    type: "radio",
    options: [
      "무슨 일이 있어도 투자원금은 보전해야 해요.",
      "10% 정도 변동이 있어도 비교적 편안하게 나아갈 수 있어요.",
      "20% 정도는 감당하지 않고 추가 매도도 가능해요.",
      "30% 정도 변동도 버틸 수 있고 그 이상의 변동도 가능해요.",
    ],
    score: [1, 3, 4, 5],
  },
  {
    key: "q6",
    text: "6. 고객님의 금융지식 수준(이해도)은 어느 정도라고 생각하시나요?",
    type: "radio",
    options: [
      "금융투자상품에 투자해 본 적이 없어요.",
      "주식, 채권, 펀드 같은 일반적인 상품 정도는 설명만 들으면 이해할 수 있어요.",
      "주식, 채권, 펀드 같은 일반적인 상품은 알고 있으며, 투자 경험도 있어요.",
      "파생상품을 포함한 대부분의 금융투자상품에 대해 충분히 잘 알고 있어요.",
    ],
    score: [1, 2, 3, 4],
  },
  {
    key: "q7",
    text:
      "7. 고령 투자자, 주부, 은퇴자 등 금융투자상품에 대한 이해가 부족하거나 투자경험이 없는 투자자의 경우, <금융소비자 보호 및 모범규준>에 따른 금융회사의 설명을 듣고 투자 상품의 위험을 다른 투자 상품과 비교하여 충분히 이해할 수 있습니다.",
    type: "radio",
    options: ["금융투자상품에 대한 이해가 부족하거나 투자 경험이 없음", "해당사항 없음"],
    score: [1, 5],
  },
  {
    key: "q8",
    text: "8. 고객님의 나이는 어떻게 되시나요?",
    type: "radio",
    options: ["20세 미만", "20~35세 미만", "35~50세 미만", "50~60세 미만", "60세 이상"],
    score: [1, 3, 5, 2, 1],
  },
  {
    key: "q9",
    text: "9. 현재 투자자산에 대한 투자예정기간은 어떻게 되시나요?",
    type: "radio",
    options: ["1년 미만", "1~2년 미만", "2~3년 미만", "3~5년 미만", "5년 이상"],
    score: [1, 2, 3, 4, 5],
  },
  {
    key: "q10",
    text: "10. 고객님의 연 소득은 어느 정도 되시나요?",
    type: "radio",
    options: ["2천만원 이하", "2천만원~5천만원 미만", "5천만원~7천만원 미만", "7천만원~1억원 미만", "1억원 이상"],
    score: [1, 2, 3, 4, 5],
  },
];

function InvestTypeSurveyPage({ onSubmit }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  // radio: number(0-based index)
  // nested-checkbox: { [mainIdx:number]: subIdxOrNull }
  const [answers, setAnswers] = useState({});
  const [error, setError] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [result, setResult] = useState(null);

  const handleRadioChange = (qKey, idx) => {
    setAnswers((prev) => ({ ...prev, [qKey]: idx }));
  };

  const toggleNestedMain = (qKey, mainIdx) => {
    setAnswers((prev) => {
      const current = prev[qKey] || {};
      const next = { ...current };
      if (next[mainIdx] !== undefined) {
        delete next[mainIdx];
      } else {
        next[mainIdx] = null; // 선택했지만 sub 아직 없음
      }
      return { ...prev, [qKey]: next };
    });
  };

  const setNestedSub = (qKey, mainIdx, subIdx) => {
    setAnswers((prev) => {
      const current = prev[qKey] || {};
      return { ...prev, [qKey]: { ...current, [mainIdx]: subIdx } };
    });
  };

  const validateAll = () => {
    for (const q of questions) {
      const a = answers[q.key];

      if (q.type === "radio") {
        if (a === undefined || a === null) return false;
      }

      if (q.type === "nested-checkbox") {
        if (!a || Object.keys(a).length === 0) return false;

        // subOptions가 있는 메인 옵션을 체크했다면 sub도 선택되어야 함
        for (const k of Object.keys(a)) {
          const mainIdx = Number(k);
          const needsSub = (q.options?.[mainIdx]?.subOptions?.length || 0) > 0;
          if (needsSub && (a[mainIdx] === null || a[mainIdx] === undefined)) {
            return false;
          }
        }
      }
    }
    return true;
  };

  const calculateScore = () => {
    let total = 0;

    for (const q of questions) {
      const a = answers[q.key];

      if (q.type === "radio") {
        // a는 0-based index
        total += q.score[a] ?? 0;
      }

      if (q.type === "nested-checkbox") {
        // a는 { [mainIdx]: subIdxOrNull }
        // 3번 문항: 중복 선택 시 최댓값만 사용 (합산X)
        const selectedMainIdxs = Object.keys(a || {}).map((x) => Number(x));
        let maxScore = 0;
        
        for (const mainIdx of selectedMainIdxs) {
          let currentScore = 0;
          
          // score가 2차원 배열인 경우 (q3)
          if (Array.isArray(q.score?.[mainIdx])) {
            const subIdx = a[mainIdx];
            // subOptions가 없는 경우 (옵션0: 경험없음)
            if (subIdx === null || subIdx === undefined) {
              currentScore = q.score[mainIdx][0] ?? 0;
            } else {
              // subOptions가 있는 경우, subIdx를 사용
              currentScore = q.score[mainIdx][subIdx] ?? 0;
            }
          } else {
            // 1차원 배열인 경우 (기존 방식)
            currentScore = q.score?.[mainIdx] ?? 0;
          }
          
          maxScore = Math.max(maxScore, currentScore);
        }
        
        total += maxScore;
      }
    }

    return total;
  };

  const getInvestorType = (score) => {
    if (score >= 30) return '공격투자형';
    if (score >= 25) return '적극투자형';
    if (score >= 20) return '위험중립형';
    if (score >= 15) return '안전추구형';
    return '안정형';
  };

  const handleSubmit = async () => {
    if (!validateAll()) {
      setError("모든 문항에 응답해 주세요. (체크 문항의 하위 기간도 선택 필요)");
      return;
    }
    setError("");

    const totalScore = calculateScore();
    const investorType = getInvestorType(totalScore);
    setResult(investorType);

    // 백엔드에 투자성향 저장
    if (user && user.userId) {
      try {
        const response = await fetch(`/api/users/${user.userId}/investment-type`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            user_id: user.userId,
            investment_type: investorType,
          }),
        });

        const data = await response.json();
        if (data.success) {
          console.log('투자성향이 저장되었습니다:', investorType);
        } else {
          console.error('투자성향 저장 실패:', data.message);
        }
      } catch (error) {
        console.error('투자성향 저장 중 오류:', error);
      }
    }

    setShowModal(true);

    // 필요하면 상위로 제출
    if (typeof onSubmit === "function") {
      onSubmit({ userId: user?.userId, investorType, answers });
    }
  };

  return (
    <main className="survey-page">
      <div className="survey-container">
        <div className="survey-header">
          <h1>투자성향 설문조사</h1>
          <p className="survey-subtitle">
            입력하신 정보는 개인 맞춤 분석에 활용되며, 구체적일수록 추천의 정확도가 높아집니다.
          </p>
        </div>

        <div className="survey-form">
          {questions.map((q) => (
            <div key={q.key} className="survey-section">
              <label className="required">{q.text}</label>

              <div className="question-options">
                {q.type === "nested-checkbox" ? (
                  q.options.map((opt, idx) => {
                    const selected = answers[q.key]?.[idx] !== undefined;
                    const subSelected = answers[q.key]?.[idx];

                    return (
                      <div key={idx} className="nested-option">
                        <label>
                          <input
                            type="checkbox"
                            name={q.key}
                            checked={selected}
                            onChange={() => toggleNestedMain(q.key, idx)}
                          />
                          {opt.text}
                        </label>

                        {selected && opt.subOptions.length > 0 && (
                          <div className="sub-options">
                            {opt.subOptions.map((subOpt, subIdx) => (
                              <label key={subIdx} className="sub-option-label">
                                <input
                                  type="radio"
                                  name={`${q.key}-sub-${idx}`}
                                  checked={subSelected === subIdx}
                                  onChange={() => setNestedSub(q.key, idx, subIdx)}
                                />
                                {subOpt}
                              </label>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })
                ) : (
                  q.options.map((opt, idx) => {
                    const checked = answers[q.key] === idx;
                    return (
                      <label key={`${q.key}-${idx}`}>
                        <input
                          type="radio"
                          name={q.key}
                          checked={checked}
                          onChange={() => handleRadioChange(q.key, idx)}
                        />
                        {opt}
                      </label>
                    );
                  })
                )}
              </div>
            </div>
          ))}
        </div>

        {error && <div className="error-message">{error}</div>}
        <button className="submit-button" onClick={handleSubmit}>
          제출
        </button>

        {showModal && (
          <div className="modal-overlay">
            <div className="modal-content">
              <div className="modal-icon">🎉</div>
              <h1>투자자 성향</h1>
              <h2 style={{ fontSize: '2rem', fontWeight: 'bold', color: '#4CAF50' }}>{result}</h2>
              <p>입력하신 정보로 맞춤형 투자 설계를 분석 중입니다.</p>
              <div className="modal-buttons">
                <button 
                  className="modal-button primary"
                  onClick={() => {
                    setShowModal(false);
                    navigate('/recommendations');
                  }}
                >
                  나만의 포트폴리오 전략 확인하러 가기
                </button>
                <button 
                  className="modal-button secondary"
                  onClick={() => setShowModal(false)}
                >
                  나중에 보기
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

export default InvestTypeSurveyPage;