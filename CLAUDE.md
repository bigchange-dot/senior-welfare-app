# CLAUDE.md — 어르신 알리미 프로젝트 지시사항

Claude Code가 이 프로젝트에서 작업할 때 반드시 따르는 규칙입니다.

---

## 프로젝트 개요

- **앱명:** 어르신 알리미 (Senior Welfare Notifier)
- **스택:** Flutter (frontend) + Firebase Cloud Functions Python 3.11 (backend)
- **DB:** Firestore (`welfare_notices` 컬렉션)
- **AI:** Gemini API `gemini-3.1-flash-lite-preview`
- **문서:** `ARCHITECTURE.md` (설계), `TODO.md` (작업 추적)

---

## 코딩 규칙

- 주석은 한국어로 작성
- 새 파일 생성 전 반드시 기존 파일을 먼저 읽고 확인
- 코드 수정 시 관련 MD 파일도 함께 업데이트:
  - 구조·화면 변경 → `ARCHITECTURE.md`
  - 기능 완료·추가 → `TODO.md`
- 과도한 리팩터링·불필요한 추상화 금지 — 요청한 것만 수정

---

## 금지 사항

- `tailwind.config.js` 생성 금지 (Flutter 프로젝트, React 아님)
- `google_fonts` 패키지 사용 금지 (시스템 폰트 사용)
- `figma.md`는 React 기준 문서 — 실제 구현 참고용으로만 사용, 코드 그대로 따르지 말 것
- `backend/.env.yaml` 커밋 금지 (로컬 전용 API 키 포함)
- `frontend/android/app/upload-keystore.jks` 커밋 금지
- `frontend/android/app/key.properties` 커밋 금지
- `frontend/lib/firebase_options.dart` 커밋 금지
- 자동 커밋 금지 — 명시적으로 요청받을 때만 커밋

---

## 프로젝트 특이사항

- `flutterfire configure` 미사용 — `firebase_options.dart`는 수동 작성
- Firestore는 `snapshots()` 대신 `get()` 사용 (비용 최적화)
- `home_screen.dart`: `kIsWeb`일 때만 Mock 데이터, 디바이스는 Firestore 실데이터
- AdMob Interstitial은 `webview_screen.dart`에 완전 구현됨
- Kotlin 증분 컴파일 오류 발생 시 → `flutter clean` 후 재빌드
- ADB 경로: `C:/Users/chae/AppData/Local/Android/Sdk/platform-tools`

---

## 복지로 API

- 엔드포인트: `NationalWelfareInformationsV001/NationalWelfarelistV001`
- 파라미터: `callTp=L, searchWrd=노인, srchKeyCode=003, numOfRows=20`
- 구 엔드포인트(`LcgvWelfareInfo`, `LcgvWelfarelist`)는 404/403 — 사용 금지

---

## Gemini API

- 모델: `gemini-3.1-flash-lite-preview`
- 호출 후 `time.sleep(13)` 필수 (무료 티어 분당 5회 제한)
- 429 발생 시 1차 65초, 2차 130초 대기 후 재시도 (최대 3회)

---

## FCM 토픽

```
all, bokjiro, nowon, dobong, jungnang, mapo, eunpyeong, seongdong, gangbuk
```

새 구청 추가 시 `notification_function.py`의 `SOURCE_TOPIC_MAP`과
`settings_screen.dart`의 `_regions`, `home_screen.dart`의 `_filters` 세 곳 모두 업데이트.

---

## Secret Manager

- 프로덕션 키: Firebase Secret Manager (`GEMINI_API_KEY`, `DATA_GO_KR_KEY`)
- 로컬 키: `backend/.env.yaml` 직접 수정
- 키 변경: `echo "새키" | firebase functions:secrets:set KEY명`
