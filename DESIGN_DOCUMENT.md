# 노인 복지 속보 알림 앱 — 설계 및 디자인 문서

> 작성일: 2026-03-03
> 버전: 1.0.0

---

## 1. 프로젝트 개요

### 앱 목적
노인 복지 공고(성동구청·강북구청·복지로)를 자동 수집하고, AI로 요약한 뒤 FCM 푸시 알림으로 어르신께 실시간 전달하는 서비스.

### 핵심 가치
- **속보성** — 하루 2회(09:00 · 18:00 KST) 자동 크롤링
- **접근성** — 어르신 친화 UI (초대형 폰트, 넉넉한 터치 영역)
- **개인화** — 지역 선택으로 관심 구청 공고만 필터링
- **수익화** — AdMob 전면 광고 (뒤로가기 시 노출)

---

## 2. 시스템 아키텍처

### 전체 흐름

```
[Cloud Scheduler]
  09:00 / 18:00 KST
       │
       ▼
[Track A: scraping_function]
  성동구청 · 강북구청 웹 크롤링
  복지로 공공 API 호출
       │
       ▼ Gemini 2.5 Flash AI 요약
       │
       ▼
[Firestore: welfare_notices 컬렉션]
       │ onCreate 트리거
       ▼
[Track B: notification_function]
  FCM Topic 발송
  /topics/all  (전체 구독자)
  /topics/{region}  (지역 구독자)
       │
       ▼
[Flutter 앱 — Android / iOS]
  FCM 수신 → 푸시 알림 표시
  딥링크 → 인앱 WebView로 공고 열기
```

### 기술 스택

| 영역 | 기술 |
|------|------|
| **Backend** | Firebase Cloud Functions (Python 3.11, 2nd Gen) |
| **Database** | Cloud Firestore (`welfare_notices` 컬렉션) |
| **AI 요약** | Google Gemini API (`gemini-3.1-flash-lite-preview`) |
| **Push 알림** | Firebase Cloud Messaging (FCM) — Topic 방식 |
| **스케줄러** | Cloud Scheduler (asia-northeast3) |
| **Frontend** | Flutter 3 (iOS / Android) |
| **WebView** | webview_flutter ^4.10.0 |
| **광고** | Google AdMob (Interstitial) |
| **로컬 저장** | SharedPreferences (지역 설정) |
| **시간 포맷** | timeago (한국어 로케일) |

---

## 3. Backend 설계

### 3.1 Firestore 데이터 모델

**컬렉션:** `welfare_notices`

| 필드 | 타입 | 설명 |
|------|------|------|
| `title` | String | 원본 공고 제목 |
| `ai_summary` | String | Gemini AI 요약 (이모지 포함, 20자 내외) |
| `source` | String | 출처 (`복지로` / `성동구청` / `강북구청`) |
| `url` | String | 원본 공고 URL |
| `timestamp` | Timestamp | 공고 등록 시각 |
| `is_notified` | Boolean | FCM 발송 완료 여부 |

### 3.2 Track A — 스크래핑 함수 (`scraping_function.py`)

**역할:** Cloud Scheduler → HTTP 트리거 → 각 사이트 크롤링 → AI 요약 → Firestore 저장

**크롤링 대상:**
- 성동구청: `requests` + `BeautifulSoup4` HTML 파싱
- 강북구청: `requests` + `BeautifulSoup4` HTML 파싱
- 복지로: 공공 DATA API (`DATA_GO_KR_KEY`)

**AI 요약 프롬프트 패턴:**
```python
client.models.generate_content(
    model="gemini-3.1-flash-lite-preview",
    contents=f"다음 공고 제목을 어르신도 이해하기 쉽게 이모지 포함 20자 이내로 요약: {title}"
)
```

**중복 방지:** Firestore에 동일 URL 존재 여부 확인 후 신규 건만 저장

**Lazy 초기화 패턴 (배포 타임아웃 방지):**
```python
_db = None
_gemini_client = None

def _get_db():
    global _db
    if _db is None:
        _db = firestore.client()
    return _db
```

### 3.3 Track B — 알림 함수 (`notification_function.py`)

**역할:** Firestore `onCreate` 트리거 → FCM 전송 → `is_notified` 업데이트

**FCM Topic 매핑:**
```python
SOURCE_TOPIC_MAP = {
    "복지로":             "bokjiro",
    "성동구청":           "seongdong",
    "성동구 어르신일자리": "seongdong",
    "강북구청":           "gangbuk",
}
```

**발송 토픽:** `all` (전체) + 출처별 지역 토픽 동시 발송

**Android FCM 설정:**
- 우선순위: `high`
- 알림 아이콘: `ic_notification`
- 알림 색상: `#0056B3` (Primary Blue)
- 채널: `welfare_alerts`

### 3.4 Cloud Scheduler 설정

| Job 이름 | 스케줄 | 시간 (KST) |
|----------|--------|-----------|
| `scraping-morning` | `0 0 * * *` (UTC) | 09:00 KST |
| `scraping-evening` | `0 9 * * *` (UTC) | 18:00 KST |

