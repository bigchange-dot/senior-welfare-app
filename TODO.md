# Senior Welfare App — 작업 현황

> 마지막 업데이트: 2026-04-29 (v1.3.1+6 게시 완료)
> 앱 버전: 1.3.1+6

---

## ✅ 완료된 작업

### v1.3.1+6 — 2026-04-21 (HTTP WebView 수정 + 광고 재활성화)
- [x] HTTP cleartext 도메인 화이트리스트 추가 (`network_security_config.xml` 신규)
  - 약수노인복지관 (`yssenior.co.kr`), 서대문노인복지관 (`sdmsenior.or.kr`), 은평구청 (`ep.go.kr`)
  - `AndroidManifest.xml`에 `android:networkSecurityConfig="@xml/network_security_config"` 추가
  - 원인: Android 9(API 28)+는 기본적으로 HTTP 차단 → WebView 로드 실패
- [x] AdMob Interstitial 광고 재활성화 (`webview_screen.dart` `_loadInterstitialAd()` 조기 return 제거)
- [x] `pubspec.yaml` 버전 1.3.0+5 → 1.3.1+6 (PATCH 버전업, 버그 수정 릴리스)
- [x] `flutter build appbundle --release` 성공 (44.4MB)
- [x] Play Console 프로덕션 트랙 AAB 업로드 및 변경사항 전송 (관리형 게시 ON 상태)
- [x] Play Console "앱 콘텐츠 → 광고 포함 = 예" 선언
- [x] Google 검토 통과 및 게시 완료 (2026-04-29)
- [ ] 실기기 테스트: 약수/서대문/은평 WebView 정상 로드 + 인터스티셜 광고 노출 확인

### 2026-04-14~18 — Play Console 프로덕션 출시
- [x] 비공개 테스트 14일 이상, 12명 이상 테스터 요건 충족 확인
- [x] 프로덕션 액세스 권한 신청 설문 작성 및 제출 (2026-04-14)
- [x] Google 프로덕션 액세스 승인 (2026-04-18)
- [x] v1.3.0+5 프로덕션 트랙 출시 제출 → 전체 출시 100%, 대한민국 (2026-04-18)
- [x] Google 검토 통과 및 게시 완료 (시크릿 브라우저 확인)

### v1.3.0+5 — 2026-04-09 ~ 2026-04-10
- [x] 구청 4곳 신규 추가: **종로구청, 중구청, 용산구청, 서대문구청**
  - 각 구청별 커스텀 스크래퍼 구현
    - 종로: `viewMove('id')` 정규식 → `selectBoardArticle.do` URL 조합
    - 중구: Seoul 표준 board (`cmsid=15450`)
    - 용산: Seoul 표준 board (`B0000095`)
    - 서대문: `goView('id')` 정규식 → `mode=view&sdmBoardSeq` URL (EUC-KR 자동감지)
- [x] 노인복지관 4곳 추가: 종로, 약수(중구), 용산, 서대문
  - 종로: G5 board `verify_ssl=False` (SSL 인증서 만료)
  - 약수: G5 `http://www.yssenior.co.kr`
  - 용산: G5 `https://www.ysnoin.or.kr/bbs/board.php?bo_table=0101`
  - 서대문: anyboard 패턴 + `num=` dedup
  - 중구노인복지관은 zipEncode JS 동적 URL이라 포기 → 약수로 대체
- [x] `_scrape_g5_board()` **기존 버그 수정** (프로덕션 4개 복지관 영향)
  - 콤마 셀렉터가 `<a class="bo_cate_link">카테고리</a>`를 먼저 매치하는 문제
  - 순차 `or` 폴백으로 변경 (`a[href*="wr_id="]` 우선)
- [x] `max_workers` 11 → 19 (신규 8개 스크래퍼 대응)
- [x] **Cloud Functions 타임아웃 버그 수정** (6일간 파이프라인 중단 원인)
  - `main.py`: `timeout_sec` 540 → 1800 (Gemini sleep 누적 초과)
  - `scraping_function.py`: `SENIOR_KEYWORDS` 프리필터 추가
    - 구청 출처는 제목에 노인 키워드 없으면 Gemini 호출 스킵
    - 복지관 출처는 `WELFARE_CENTER_SOURCES` 기준 그대로 통과
- [x] **Cloud Scheduler 설정 수정**
  - morning/evening `attemptDeadline=1800s` (기본 180s 초과로 인한 실패 방지)
  - evening 잘못된 설정 바로잡음: `0 9 * * * UTC` → `0 18 * * * Asia/Seoul`
  - morning cron `0 0 * * *` → `0 9 * * *` (사용자 수정)
