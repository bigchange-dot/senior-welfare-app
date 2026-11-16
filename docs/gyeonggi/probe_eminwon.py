"""경기도 31개 시·군 새올(eminwon) 고시공고 목록 접근 가능 여부 점검.

사용법 (Mac. 시스템 python3에는 requests가 없으므로 backend venv를 쓴다):
    cd docs/gyeonggi
    ../../backend/venv/bin/python probe_eminwon.py gyeonggi_sources.yaml

결과: 시·군별로 접근 결과, 목록 행 수, 첫 행을 출력.
- eminwon: none 인 곳은 homepage_list(홈페이지 목록)를 대신 점검한다.
- eminwon_base, tls(legacy/chain) 설정은 yaml 머리말 참고. 인증서 검증은 끄지 않는다.
봇 차단(403, 캡차)이 나오는 곳은 우회하지 말고 목록에서 제외할 것.
"""
import re
import ssl
import sys
import tempfile
import time
from urllib.parse import urlparse

import certifi
import requests
import yaml
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

HEADERS = {"User-Agent": "Mozilla/5.0 (senior-welfare-app probe)"}

# 새올 고시공고 목록 경로 (2026-11-16 점검: 새올을 쓰는 30개 시·군 공통)
LIST_PATH = (
    "/emwp/gov/mogaha/ntis/web/ofr/action/OfrAction.do"
    "?jndinm=OfrNotAncmtEJB&context=NTIS&method=selectListOfrNotAncmt"
    "&methodnm=selectListOfrNotAncmtHomepage&homepage_pbs_yn=Y&subCheck=Y"
    "&ofr_pageSize=10&not_ancmt_se_code={codes}&initValue=Y&countYn=Y&epcCheck=Y"
)

# 새올 목록 행에는 템플릿과 관계없이 searchDetail('공고관리번호')가 들어 있다
# (a href, a onclick, td onclick 중 한 곳). tbody 유무·칸 수는 시·군마다 다르다.
DETAIL_RE = re.compile(r"searchDetail\(\s*'(\d+)'")
# 홈페이지 목록 폴백용: 고시공고번호("○○시 공고 제2026-123호")가 있는 행
NOTICE_NO_RE = re.compile(r"공고\s*제\s*\d{4}")


class LegacyTLSAdapter(HTTPAdapter):
    """옛 암호화 방식만 지원하는 서버용 (tls: legacy). 인증서 검증은 그대로 한다."""

    def __init__(self, ciphers: str, **kwargs):
        self._ciphers = ciphers
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.set_ciphers(self._ciphers)
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


def build_ca_bundle(cert_urls: list[str]) -> str:
    """certifi 루트 인증서 + 중간 인증서(tls: chain용)를 합친 임시 번들 경로를 돌려준다."""
    with open(certifi.where(), encoding="ascii") as f:
        parts = [f.read()]
    for url in cert_urls:
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.raise_for_status()
        body = res.content
        parts.append(body.decode("ascii") if body.startswith(b"-----BEGIN") else ssl.DER_cert_to_PEM_cert(body))
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False, encoding="ascii") as f:
        f.write("\n".join(parts))
        return f.name


def is_eminwon_row(tr) -> bool:
    return bool(DETAIL_RE.search(str(tr)))


def is_notice_row(tr) -> bool:
    return bool(NOTICE_NO_RE.search(tr.get_text(" ", strip=True)))


def probe(session: requests.Session, url: str, ca_bundle: str, is_row) -> tuple[str, list[str]]:
    try:
        res = session.get(url, timeout=15, verify=ca_bundle)
    except requests.RequestException as e:
        return f"ERR {type(e).__name__}", []
    if res.status_code != 200:
        return f"HTTP {res.status_code}", []
    # 새올은 EUC-KR 페이지가 섞여 있음
    res.encoding = res.apparent_encoding or "utf-8"
    soup = BeautifulSoup(res.text, "lxml")
    # 안쪽에 표가 또 있는 바깥 행은 빼고, 실제 목록 행만 센다
    rows = [tr for tr in soup.find_all("tr") if not tr.find("tr") and is_row(tr)]
    if not rows:
        return "목록 없음", []
    return "OK", [tr.get_text(" ", strip=True) for tr in rows]


def main(path: str) -> None:
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    defaults = cfg["defaults"]
    tls_cfg = cfg.get("tls", {})
    codes = "%2C".join(defaults["se_codes"])
    ca_bundle = build_ca_bundle(tls_cfg.get("intermediate_certs", []))

    ok = 0
    for c in cfg["cities"]:
        session = requests.Session()
        session.headers.update(HEADERS)
        if c.get("tls") == "legacy":
            session.mount("https://", LegacyTLSAdapter(tls_cfg["legacy_ciphers"]))

        if c.get("eminwon") == "none":
            url, is_row, kind = c["homepage_list"], is_notice_row, "폴백"
        else:
            base = c.get("eminwon_base") or defaults["eminwon_base"].format(domain=c["domain"])
            url, is_row, kind = base + LIST_PATH.format(codes=codes), is_eminwon_row, "새올"

        status, titles = probe(session, url, ca_bundle, is_row)
        ok += status == "OK"
        tag = f"{kind}{'/' + c['tls'] if c.get('tls') else ''}"
        first = titles[0][:60] if titles else ""
        print(f"{c['name']:<6} {urlparse(url).netloc:<24} {tag:<10} {status:<12} {len(titles):>3}행  {first}")
        time.sleep(1)  # 사이트 부담 최소화

    print(f"\n{ok}/{len(cfg['cities'])}곳 목록 확인")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "gyeonggi_sources.yaml")