- 리전: `asia-northeast3` (서울)
- HTTP Target: Cloud Functions scraping 엔드포인트
- 상태: ENABLED

---

## 4. Frontend 설계

### 4.1 화면 구성 (3탭)

```
┌─────────────────────────────┐
│  AppBar: "홈 (속보)"  🔄    │
├─────────────────────────────┤
│  [전체] [성동구청] [강북구청] [복지로]  ← 필터 칩 바
├─────────────────────────────┤
│                             │
│  ┌─────────────────────┐    │
│  │ [성동구청]    2시간 전│    │
│  │ 📢 어르신 공공일자리  │    │
│  │    모집 시작!        │    │
│  │ 2026년 어르신 공공.. │    │
│  │              자세히→ │    │
│  └─────────────────────┘    │
│  ┌─────────────────────┐    │
│  │      광  고          │    │  ← 5건마다 광고 카드
│  └─────────────────────┘    │
│                             │
├─────────────────────────────┤
│  [홈] [찜] [설정]            │  ← BottomNavigationBar
└─────────────────────────────┘
```

### 4.2 탭별 기능

| 탭 | 주요 기능 |
|----|----------|
| **홈 (속보)** | 전체 공고 실시간 스트림, 필터 칩(전체/성동구청/강북구청/복지로), 5건마다 광고 삽입, 공고 카드 ♥ 버튼으로 찜 추가 |
| **찜한 공고** | SharedPreferences에 저장된 공고 ID를 Firestore에서 조회, 최대 30건, 탭 전환 시 자동 새로고침, 찜 해제 가능 |
| **설정** | 지역 선택(FCM 토픽 자동 변경), 알림 ON/OFF, 앱 정보 |

### 4.3 공고 상세 (WebViewScreen)

- 인앱 WebView로 원본 공고 URL 열기
- AppBar: 뒤로가기 버튼 + 브라우저로 열기 버튼
- 뒤로가기 시 **AdMob Interstitial 전면 광고** 노출
- FCM 딥링크로 직접 진입 가능 (`/webview` 라우트)
- 광고 단위 ID: 환경변수 `ADMOB_INTERSTITIAL_ID` (기본값: 구글 테스트 ID)

### 4.4 FCM Deep Linking 흐름

```
FCM 알림 수신
    │
    ├─ 앱 실행 중: onMessage → SnackBar 표시
    ├─ 백그라운드: onMessageOpenedApp → WebViewScreen 이동
    └─ 앱 종료 상태: getInitialMessage → 시작 시 WebViewScreen 이동
```

### 4.5 주요 패키지

```yaml
firebase_core: ^3.6.0
cloud_firestore: ^5.4.4
firebase_messaging: ^15.1.4
webview_flutter: ^4.10.0
shared_preferences: ^2.3.3
google_mobile_ads: ^5.1.0
url_launcher: ^6.3.0
timeago: ^3.7.0
```

---

## 5. 디자인 시스템 (figma.md 기준)

### 5.1 컬러 팔레트

| 토큰 | 색상값 | 용도 |
|------|--------|------|
| `primary` | `#0056B3` | 버튼, AppBar, 선택 상태, FCM 알림 아이콘 |
| `orangeAccent` | `#E65100` | 긴급 버튼, 중요 배지 |
| `background` | `#F8F9FA` | 앱 전체 배경 |
| `surface` | `#FFFFFF` | 카드 배경 |
| `divider` | `#E0E0E0` | 카드 테두리, 구분선 |
| `textPrimary` | `#111111` | 본문 텍스트 |
| `textSecond` | `#555555` | 보조 텍스트, 시간 |
| `badgeSeongdong` | `#2E7D32` | 성동구청 배지 (Green) |
| `badgeGangbuk` | `#B71C1C` | 강북구청 배지 (Red) |
| `badgeBokjiro` | `#0056B3` | 복지로 배지 (Primary Blue) |

### 5.2 타이포그래피

| 토큰 | 크기 | 용도 |
|------|------|------|
| `fontXS` | 14px | 배지, 캡션 (비본문) |
| `fontSM` | 18px | 보조 본문 (WCAG AA 최소) |
| `fontMD` | 20px | 메인 본문 |
| `fontLG` | 24px | 카드 제목 (figma 최소) |
| `fontXL` | 28px | 섹션 헤더 |
| `fontXXL` | 34px | AppBar / 히어로 텍스트 |

- **폰트 패밀리:** Roboto (Android 시스템 기본, iOS 폴백)
- **접근성 기준:** WCAG AA — 본문 18px 이상, 제목 24px 이상

### 5.3 컴포넌트 규격

| 항목 | 값 |
|------|-----|
| 카드 모서리 반경 | 16px |
| 카드 elevation | 0 (테두리로 구분) |
| 카드 테두리 | `#E0E0E0` 1px |
| 터치 패딩 (상하) | 20px |
| 터치 패딩 (좌우) | 16px |
| 버튼 최소 높이 | 56px (터치 영역 확보) |
| 아이콘 크기 | 30px (BottomNavigationBar) |

### 5.4 NoticeCard 구조