- [x] `theme.dart` 배지 색상 확장: 성동/강북 2개 → **11개 구청 + 복지로**
  - 복지관은 소속 구청과 동일 색상 매핑 (수락→노원, 약수→중구 등)
- [x] `home_screen.dart` `_filters` 13개로 확장 (종로/중구/용산/서대문 추가)
- [x] `settings_screen.dart` `_regions` 13개로 확장 + FCM 토픽 매핑
- [x] `notification_function.py` `SOURCE_TOPIC_MAP`에 신규 8개 매핑 추가
- [x] `flutter build appbundle --release` 성공 (44.4MB, v1.3.0+5)
- [ ] Play Console 내부 테스트 트랙 업로드 (사용자 작업 대기)

### v1.2.0 — 2026-03-30
- [x] 은평노인복지관 인코딩 버그 수정 (`res.encoding = 'utf-8'` 명시)
  - 기존 저장된 깨진 데이터 10건 Firestore에서 삭제 후 재수집
- [x] 홈 화면 이모지 폰트 깨짐 수정 (`theme.dart` fontFamily 강제 지정 제거)
- [x] 홈 화면 `_selectedSource` 잔존 참조 컴파일 오류 수정
- [x] `flutter build appbundle --release` 성공 (44.4MB, v1.2.0+3)
- [x] Play Console 비공개 테스트 트랙 AAB 업로드 준비 완료

### v1.1.4 — 2026-03-28
- [x] 노인복지관 4개 스크래핑 추가
  - 수락노인복지관(노원), 마포노인복지관, 도봉노인복지관, 은평노인복지관
  - `_scrape_g5_board()` G5 BBS 공통 헬퍼 추가
  - 마포: `data-wr-id` 속성으로 URL 조합하는 커스텀 파서
  - 은평: `a[href*="Mode=view"]` anyboard 셀렉터
  - 접속 불가 3개 제외: 신내(SSL 오류), 노원노인복지관(게시판 없음), 강북복지관(403)
- [x] Gemini 프롬프트 — 복지관 출처 맥락 추가로 SKIP 비율 완화
  - `WELFARE_CENTER_SOURCES` 집합 정의
  - 복지관 출처일 때 프로그램·여가·교육 모집도 PASS 처리
  - 행정·회계 공고는 여전히 SKIP
- [x] `summarize_with_gemini()` — `source` 파라미터 추가
- [x] Gemini `PASS:` 접두어 버그 수정 (Firestore 기존 3건 직접 수정)
- [x] 홈 필터 칩 — 구청 칩에 복지관 데이터 통합 (`whereIn` 쿼리)
  - `_FilterChipData.source` → `sources: List<String>` 변경
  - 필터 칩 9개 유지 (별도 복지관 칩 없음)
- [x] Cloud Functions 재배포 (scraping_function, notification_function)
- [x] 파이프라인 결과: 수집 170건 → 저장 22건 (기존 0건에서 개선)

### v1.1.3 — 2026-03-17
- [x] Gemini 할루시네이션 방지 및 구청 공고 본문 fetch 추가
  - `fetch_detail_content()` 추가 — 구청 상세 페이지 본문 300자 추출 후 Gemini 전달
  - Gemini 프롬프트 개선 — 직원·강사·지도사 채용 SKIP 명시, 없는 단어 추가 금지
  - 파이프라인: 구청 공고 content 없으면 자동 fetch
  - 결과: 저장 건수 92건 → 23건 (불필요 공고 대폭 감소)
- [x] `scraping_function` Cloud Functions 재배포 (00007 revision)
- [x] Firestore 전체 초기화 후 재스크래핑 (23건 저장)
- [x] 테스트 기간 광고 비활성화 (`webview_screen.dart` — 출시 전 재활성화 필요)
- [x] 스토어 자산 준비
  - 스크린샷 4장 캡처 (홈/찜/내지역공고/설정)
  - 앱 아이콘 512×512 (`store-assets/icon_512.png`)
  - 피처드 이미지 1024×500 (`store-assets/featured_1024x500.png`)
- [x] Google Play 개발자 계정 등록 ($25 결제 완료, 본인확인 대기 중, 2026-03-17)
- [x] 테스트용 APK 빌드 (47.2MB, 광고 비활성화)

### v1.1.2 — 2026-03-13
- [x] 알림 토글 즉시 반응 버그 수정 (`_toggleNotif` 낙관적 업데이트 적용)
- [x] 앱 정보 섹션 간소화 (데이터 항목 제거, AI 요약 → 'Gemini'만 표시)
- [x] 개인정보처리방침 작성 및 GitHub Pages 호스팅
  - URL: https://bigchange-dot.github.io/senior-welfare-app/privacy-policy.html
