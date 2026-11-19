# 노인 복지 속보 알림 앱 — 아키텍처 문서

> 최초 작성: 2026-03-03
> 최종 업데이트: 2026-11-18 (전체 검토 1~7단계 반영)
> 앱 버전: 1.4.0+7 제출본, 1.4.1+8 준비 중 (TODO.md)

---

## 1. 프로젝트 개요

### 앱 목적
노인 복지 공고(서울 주요 구청·복지로)를 자동 수집하고, AI로 요약한 뒤 FCM 푸시 알림으로 어르신께 실시간 전달하는 서비스.

### 핵심 가치
- **속보성** — 하루 2회(09:00 · 18:00 KST) 자동 크롤링
- **접근성** — 어르신 친화 UI (초대형 폰트, 넉넉한 터치 영역)
- **개인화** — 지역 선택으로 관심 구청 공고만 필터링
- **수익화** — AdMob 전면 광고 (뒤로가기 시 노출)

---

## 2. 시스템 아키텍처

### 전체 흐름

```
[맥 launchd] 09:00 / 18:00 KST  (2026-11-16~, 클라우드 Cloud Scheduler 수집은 일시정지)
  backend/scraping_function.py 직접 실행, AI는 로컬 Ollama
       │
       ▼
[Track A: 수집 파이프라인]
  성동구청 · 강북구청 웹 크롤링
  복지로 공공 API 호출
       │
       ▼ AI 판정·요약 (llm_judge.py: 규칙 필터 → Ollama/Gemini)
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

[운영 감시] (2026-11-16, 3.5 참고)
  scraping_function ─ 실행마다 ─▶ Firestore pipeline_runs / system_status
  health_check_function (10:00 / 19:00 KST) ─ 문제 시 HEALTH_ALERT 로그
       └▶ Cloud Monitoring 로그 알림 정책 ─▶ 이메일
```

### 기술 스택

| 영역 | 기술 |
|------|------|
| **Backend** | Firebase Cloud Functions (Python 3.11, 2nd Gen) |
| **Database** | Cloud Firestore (`welfare_notices` 컬렉션) |
| **AI 요약** | `LLM_PROVIDER`로 선택 — 로컬 Ollama `qwen2.5:14b` / Google Gemini API `gemini-3.1-flash-lite-preview` (3.2 참고) |
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
| `source` | String | 출처 이름 (`복지로` / `도봉노인복지관` / `서호노인복지관` …) |
| `region` | String | 지역 코드 = FCM 토픽 = 앱 `Region.id` (`nowon`, `gg-suwon`, 복지로는 `bokjiro`). v1.5, 2026-11-18 추가·기존 407건 백필 |
| `province` | String | `seoul` / `gyeonggi` / `national` |
| `url` | String | 원본 공고 URL |
| `timestamp` | Timestamp | 공고 등록 시각 |
| `is_notified` | Boolean | FCM 발송 완료 여부 |

**컬렉션:** `skipped_notices` (2026-09-03 추가, 백엔드 전용)

Gemini가 SKIP 판정한 공고의 URL 캐시. 문서 ID는 `welfare_notices`와 동일한 URL 해시.
매 실행마다 같은 공고(직원 채용·합격자 명단 등)를 Gemini에 재전송하던 낭비를 제거.
필드: `title`, `source`, `url`, `timestamp`. Gemini 호출 자체가 실패한 건(`ERROR`)은 기록하지 않고 다음 실행에 재시도.

**컬렉션:** `pipeline_runs` / `system_status` (2026-11-16 추가, 백엔드 전용 — `monitoring.py`)

수집 실행 기록. `pipeline_runs/{자동 ID}`는 실행마다 1건 쌓이는 이력, `system_status/pipeline`은 마지막 실행 1건(헬스체크가 읽음).
`system_status/source_warmup`(v1.5)은 한 번 이상 수집을 마친 출처 이름 목록 — 여기 없는 출처의 첫 수집분은 알림 없이 저장한다.
두 컬렉션 모두 `firestore.rules`의 기본 차단 규칙에 걸려 앱에서는 읽을 수 없다.

