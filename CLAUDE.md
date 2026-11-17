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
- ADB 경로 (Mac): `~/Library/Android/sdk/platform-tools` (구 Windows: `C:/Users/chae/AppData/Local/Android/Sdk/platform-tools`)
- Mac 개발환경: Homebrew 설치 (Flutter, openjdk@17, python@3.11, firebase-cli, gcloud), 환경변수는 `~/.zprofile`

---

## 복지로 API

- 엔드포인트: `NationalWelfareInformationsV001/NationalWelfarelistV001`
- 파라미터: `callTp=L, searchWrd=노인, srchKeyCode=003, numOfRows=20`
- 구 엔드포인트(`LcgvWelfareInfo`, `LcgvWelfarelist`)는 404/403 — 사용 금지

---

## AI 판정 (`backend/llm_judge.py`)

- `LLM_PROVIDER`로 선택: `ollama`(맥 로컬, 기본 모델 `qwen2.5:14b`) / `gemini`(기본값, 클라우드)
- 판정 정책·규칙 필터·요약 검사는 ARCHITECTURE.md 3.2. 규칙·프롬프트를 바꾸면 과거 판정으로 재평가할 것
- Gemini: 모델 `gemini-3.1-flash-lite-preview`, 호출 후 `time.sleep(13)` (분당 5회 제한), 429는 65초·130초 대기 후 재시도.
  **2026-10-23부터 선불 크레딧 소진(402)** — 지금은 쓰지 않음. 다시 쓰려면 AI Studio에서 충전

---

## 로컬 수집 실행 (2026-11-16~, 클라우드 수집 대신)

- 수집 파이프라인은 이 맥에서 launchd로 매일 09:00·18:00 실행. 알림 함수·헬스체크는 그대로 클라우드
- launchd 원본: `launchd/com.seniorwelfare.pipeline.plist` → `~/Library/LaunchAgents/com.seniorwelfare.pipeline.plist`(심볼릭 링크)
  - plist를 고치면 `launchctl unload` 후 `load` 다시
- 로그: `logs/pipeline.log` (git 제외)
- 맥(MacBook)이 잠자기면 그 시각엔 안 돌고 깨어날 때 한 번 실행, 꺼져 있으면 건너뜀. 그래서 **09:00 회차는 매일 09:01 자동 깨우기로 보장**,
  18:00 회차는 맥이 켜져 있을 때만 돈다 (사용자 결정 2026-11-16)
  - 깨우기 예약 (시스템 설정, 프로젝트 밖): `sudo pmset repeat wakeorpoweron MTWRFSU 09:01:00` — 확인 `pmset -g sched`, 해제 `sudo pmset repeat cancel`
  - FileVault가 켜져 있고 자동 로그인이 꺼져 있어 재시동 후에는 로그인해야 수집이 시작됨
  - 뚜껑 닫힌 배터리 상태에서는 macOS 점검 깨어남(DarkWake) 때 작업이 시작돼 잠들고 깨기를 반복하며 느리게 끝남(18시 회차 1시간).
    `caffeinate`로 못 막음. Ollama 호출 재시도로 결과는 정상 (2026-11-17 확인)
- Firestore 인증: gcloud ADC (`~/.config/gcloud/application_default_credentials.json`, 할당량 프로젝트 `senior-welfare-app`).
  만료되면 **터미널 앱에서** `gcloud auth application-default login` (Claude Code `!`로는 브라우저가 안 열림)
- 수동 실행: `cd backend && LLM_PROVIDER=ollama GOOGLE_CLOUD_PROJECT=senior-welfare-app venv/bin/python scraping_function.py`
  - 밀린 공고를 알림 없이 저장하려면 `SILENT_SAVE=1` 추가
- Cloud Scheduler `scraping-morning`·`scraping-evening`은 일시정지 상태. 클라우드로 되돌리려면 `gcloud scheduler jobs resume <이름> --location=asia-northeast3` (Gemini 충전 필요)
- 실패 감시: 클라우드 `health_check_function`(10:00·19:00)이 실행 기록을 보고 메일 알림 (ARCHITECTURE.md 3.5). 맥이 꺼져 있어 수집을 못 하면 "N시간째 실행되지 않음" 메일이 옴

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
