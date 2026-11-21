# CLAUDE.md — 어르신 알리미 프로젝트 지시사항

Claude Code가 이 프로젝트에서 작업할 때 반드시 따르는 규칙입니다.

---

## 프로젝트 개요

- **앱명:** 어르신 알리미 (Senior Welfare Notifier)
- **스택:** Flutter (frontend) + Firebase Cloud Functions Python 3.11 (backend)
- **DB:** Firestore (`welfare_notices` 컬렉션)
- **AI:** 맥 로컬 Ollama `qwen2.5:14b` (2026-11-16~). Gemini `gemini-3.1-flash-lite-preview`는 클라우드 예비 — 선불 크레딧 소진 상태
- **수집 실행:** 맥 launchd (아래 "로컬 수집 실행"). 알림·헬스체크는 Cloud Functions
- **문서:** `ARCHITECTURE.md` (설계), `TODO.md` (작업 추적), `docs/` (점검·조사 기록 — 2026-11 전체 검토 결과, 운세 설계)

---

## 테스트 (2026-11-18 추가)

- 백엔드: `cd backend && venv/bin/python -m pytest` (네트워크·Firestore·LLM 안 부름, pytest는 `requirements-dev.txt`)
- 프론트엔드: `cd frontend && flutter test` → 끝나면 `git checkout -- frontend/analysis_options.yaml`
- 판정 규칙·요약 검사·헬스체크·새올 파서·카드 레이아웃·게시판 파서·출처 등록표·지역 목록을 바꾸면 테스트도 함께 고칠 것
- 게시판 출처 실제 점검(저장·AI 없음): `cd backend && venv/bin/python board_parser.py [이름 일부]`

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
- **알림이 아무에게도 안 가던 문제 (2026-11-19 해결)**: 앱 API 키(`senior app api key`)가 허용한 SHA-1(b4d1be8a…)이 실제 Play 앱 서명 키(441cdf10…)가
  아니어서 Play 빌드도 Firebase Installations 403 → 토큰·토픽 구독 실패였다. 키의 Android 앱 제한에 Play 서명·업로드(b7599c8c…)·이 맥 디버그(3ebc1511…)
  SHA-1을 추가함 → 로컬 디버그 빌드도 알림을 받는다. 확인법: `adb logcat | grep -E "Firebase-Installations|FCM 토픽"` (403이 없고 '토픽 동기화'가 보여야 함)
- `flutter analyze`/`build`가 `frontend/analysis_options.yaml`을 자동 수정함 → 커밋 전 `git checkout -- frontend/analysis_options.yaml`
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
  - 경기 52기관까지 수집하려면 `GYEONGGI=1` 추가. **v1.5 앱 출시 전에는 켜지 않는다** (v1.4 사용자는 지역을 못 골라 경기 알림이 모두 감).
    출시 때 launchd plist의 EnvironmentVariables에 `GYEONGGI=1`을 넣고 unload/load
- 이 폴더가 `v1.5-regions` 브랜치일 때는 그 브랜치의 백엔드가 자동 수집에 쓰인다 — 백엔드는 테스트가 통과하는 상태로만 둘 것
- Cloud Scheduler `scraping-morning`·`scraping-evening`은 일시정지 상태. 클라우드로 되돌리려면 `gcloud scheduler jobs resume <이름> --location=asia-northeast3`
  — Gemini 충전 필요, 그리고 `scraping_function`이 비공개(`invoker="private"`, 2026-11-17)라 스케줄러 작업에 OIDC 인증을 붙여야 함
- ⚠️ `scraping_function` 주소로 요청을 보내면 GET·HEAD 가리지 않고 수집이 실제로 실행된다. 확인용 요청 금지
- 실패 감시: 클라우드 `health_check_function`(10:00·19:00)이 실행 기록을 보고 메일 알림 (ARCHITECTURE.md 3.5). 맥이 꺼져 있어 수집을 못 하면 "N시간째 실행되지 않음" 메일이 옴

---

## 지역·출처·FCM 토픽 (v1.5, 2026-11-18~)

- 지역 기준은 두 파일: 앱 `frontend/lib/regions.dart`(서울 25·경기 31, `available`), 백엔드 `backend/sources.py`(출처 → 지역 코드·복지관 여부)
  + `backend/board_sources.py`(범용 파서로 읽는 게시판 목록). `backend/tests/test_sources.py`가 둘이 맞는지 확인