| 필드 | 설명 |
|------|------|
| `started_at` / `finished_at` | 실행 시작·종료 시각 (UTC) |
| `runner` | `cloud`(Cloud Functions) / `local`(직접 실행) |
| `collected` / `saved` / `skipped` | 수집·저장·건너뜀 건수 |
| `llm_calls` / `llm_errors` / `llm_error` | AI 요약 호출 수, 실패(보류) 수, 마지막 오류 메시지 |
| `source_counts` | 스크래퍼 함수명 → 수집 건수 (`-1` = 예외로 실패) |
| `errors` | 실행 중 ERROR 로그 요약 `[{message, count}]` (최대 20개) |
| `fatal` | 파이프라인이 예외로 중단됐을 때 사유 (정상이면 빈 문자열) |

### 3.2 Track A — 스크래핑 함수 (`scraping_function.py`)

**역할:** 각 사이트 수집 → AI 판정·요약 → Firestore 저장 → 실행 기록

**실행 방식 (2026-11-16~):** 맥 launchd가 `scraping_function.py`를 직접 실행(09:00·18:00, CLAUDE.md "로컬 수집 실행").
Cloud Functions HTTP 트리거(`scraping_function`)는 남아 있지만 비공개(`invoker="private"`)이고 스케줄러는 일시정지.

**수집 대상 (2026-11-18, `_run_pipeline`의 `scrapers`):**
- 복지로: 공공 DATA API (`DATA_GO_KR_KEY`) — `NationalWelfareInformationsV001`
- 구청 게시판 10곳: 노원·도봉·중랑·마포·은평·종로·중구·용산·서대문·양천 + 성동구청 채용
  (`_scrape_seoul_board()` / `_scrape_nowon_board()` 등 공통 헬퍼)
- 노인복지관 7곳: 수락·도봉·은평·종로·약수·용산·서대문 (`_scrape_g5_board()` 등). 저장 공고의 대부분이 여기서 나옴
- **게시판 출처 (v1.5, `board_sources.py` + 범용 목록 파서 `board_parser.py`):**
  - 서울 4곳 — 6개월 저장 0건이던 강서·동작·관악구청 대신 강서노인종합·마곡·사당·관악노인종합복지관
  - 경기 52기관 (복지관·시니어클럽, 24개 시·군) — **환경변수 `GYEONGGI=1`일 때만** (v1.5 앱 출시 때 켬)
    - 전용 처리: 광주(글 링크가 javascript → `JS_LINKS`로 상세 주소), 부천 공동 포털(한 게시판에 4기관 → 제목 앞 기관 표시로 출처 구분,
      `BOARD_LABELS`), 화성 동탄(JSON 목록·본문, `JSON_BOARDS`·`scrape_json_board`)
  - 파서: 목록 페이지에서 '날짜가 가까이 붙은 링크'(링크 위 4단계, 400자·글 링크 2개 이하 영역)를 글로 읽음.
    최근 45일 글만. 그누보드·`bid=`형·자체 구조를 사이트별 코드 없이 처리. 점검: `venv/bin/python board_parser.py [이름]`
- 제외: 강북구청(차단), 마포·성동·신내·강북·노원 노인복지관(차단·폐쇄·게시판 없음) — 스크래퍼 코드는 2026-11-18 삭제 (git 이력 742c192 이전)

**출처 등록표 `sources.py` (v1.5):** 출처 이름 → (지역 코드, 복지관 여부). 저장 시 `region`·`province`, 알림 토픽, 키워드 필터 면제(복지관)를
모두 여기서 정한다. 예전 `SOURCE_TOPIC_MAP`(알림)·`WELFARE_CENTER_SOURCES`(수집)를 대신함. 앱 `frontend/lib/regions.dart`와 지역 코드·
'준비 중' 여부가 맞는지 `tests/test_sources.py`가 확인한다. 새 출처: 등록표(또는 `board_sources.py`)에 추가 → 그 지역 첫 출처면 앱 `available: true`.

**새 출처 첫 실행은 알림 없이 (v1.5):** `system_status/source_warmup`에 없는 출처의 공고는 그 실행에서 `is_notified=True`로 저장하고
목록에 추가한다. 출처를 붙인 날 그동안 밀린 공고(경기 첫 실행은 약 300건 중 판정 통과분)가 한꺼번에 알림으로 나가지 않게.

**AI 판정·요약 (`llm_judge.py`, 2026-11-16 개편):**

판정 순서 (복지로 제외 출처): 중복 → **규칙 필터** → 키워드 필터(구청 등 일반 출처) → SKIP 캐시 → 본문 추출 → **LLM 판정**

