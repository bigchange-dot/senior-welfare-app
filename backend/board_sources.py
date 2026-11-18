"""게시판 출처 목록 — 범용 목록 파서(board_parser.py)로 읽는 복지관·시니어클럽 (v1.5, 2026-11-18).

(출처 이름, 지역 코드, 목록 주소들). 지역 코드는 frontend/lib/regions.dart의 id.
경기: docs/gyeonggi/gyeonggi_centers.yaml에서 status: ok이고 범용 파서로 읽히는 곳만 옮김
      아래 '전용 처리'에 광주(javascript 링크)·부천 포털(4기관)·동탄(JSON). 기흥(목록 날짜 암호화)과 추가 확인 33곳은 아직 없음.
서울: 6개월 저장 0건이던 강서·동작·관악구청 수집기를 그 구의 복지관으로 교체
      (docs/강서-동작-관악-복지관-조사-2026-11-18.md).
점검(저장 안 함): venv/bin/python board_parser.py [이름 일부]
"""

SEOUL_BOARDS: list[tuple[str, str, list[str]]] = [
    ("강서노인종합복지관",     "gangseo", ["http://www.gangseosenior.or.kr/notice"]),
    ("마곡어르신복지관",       "gangseo", ["https://magoksenior.or.kr/notice"]),   # 중간 인증서 추가함 (certs/)
    ("사당어르신종합복지관",   "dongjak", ["https://www.sadangeorsin.or.kr/bbs/board.php?bo_table=0301"]),
    ("관악노인종합복지관",     "gwanak",  ["https://www.noinjigi.org/notice"]),
]

# 경기는 GYEONGGI=1일 때만 수집 (scraping_function.py) — v1.5 앱 출시 전에 공고가 쌓여 알림이 나가지 않게
GYEONGGI_BOARDS: list[tuple[str, str, list[str]]] = [
    # 안성시
    ("안성시노인복지관", "gg-anseong", ["http://www.anseongnoin.or.kr/bbs/board.php?bo_table=notice"]),
    ("안성맞춤시니어클럽", "gg-anseong", ["http://xn--9i1bu2hgubj6nb7bhvfzvar60ci4f.com/bbs/board.php?bo_table=notice"]),
    # 가평군
    ("가평군노인복지관", "gg-gapyeong", ["http://gpsilver.org/home/?page_id=86"]),
    # 김포시
    ("김포시노인종합복지관", "gg-gimpo", ["https://gimposenior.org/bbs/board.php?bo_table=0501"]),
    ("김포시북부노인복지관", "gg-gimpo", ["https://www.gpnsenior.org/bbs/?bid=join"]),
    ("김포시니어클럽", "gg-gimpo", ["http://gpsenior.or.kr/sub/noti_notice.html"]),
    # 고양시
    ("고양시대화노인종합복지관", "gg-goyang", ["https://senior-edu.net/guide/notice.php"]),
    # 하남시
    ("하남시미사노인복지관", "gg-hanam", ["https://misanoin.co.kr/contents.html?pageId=HWNWWCQ8591VBVE9K1DL"]),
    ("하남시니어클럽", "gg-hanam", ["https://hnsc.or.kr/notice"]),
    # 화성시
    ("화성시남부노인복지관", "gg-hwaseong", ["https://www.hssenior.or.kr/notice"]),
    ("화성시니어클럽", "gg-hwaseong", ["https://www.hsseniorclub.or.kr/bbs/?bid=notice"]),
    # 이천시
    ("이천시청미노인복지관", "gg-icheon", ["https://cmnoin.or.kr/109"]),
    # 남양주시
    ("해피누리노인복지관", "gg-namyangju", ["http://www.js1004.kr/bbs/board.php?bo_table=notice_new"]),
    ("남양주시니어클럽", "gg-namyangju", ["https://www.nyjcsc.kr/4010"]),
    # 오산시
    ("오산노인종합복지관", "gg-osan", ["https://www.osannoin.or.kr/bbs/?bid=notice"]),
    # 파주시
    ("운정다누림노인복지관", "gg-paju", ["https://ujdanurim.or.kr/index?category=78V73c8K1w"]),
    ("파주시노인복지관", "gg-paju", ["http://www.pajusenior.or.kr/notice"]),
    ("파주시니어클럽", "gg-paju", ["https://pjsenior.or.kr/53"]),
    # 포천시
    ("포천시노인복지관", "gg-pocheon", ["http://www.pcsc.kr/bbs/board.php?bo_table=notice"]),
    ("포천시니어클럽", "gg-pocheon", ["https://www.pocheonsc.or.kr/bbs/board.php?bo_table=new_notice"]),
    # 평택시
    ("평택남부노인복지관", "gg-pyeongtaek", ["https://www.ptsenior.or.kr/notice"]),
    ("평택북부노인복지관", "gg-pyeongtaek", ["https://bbnoin.or.kr:41004/bbs/board.php?bo_table=bbnotice"]),
    ("평택서부노인복지관", "gg-pyeongtaek", ["http://www.sbnoin.net/bbs/board.php?bo_table=sub05_01"]),
    # 성남시
    ("분당노인종합복지관", "gg-seongnam", ["https://www.bdsenior.or.kr/73"]),
    ("수정노인종합복지관", "gg-seongnam", ["https://www.sunobok.or.kr/content/05notice/01_01.php"]),
    ("수정중앙노인종합복지관", "gg-seongnam", ["https://www.sswc.kr/bbs/?bid=notice"]),
    ("중원노인종합복지관", "gg-seongnam", ["https://jwnoin.org/bbs/?bid=notice", "https://jwnoin.org/bbs/?bid=participant"]),
    ("판교노인종합복지관", "gg-seongnam", ["https://www.pangyonoin.or.kr/board_notice01/list.php?tn=board_notice01&G_state=Y"]),
    ("성남시분당시니어클럽", "gg-seongnam", ["https://www.sbdsenior.or.kr/gboard/bbs/board.php?bo_table=notice"]),
    # 수원시
    ("SK청솔노인복지관", "gg-suwon", ["http://scsnoin.or.kr/?state=notice"]),
    ("서호노인복지관", "gg-suwon", ["https://www.seoho.or.kr/well/board/notice_list.jsp"]),
    ("팔달노인복지관", "gg-suwon", ["http://www.pdsenior.or.kr/paldalintro/paldal_notice.jsp"]),
    # 의정부시
    ("의정부시니어클럽", "gg-uijeongbu", ["https://ucsc4u.or.kr/20"]),
    # 의왕시
    ("의왕시아름채노인복지관", "gg-uiwang", ["https://uwsenior.or.kr/bbs/?bid=notice"]),
    ("의왕시니어클럽", "gg-uiwang", ["https://www.uwsc.or.kr/bbs/?bid=notice"]),
    # 양주시
    ("양주시희망노인복지관", "gg-yangju", ["https://www.yangjuhm.or.kr/bbs/board.php?bo_table=participants"]),
    # 양평군
    ("양평군노인복지관", "gg-yangpyeong", ["http://www.ypsilver21.or.kr/bbs/board.php?bo_table=0501"]),
    # 여주시
    ("여주시노인복지관", "gg-yeoju", ["https://www.yjsilver.or.kr/board/board.php?b_id=notice"]),
    # 용인시
    ("용인시처인노인복지관", "gg-yongin", ["http://www.yiswc.or.kr/News_01.php"]),
    ("용인시니어클럽", "gg-yongin", ["https://www.yisenior.com/board/index.html?id=notice"]),
]

