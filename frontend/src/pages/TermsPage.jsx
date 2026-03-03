import React, { useState } from 'react'
import TermsCheckbox from '../components/TermsCheckbox'
import './TermsPage.css'

const TERMS_DATA = [
  {
    id: 'service-terms',
    type: '필수',
    title: '서비스 이용약관 동의',
    content: `제 1 조 (목적)

본 약관은 Seedup(이하 "회사"라 합니다)이 제공하는 투자정보서비스(이하 "본 서비스"라 합니다)를 고객이 이용함에 있어서 필요한 사항을 정함을 목적으로 합니다.

 

제 2 조 (용어의 정의)

본 약관에서 사용하는 용어의 정의는 다음 각 호와 같습니다.

"Seedup"이란 회사가 고객에 대하여 증권매매거래 기타 서비스를 제공함에 있어서 이용하는 스마트폰 어플리케이션을 의미하며, "Seedup탭"이란 회사가 고객에 대하여 증권매매거래 기타 서비스를 제공함에 있어서 이용하는 화면으로서 고객이 Seedup웹을 통하여 진입할 수 있는 것을 의미합니다.

"WTS"란 회사가 고객에 대하여 증권매매거래 기타 서비스를 제공함에 있어서 이용하는 웹트레이딩시스템을 의미합니다.

"투자정보"란 금융투자에 관련된 지식 또는 정보로서 다음 각 목의 것을 포함하며, 본 서비스의 이용고객에게 송신, 배포, 게재할 목적으로 회사가 작성 또는 촬영, 이용권한 확보, 수집, 발췌, 편집, 배열, 구성, 결합, 번역 등을 한 것(글, 그림, 동영상 등 형태를 불문합니다)을 말합니다.

제 3 조 (서비스 제공)

① 회사는 본 약관에 따라 본 서비스의 이용이 승인된 고객(이하 "이용고객")에 대하여 본 서비스를 제공합니다.`
  },
  {
    id: 'privacy-policy',
    type: '필수',
    title: '개인정보 처리방침 동의',
    content: `개인정보 수집·이용 동의(투자정보서비스)

Seedup은 「개인정보 보호법」, 「신용정보의 이용 및 보호에 관한 법률」 등 관련 법령에 따라 고객님께 아래와 같은 '수집이용 목적, 수집이용 항목, 이용 및 보유기간, 동의 거부권 및 동의 거부 시 불이익에 관한 사항'을 안내 드리고 개인정보 수집▪이용 동의를 받고자 합니다.

수집이용 목적: 투자정보서비스 제공

수집이용 항목: 이름, 고객식별값, 휴대폰번호

이용 및 보유기간: 서비스 해지·취소 시 또는 회원탈퇴 시 까지(단, 관련 법령에 따라 보존할 필요가 있는 경우는 해당 보존기간)

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

function TermsPage() {
  const [checkedTerms, setCheckedTerms] = useState({
    'service-terms': false,
    'privacy-policy': false,
    'marketing': false,
    'personalized-service': false
  })

  const handleTermsChange = (termId) => {
    setCheckedTerms(prev => ({
      ...prev,
      [termId]: !prev[termId]
    }))
  }

  const requiredTermsChecked = 
    checkedTerms['service-terms'] && checkedTerms['privacy-policy']

  const handleSubmit = () => {
    if (requiredTermsChecked) {
      alert('약관에 동의하셨습니다.')
      console.log('제출된 약관 동의 상태:', checkedTerms)
      // 실제 제출 로직
    }
  }

  return (
    <main className="terms-page">
      <div className="terms-container">
        <div className="terms-header">
          <h1>서비스 이용약관 동의</h1>
          <p>SeedUp 서비스를 이용하시기 위해 아래 약관에 동의해주세요.</p>
        </div>

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
          <p>필수 약관에 동의하셔야 제출할 수 있습니다.</p>
        </div>

        <button
          className={`submit-button ${requiredTermsChecked ? 'enabled' : 'disabled'}`}
          onClick={handleSubmit}
          disabled={!requiredTermsChecked}
        >
          제출하기
        </button>
      </div>
    </main>
  )
}

export default TermsPage