- 규칙 필터 `rule_skip_reason()`: 합격자·추첨·선정 결과, 행정 공개(업무추진비·수의계약·회의록 등), 행정 공고(공시송달·입찰 등),
  제목에 마감 표시가 있는 글은 LLM에 묻지 않고 제외. 결과 발표라도 "추가 접수/모집"이 있으면 LLM으로 넘김.
  (도입 이유: 같은 유형 판정이 엇갈림 — 수락 '합격자 명단' 9건 SKIP·5건 PASS, 도봉은 같은 문장 알림 15건+)
- 정책 (2026-11-16 결정): 합격자·결과 발표 제외 / 이미 끝난 일 보도(성료·협약·수상·전달식) 제외 /
  요약은 대상·날짜·마감 위주 정보형, 🚨·[속보]·느낌표 금지
- 프롬프트에 오늘 날짜를 넣어 마감 지난 공고 제외. 본문은 800자까지 (기존 300자)
- 출력은 JSON `{"decision": "PASS|SKIP", "summary": "..."}`. Ollama는 JSON 스키마 구조화 출력, Gemini는 `response_mime_type=application/json`
- 저장 전 검사 `is_valid_summary()`: 40자 초과, 한자, 한글 4자 미만, **제목·본문에 없는 숫자**(지어낸 날짜·인원),
  제목·본문에 없는 영문 단어, **제목과 다른 글을 요약**(흔한 말·기관 이름을 빼고 같은 낱말이나 두 글자 조각 2개 이상을 나누지 않음,
  가정통신문·월간 소식 같은 정기 소식 제목은 예외 — `summary_matches_title`, 2026-11-18) → 제목 기반 문구 `📢 제목 28자`로 대체
- LLM 선택: 환경변수 `LLM_PROVIDER` — `gemini`(기본, 클라우드) / `ollama`(맥 로컬, `qwen2.5:14b`)
- **기간 지남 검사** `latest_date_in()`: 요약에 적힌 마지막 날짜(`11/12`, `10월 30일`, `~30일`, `10.27까지`·`~10.27`)가 오늘보다 앞서면 SKIP.
  LLM이 날짜 비교를 자주 놓침 (첫 로컬 실행에서 끝난 전시회·강좌 2건 저장)
- Ollama 연결 오류·5xx는 10초 뒤 최대 2번 다시 시도 (맥이 실행 도중 잠들었다 깨면 500이 남, 2026-11-17)
- 호출 실패는 `"ERROR"` → 저장하지 않고 다음 실행에 재시도, 실행 기록 `llm_errors`로 집계

**본문 추출 `fetch_detail_content()` (2026-11-16 수정):** 게시판 전용 영역(`div.view_content`, `div.xe_content` 등)은 그대로 쓰고,
범용 영역(`article`, `div#content`, `<p>` 합산)은 제목과 겹치는 단어가 있을 때만 쓴다. 이전에는 강북구청 언론보도(외부 신문사 링크)에서
다른 기사 제목들을 긁어 엉뚱한 요약이 저장됐다. 응답 헤더에 charset이 없으면 인코딩을 추정해 한글 깨짐을 막는다.
도봉노인복지관(본문이 포스터 이미지)·은평노인복지관(본문이 스크립트로 암호화)은 본문 없이 제목으로만 판정된다.

**알림 없이 저장 `SILENT_SAVE=1`:** `is_notified=True`로 저장해 알림 함수가 발송을 건너뜀. 장애 뒤 밀린 공고를 한꺼번에 처리할 때 사용.

**중복 방지:** Firestore에 동일 URL 존재 여부 확인 후 신규 건만 저장

**복지로 신규 상한:** `BOKJIRO_MAX_NEW_PER_RUN = 2` — 복지로는 Gemini 없이 직접 저장되므로
신규가 한꺼번에 생기면 FCM 알림이 폭주함. 실행당 2건까지만 저장하고 나머지는 다음 실행으로 이월.

**로깅 (`log_config.py`, 2026-09-03):** Functions 런타임이 루트 로거를 WARNING으로 잡아
`logger.info()`가 Cloud Logging에 올라가지 않던 문제 해결. Cloud Run 환경(`K_SERVICE`)에서는
stdout에 `{"severity","message"}` JSON 한 줄로 출력해 severity 필터가 동작하고, 로컬은 평문.
복지로 API 오류 메시지의 `serviceKey`는 `***`로 마스킹.

