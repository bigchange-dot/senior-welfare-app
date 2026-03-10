// firebase_options.dart — flutterfire configure 대신 수동 생성
// google-services.json 기반으로 작성됨
import 'package:firebase_core/firebase_core.dart' show FirebaseOptions;
import 'package:flutter/foundation.dart' show defaultTargetPlatform, TargetPlatform;

class DefaultFirebaseOptions {
  static FirebaseOptions get currentPlatform {
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return android;
      case TargetPlatform.iOS:
        return ios;
      default:
        return android;
    }
  }

  static const FirebaseOptions android = FirebaseOptions(
    apiKey:            'AIzaSyA5T6w5z6CtRLFvsPTtB4HbO6aXLF4ndA0',
    appId:             '1:981112915862:android:59372a0f4df2639fefffb7',
    messagingSenderId: '981112915862',
    projectId:         'senior-welfare-app',
    storageBucket:     'senior-welfare-app.firebasestorage.app',
  );

  // iOS 설정이 생기면 GoogleService-Info.plist 값으로 교체
  static const FirebaseOptions ios = FirebaseOptions(
    apiKey:            'AIzaSyA5T6w5z6CtRLFvsPTtB4HbO6aXLF4ndA0',
    appId:             '1:981112915862:ios:000000000000000000000000',
    messagingSenderId: '981112915862',
    projectId:         'senior-welfare-app',
    storageBucket:     'senior-welfare-app.firebasestorage.app',
    iosClientId:       '',
    iosBundleId:       'com.seniorwelfare.seniorWelfareApp',
  );
}
