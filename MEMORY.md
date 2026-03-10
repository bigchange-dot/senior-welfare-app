# 노인 복지 속보 알림 앱 — 프로젝트 메모리

## 프로젝트 개요
- **앱명:** 우리동네 복지 알림 (Senior Welfare Notifier)
- **목적:** 복지로·성동구청·강북구청 공고 자동 수집 → AI 요약 → FCM 푸시

## 기술 스택
- **Backend:** Firebase Cloud Functions (Python 3.11) — `backend/` 폴더
- **Frontend:** Flutter (iOS/Android) — `frontend/` 폴더
- **DB:** Firestore (`welfare_notices` 컬렉션)
- **AI:** Gemini API (gemini-2.5-flash)
- **Push:** FCM (Topic: all, bokjiro, seongdong, gangbuk)
- **시크릿:** Firebase Secret Manager (GEMINI_API_KEY, DATA_GO_KR_KEY)

## 현재 구현 상태 (2026-03-09, Android 에뮬레이터 실행 확인)
- [x] backend/main.py — Cloud Functions 진입점 (scraping_function에 secrets=[] 적용)
- [x] backend/scraping_function.py — Track A 스크래핑 전체 구현
- [x] backend/notification_function.py — Track B FCM 발송 구현
- [x] backend/.env.yaml — 로컬 에뮬레이터 전용 (gitignore됨, 프로덕션은 Secret Manager 사용)
- [x] backend/.env.yaml.example — 키 입력 템플릿
- [x] firestore.indexes.json — source+timestamp 복합 인덱스 (배포 완료)
- [x] setup-cloud-scheduler.sh — 오전 9시/오후 6시 KST 스케줄러 (Asia/Seoul 기준 통일)
- [x] frontend/lib/theme.dart — SeniorTheme (figma.md 토큰 적용 완료)
- [x] frontend/lib/main.dart — FCM 딥링크 + 3탭 네비게이션
- [x] frontend/lib/screens/home_screen.dart — 필터 칩(전체/성동구청/강북구청/복지로) + 실시간 스트림
- [x] frontend/lib/screens/webview_screen.dart — AdMob Interstitial 구현 + 브라우저 열기 구현
- [x] frontend/lib/screens/my_region_screen.dart — 완성
- [x] frontend/lib/screens/settings_screen.dart — 완성
- [x] frontend/lib/widgets/notice_card.dart
- [x] frontend/lib/services/fcm_service.dart
- [x] frontend/lib/models/welfare_notice.dart
- [x] frontend/lib/firebase_options.dart — 수동 생성 (flutterfire configure 미사용)

## 디자인 토큰 (figma.md 기준, theme.dart 적용 완료)
- Primary Blue: #0056B3
- Orange Accent: #E65100
- Background: #F8F9FA
- Surface (카드): #FFFFFF
- Card Border: #E0E0E0
- Body Text: #111111
- Sub Text: #555555
- Font: Roboto (fontFamily)
- 본문 폰트: 18px 이상 (fontSM=18)
- 제목 폰트: 24px 이상 (fontLG=24)
- 터치 영역: 56px × 56px 이상

## 주요 파일 경로
- `frontend/lib/theme.dart` — 전역 테마
- `frontend/lib/firebase_options.dart` — Firebase 초기화 옵션 (수동 생성)
- `frontend/pubspec.yaml` — 패키지 (google_mobile_ads, webview_flutter 등)
- `frontend/android/app/src/main/AndroidManifest.xml` — AdMob App ID 포함
- `frontend/android/app/google-services.json` — Firebase Android 설정
- `backend/scraping_function.py` — 스크래핑 로직
- `backend/notification_function.py` — FCM 발송
- `backend/.env.yaml` — 로컬 에뮬레이터 전용 환경변수 (gitignore됨)
- `firestore.indexes.json` — Firestore 복합 인덱스

## Secret Manager 관리
- 프로덕션 키는 Firebase Secret Manager에 저장됨
- `scraping_function` 데코레이터에 `secrets=["GEMINI_API_KEY", "DATA_GO_KR_KEY"]` 적용
- 키 변경 시: `echo "새키" | firebase functions:secrets:set KEY명` → `firebase deploy --only functions:scraping_function`
- 로컬 에뮬레이터 키 변경 시: `backend/.env.yaml` 직접 수정

## Cloud Scheduler
- 오전 9시 KST: `--schedule="0 9 * * *" --time-zone="Asia/Seoul"`
- 오후 6시 KST: `--schedule="0 18 * * *" --time-zone="Asia/Seoul"`
- 스케줄러 재등록 시 기존 작업 삭제 후 `bash setup-cloud-scheduler.sh` 실행

## Android 에뮬레이터 실행 설정 (2026-03-09 확인)
- ADB 경로: `C:/Users/chae/AppData/Local/Android/Sdk/platform-tools`
- 터미널에서 adb 사용: `export PATH="/c/Users/chae/AppData/Local/Android/Sdk/platform-tools:$PATH"`
- AdMob 테스트 App ID: `ca-app-pub-3940256099942544~3347511713` (출시 전 실제 ID로 교체 필요)
- google-services.json 패키지명: `com.seniorwelfare.senior_welfare_app` (build.gradle.kts applicationId와 일치)
- firebase_options.dart: flutterfire configure 미사용, 수동으로 google-services.json 값 기반 작성
- Firebase 초기화: `Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform)` 방식 사용
- Firestore 규칙 배포: `firebase deploy --only firestore:rules`

## Gemini API Rate Limit 처리 (scraping_function.py)
- 모델: `gemini-2.5-flash` (안정적, 사용 권장)
- 호출 후 `time.sleep(13)` — 무료 티어 분당 5회 제한 준수
- 429 발생 시 재시도: 1차 65초 대기, 2차 130초 대기 후 재시도 (최대 3회)
- 강북구청 언론보도 링크: `javascript:viewCount('ID', 'https://...')` → 정규식으로 URL 추출

## 스크래핑 실행 결과 (2026-03-09)
- 수집: 40건 (성동구청 10 + 강북구청 30), 복지로 API 404 오류
- 저장: 5건 신규, 14건 중복 스킵
- 로컬 실행: `GOOGLE_APPLICATION_CREDENTIALS="...json" python scraping_function.py`

## 주의사항
- tailwind.config.js 생성 금지 (없음 — Flutter 프로젝트)
- `pubspec.yaml` 주석: google_fonts 패키지 사용 안 함 (시스템 폰트 사용)
- AdMob Interstitial은 webview_screen.dart에 완전 구현됨 (TODO 아님)
- figma.md는 React 스택 설명이지만, 실제 구현은 Flutter
- home_screen.dart: `kIsWeb`일 때만 Mock 데이터 사용, 디바이스(debug/release) 모두 Firestore 실데이터 사용
- 복지로 API (data.go.kr) 404 오류 — 엔드포인트 변경 가능성 있음, 추후 확인 필요
- Firebase 출시 전 할 일: AdMob 실제 App ID 교체, Firebase 콘솔에서 패키지명 `com.seniorwelfare.senior_welfare_app`으로 앱 재등록