**출처 현황 (2026-11-16 점검, 상세 `docs/수집기-현황-2026-11-16.md`):**
- 중구청·성동구청 채용: SSL 중간 인증서 누락 → `tls_compat.install_ca_bundle()`이 certifi 루트 + `certs/intermediates.pem`을
  `REQUESTS_CA_BUNDLE`로 지정해 해결 (2026-11-16). 인증서 검증은 끄지 않음
- 은평·용산구청: 구글 IP 차단, 맥 로컬 수집으로 회복
- 강북구청 3개 게시판: 구글 IP 차단(10-26~)에 이어 맥에서도 연결 끊김(11-16~17, 4회 연속) → **수집 목록에서 제외** (2026-11-17)
- 강서·동작·관악구청: 2026-05 추가 이후 저장 0건 (어르신과 무관한 게시판) → 2026-11-18 그 구의 복지관 게시판으로 교체
- 마곡어르신복지관·수원 서호노인복지관: 중간 인증서 누락 → `certs/intermediates.pem`에 ZeroSSL DV CA 2·RapidSSL G5 추가 (2026-11-18)

**접속 불가 출처 (2026-09-03 기준):**
- 마포노인복지관(senior21.or.kr): 봇 차단 403 → 스크래퍼 목록에서 제외
- 중랑구청: 당시 구글 IP에서 연결 타임아웃 → 2026-10~11 클라우드·맥 모두 정상 수집 (해결됨)
- 성동노인종합복지관(sdsenior.or.kr): 파서는 재작성했으나 구글 IP에서 403 차단 → 목록에서 제외. 한국 IP 프록시 등 인프라 대안 필요

**Lazy 초기화 패턴 (배포 타임아웃 방지):** Firestore는 `_get_db()`, Gemini 클라이언트는 `llm_judge._call_gemini()` 안에서 처음 쓸 때 만든다.
```python
_db = None

def _get_db():
    global _db
    if _db is None:
        _db = firestore.client()
    return _db
```

### 3.3 Track B — 알림 함수 (`notification_function.py`)

**역할:** Firestore `onCreate` 트리거 → FCM 전송 → `is_notified` 업데이트

**FCM Topic 매핑 (v1.5):** 공고 문서의 `region`을 지역 토픽으로 쓴다(없으면 `sources.region_of(source)`). 수집은 맥에서 돌아
클라우드에 배포된 등록표보다 새로울 수 있어서 문서 값을 먼저 본다. 서울 토픽 이름은 v1.4 그대로(`nowon` 등), 경기는 `gg-suwon` 형식.

**발송 토픽:** `all` (전체) + 출처별 지역 토픽 동시 발송

**Android FCM 설정:**
- 우선순위: `high`
- 알림 아이콘: `ic_notification`
- 알림 색상: `#0056B3` (Primary Blue)
- 채널: `welfare_alerts`

### 3.3a 오늘의 운세 (`fortune.py`, v1.6 — 설계 `docs/운세-설계-2026-11-18.md`)

- `fortune_function`(예약 함수, 매일 07:00 KST): 오늘·내일 `fortunes/{YYYY-MM-DD}` 문서(60갑자 년주 전부, 약 30KB)를 쓰고
  토픽 `fortune`으로 알림 1건. `system_status/fortune.last_push_date`로 하루 한 번만 보낸다. **AI·맥과 상관없이 돈다**
- 계산: 일진·년주 → 십신 × 합·충 → 등급 3가지(좋음·보통·차분히). 문장은 `fortune_phrases.yaml`(330문장)에서
  `sha256(날짜|년주|칸)`으로 고른다 — 같은 날·같은 년주면 언제 계산해도 같다
- 알림: "🐵 오늘은 원숭이띠 날 · 오늘의 운세" / "44년생 … · 56년생 … · 68년생 …" (본문 40자 이내), 채널 `fortune`, 12시간 뒤 만료
- 감시: `health_check_function`이 08시 이후 오늘 발송 기록을 확인 (`monitoring.fortune_problems`)
- 앱: 띠·년생은 기기에만 저장. 운세 알림은 공고 알림과 따로이고 기본 꺼짐 — 첫 운세를 본 뒤 한 번 묻는다

### 3.4 Cloud Scheduler 설정

| Job 이름 | 스케줄 | 시간 (KST) |
|----------|--------|-----------|
| `scraping-morning` | `0 0 * * *` (UTC) | 09:00 KST |
| `scraping-evening` | `0 9 * * *` (UTC) | 18:00 KST |

