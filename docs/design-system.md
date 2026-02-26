# SeedUp Design System — 스타일 가이드

이 문서는 프로젝트의 UI 템플릿(색상, 타이포그래피, 여백, 버튼/입력/카드 스타일 등)을 통일하기 위한 디자인 토큰과 컴포넌트 스타일 규칙을 담습니다.

목표: 현재 화면(약관 동의 이미지, 회원가입 등)에서 보이는 색감·글씨체·헤더 크기·박스 크기·굵기 등을 컴포넌트별로 일관되게 적용하도록 정의합니다.

---

## 1. 핵심 디자인 토큰 (CSS 변수)
프로젝트 루트 CSS에 아래 변수를 추가하세요 (예: `src/index.css` 혹은 `App.css`).

:root {
  /* Colors */
  --color-primary: #ffd84b;        /* 버튼/액센트 (이미지 노란색) */
  --color-primary-600: #ffd43a;
  --color-secondary: #f6f6f6;      /* 배경 카드 */
  --color-bg: #ffffff;             /* 페이지 배경 */
  --color-surface: #f3f7fb;        /* 약관 박스 배경(연한 블루) */
  --color-muted: #f1f1f1;          /* 안내 박스 배경(연회색) */
  --color-text: #222831;           /* 기본 텍스트(진한 회색) */
  --color-subtext: #6b7280;        /* 보조 텍스트(중간 회색) */
  --color-link: #0b7cff;           /* 링크/액션 */
  --color-success: #16a34a;        /* 성공 */
  --color-danger: #fca5a5;         /* 오류 메시지(연한 빨강) */

  /* Typography */
  --font-family-base: "Noto Sans KR", system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial;
  --font-weight-regular: 400;
  --font-weight-medium: 500;
  --font-weight-semibold: 600;
  --font-weight-bold: 700;

  /* Sizes */
  --font-size-base: 16px;
  --font-size-sm: 14px;
  --font-size-lg: 18px;
  --line-height-base: 1.6;

  /* Headings */
  --h1-size: 28px;    /* 페이지 타이틀 (예: "서비스 이용약관 동의") */
  --h2-size: 22px;    /* 섹션 타이틀 */
  --h3-size: 18px;
  --h4-size: 16px;

  /* Layout */
  --container-max-width: 1024px;
  --container-padding: 24px;

  /* Spacing scale */
  --space-xxs: 4px;
  --space-xs: 8px;
  --space-sm: 12px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;

  /* Radii & Shadows */
  --radius-sm: 6px;
  --radius-md: 12px;
  --shadow-sm: 0 1px 3px rgba(16,24,40,0.04);
  --shadow-md: 0 6px 20px rgba(16,24,40,0.08);
}

---

## 2. 타이포그래피 규칙
- 기본 폰트: `--font-family-base` (국문 컨텐츠에 `Noto Sans KR` 권장). 웹폰트가 없을 경우 시스템 폰트 사용.
- 본문: `font-size: var(--font-size-base); line-height: var(--line-height-base); color: var(--color-text);`
- 헤더:
  - `h1` - `font-size: var(--h1-size); font-weight: var(--font-weight-bold); text-align: center;` (페이지 제목)
  - `h2` - `font-size: var(--h2-size); font-weight: var(--font-weight-semibold);`
  - `h3` - `font-size: var(--h3-size); font-weight: var(--font-weight-medium);`

접근성: 타이포 간 대비는 WCAG 기준에 가깝게 유지(명확한 대비 색 사용).

---

## 3. Header (상단바) 스타일
파일 참조: `frontend/src/components/Header.css`

- 높이: `64px` (데스크톱)
- 배경: `--color-bg` (흰색)
- 로고: 좌측 정렬, `font-weight: 700`, 색상 `--color-primary` 또는 `--color-text` 둘 중 상황에 맞게 사용
- 우측 네비게이션: 텍스트 크기 `14px`, 색상 `--color-subtext`, hover 시 `--color-text`
- sticky: `position: sticky; top: 0; z-index: 50; box-shadow: var(--shadow-sm);`

---

## 4. 카드(약관 항목, 회원가입 카드) 스타일
공통 클래스: `.card` / `.signup-card` / `.terms-card`

- 배경: `--color-surface` (약관 박스는 연한 블루 느낌이면 `#eef6ff` 등으로 조정)
- 경계 반경: `var(--radius-md)`
- 패딩: `var(--space-md)` (24px)
- 그림자: `var(--shadow-sm)`
- 내부 요소 간 간격: `gap: var(--space-sm)`

약관 항목 체크박스:
- 전체 행 클릭 가능 (이미 구현되어 있음). 행에 hover 시 배경을 `rgba(11,124,255,0.05)` 정도로 변경.
- 체크 표시 색: `--color-primary`

박스 크기: 데스크톱에서 가로폭은 `min(880px, 94%)`, 중앙 정렬.

---

## 5. 폼 입력 (Input) 스타일
공통 클래스: `.form-group`, `input`, `select`, `textarea`