```
┌──────────────────────────────────┐
│ [성동구청] 배지          2시간 전 │  ← 출처 배지 + timeago
│                                  │
│ 📢 어르신 공공일자리 모집 시작!   │  ← AI 요약 (fontLG, w800)
│                                  │
│ 2026년 어르신 공공일자리 사업     │  ← 원본 제목 (bodyMedium, 2줄)
│ 참여자 모집 공고                  │
│                                  │
│                      자세히 보기→ │  ← CTA (Primary Blue)
└──────────────────────────────────┘
```

---

## 6. 파일 구조

```
senior-welfare-app/
├── backend/
│   ├── main.py                    # Cloud Functions 진입점 (트리거 등록)
│   ├── scraping_function.py       # Track A: 크롤링 + AI 요약 + Firestore 저장
│   ├── notification_function.py   # Track B: FCM 푸시 발송
│   ├── requirements.txt           # Python 패키지
│   └── .env.yaml                  # 환경변수 (gitignore — API 키)
│
├── frontend/
│   ├── lib/
│   │   ├── main.dart              # 앱 진입점, 3탭 스캐폴드, FCM 딥링크
│   │   ├── theme.dart             # SeniorTheme (전역 디자인 토큰)
│   │   ├── models/
│   │   │   └── welfare_notice.dart  # Firestore 데이터 모델
│   │   ├── screens/
│   │   │   ├── home_screen.dart       # 홈(속보) 탭 — 필터 칩 + 실시간 스트림 + 찜 버튼
│   │   │   ├── bookmarks_screen.dart  # 찜한 공고 탭 — SharedPreferences + Firestore 조회
│   │   │   ├── settings_screen.dart   # 설정 탭 — 지역 선택 + 알림 ON/OFF
│   │   │   └── webview_screen.dart    # 공고 상세 — InApp WebView + AdMob
│   │   ├── widgets/
│   │   │   └── notice_card.dart     # 공고 카드 + 광고 플레이스홀더
│   │   └── services/
│   │       └── fcm_service.dart     # FCM 초기화, 토픽 구독 관리
│   └── pubspec.yaml
│
├── setup-cloud-scheduler.sh       # Cloud Scheduler gcloud CLI 등록 스크립트
├── .env                           # 로컬 환경변수 (gitignore)
├── .gitignore
└── DESIGN_DOCUMENT.md             # 이 파일
```

---

## 7. 배포 현황 (2026-03-11 기준)

| 항목 | 상태 | 비고 |
|------|------|------|
| Cloud Functions: `scraping_function` | ✅ 배포 완료 | asia-northeast3 |
| Cloud Functions: `notification_function` | ✅ 배포 완료 | asia-northeast3 |
| Cloud Scheduler: `scraping-morning` (09:00 KST) | ✅ ENABLED | Asia/Seoul |
| Cloud Scheduler: `scraping-evening` (18:00 KST) | ✅ ENABLED | Asia/Seoul |
| Firestore Database | ✅ 생성 완료 | asia-northeast3 |
| Firestore 보안 규칙 | ✅ 배포 완료 | welfare_notices 읽기 허용 |
| Firestore 복합 인덱스 | ✅ 배포 완료 | source + timestamp |
| AdMob 앱·광고단위 등록 | ✅ 완료 | `ca-app-pub-5634467403173492/3253182704` |
| Firebase 앱 등록 (`com.seniorwelfare.senior_welfare_app`) | ✅ 완료 | google-services.json 적용 |
| Flutter 앱 (Android 에뮬레이터) | ✅ 정상 작동 확인 | Firestore 연동 확인 |
| Flutter 앱 (Android 실기기) | 🔲 미확인 | FCM 푸시 테스트 필요 |
| Flutter 앱 (iOS) | 🔲 미진행 | — |

---

## 8. 남은 작업

→ 상세 작업 현황은 `TODO.md` 참고

| 항목 | 우선순위 |
|------|----------|
| 실기기(Android)에서 FCM 푸시 수신 및 딥링크 확인 | 높음 |
| Firestore `snapshots()` → `get()` 전환 (비용 최적화) | 높음 |
| 복지로 API 404 오류 수정 (data.go.kr 엔드포인트 변경 확인) | 중간 |
| iOS 빌드 및 테스트 (GoogleService-Info.plist 등록 필요) | 중간 |
| 앱 아이콘 · 스플래시 스크린 제작 | 중간 |
| 개인정보처리방침 작성 및 호스팅 | 출시 전 필수 |
| App Check 적용 (플레이스토어 등록 후) | 출시 전 필수 |
| 앱스토어 / 구글플레이 배포 준비 (서명 키, 스토어 설명) | 낮음 |

---

## 9. 환경변수

| 변수명 | 위치 | 용도 |
|--------|------|------|
| `GEMINI_API_KEY` | `.env`, `backend/.env.yaml` | Gemini AI 요약 API |
| `DATA_GO_KR_KEY` | `.env`, `backend/.env.yaml` | 복지로 공공 DATA API |
| `ADMOB_INTERSTITIAL_ID` | Flutter `--dart-define` | AdMob 전면 광고 ID |

> **주의:** `.env`, `backend/.env.yaml`은 `.gitignore`에 등록되어 있음
