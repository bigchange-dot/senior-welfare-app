"""범용 게시판 목록 파서 (board_parser.py, v1.5) — 실제 점검에서 본 목록 형태들로"""

from datetime import datetime

import board_parser as bp

TODAY = datetime(2026, 11, 18)


def test_표_형식_그누보드():
    html = """<table><tbody>
      <tr><td>12</td><td><a href="/bbs/board.php?bo_table=notice&wr_id=12">2027년 스마트폰 교실 참여자 모집</a></td><td>관리자</td><td>2026-11-17</td></tr>
      <tr><td>11</td><td><a href="/bbs/board.php?bo_table=notice&wr_id=11">11월 법률상담 안내</a></td><td>관리자</td><td>2026-11-02</td></tr>
    </tbody></table><a href="/intro">기관소개 바로가기</a>"""
    rows = bp.parse_list(html, "https://x.or.kr/bbs/board.php?bo_table=notice", TODAY)
    assert [t for t, _, _ in rows] == ["2027년 스마트폰 교실 참여자 모집", "11월 법률상담 안내"]
    assert rows[0][1] == "https://x.or.kr/bbs/board.php?bo_table=notice&wr_id=12"


def test_목록형_짧은_날짜와_월일만_있는_날짜():
    html = """<ul>
      <li><a href="v?no=3">경로식당 운영시간 변경 안내</a><span>26.11.16</span></li>
      <li><a href="v?no=2">겨울철 한파 대비 건강 수칙</a><span class="date">11-10</span></li>
    </ul>"""
    rows = bp.parse_list(html, "https://y.or.kr/board/list", TODAY)
    assert [(t, d.date().isoformat()) for t, _, d in rows] == [
        ("경로식당 운영시간 변경 안내", "2026-11-16"), ("겨울철 한파 대비 건강 수칙", "2026-11-10")]


def test_연말에_본_내년_월일은_작년으로():
    assert bp.parse_dates("12-30", datetime(2027, 1, 5)) == [datetime(2026, 12, 30)]


def test_오래된_글_자바스크립트_링크_작성자_링크는_뺀다():
    html = """<table>
      <tr><td><a href="v?no=9">2020년 고정 공지 이용 안내</a></td><td>2020-03-01</td></tr>
      <tr><td><a href="javascript:fView('8494')">신규강사 모집의 건</a></td><td>2026-11-17</td></tr>
      <tr><td><a href="v?no=8">어르신 김장 나눔 행사</a> <a href="/member/admin">admin</a></td><td>2026-11-15</td></tr>
      <tr><td><a href="v?no=7">공지</a></td><td>2026-11-14</td></tr>
    </table>"""
    rows = bp.parse_list(html, "https://z.or.kr/list", TODAY)
    assert [t for t, _, _ in rows] == ["어르신 김장 나눔 행사"]


def test_행_전체가_링크면_번호_날짜_작성자를_떼어_낸다():
    assert bp.clean_title("NO. 242 2027년 노인일자리 참여자 모집 안내 최고관리자 2026-11-16 62") == "2027년 노인일자리 참여자 모집 안내"
    assert bp.clean_title("공지 김포시니어클럽 사회복지사 채용 면접 결과 안내 최고관리자 2026-11-18 35") == "김포시니어클럽 사회복지사 채용 면접 결과 안내"
    assert bp.clean_title("[홍보] 선배시민 문화활동 진행! 2026-11-12 | HIT 61") == "[홍보] 선배시민 문화활동 진행!"
    assert bp.clean_title("2027년 1기 컴퓨터반 모집") == "2027년 1기 컴퓨터반 모집"


def test_같은_글_주소는_한_번만_긴_제목으로():
    html = """<div><a href="v?no=5">스마트폰 교실</a><a href="v?no=5">2027년 스마트폰 교실 참여자 모집</a><em>2026.11.17</em></div>"""
    rows = bp.parse_list(html, "https://w.or.kr/", TODAY)
    assert [t for t, _, _ in rows] == ["2027년 스마트폰 교실 참여자 모집"]


def test_목록_오류는_빈_목록(monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("끊김")
    monkeypatch.setattr(bp.requests, "get", boom)
    assert bp.scrape_board(["https://down.or.kr/list"], "테스트복지관", {}) == []


def test_자바스크립트_링크를_상세_주소로_바꾼다_광주():
    html = """<table><tr><td>[공지]</td><td><a href="javascript:fView('8494')">2027년 신규강사 모집의 건</a></td>
              <td>관리자</td><td>2026-11-18</td></tr></table>"""
    rows = bp.parse_list(html, "https://www.gjswc.kr/gjnoin/sub3_1.do", TODAY)
    assert rows[0][1] == "https://www.gjswc.kr/gjnoin/sub3_1_view.do?board_idx=8494"


def test_부천_포털은_기관_표시로_출처를_나눈다(monkeypatch):
    html = """<div class="board_ty">
      <div class="row"><div class="cell title"><a href="#none" onclick="opView('2', '1005', '20261118152519256');">
        <em class="ico_district">시니어클럽</em> <span class="tit">부천시니어클럽 사회복지사 채용공고</span> <i><em>새글</em></i></a></div>
        <div class="cell date">2026-11-18</div></div>
      <div class="row"><div class="cell title"><a href="#none" onclick="opView('2', '1005', '20261116165304470');">
        <em class="ico_district">원미</em> <span class="tit">어르신 구강검진 안내</span></a></div>
        <div class="cell date">2026-11-16</div></div>
    </div>"""
    list_url = "https://senior.bucheon4u.kr/senior/user/bbs/BD_selectBbsList.do?q_domnCode=2&q_bbsCode=1005"

    class R:
        status_code, text, url, headers = 200, html, list_url, {"content-type": "text/html; charset=utf-8"}
        def raise_for_status(self): pass
    monkeypatch.setattr(bp.requests, "get", lambda *a, **k: R())
    labels = {"원미": "부천시원미노인복지관", "시니어클럽": "부천시니어클럽"}
    got = bp.scrape_board([list_url], "부천시 노인복지기관 포털", {}, labels=labels, today=TODAY)
    assert [(g["source"], g["title"]) for g in got] == [
        ("부천시니어클럽", "부천시니어클럽 사회복지사 채용공고"), ("부천시원미노인복지관", "어르신 구강검진 안내")]
    assert got[1]["url"].endswith("BD_selectBbs.do?q_domnCode=2&q_bbsCode=1005&q_bbscttSn=20261116165304470")


def test_JSON_게시판은_본문까지_받고_오래된_글은_뺀다(monkeypatch):
    data = {"items": [
        {"SNTNC_NO": 8134, "SJ": "해온합창단 정기공연 안내", "REG_DT": "2026-11-09 11:34:04.4", "CNTN": "<p>11월 20일 <b>공연</b></p>"},
        {"SNTNC_NO": 1220, "SJ": "고객응대근로자 보호조치 안내", "REG_DT": "2020-09-01 00:00:00.0", "CNTN": ""},
    ]}

    class R:
        def raise_for_status(self): pass
        def json(self): return data
    monkeypatch.setattr(bp.requests, "get", lambda *a, **k: R())
    cfg = {"api": "https://x/api", "view": "https://x/v?no={SNTNC_NO}", "title": "SJ", "date": "REG_DT", "body": "CNTN"}
    got = bp.scrape_json_board(cfg, "화성시동탄노인복지관", {}, today=TODAY)
    assert got == [{"title": "해온합창단 정기공연 안내", "url": "https://x/v?no=8134", "content": "11월 20일 공연", "source": "화성시동탄노인복지관"}]