- 리전: `asia-northeast3` (서울)
- HTTP Target: Cloud Functions scraping 엔드포인트
- 상태: **PAUSED** (2026-11-16, 맥 로컬 수집으로 전환. 되돌리기: `gcloud scheduler jobs resume <이름> --location=asia-northeast3`)
- 재시도 설정 없음(retryCount 0) — 2026-11-16 오전 인스턴스 대기 초과 500 한 번에 그 회차가 빠졌음

### 3.5 운영 감시 (`monitoring.py`, 2026-11-16)

**배경:** 2026-10-23부터 Gemini 선불 크레딧 소진(402)으로 25일간 신규 저장 0건이었지만, 수집 함수가 매번
200으로 끝나 스케줄러·로그 어디에서도 실패로 드러나지 않았다.

**구조:**
1. `run_scraping_pipeline()`이 성공·실패와 관계없이 실행 기록을 남긴다 (`try/finally`). 스크래퍼별 오류는
   루트 로거에 붙인 `ErrorCollector`가 ERROR 로그를 모아 요약한다. 기록 실패는 경고만 남기고 수집에 영향을 주지 않는다.
2. `health_check_function`(스케줄 트리거, 매일 10:00·19:00 KST)이 `system_status/pipeline`과
   최신 `welfare_notices.timestamp`를 읽어 판정한다. 수집을 클라우드에서 하든 로컬에서 하든 같은 기록을 보므로 감시 방식은 같다.
3. 문제가 있으면 `HEALTH_ALERT | 문제1 / 문제2 | 참고: 0건·실패 출처 …`를 ERROR 로그로 남긴다.
4. Cloud Monitoring 로그 알림 정책이 `health-check-function`의 ERROR 로그(헬스체크 함수 자체의 오류 포함)를 이메일로 보낸다.

**알림 조건 (`find_problems`):**

| 조건 | 기준 |
|------|------|
| 수집이 멈춤 | 마지막 실행 종료 후 16시간 초과 (정상 최대 간격 15시간) |
| 수집 중단 | `fatal` 있음 |
| 수집 0건 | `collected == 0` (모든 출처 실패) |
| AI 요약 실패 | 실패 3건 이상, 또는 호출한 건이 전부 실패 (일시적 429 1~2건은 무시) |
| 새 공고 없음 | 최신 공고가 4일 넘게 없음 (2026-03~10 평균 하루 1.8건) |
| 기록 없음 | `system_status/pipeline` 문서 없음 (배포 직후 첫 수집 전이면 한 번 뜰 수 있음) |

출처별 0건·실패는 알림 조건이 아니라 메일 본문 참고 정보로만 넣는다 (구글 IP 차단 출처가 상시 0건이라 매번 울리게 됨).

---

## 4. Frontend 설계

**지역 (v1.5, 2026-11-18):** `lib/regions.dart` 한 곳에 서울 25개 구 + 경기 31개 시·군. `Region.id`는 공고 `region` 필드·FCM 토픽·
저장값으로 함께 쓴다. `available: false`인 지역은 지역 선택 화면에 '준비 중'(백엔드 등록표와 테스트로 맞춤).
**내 지역**(`services/region_prefs.dart`, 최대 3곳)은 홈·찜·알림이 같이 쓴다 — 예전엔 홈 칩과 설정 알림 지역이 따로였다.
저장 키 `selected_regions`·`bokjiro_notif`. v1.4 설정(`selected_topics`·`selected_sources`)은 첫 실행 때 옮기고 지운다.

**FCM 토픽 구독 규칙 (`FcmService.syncSubscriptions`):**
서버는 모든 공고를 `all` + 지역 토픽에 동시 발송한다. 중복 수신을 막기 위해 앱은
내 지역을 고른 사용자는 그 지역 토픽(+'전국 공고(복지로)도 받기'를 켜면 `bokjiro`)만, 고르지 않은 사용자는 `all`(서울·경기 전부)만 구독한다
(사용자 결정 2026-11-18). 토픽이 58개라 구독 중인 목록을 `fcm_topics`에 적어 두고 바뀐 것만 구독·해지한다.
알림 OFF는 전체 토픽 해지.

### 4.1 화면 구성 (3탭)

