"""
Cloud Functions(Cloud Run) 로깅 설정.

문제: Functions 런타임이 루트 로거를 WARNING 레벨로 잡아 logger.info()가
Cloud Logging에 올라가지 않았음 (오류만 보임). 또한 stderr 평문 로그는
severity가 비어 필터링이 안 됨.

해결: Cloud Run은 stdout의 JSON 한 줄을 구조화 로그로 파싱하므로
{"severity": ..., "message": ...} 형식으로 출력. 로컬 실행(K_SERVICE 없음)은
사람이 읽기 쉬운 평문 유지.
"""

import json
import logging
import os
import sys


class _CloudJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "severity": record.levelname,
            "message":  record.getMessage(),
            "logger":   record.name,
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def configure_logging() -> None:
    """루트 로거를 INFO로 강제하고 핸들러를 교체 (여러 번 호출해도 안전)."""
    root = logging.getLogger()
    if getattr(root, "_senior_welfare_configured", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    if os.getenv("K_SERVICE"):  # Cloud Run/Functions 환경
        handler.setFormatter(_CloudJsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    root._senior_welfare_configured = True