- [x] 저장소 public 전환 전 보안 검사
  - `google-services.json` 전체 git 이력에서 제거 (filter-branch)
  - 저장소 public 전환 완료
  - GitHub Pages 활성화 완료

### v1.1.1 — 2026-03-13
- [x] 설정탭 지역 선택 단일 → 복수 선택 (최대 3개) 변경
  - `radio_button` 아이콘 → `check_box` 아이콘 (다중 선택 UI)
  - `selected_source`(String) → `selected_sources`(StringList) SharedPreferences 변경
  - 찜 탭 지역 공고: `isEqualTo` → `whereIn` 쿼리 (복수 지역 합산 표시)
  - `X/3 선택` 카운트 배지 표시
- [x] 홈 필터 칩 배경색 수정 (흰색 배경 → 투명, 테두리만 표시)
- [x] 앱 이름 변경: `senior_welfare_app` → `어르신 알리미` (AndroidManifest.xml)
- [x] 설정 지역 선택 즉시 반응 (낙관적 업데이트 — FCM 호출 전 setState 먼저)
- [x] 푸시알림 ON/OFF 버그 수정 (`_selectedTopic` → `_selectedTopics` 참조 오류)
- [x] Kotlin 증분 컴파일 오류 수정 (`kotlin.incremental=false`, gradle.properties)
  - 원인: D드라이브 프로젝트 + C드라이브 Pub캐시 간 다른 루트 경로
- [x] 앱 아이콘 제작 및 적용 (Android mipmap-*/drawable-* 전 해상도, iOS AppIcon.appiconset 전 해상도)
  - Android: mipmap-anydpi-v26 (adaptive icon) 포함, colors.xml 추가
  - 1024×1024 마스터 아이콘 생성 (`senior-welfare-app-icon.png`)

### v1.1 — 2026-03-12
- [x] AppBar 타이틀 `홈 (속보)` → `어르신 알리미` 변경
- [x] 서울 5개 구청 스크래핑 추가 (노원·도봉·중랑·마포·은평)
- [x] `_scrape_seoul_board()` 공통 헬퍼 함수 추가
- [x] FCM 토픽 매핑 5개 추가 (nowon·dobong·jungnang·mapo·eunpyeong)
- [x] 홈 필터 칩 9개로 확장
- [x] 설정 화면 지역 목록 9개로 확장
- [x] 찜 탭 — 상단: 찜한 공고 / 하단: 내 지역 공고로 개편
- [x] 구청별 실제 게시판 URL 검증 및 수정
  - 노원구청: `opView('ID')` JS 링크 → 상세 URL 직접 생성 (10건 수집 ✅)
  - 도봉구청: 채용공고 동적 로딩 불가 → 공지사항으로 대체 (10건 수집 ✅)
  - 은평구청: https 타임아웃 → http로 전환, `./` 상대경로 처리 추가 (10건 수집 ✅)
  - 중랑·마포: URL 정상 확인 (각 10건 수집 ✅)
- [x] 스크래핑 총 수집 110건 달성 (기존 80건 → 110건)

### 프론트엔드 / 광고
- [x] AdMob 콘솔 앱·광고단위 등록 및 실제 ID 적용 (`ca-app-pub-5634467403173492/3253182704`)
- [x] Firebase 콘솔 앱 재등록 (`com.seniorwelfare.senior_welfare_app`) 및 `google-services.json` 교체

### 인프라 / 백엔드
- [x] Cloud Functions 배포 — `scraping_function` (스크래핑 + AI 요약 + Firestore 저장)
- [x] Cloud Functions 배포 — `notification_function` (FCM 푸시 발송)
- [x] Cloud Scheduler 등록 — 09:00 / 18:00 KST 자동 실행
- [x] Firestore 생성 및 보안 규칙 배포
- [x] Firestore 복합 인덱스 배포 (source + timestamp)

### 프론트엔드
- [x] Flutter 앱 기본 구조 (3탭: 홈/즐겨찾기/설정) — 내지역 탭을 즐겨찾기로 변경
- [x] Firestore 연동 (공고 목록 조회)
- [x] FCM 푸시 알림 수신 및 딥링크 처리
- [x] AdMob Interstitial 광고 (뒤로가기 시 노출)
- [x] Android 에뮬레이터 정상 작동 확인

### 보안
- [x] Firebase API 키 유출 대응 (2026-03-11)
  - 구 키 삭제, 신 키 발급 
  - `firebase_options.dart` gitignore 처리
  - `firebase_options.dart.example` 템플릿 추가