```
┌─────────────────────────────┐
│  AppBar: "어르신 알리미"  🔄 │
├─────────────────────────────┤
│ 📍 노원구 · 수원시        [지역 바꾸기] │  ← v1.5: 지역 선택 화면 열기
│  [내 지역] [전체] [복지로]                 ← 칩 3개 (예전 구청 칩 13개 가로 스크롤 대신)
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
| **어르신 알리미** | 전체 공고, 필터 칩(전체/복지로/노원/도봉/중랑/마포/은평/성동/강북 — 가로 스크롤), 5건마다 광고 삽입, ♥ 버튼으로 찜 추가 |
| **찜한 공고** | **상단:** 찜한 공고 목록 / **하단:** 설정한 내 지역 공고 목록 — 탭 전환 시 자동 새로고침 |
| **설정** | 지역 선택 9개(복지로·노원·도봉·중랑·마포·은평·성동·강북·전체), FCM 토픽 자동 변경, 알림 ON/OFF |

### 4.3 공고 상세 (WebViewScreen)

- 인앱 WebView로 원본 공고 URL 열기
- AppBar: 뒤로가기 버튼 + 브라우저로 열기 버튼
- 뒤로가기 시 **AdMob Interstitial 전면 광고** 노출
- FCM 딥링크로 직접 진입 가능 (`/webview` 라우트)
- 광고 단위 ID: 환경변수 `ADMOB_INTERSTITIAL_ID` (기본값: 구글 테스트 ID)

### 4.3a 광고 (`services/ad_service.dart`, 2026-09-03)

| 포맷 | 위치 | 비고 |
|------|------|------|
| 배너 (320×100) | 홈 목록 6번째 항목마다 `BannerAdCard` | `AutomaticKeepAliveClientMixin`으로 스크롤 시 재요청 방지, 로드 실패 시 숨김 |
| 전면광고 | WebView 뒤로가기 | 세션당 3회, 3분 간격 상한 (`AdService.canShowInterstitial`) |

- 디버그 빌드는 구글 테스트 광고 ID, 릴리스만 실제 ID 사용
- 배너 광고 단위 ID는 AdMob 콘솔에서 생성 후 `_bannerProd`에 입력 필요

### 4.3b 홈 화면 상태 처리 (2026-11-17)

- 캐시의 빈 결과(`metadata.isFromCache` + 0건) → "인터넷에 연결되어 있지 않아요" + 다시 시도. 오류 화면도 다시 시도 버튼·당겨서 새로고침
- 저장된 공고(캐시)를 보여 줄 때 목록 맨 위에 오프라인 안내
- 새로고침(앱바 버튼·당겨서·다시 시도)은 `GetOptions(source: Source.server)`로 서버에서 다시 받음 (`HomeScreenState.refresh`)
- 목록 배너 광고 위에 '광고' 표시. 카드의 시간·출처 배지 16px, 찜 버튼 52×52

### 4.4 FCM Deep Linking 흐름

```
FCM 알림 수신
    │
    ├─ 앱 실행 중: onMessage → 로그만 (화면 표시 없음 — 미구현)
    ├─ 백그라운드: onMessageOpenedApp → WebViewScreen 이동
    └─ 앱 종료 상태: getInitialMessage → 첫 화면이 그려진 뒤 WebViewScreen 이동
