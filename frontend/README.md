# 우리동네 복지 알림 — Flutter 앱

노인 복지·일자리 공고를 자동 수집하여 AI 요약 후 FCM 푸시로 전달하는 앱.

## 개발 환경

- Flutter 3.x
- Dart
- Firebase (Firestore, FCM, Analytics)
- Google AdMob

## 실행 방법

```bash
cd frontend
flutter pub get
flutter run
```

## 에뮬레이터 디버그 (ADB)

```bash
export PATH="/c/Users/chae/AppData/Local/Android/Sdk/platform-tools:$PATH"
adb devices
adb logcat -c && adb logcat AndroidRuntime:E flutter:V *:S
```

## 주요 파일

| 파일 | 역할 |
|------|------|
| `lib/main.dart` | 앱 진입점, Firebase 초기화, 3탭 스캐폴드 |
| `lib/firebase_options.dart` | Firebase 초기화 옵션 (수동 작성) |
| `lib/theme.dart` | SeniorTheme 전역 디자인 토큰 |
| `lib/screens/home_screen.dart` | 홈(속보) 탭 — 필터 칩 + Firestore 실시간 스트림 |
| `lib/screens/webview_screen.dart` | 공고 상세 — InApp WebView + AdMob Interstitial |
| `lib/screens/my_region_screen.dart` | 내 지역 탭 |
| `lib/screens/settings_screen.dart` | 설정 탭 — 지역 선택, 알림 ON/OFF |
| `lib/widgets/notice_card.dart` | 공고 카드 위젯 |
| `lib/services/fcm_service.dart` | FCM 초기화 및 토픽 구독 관리 |
| `lib/models/welfare_notice.dart` | Firestore 데이터 모델 |

## Android 설정

- `android/app/google-services.json` — Firebase 설정 (패키지명: `com.seniorwelfare.senior_welfare_app`)
- `android/app/src/main/AndroidManifest.xml` — AdMob App ID 포함
- AdMob 테스트 App ID: `ca-app-pub-3940256099942544~3347511713` (출시 전 실제 ID 교체 필요)

## 출시 전 체크리스트

- [ ] AdMob 실제 App ID 및 광고단위 ID 교체
- [ ] Firebase 콘솔에서 패키지명 `com.seniorwelfare.senior_welfare_app`으로 앱 재등록
- [ ] GoogleService-Info.plist 추가 (iOS)
- [ ] 릴리즈 서명 키 설정 (`key.jks`)
