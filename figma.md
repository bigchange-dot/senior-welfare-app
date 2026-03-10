# 우리동네 복지 알림 — Claude Code 인수인계 문서

## 프로젝트 개요
60~70대 어르신을 위한 모바일 복지 알림 앱 (React + Tailwind CSS v4 + Vite).  
Figma Make 환경에서 개발 완료된 코드를 Claude Code로 이관하여 계속 개발합니다.

---

## 기술 스택
- **프레임워크**: React 18 + TypeScript
- **스타일**: Tailwind CSS v4 (인라인 style prop 위주, tailwind.config.js 없음)
- **번들러**: Vite 6
- **패키지 매니저**: pnpm
- **아이콘**: lucide-react
- **폰트**: Roboto (Google Fonts, `/src/styles/fonts.css`에서 import)

---

## 접근성 가이드라인 (시니어 사용자 필수 준수)
| 항목 | 기준 |
|------|------|
| 본문 폰트 크기 | **18px 이상** |
| 제목 폰트 크기 | **24px 이상** |
| 색상 대비 | 흰 배경 + 검정 텍스트 (WCAG AA 이상) |
| 터치 영역 | **최소 56px × 56px** |
| 하단 네비게이션 | **최대 3개 탭**, 아이콘 + 텍스트 병기 |
| UI 원칙 | 직관적·단순, 복잡한 트렌드 지양 |

---

## 파일 구조
```
src/
├── app/
│   ├── App.tsx                        # 루트 컴포넌트 (탭 라우팅 + 하단 네비게이션)
│   └── components/
│       ├── HomeScreen.tsx             # 홈 — 복지 소식 피드 (필터 + 카드 목록)
│       ├── DetailModal.tsx            # 카드 상세 모달 (전화·공유 버튼)
│       ├── RegionScreen.tsx           # 내 동네 — 알림 받을 구 선택
│       └── SettingsScreen.tsx         # 설정 — 알림·화면·기타 토글/링크
├── styles/
│   ├── fonts.css                      # @import Roboto
│   ├── index.css                      # 전역 CSS
│   ├── tailwind.css                   # Tailwind 진입점
│   └── theme.css                      # CSS 변수 (건드리지 말 것)
```

---

## 디자인 토큰 (인라인 style 에서 공통 사용)
```
Primary Blue   : #0056B3   (버튼, 활성 탭, 강조)
Orange Accent  : #E65100   (긴급 버튼, 배지, 저장)
Green          : #2E7D32   (복지로 소스 색상)
Background     : #F8F9FA
Card Border    : #E0E0E0
Body Text      : #111111 / #222222
Sub Text       : #555555 / #666666
Font Family    : "Roboto, sans-serif"
```

---

## 완료된 작업 내역

### App.tsx
- 탭: `home | region | settings` 3개
- 하단 네비게이션 높이 80px, 아이콘(30px) + 텍스트(14px)
- 활성 탭 상단 파란 pill 인디케이터
- iPhone 스타일 상태바 + 홈 인디케이터 장식
- 폰 프레임: `width: min(100%, 430px)`, `height: min(100%, 932px)`

### HomeScreen.tsx
- 필터 칩 순서: `["전체", "성동구청", "강북구청", "복지로"]`
- 카드 내부 여백: `px-6`, `pt-6`
- 카드 제목: 24px / 800 weight
- 카드 요약: 19px
- `wordBreak: "keep-all"` 적용
- 하단 "자세히 보기" 버튼: 높이 64px, 폰트 21px
- **핵심 수정**: 카드(`article`)에 `flexShrink: 0` 추가 → 텍스트 잘림 현상 방지

### DetailModal.tsx
- 전체화면 모달 (absolute inset-0)
- 신청기간·장소 정보 카드 (파란 배경 박스)
- 본문 whitespace: pre-line
- 전화하기(60px) + 공유하기(56px) 버튼

### RegionScreen.tsx
- 구 목록 체크박스 (72px 터치 영역)
- 전체보기 / 개별 구 토글 로직
- 저장 완료 피드백 (2초 후 복귀)

### SettingsScreen.tsx
- ToggleRow (푸시알림, 알림음, 글자크게, 다크모드)
- LinkRow (고객센터, 앱정보)
- 복지관 바로 전화하기 버튼 (68px, E65100)

---

## 뉴스 데이터 구조 (HomeScreen.tsx)
```ts
interface NewsCard {
  id: number;
  source: "성동구청" | "강북구청" | "복지로";
  sourceColor: string;   // 소스별 HEX
  date: string;          // "오늘" | "2/25" 등
  title: string;
  summary: string;
  isNew: boolean;
}
```
현재 목 데이터 5건 (id: 1~5). 상세 콘텐츠는 `DetailModal.tsx`의 `detailContent` Record에서 id로 매핑.

---

## 알려진 이슈 및 개선 예정
- [ ] 실제 API 연동 (현재 목 데이터)
- [ ] RegionScreen 선택 구가 HomeScreen 필터에 반영되지 않음 (상태 전역화 필요)
- [ ] SettingsScreen 글자 크게 / 다크모드 토글이 실제 UI에 미적용 상태
- [ ] 알림(Bell 버튼) 기능 미구현

---

## 개발 시작 방법
```bash
pnpm install
pnpm build   # 또는 vite dev (dev server)
```

---

## 주의사항
- `tailwind.config.js` 생성 금지 (Tailwind v4, CSS-first 방식)
- `/src/styles/theme.css` CSS 변수 직접 수정 금지
- 폰트 import는 반드시 `/src/styles/fonts.css` 에만 추가
- 이미지가 필요할 때는 `ImageWithFallback` 컴포넌트 사용 (`/src/app/components/figma/ImageWithFallback.tsx`)