```

- 2026-11-17 수정: 예전엔 `main()`이 `runApp()` 전에 초기화를 기다리며 시작 메시지를 처리해 네비게이터가 없어 무시됐음(홈이 열림).
  지금은 `_handleMessage`가 네비게이터가 없으면 `addPostFrameCallback`으로 미루고, `main()`은 FCM 초기화를 기다리지 않음
- `initialize()`는 권한·토큰(디버그만)·처리기 등록·시작 메시지·토픽 구독을 단계별로 예외 처리 (토큰 실패가 나머지를 막지 않게)
- 2026-11-19: Play 내부 테스트(1.5.0)에서 꺼진 상태 알림 탭 → 공고 화면 확인. 앱 API 키에 Play 서명·업로드·디버그 SHA-1을 추가해
  로컬 디버그 빌드도 토큰을 받는다 (그 전엔 Play 빌드까지 Firebase Installations 403이라 알림이 아무에게도 안 갔음, CLAUDE.md)
- 알림 채널 `welfare_alerts`(중요도 높음)를 `MainActivity`가 만들고, 매니페스트 기본 채널로 지정 (2026-11-19)

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
│   ├── llm_judge.py               # AI 판정·요약: 규칙 필터, 프롬프트, Ollama/Gemini 호출, 결과 검사 (3.2)
│   ├── monitoring.py              # 운영 감시: 실행 기록 + 헬스체크 (3.5)
│   ├── log_config.py              # Cloud Logging용 JSON 로그 설정
│   ├── fortune.py                 # 오늘의 운세: 간지 계산·문장 고르기·날짜 문서·알림 (v1.6)
│   ├── fortune_phrases.yaml       # 운세 문장 묶음 330개
│   ├── sources.py                 # 출처 등록표: 출처 → 지역 코드·복지관 여부 (v1.5)
│   ├── board_sources.py           # 범용 파서로 읽는 게시판 목록 (서울 교체 4 + 경기 52기관, v1.5)
│   ├── board_parser.py            # 범용 게시판 목록 파서 (v1.5)
│   ├── tls_compat.py              # 중간 인증서 누락·옛 암호화 사이트 대응 (검증은 유지)
│   ├── certs/intermediates.pem    # 서버가 안 보내는 중간 인증서 5개 (tls_compat.py가 사용)
│   ├── eminwon.py                 # 새올 고시공고 공통 파서 (경기용, 파이프라인 미연결 — dry-run만)
│   ├── requirements.txt           # Python 패키지
│   ├── requirements-dev.txt       # 테스트 전용 (pytest, 배포 제외)
│   ├── pytest.ini                 # 테스트 설정
│   ├── tests/                     # 백엔드 테스트 (2026-11-18, 배포 제외)
│   └── .env.yaml                  # 환경변수 (gitignore — API 키)
│
├── frontend/
│   ├── lib/
│   │   ├── main.dart              # 앱 진입점, 3탭 스캐폴드, FCM 딥링크
│   │   ├── regions.dart           # 지역 목록 (서울 25·경기 31) — 지역을 다루는 모든 곳의 기준 (v1.5)
│   │   ├── theme.dart             # SeniorTheme (전역 디자인 토큰)
│   │   ├── models/
│   │   │   └── welfare_notice.dart  # Firestore 데이터 모델
│   │   ├── screens/
│   │   │   ├── home_screen.dart       # 홈(속보) 탭 — 내 지역 + [내 지역][전체][복지로] 칩 + 찜 버튼
│   │   │   ├── region_picker_screen.dart # 내 지역 고르기 — 시·도 버튼 → 시·군·구 타일 (v1.5)
│   │   │   ├── fortune_screen.dart    # 오늘의 운세 — 띠·년생 고르기, 운세, 알림 질문, 광고 (v1.6)
│   │   │   ├── bookmarks_screen.dart  # 찜한 공고 탭 — SharedPreferences + Firestore 조회
│   │   │   ├── settings_screen.dart   # 설정 탭 — 내 지역 + 복지로 알림 + 알림 ON/OFF
│   │   │   └── webview_screen.dart    # 공고 상세 — InApp WebView + AdMob
│   │   ├── widgets/
│   │   │   └── notice_card.dart     # 공고 카드 + 광고 플레이스홀더
│   │   └── services/
│   │       ├── fcm_service.dart     # FCM 초기화, 토픽 구독 관리
│   │       ├── region_prefs.dart    # 내 지역 설정 (홈·찜·알림 공용, v1.5)
│   │       ├── fortune_prefs.dart   # 띠·년생(기기에만)·운세 알림 설정, 오늘 운세 문서 읽기 (v1.6)
│   │       └── analytics_service.dart # Firebase Analytics 이벤트 5가지 — 띠·년생은 넣지 않음 (v1.6)
│   └── pubspec.yaml
│
├── docs/                          # 작업 인계, 경기도 확장 조사 (gyeonggi/)
├── launchd/                       # 맥 로컬 수집 launchd plist 원본 (~/Library/LaunchAgents에 링크)
├── logs/                          # 로컬 수집 로그 (git 제외)
├── setup-cloud-scheduler.sh       # Cloud Scheduler gcloud CLI 등록 스크립트
├── .env                           # 로컬 환경변수 (gitignore)
├── .gitignore
├── CLAUDE.md                      # 작업 규칙·운영 메모
├── TODO.md                        # 작업 현황
├── figma.md                       # 초기 디자인 참고 (React 기준, 그대로 따르지 않음)
└── ARCHITECTURE.md                # 이 파일
```

---

## 7. 배포 현황 (2026-11-18 갱신)

