# design-system (SeedUp)

이 폴더는 프로젝트의 공통 디자인 토큰과 재사용 가능한 UI 컴포넌트를 담고 있습니다.
팀원은 페이지 코드에서 이 디자인 시스템의 토큰과 컴포넌트만 사용해야 합니다.

## 사용 예시

1. 토큰(전역 CSS) import
```css
@import '../design-system/tokens.css';
@import '../design-system/theme.css';
```

2. 컴포넌트 사용 (React 예시)
```tsx
import Header from '../design-system/components/Header';

export default function Page(){
  return (
    <>
      <Header />
      <main>...</main>
    </>
  )
}
```

## 운영 규칙
- `src/design-system/` 변경은 반드시 `CODEOWNERS`에 지정된 리뷰어가 승인해야 합니다.
- 하드코딩된 색상/폰트 사용 금지(Stylelint로 검증)
- 디자인 변경 시 README에 변경 내역과 버전 기록을 남기세요.

## Lint & 사용법 (팀 안내)

1) 로컬에서 CSS 린트 실행

```bash
npm ci
npm run lint:css
```

2) PR 템플릿에 다음 항목을 추가하세요:
- 이 변경이 `design-system`에 영향을 주나요? (예/아니오)

3) 디자인 규칙 요약:
- 색상/간격/폰트는 반드시 `tokens.css`의 변수를 사용하세요.
- 공통 컴포넌트(`Header`, `Button`, `Card`)를 재사용하세요.

문의: 디자인/컴포넌트 변경은 `@ui-lead`에게 문의하세요.

## 배포(옵션)
원한다면 이 디렉터리를 별도의 패키지로 분리하여 `npm` 또는 `git`으로 배포하는 것을 추천합니다.