# ── 전용 처리가 필요한 경기 게시판 (2026-11-18) ──
GYEONGGI_BOARDS += [
    # 글 링크가 javascript:fView('번호') → board_parser.JS_LINKS가 상세 주소로 바꿈
    ("광주시노인복지관", "gg-gwangju", ["https://www.gjswc.kr/gjnoin/sub3_1.do"]),
    # 부천시가 운영하는 공동 게시판 하나에 4기관 글이 모임 → 제목 앞 기관 표시로 출처를 나눔 (BOARD_LABELS)
    ("부천시 노인복지기관 포털", "gg-bucheon",
     ["https://senior.bucheon4u.kr/senior/user/bbs/BD_selectBbsList.do?q_domnCode=2&q_bbsCode=1005"]),
]

# '복지관 소식' 이름이라 점검에서 보류했다가 글 내용을 보고 공지 게시판으로 확인 (2026-11-18)
GYEONGGI_BOARDS += [
    ("과천시노인복지관",         "gg-gwacheon",   ["https://www.gcsilver.or.kr/bbs/board.php?bo_table=0401"]),
    ("남양주시동부노인복지관",   "gg-namyangju",  ["https://www.dongbusenior.or.kr/bbs/?bid=notice"]),
    ("평택팽성노인복지관",       "gg-pyeongtaek", ["https://pssenior.or.kr:41006/bbs/board.php?bo_table=sub04_01"]),
    ("황송노인종합복지관",       "gg-seongnam",   ["https://www.ypinetree.or.kr/content/01news/01_01.php"]),
    # 점검 때 접속 오류였다가 다시 확인: 군포는 http가 자기 자신으로 무한 이동 → https로, 수원시니어클럽은 옛 암호화(LEGACY_TLS_HOSTS)
    ("군포시노인복지관",         "gg-gunpo",      ["https://www.gpbokji.org/module/board/board.php?bo_table=notice"]),
    ("수원시니어클럽",           "gg-suwon",      ["https://www.swsc.co.kr/bbs/board.php?bo_table=notice"]),
]

# 한 게시판에 여러 기관 글이 모이는 곳: 게시판 이름 → {제목 앞 기관 표시: 출처 이름}
BOARD_LABELS: dict[str, dict[str, str]] = {
    "부천시 노인복지기관 포털": {
        "원미": "부천시원미노인복지관", "소사": "부천시소사노인복지관",
        "오정": "부천시오정노인복지관", "시니어클럽": "부천시니어클럽",
    },
}

# 목록을 JSON으로 주는 게시판 (board_parser.scrape_json_board). 경기라 GYEONGGI=1일 때만
JSON_BOARDS: list[tuple[str, str, dict]] = [
    ("화성시동탄노인복지관", "gg-hwaseong", {
        "api": "https://www.dtsenior.or.kr/api/bbs/1.0/base",
        "params": {"BBS_CD": "001", "PAGE_NO": "1", "PAGE_SIZE": "20"},
        "referer": "https://www.dtsenior.or.kr/bbs/basel.do?BBS_CD=001",
        "view": "https://www.dtsenior.or.kr/bbs/basev.do?BBS_CD=001&SNTNC_NO={SNTNC_NO}",
        "title": "SJ", "date": "REG_DT", "body": "CNTN",
    }),
]

ALL_BOARDS = SEOUL_BOARDS + GYEONGGI_BOARDS
