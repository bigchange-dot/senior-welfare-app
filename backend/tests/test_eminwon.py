"""eminwon: 새올 목록 파싱. 2026-11-16 경기 실측에서 본 세 가지 템플릿을 최소 HTML로 흉내 낸다."""

import eminwon as E

# 템플릿 1: tbody 안, <a onclick="searchDetail(...)"> (안성·동두천 등)
TPL_A_ONCLICK = """
<table><thead><tr><th>번호</th><th>고시공고번호</th><th>제목</th><th>담당부서</th><th>등록일</th><th>조회</th></tr></thead>
<tbody>
<tr><td>1667</td><td>안성시 공고 제2026-3042호</td>
<td><a href="#" onclick="javaScript:searchDetail('75167')">2026년 노인일자리 참여자 모집</a></td>
<td>노인장애인과</td><td>2026-11-16</td><td>12</td></tr>
</tbody></table>"""

# 템플릿 2: tbody 없음, <td onclick="searchDetail(...)"> (파주·이천·양평 등)
TPL_TD_ONCLICK = """
<table><tr><th>번호</th><th>고시공고번호</th><th>제목</th><th>담당부서</th><th>등록일</th></tr>
<tr><td>3065</td><td>파주시 공고 제2026-2978호</td>
<td onclick="javaScript:searchDetail('75810')">골목형상점가 (변경)지정 공고</td>
<td>민생경제과</td><td>2026-11-16</td></tr>
</table>"""

# 템플릿 3: 머리글 칸 수가 행과 다름, <a href="javaScript:searchDetail(...)"> (김포·광명 등)
TPL_HREF = """
<table><tr><th>번호</th><th>제목</th><th>등록일</th></tr>
<tr><td>2250</td><td>수원시 팔달구 공고 제2026-296호</td>
<td><a href="javaScript:searchDetail('76421');">어르신 무료 건강검진 안내</a></td><td>보건소</td><td>2026-11-13</td></tr>
</table>"""


def test_a_onclick_template():
    rows = E.parse_list(TPL_A_ONCLICK)
    assert rows == [{"id": "75167", "title": "2026년 노인일자리 참여자 모집",
                     "notice_no": "안성시 공고 제2026-3042호", "dept": "노인장애인과", "date": "2026-11-16"}]


def test_td_onclick_template_without_tbody():
    rows = E.parse_list(TPL_TD_ONCLICK)
    assert len(rows) == 1
    assert rows[0]["id"] == "75810"
    assert rows[0]["title"] == "골목형상점가 (변경)지정 공고"
    assert rows[0]["date"] == "2026-11-16"


def test_header_mismatch_falls_back_to_content_shape():
    rows = E.parse_list(TPL_HREF)
    assert rows[0]["id"] == "76421"
    assert rows[0]["title"] == "어르신 무료 건강검진 안내"
    assert rows[0]["notice_no"] == "수원시 팔달구 공고 제2026-296호"
    assert rows[0]["date"] == "2026-11-13"


def test_sub_district():
    city = {"name": "수원시", "sub_districts": ["장안구", "권선구", "팔달구", "영통구"]}
    assert E.sub_district("수원시 팔달구 공고 제2026-296호", city) == "팔달구"
    assert E.sub_district("수원시 공고 제2026-1호", city) == ""


def test_base_url_override():
    defaults = {"eminwon_base": "https://eminwon.{domain}"}
    assert E.base_url({"domain": "suwon.go.kr"}, defaults) == "https://eminwon.suwon.go.kr"
    assert E.base_url({"domain": "pocheon.go.kr", "eminwon_base": "https://eminwon.pcs21.net"}, defaults) == "https://eminwon.pcs21.net"


def test_truncated_title():
    assert E.is_truncated("평택보건소 치매안심센터 기간제근로자(청소 인부) 채...")
    assert E.is_truncated("광명시보건소 노인건강증진센터…")
    assert not E.is_truncated("어르신 무료 건강검진 안내")
