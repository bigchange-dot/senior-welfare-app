"""
보안 연결 예외 처리 (2026-11-16)

공공기관 사이트 중 일부는 서버 설정 문제로 Python 기본 설정에서 연결이 실패한다. 인증서 검증은 끄지 않고 맞춰 준다.

1. 중간 인증서 누락 — 서버가 중간 인증서를 보내지 않아 "unable to get local issuer certificate"
   (브라우저는 알아서 받아 오지만 Python은 그러지 않음)
   → certs/intermediates.pem을 certifi 루트 번들 뒤에 붙인 번들을 REQUESTS_CA_BUNDLE로 지정.
     requests는 verify=True(기본값)일 때 이 환경변수를 쓰므로 스크래퍼 코드를 고치지 않아도 된다.
   해당: 중구청, 성동구청 채용, (경기) 남양주·의정부
2. 옛 암호화 방식만 지원 — AES128-SHA 등 RSA 키교환만 받아 handshake 실패
   → LegacyTLSAdapter를 그 도메인 세션에만 붙인다 (SECLEVEL=1). 해당: (경기) 성남·이천·구리

중간 인증서 만료: GlobalSign GCC R6 AlphaSSL CA 2025는 2027-05-21 — 그 전에 사이트가 바꾼 인증서를 다시 확인할 것.
"""

import os
import tempfile

import certifi
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

INTERMEDIATES = os.path.join(os.path.dirname(__file__), "certs", "intermediates.pem")
LEGACY_CIPHERS = "DEFAULT:@SECLEVEL=1"

_bundle_path: str | None = None


def ca_bundle_path() -> str:
    """certifi 루트 + 중간 인증서를 합친 번들 파일 경로 (처음 부를 때 임시 폴더에 만든다)."""
    global _bundle_path
    if _bundle_path and os.path.exists(_bundle_path):
        return _bundle_path
    with open(certifi.where(), encoding="ascii") as f:
        roots = f.read()
    with open(INTERMEDIATES, encoding="utf-8") as f:
        extra = f.read()
    with tempfile.NamedTemporaryFile("w", suffix="-ca-bundle.pem", delete=False, encoding="utf-8") as f:
        f.write(roots + "\n" + extra)
        _bundle_path = f.name
    return _bundle_path


def install_ca_bundle() -> None:
    """이 프로세스의 requests 요청이 합친 번들로 검증하게 한다. 이미 지정돼 있으면 건드리지 않는다."""
    os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_bundle_path())


class LegacyTLSAdapter(HTTPAdapter):
    """옛 암호화 방식만 지원하는 서버용. session.mount("https://도메인", LegacyTLSAdapter())로 그 도메인에만 쓴다."""

    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.set_ciphers(LEGACY_CIPHERS)
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)