- 높이: `44px`
- padding: `0 var(--space-md)`
- border: `1px solid #e6e9ee`(연한 회색)
- border-radius: `var(--radius-sm)`
- font-size: `var(--font-size-base)`
- focus: `outline: none; box-shadow: 0 0 0 4px rgba(255,216,75,0.12); border-color: var(--color-primary-600)`
- error 상태: border `1px solid var(--color-danger)`; 작은 에러 텍스트 `font-size: 13px; color: var(--color-danger)`

라벨: `font-size: 14px; font-weight: 500; margin-bottom: 8px; color: var(--color-text)`

---

## 6. 버튼(Button) 스타일
공통 클래스: `.btn`, `.submit-button`, `.modal-button`

- 기본 버튼 (Primary)
  - 배경: `var(--color-primary)`
  - color: `#111` (또는 `#222`), font-weight: `600`
  - padding: `12px 20px`, border-radius: `10px`
  - height: 48px; font-size: 16px
  - hover: filter brightness(0.98) 또는 `background: var(--color-primary-600)`
  - disabled: opacity `0.5`, cursor `not-allowed`

- secondary (outline)
  - background: transparent; border: `1px solid #e6e9ee`; color: `var(--color-text)`

모달 버튼은 primary 스타일을 따름.

---

## 7. 에러 / 성공 메시지 박스
- 에러: 배경 `var(--color-danger)` (연한) 또는 `#fff5f5` 같은 색, 텍스트는 진한 빨강
- 성공: 연두계열(예: `#ecfdf5`) 배경, 텍스트는 `--color-success`
- 공통: border-radius `8px`, padding `14px`, font-size `14px`

---

## 8. 레이아웃 / 컨테이너
- 페이지 컨테이너: `max-width: var(--container-max-width); margin: 0 auto; padding: 0 var(--container-padding);`
- 섹션 마진: 섹션 상하 `var(--space-xl)`

---

## 9. 반응형(모바일) 규칙
- Breakpoints
  - `--bp-mobile: 480px`
  - `--bp-tablet: 768px`
  - `--bp-desktop: 1024px`

- 모바일에서 헤더 높이 축소: 56px
- 카드 내부 패딩 축소: `var(--space-sm)`
- 버튼 full-width 권장

---

## 10. 접근성 권장사항
- 버튼/텍스트 대비는 WCAG AA 권장 수준으로 유지
- 폼 필드에 `aria-*` 속성 추가 권장 (에러 메시지 연계용)
- 체크박스/라디오에 키보드 포커스 스타일 명확히 표시

---

## 11. 클래스 매핑(현재 코드 참고)
아래 클래스들을 디자인 가이드에 맞게 조정하세요:

- Header: `frontend/src/components/Header.css` → `.header`, `.header-container`, `.logo`, `.nav-menu`, `.nav-item`
- Terms: `frontend/src/pages/TermsPage.css` 또는 컴포넌트 `TermsCheckbox.css` → `.terms-checkbox-wrapper`, `.terms-checkbox-row`, `.terms-info-section`
- Signup: `frontend/src/pages/SignupPage.css` → `.signup-card`, `.form-group`, `.submit-button`, `.error-text`, `.success-text`

(위 파일들이 프로젝트에 이미 존재하므로, 각 파일의 CSS를 위 토큰/규칙에 맞게 교체하세요.)

---

## 12. 예시 CSS 스니펫
아래를 `src/index.css` 또는 공용 CSS에 붙여넣어 기본 토큰을 적용하세요.

```css
:root { /* (위 토큰 복사) */ }

body {
  font-family: var(--font-family-base);
  font-size: var(--font-size-base);
  color: var(--color-text);
  background: var(--color-bg);
  -webkit-font-smoothing: antialiased;
}

h1 { font-size: var(--h1-size); font-weight: var(--font-weight-bold); margin: 0 0 var(--space-md) 0 }

.header { height: 64px; display:flex; align-items:center; justify-content:space-between; padding: 0 var(--container-padding); background: var(--color-bg); box-shadow: var(--shadow-sm); position: sticky; top:0; z-index:50 }

.card { background: var(--color-surface); border-radius: var(--radius-md); padding: var(--space-md); box-shadow: var(--shadow-sm) }

input, select, textarea { height:44px; padding: 0 var(--space-md); border-radius: var(--radius-sm); border:1px solid #e6e9ee; font-size:var(--font-size-base) }

.submit-button { background: var(--color-primary); color: #111; padding: 12px 20px; border-radius: 10px; font-weight:600; border: none }

.error-text { color: var(--color-danger); font-size:13px; margin-top:6px }
.success-text { color: var(--color-success); font-size:13px; margin-top:6px }
```

---

## 13. 적용 절차(권장)
1. `src/index.css`에 토큰 변수 추가
2. 각 컴포넌트의 CSS 파일(`Header.css`, `SignupPage.css`, `TermsCheckbox.css`)을 토큰과 규칙에 맞게 리팩토링
3. 브라우저에서 데스크톱/모바일 확인, 색 대비와 폰트 사이즈 점검
4. 필요 시 디자인 픽셀 정리를 위해 시안 이미지와 맞춤 조정

---

필요하시면 제가 위 규칙을 바탕으로 `Header.css`, `SignupPage.css`, `TermsCheckbox.css` 파일들을 직접 토큰 적용해서 패치해 드리겠습니다. 어떤 파일부터 적용할까요?