- 지역 코드 = 공고 `region` 필드 = FCM 토픽 = 앱 저장값. 서울은 v1.4 토픽 이름 그대로(`nowon` 등), 경기는 `gg-suwon` 형식, 복지로 `bokjiro`, 전체 `all`
- **새 출처 추가**: `sources.py`(또는 게시판이면 `board_sources.py`)에 넣기 → 그 지역 첫 출처면 `regions.dart`의 `available: true` → 테스트.
  첫 실행분은 자동으로 알림 없이 저장됨(`system_status/source_warmup`)
- 지역을 안 고른 사용자는 `all` = 서울·경기 전부 받음 (사용자 결정 2026-11-18)
- 알림 함수는 문서의 `region`으로 토픽을 정하므로 등록표만 바꿀 때는 재배포 안 해도 됨

## 오늘의 운세·Analytics (v1.6, 2026-11-19~)

- 설계 `docs/운세-설계-2026-11-18.md`. 서버 `backend/fortune.py` + `fortune_phrases.yaml`(문장 330개), 클라우드 `fortune_function`이 **매일 07:00**
  `fortunes/{날짜}` 문서(오늘·내일)를 쓰고 토픽 `fortune`으로 알림 1건. AI·맥과 상관없이 돈다. 발송 여부는 헬스체크가 확인
- **띠·출생연도는 기기에만 저장** — 서버·Analytics 이벤트에 넣지 않는다 (테스트로 고정). 운세 알림은 공고 알림과 따로이고 기본 꺼짐(첫 운세 뒤 한 번 묻기)
- 운세 문장 규칙 (새로 쓰거나 고칠 때): 돈·계약·기관 소식을 약속하지 않는다(사기 전화와 겹칠 위험), 자녀·손주·배우자가 있다고 전제하지 않는다,
  약 복용을 전제하지 않는다, 금지어·40자·핵심어 6자는 `tests/test_fortune.py`가 검사
- Analytics 이벤트는 `analytics_service.dart` 한 곳에서만 보낸다. 디버그 빌드는 수집 끔, 광고 ID 수집 끔
- 개인정보처리방침 `docs/privacy-policy.html`은 **master에 푸시하면 GitHub Pages로 바로 공개**된다 — 앱 출시와 맞춰 합칠 것

## 디자인·시안 작업 (2026-11-19 사용자 결정)

- 화면 구조와 색은 지금 것을 유지하고 **부분 다듬기**로 간다. 전면 재디자인 시안(일력·마감 수첩·소식지)은 "현재가 더 낫다"로 채택하지 않음
- 시안·보고서는 **claude.ai 아티팩트로 올리지 않는다.** 이 PC의 파일로 만들어 `open`으로 띄우거나 태블릿 화면으로 보여 줄 것
- 공고 카드: 출처는 한 가지 색 글자, 요약 앞 이모지는 화면에서 떼고 분야 글자로(`notice_card.dart`의 `splitSummary`). 서버 요약은 이모지를 그대로 붙여 저장한다

## 출시 상태 (2026-11-19)

- Play 출시본 **1.5.0(10)** (2026-11-21 스토어 페이지에서 확인). 같은 날 launchd plist에 `GYEONGGI=1`을 넣어 경기 수집 시작 — 첫 회차는 알림 없이 저장
- 1.6.0(11)은 `v1.6-fortune` 브랜치: 운세 + Analytics + 화면 다듬기. 출시 전 Play Console 데이터 보안에 '앱 활동'·'기기 ID'(분석 목적) 추가 필요
- 출시 파일 보관: `frontend/build/release-keep/` (git 제외). 내부 테스트 링크는 Play Console → 내부 테스트 → 테스터
- 태블릿 시험: 디버그 빌드와 Play 빌드는 서명이 달라 서로 덮어 설치되지 않음(먼저 제거). 잠금이 있어 화면이 꺼지면 사용자가 풀어야 함 —
  시험 중 `adb shell svc power stayon usb`, 끝나면 `stayon false`
- 시험 알림은 구독자가 시험 기기뿐인 토픽으로만 보낼 것 (예: 그 기기에서 고른 경기 지역 토픽). `all`·서울 구 토픽으로 보내면 실제 사용자에게 간다

## Secret Manager

- 프로덕션 키: Firebase Secret Manager (`GEMINI_API_KEY`, `DATA_GO_KR_KEY`)
- 로컬 키: `backend/.env.yaml` 직접 수정
- 키 변경: `echo "새키" | firebase functions:secrets:set KEY명`
