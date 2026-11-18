package com.seniorwelfare.senior_welfare_app

import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import android.os.Bundle
import io.flutter.embedding.android.FlutterActivity

class MainActivity : FlutterActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        createNotificationChannels()
    }

    /**
     * 알림 채널 (2026-11-19). 서버는 공고 알림을 channel_id="welfare_alerts"로 보내지만 앱이 이 채널을
     * 만들지 않아 안드로이드 기본 '기타' 채널(중요도 보통, 화면 위 팝업 없음)로 들어가고 있었다 (태블릿에서 확인).
     * 중요도 높음으로 만들어 새 공고가 화면 위에 잠깐 뜨게 한다. 이미 있으면 아무 일도 하지 않는다.
     */
    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java) ?: return
        val notices = NotificationChannel(
            "welfare_alerts", "복지 공고 알림", NotificationManager.IMPORTANCE_HIGH
        ).apply { description = "내 지역 새 복지 공고" }
        manager.createNotificationChannel(notices)
    }
}
