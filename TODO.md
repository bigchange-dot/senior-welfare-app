# Senior Welfare App — 작업 현황

> 마지막 업데이트: 2026-03-16 (v1.1.3)
> 앱 버전: 1.1.0+2

---

## ✅ 완료된 작업

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

- 없음 (현재 대기 중)

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
- [x] Google Play 개발자 계정 등록 ($25 결제 완료, 본인확인 대기 중, 2026-03-16)
- [ ] Play Console 앱 등록 및 스토어 등록 정보 입력 (본인확인 완료 후)
- [ ] 내부 테스트 트랙 업로드 및 테스트
- [ ] App Check 적용 (플레이스토어 등록 후 — Firestore 무단 접근 차단)
- [ ] Google Cloud 예산 알림 설정 (비용 폭탄 방지)

### 검토 사항
- [ ] Gemini API 무료 할당량 확인 (사용자 증가 시)
- [ ] data.go.kr API 일일 호출 한도 확인
- [ ] Firestore 보안 규칙 강화 (App Check 연동 후)