| 항목 | 상태 | 비고 |
|------|------|------|
| Cloud Functions: `scraping_function` | ✅ 배포 완료 | asia-northeast3 |
| Cloud Functions: `notification_function` | ✅ 배포 완료 (2026-11-18 지역 코드 토픽) | asia-northeast3 |
| Cloud Functions: `health_check_function` | ✅ 배포 완료 (2026-11-16) | 10:00·19:00 KST 스케줄 |
| Cloud Monitoring 알림 정책 (HEALTH_ALERT → 이메일) | ✅ 설정 (2026-11-16) | 3.5 참고 |
| 맥 로컬 수집 (launchd `com.seniorwelfare.pipeline`) | ✅ 운영 (2026-11-16~) | CLAUDE.md "로컬 수집 실행" |
| Cloud Scheduler: `scraping-morning` (09:00 KST) | ⏸ PAUSED (2026-11-16, 맥 로컬 수집으로 전환) | Asia/Seoul |
| Cloud Scheduler: `scraping-evening` (18:00 KST) | ⏸ PAUSED (2026-11-16) | Asia/Seoul |
| Firestore Database | ✅ 생성 완료 | asia-northeast3 |
| Firestore 보안 규칙 | ✅ 배포 완료 | welfare_notices 읽기 허용 |
| Firestore 복합 인덱스 | ✅ 배포 완료 | source + timestamp, region + timestamp (2026-11-18) |
| AdMob 앱·광고단위 등록 | ✅ 완료 | 전면 `…/3253182704`, 배너 `홈목록_배너` `…/4679949677` (2026-11-18) |
| Firebase 앱 등록 (`com.seniorwelfare.senior_welfare_app`) | ✅ 완료 | google-services.json 적용 |
| Flutter 앱 (Android 에뮬레이터) | ✅ 정상 작동 확인 | Firestore 연동 확인 |
| Flutter 앱 (Android 실기기) | ✅ 확인 완료 | FCM·딥링크 정상 (2026-03-12) |
| Play 스토어 | v1.4.0+7 제출 (2026-09 기록상 '검토 중' — 게시 여부는 Play Console에서 확인) | v1.5.0+9(v1.4.1 포함) 내부 테스트 준비 (2026-11-18) |
| Flutter 앱 (iOS) | 🔲 미진행 | — |

---

## 8. 남은 작업

→ 상세 작업 현황은 `TODO.md` 참고 (2026-11-18 기준 주요 항목)

| 항목 | 비고 |
|------|------|
| v1.5.0+9 출시 (v1.4.1 포함) | Play 내부 테스트에서 지역 알림·꺼진 상태 알림 탭 확인 → 출시 → 맥 수집 `GYEONGGI=1` |
| 경기 남은 출처 | 추가 확인 33곳 + 기흥(목록 날짜 암호화) (`docs/gyeonggi/gyeonggi_centers.yaml`) |
| 보안 보강 | 함수 전용 서비스 계정, 앱 Android 키 제한, App Check (`docs/보안-비용-점검-2026-11-17.md`) |
| 운세 기능 (v1.6) | `v1.6-fortune` 브랜치에 구현·테스트 완료 (2026-11-19). 문장 검토 → 함수·규칙 배포 → 개인정보처리방침·Play 데이터 보안 → 출시 (TODO.md) |

---

## 9. 환경변수

| 변수명 | 위치 | 용도 |
|--------|------|------|
| `GEMINI_API_KEY` | `.env`, `backend/.env.yaml` | Gemini AI 요약 API |
| `DATA_GO_KR_KEY` | `.env`, `backend/.env.yaml` | 복지로 공공 DATA API |
| `ADMOB_INTERSTITIAL_ID` | Flutter `--dart-define` | AdMob 전면 광고 ID |
| `LLM_PROVIDER` | 실행 환경 | `gemini`(기본) / `ollama` — AI 판정에 쓸 모델 |
| `OLLAMA_MODEL`, `OLLAMA_URL` | 실행 환경 | 기본 `qwen2.5:14b`, `http://localhost:11434` |
| `SILENT_SAVE` | 실행 환경 | `1`이면 알림 없이 저장 (밀린 공고 처리용) |
| `GYEONGGI` | 실행 환경 | `1`이면 경기 52기관도 수집 (v1.5 앱 출시 때 launchd plist에 추가) |
| `GOOGLE_CLOUD_PROJECT` | 로컬 실행 | `senior-welfare-app` — 로컬에서 Firestore 접속 시 프로젝트 지정 |

> **주의:** `.env`, `backend/.env.yaml`은 `.gitignore`에 등록되어 있음