---

## 🔄 진행 중인 작업

- 실기기 회귀 테스트 (약수/서대문/은평 WebView + 인터스티셜 광고)

---

## 📋 추후 진행 작업

### 높은 우선순위
- [x] 실기기(Android)에서 FCM 푸시 수신 및 딥링크 확인 (2026-03-12 태블릿 테스트 완료)
- [x] Firestore `snapshots()` → `get()` 전환 (비용 최적화 — 읽기 90% 절감, 2026-03-12 완료)

### 중간 우선순위
- [x] 복지로 API 엔드포인트 수정 (`NationalWelfareInformationsV001/NationalWelfarelistV001`, 20건 수집 확인, 2026-03-12 완료)
- [ ] iOS 빌드 및 테스트 (GoogleService-Info.plist 등록 필요)
- [x] 앱 아이콘 제작 (Android/iOS 전 해상도 적용 완료, 2026-03-13)
- [ ] 스플래시 스크린 제작

### 출시 준비
- [x] 릴리즈 키스토어 생성 (`upload-keystore.jks`, alias=upload, 2026-03-12 완료)
- [x] build.gradle.kts 서명 설정 완료 (2026-03-12)
- [x] 릴리즈 SHA-256 Firebase Console 등록 완료 (2026-03-12)
- [x] `flutter build apk --release` 성공 (46.7MB, 2026-03-12)
- [x] `flutter build appbundle --release` 성공 (44.4MB, 2026-03-13)
  - 해결 과정: cmdline-tools 설치 → 라이선스 수락 → `debugSymbolLevel = "SYMBOL_TABLE"` 설정
  - 원인: `debugSymbolLevel = "NONE"` 설정 시 `.so.sym` 파일 미생성 → Flutter 검증 실패
  - 추가 설정: `kotlin.incremental=false` (D드라이브 프로젝트 + C드라이브 Pub캐시 경로 충돌 방지)
- [x] 개인정보처리방침 작성 및 호스팅 (https://bigchange-dot.github.io/senior-welfare-app/privacy-policy.html, 2026-03-13)
- [x] 앱 아이콘 1024×1024 준비 (`senior-welfare-app-icon.png`, 2026-03-13)
- [x] 스토어 등록 정보 초안 작성 (설명 문구, 스크린샷, 아이콘, 피처드 이미지 준비 완료, 2026-03-16)
- [x] Google Play 개발자 계정 등록 ($25 결제 완료, 2026-03-16)
- [x] Google Play 개발자 본인인증 완료 (2026-03-19)
- [x] AAB 재빌드 (44.4MB, 2026-03-19)
- [x] Play Console 앱 등록 및 스토어 등록 정보 입력 (2026-03-19)
  - 앱 콘텐츠 정보 입력 완료 (개인정보처리방침, 광고 ID, 데이터 보안 등)
  - 카테고리: 도구
  - 스크린샷 4장, 아이콘, 피처드 이미지 업로드
- [x] 내부 테스트 트랙 AAB 업로드 및 검토 제출 (2026-03-19)
- [x] 내부 테스트 승인 후 기기 설치 확인
- [x] 비공개 테스트 (12명 이상, 14일 이상) — 정식 출시 전 필수
- [x] 프로덕션 액세스 권한 신청 설문 제출 (2026-04-14 21:50)
- [x] Google 프로덕션 액세스 승인 완료 (2026-04-18)
- [x] 프로덕션 트랙에 v1.3.0+5 AAB 출시 제출 — 전체 출시(100%), 대한민국 (2026-04-18)
- [x] v1.3.0+5 프로덕션 게시 완료 (시크릿 브라우저 검증)
- [x] 광고 재활성화 (v1.3.1+6, 2026-04-21)
- [x] Play Console "광고 포함" 선언 (2026-04-21)
- [x] v1.3.1+6 Google 검토 통과 및 게시 완료 (2026-04-29)
- [ ] AdMob ↔ Play Store 앱 연결 (3~7일 후, Play Store 인덱싱 완료 시점)
- [ ] AdMob 결제 정보 / 세금 정보 입력
- [ ] App Check 적용 (v1.3.2 예정 — Firebase Console Play Integrity 등록 선행)
- [ ] Google Cloud 예산 알림 설정 (월 $10, 50/90/100/120% 임계값)

### 검토 사항
- [ ] Gemini API 무료 할당량 확인 (사용자 증가 시)
- [ ] data.go.kr API 일일 호출 한도 확인
- [ ] Firestore 보안 규칙 강화 (App Check 연동 후)
