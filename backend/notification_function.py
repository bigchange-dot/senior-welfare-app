"""
Track B: Firestore onCreate 트리거 → FCM 푸시 알림 발송
welfare_notices 컬렉션에 새 문서가 생성될 때마다 자동 실행됩니다.
"""

import logging
import os

import firebase_admin
from firebase_admin import credentials, firestore, messaging
from dotenv import load_dotenv

# 로컬 실행 시 .env 로드
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Firebase Admin 초기화 (이미 초기화된 경우 재사용)
if not firebase_admin._apps:
    firebase_admin.initialize_app()

# 지연 초기화 — 배포 타임아웃 방지
_db = None

def _get_db():
    global _db
    if _db is None:
        _db = firestore.client()
    return _db

# 출처별 FCM 토픽 매핑
SOURCE_TOPIC_MAP = {
    "복지로":             "bokjiro",
    "성동구청":           "seongdong",
    "성동구 어르신일자리": "seongdong",
    "강북구청":           "gangbuk",
}


def send_notification_for_doc(doc_id: str, doc_data: dict) -> bool:
    """
    특정 문서의 데이터로 FCM 푸시 알림을 발송합니다.
    전체 구독자(/topics/all) + 지역 구독자(/topics/{region}) 동시 발송.
    """
    source      = doc_data.get("source",     "복지 알림")
    ai_summary  = doc_data.get("ai_summary", "새 공고가 등록되었습니다.")
    url         = doc_data.get("url",        "")
    title_orig  = doc_data.get("title",      "")

    # 알림 제목/본문 구성
    notif_title = f"[{source}] 새 소식 도착! 📢"
    notif_body  = ai_summary

    # FCM 데이터 페이로드 (Deep Linking용)
    data_payload = {
        "doc_id": doc_id,
        "url":    url,
        "source": source,
    }

    # 발송할 토픽 목록 (전체 + 지역별)
    topics = ["all"]
    region_topic = SOURCE_TOPIC_MAP.get(source)
    if region_topic:
        topics.append(region_topic)

    success = True
    for topic in topics:
        try:
            message = messaging.Message(
                notification=messaging.Notification(
                    title=notif_title,
                    body=notif_body,
                ),
                data=data_payload,
                topic=topic,
                android=messaging.AndroidConfig(
                    priority="high",
                    notification=messaging.AndroidNotification(
                        icon="ic_notification",
                        color="#0056B3",  # figma.md Primary Blue
                        channel_id="welfare_alerts",
                    ),
                ),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            sound="default",
                            badge=1,
                        )
                    )
                ),
            )
            response = messaging.send(message)
            logger.info(f"📨 FCM 발송 성공 [topic={topic}]: {response}")

        except Exception as e:
            logger.error(f"❌ FCM 발송 실패 [topic={topic}]: {e}")
            success = False

    return success


def update_is_notified(doc_id: str, status: bool = True):
    """알림 발송 완료 후 is_notified 플래그 업데이트."""
    try:
        _get_db().collection("welfare_notices").document(doc_id).update({
            "is_notified": status
        })
        logger.info(f"🔄 is_notified 업데이트: {doc_id} → {status}")
    except Exception as e:
        logger.error(f"❌ is_notified 업데이트 실패: {e}")


def process_new_document(doc_id: str, doc_data: dict):
    """새 문서 생성 시 호출되는 핵심 로직."""
    logger.info(f"🔔 새 문서 감지: {doc_id} | 출처: {doc_data.get('source')}")

    # 이미 알림 발송된 문서 중복 발송 방지
    if doc_data.get("is_notified", False):
        logger.info("⏭️  이미 알림 발송된 문서, 스킵")
        return

    # FCM 발송
    success = send_notification_for_doc(doc_id, doc_data)

    # 발송 상태 업데이트
    update_is_notified(doc_id, success)


# ─────────────────────────────────────────────
# Firebase Cloud Functions 트리거 핸들러
# (main.py에서 import 후 등록)
# ─────────────────────────────────────────────
def on_welfare_notice_created(event):
    """
    Firestore onCreate 트리거 핸들러.
    welfare_notices/{docId} 에 새 문서 생성 시 자동 호출.
    """
    try:
        doc_id   = event.params.get("docId", "unknown")
        doc_data = event.data.to_dict() if event.data else {}
        process_new_document(doc_id, doc_data)
    except Exception as e:
        logger.error(f"❌ 트리거 핸들러 오류: {e}")


# ─────────────────────────────────────────────
# 로컬 테스트용 직접 실행
# ─────────────────────────────────────────────
if __name__ == "__main__":
    # 수동 테스트: Firestore에서 미발송 문서 1건 찾아 발송
    query = (
        _get_db().collection("welfare_notices")
        .where("is_notified", "==", False)
        .limit(1)
        .stream()
    )
    for doc in query:
        print(f"테스트 발송: {doc.id}")
        process_new_document(doc.id, doc.to_dict())
        break
    else:
        print("테스트용 미발송 문서 없음. Firestore에 데이터를 먼저 추가하세요.")
