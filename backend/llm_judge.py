"""
AI 판정·요약 (2026-11-16 개편)

공고 1건을 보고 "어르신에게 알릴 공고인지(PASS/SKIP)"와 "알림·카드에 쓸 한 줄 요약"을 만든다.

개편 내용 (근거: Firestore 판정 기록 460건 검토, 2026-11-16)
- 규칙 필터: 합격자·추첨 결과, 행정 공개처럼 LLM 판정이 엇갈리던 유형은 LLM에 묻기 전에 규칙으로 고정
  (예: 수락노인복지관 '합격자 명단'이 9건 SKIP·5건 PASS로 갈렸고, 도봉은 같은 문장 알림이 15건 넘게 나감)
- 정책 (사용자 결정 2026-11-16): 합격자·결과 발표 제외, 이미 끝난 일 보도 제외, 요약은 대상·날짜·마감 위주
- 프롬프트에 오늘 날짜를 넣어 마감 지난 공고를 거른다
- 결과를 JSON으로 받고, 저장 전에 요약을 검사한다 (지어낸 숫자, 한자·영문, 경고 표현)
- 실행 위치에 따라 LLM을 고른다: LLM_PROVIDER=ollama (맥 로컬) / gemini (클라우드, 기본값)

반환 규칙 (scraping_function._run_pipeline이 사용):
- "SKIP"  → 제외 (skipped_notices에 캐시)
- "ERROR" → 호출 실패. 저장하지 않고 다음 실행에 재시도
- 그 외    → 저장할 요약 문장
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

GEMINI_MODEL  = "gemini-3.1-flash-lite-preview"
OLLAMA_MODEL  = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
OLLAMA_URL    = os.getenv("OLLAMA_URL", "http://localhost:11434")
CONTENT_CHARS = 800   # 프롬프트에 넣는 본문 길이 (기존 300자는 모집 대상·기간이 잘리는 경우가 많았음)
SUMMARY_MAX   = 40    # 이모지 포함 요약 최대 길이. 넘으면 제목 기반 문구로 대체

KST   = timezone(timedelta(hours=9))
state = {"last_error": ""}   # 마지막 호출 오류 (실행 기록·헬스체크용)


def provider() -> str:
    return os.getenv("LLM_PROVIDER", "gemini").strip().lower()


# ─────────────────────────────────────────────
# 1. 규칙 필터 (LLM 호출 전)
# ─────────────────────────────────────────────
RULE_SKIP = [
    ("합격·선정 결과", re.compile(
        r"합격자|합격\s*예정자|최종\s*합격|서류\s*전형|서류\s*심사|면접\s*전형|추첨\s*결과|당첨자|당첨\s*결과|선정\s*결과|선발\s*결과")),
    ("행정 공개", re.compile(
        r"업무추진비|수의계약|운영위원회|회의록|정보\s*공개|결과\s*공개|추진\s*현황|사용\s*내역")),
    ("행정 공고", re.compile(r"공시송달|입찰|견적|납품\s*업체|행정처분|입법예고|조례|명단\s*공표|기관\s*공표|위반\s*사실\s*공표")),
    # 서비스 제공기관·수행기관을 뽑는 공고 (어르신이 아니라 기관 대상)
    ("기관 모집", re.compile(r"(제공|수행|수탁|위탁|운영|지원)\s*기관\s*(모집|공모|선정|지정)|수탁자\s*(모집|선정)|위탁\s*운영\s*(기관\s*|법인\s*)?(모집|공모)|민간\s*위탁")),
    # 종사자 채용 — 2차 평가에서 LLM이 "필라테스 강사 채용" 등 3건을 통과시켜 규칙으로 고정.
    # 경기 새올 실측(2026-11-16)에서 "치매안심센터 기간제근로자 채용"류가 키워드 필터를 통과해 직종 추가
    # "시니어 강사", "어르신 강사"처럼 어르신이 일하는 자리는 제외하지 않는다
    ("종사자 채용", re.compile(
        r"\[\s*(직원|강사)\s*채용\s*\]|"
        r"(?<!시니어)(?<!시니어 )(?<!어르신)(?<!어르신 )"
        r"(강사|직원|사회복지사|요양보호사|생활지원사|조리원|운전원|취사원|간호사|영양사|매니저|팀장|사무원|교사|"
        r"기간제\s*근로자|종사자|치료사|돌봄교사|청소\s*인부)"
        r"(\s*\([^)]{0,40}\))?\s*(대체\s*인력\s*)?(공개\s*)?(채용|모집)")),
    # "[접수마감] 구강교육 참여자 모집"처럼 제목에 마감 표시가 붙은 글 ("마감 임박"은 통과)
    ("마감", re.compile(r"[\[\(【]\s*(접수\s*|모집\s*)?마감\s*[\]\)】]|모집\s*마감(?!\s*임박)|접수\s*마감\s*(안내|되었|됨)|조기\s*마감")),
]
# 결과 발표라도 새로 신청할 수 있으면 LLM 판정으로 넘긴다
RULE_KEEP = re.compile(r"추가\s*(접수|모집|신청)|잔여\s*(석|인원)|재\s*모집")


# 일반 출처(구청·시청 등)는 제목에 이 단어가 없으면 AI에 묻지 않는다 (노인복지관 출처는 적용 안 함).
# 구청 게시판은 대부분 일반 행정 공지라 AI 호출 수를 크게 줄인다 (2026-11-16 점검: 구청 12곳 160건 중 AI로 간 건 3건)
SENIOR_KEYWORDS = (
    "노인", "어르신", "경로", "실버", "시니어", "고령", "65세",
    "요양", "돌봄", "치매", "장사", "기초연금", "복지관", "경로당",
)


def has_senior_keyword(title: str) -> bool:
    return any(k in title for k in SENIOR_KEYWORDS)


# 어르신을 고용하는 기관의 채용은 '종사자 채용' 규칙에서 빼고 AI 판정에 맡긴다
# (예: "노원어르신행복주식회사 기간제 근로자(바리스타) 채용", "시니어인턴 채용")
SENIOR_EMPLOYER_RE = re.compile(r"어르신\s*(행복|일자리)|시니어\s*(클럽|인턴)|노인\s*일자리|고령자\s*(채용|일자리)")


def rule_skip_reason(title: str) -> str | None:
    """정책상 무조건 제외하는 제목이면 이유를, 아니면 None을 돌려준다."""
    if RULE_KEEP.search(title):
        return None
    for reason, pattern in RULE_SKIP:
        if reason == "종사자 채용" and SENIOR_EMPLOYER_RE.search(title):
            continue
        if pattern.search(title):
            return reason
    return None


# ─────────────────────────────────────────────
# 2. 프롬프트
# ─────────────────────────────────────────────
SYSTEM = (
    "너는 서울·경기 어르신(60세 이상)에게 복지 소식을 알려 주는 앱의 편집자다. "
    "모든 답은 한국어 한글로만 쓰고, 중국어·한자·영어 문장은 쓰지 않는다. "
    "요청한 JSON 외에는 아무것도 출력하지 않는다."
)

JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["PASS", "SKIP"]},
        "summary":  {"type": "string"},
    },
    "required": ["decision", "summary"],
}


def build_prompt(title: str, content: str, source: str, is_center: bool, today: datetime | None = None) -> str:
    today = (today or datetime.now(KST)).astimezone(KST)
    weekday = "월화수목금토일"[today.weekday()]
    center_note = " (노인복지관 — 이용자가 모두 어르신)" if is_center else ""
    body = content[:CONTENT_CHARS] if content else "(없음)"
    return f"""오늘은 {today:%Y년 %m월 %d일}({weekday})이다. 아래 공고를 판정하라.

출처: {source}{center_note}
제목: {title}
본문: {body}

[PASS] 어르신 본인이나 어르신을 돌보는 가족이 지금 신청·참여·이용할 수 있는 것
- 프로그램·교육·강좌·행사 참여자 모집, 접수 안내
- 어르신이 직접 일하는 일자리·사회활동 참여자 모집
- 지원금·수당·서비스·검진·예방접종 신청 안내
- 어르신이 이용할 수 있는 상담·서비스 안내 (법률·심리 상담, 생활 지원·동행 서비스 등)
- 어르신 안전 주의 안내 (보이스피싱·사기, 폭염·한파·미세먼지)

[SKIP]
- 합격자·당첨자·추첨 결과·선정 결과 발표 (추가 접수가 있으면 PASS)
- 직원·강사·사회복지사·요양보호사·생활지원사 등 종사자 채용과 그 결과
- 이미 끝난 일을 알리는 보도: 행사 성료, 업무협약, 수상, 전달식, 방문, 기공식
  (단, 지금 신청할 수 있는 혜택이 담긴 보도는 PASS)
- 업무추진비·계약·회의록·운영위원회 등 행정 공개, 시설 공사·점검, 휴관·분실물 안내
- 모금·후원·기부 요청, 반려동물·아동 등 어르신 대상이 아닌 안내
- 어르신과 관계없는 내용, 마감이 이미 지난 공고

[요약 규칙] PASS일 때만 쓴다. SKIP이면 summary는 빈 문자열.
- 반드시 내용에 맞는 이모지 1개로 시작하는 30자 이내 한 줄
- 무엇을, 누가(대상), 언제(날짜·마감)를 앞세운다. 제목을 그대로 옮기지 않는다
- 제목·본문에 있는 사실만 쓴다. 날짜·인원·금액을 지어내지 않는다
- 날짜·대상을 제목·본문에서 찾을 수 없으면 "·" 뒤를 붙이지 말고 내용만 쓴다.
  "오늘부터", "지금", "접수 중", "신청 가능", "2026년"처럼 막연한 말로 채우지 않는다
- "[속보]", "긴급", 🚨·⚠️ 같은 경고 표시, 느낌표를 쓰지 않는다. 기관 이름은 빼도 된다
- 형식 예시 (내용은 실제 공고대로): "💉 65세 이상 독감 무료접종 · 이달 말까지", "🎨 어르신 민화교실 수강생 모집"

다음 JSON으로만 답하라: {{"decision": "PASS 또는 SKIP", "summary": "요약"}}"""


# ─────────────────────────────────────────────
# 3. LLM 호출
# ─────────────────────────────────────────────
OLLAMA_RETRIES    = 2    # 실패 시 추가 시도 횟수
OLLAMA_RETRY_WAIT = 10   # 초


def _call_ollama(prompt: str) -> str:
    """Ollama 호출. 연결 오류·5xx는 잠시 뒤 다시 시도한다.

    맥이 뚜껑 닫힌 채 배터리로 자다가 점검차 잠깐 깨어날 때(DarkWake) launchd 작업이 시작되면,
    실행 도중 다시 잠들었다 깨면서 Ollama가 500을 돌려준다 (2026-11-17 18시 실행에서 2건 보류).
    깨어난 직후 다시 부르면 대부분 성공한다.
    """
    for attempt in range(OLLAMA_RETRIES + 1):
        try:
            res = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model":   OLLAMA_MODEL,
                    "system":  SYSTEM,
                    "prompt":  prompt,
                    "stream":  False,
                    "format":  JSON_SCHEMA,          # 구조화 출력 (JSON 깨짐 방지)
                    "options": {"temperature": 0.1},
                },
                timeout=180,
            )
            if res.status_code < 500:
                res.raise_for_status()
                return res.json()["response"]
            error = requests.HTTPError(f"{res.status_code} Server Error", response=res)
        except (requests.ConnectionError, requests.Timeout) as e:
            error = e
        if attempt < OLLAMA_RETRIES:
            logger.warning(f"⏳ Ollama 호출 실패({error}), {OLLAMA_RETRY_WAIT}초 뒤 다시 시도 ({attempt + 1}/{OLLAMA_RETRIES})")
            time.sleep(OLLAMA_RETRY_WAIT)
    raise error


_gemini = None


def _call_gemini(prompt: str) -> str:
    global _gemini
    from google import genai
    from google.genai import types
    if _gemini is None:
        _gemini = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM,
        response_mime_type="application/json",
        temperature=0.1,
    )
    for attempt in range(3):
        try:
            response = _gemini.models.generate_content(model=GEMINI_MODEL, contents=prompt, config=config)
            time.sleep(13)  # 무료 티어 분당 5회 제한 준수
            return response.text
        except Exception as e:
            if "429" in str(e) and attempt < 2:
                wait = 65 if attempt == 0 else 130
                logger.warning(f"⏳ Gemini 429 Rate Limit, {wait}초 대기 후 재시도...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Gemini 재시도 소진")


# ─────────────────────────────────────────────
# 4. 결과 검사
# ─────────────────────────────────────────────
_WARN_RE   = re.compile(r"\[\s*속보\s*\]|속보\s*[:：]|긴급|🚨|⚠️?|❗|‼️?|❕")
_CJK_RE    = re.compile(r"[一-鿿]")
_HANGUL_RE = re.compile(r"[가-힣]")
_NUM_RE    = re.compile(r"\d+")
_LATIN_RE  = re.compile(r"[A-Za-z]{3,}")
_EMOJI_RE  = re.compile(r"^[\U0001F300-\U0001FAFF☀-➿⭐⭕]")


# "· 오늘부터", "· 2026년"처럼 정보 없는 꼬리말 (2차 평가에서 19건)
_FILLER_TAIL_RE = re.compile(
    r"\s*·\s*(오늘부터|지금(\s*신청)?|접수\s*중|신청\s*가능|참여\s*가능|이용\s*(시\s*)?참고|제공|진행\s*중|\d{4}년)\s*$")

# 모델이 이모지를 자주 빼먹어(2차 평가 85%) 내용 키워드로 코드가 고른다. 위에서부터 먼저 맞는 것
_EMOJI_RULES = [
    ("💉", r"접종|백신"), ("🩺", r"검진|검사|진료|건강검진"), ("🧠", r"치매|인지|기억"),
    ("💬", r"상담|우울|마음"), ("⚖️", r"법률|권익|인권"), ("🚫", r"사기|보이스피싱|스미싱"),
    ("☀️", r"폭염|더위"), ("❄️", r"한파|추위|한랭"), ("😷", r"미세먼지|감염|결핵"),
    ("💼", r"일자리|취업|인턴|채용"), ("💰", r"지원금|수당|연금|바우처|응모료|응시료"),
    ("📱", r"스마트폰|디지털|키오스크|AI|컴퓨터|정보화"), ("🎨", r"미술|민화|그림|서예|캘리"),
    ("🎵", r"노래|합창|음악|악기|하모니카|통기타|난타|댄스|춤"), ("🏃", r"운동|체조|요가|걷기|헬스|스트레칭"),
    ("🍲", r"식사|급식|도시락|반찬|김장"), ("🎬", r"영화|상영|공연"), ("🎉", r"축제|잔치|기념행사|행사"),
    ("📚", r"교육|강좌|교실|강의|특강|아카데미"), ("🤝", r"봉사|자원봉사|돌봄"),
]
_EMOJI_RULES = [(e, re.compile(p)) for e, p in _EMOJI_RULES]


def pick_emoji(text: str) -> str:
    for emoji, pattern in _EMOJI_RULES:
        if pattern.search(text):
            return emoji
    return "📢"


def _clean(text: str) -> str:
    text = _WARN_RE.sub("", text or "")
    text = re.sub(r"[!！]+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -·:")
    return _FILLER_TAIL_RE.sub("", text).strip(" -·:")


def fallback_summary(title: str) -> str:
    """요약이 검사를 통과하지 못하면 쓰는 제목 기반 문구. 단어 중간에서 자르지 않는다."""
    text = _clean(re.sub(r"^\s*[\[\(【<][^\]\)】>]{0,15}[\]\)】>]\s*", "", title))   # 앞머리 [안내] 등 제거
    if len(text) > 28:
        cut = text[:28]
        text = cut[:cut.rfind(" ")] if " " in cut[10:] else cut
        text = text.rstrip(" ,·…'‘’\"“”") + "…"
    return f"{pick_emoji(title)} {text}"


def is_valid_summary(summary: str, title: str, content: str) -> bool:
    if not summary or len(summary) > SUMMARY_MAX:
        return False
    if _CJK_RE.search(summary) or len(_HANGUL_RE.findall(summary)) < 4:
        return False
    source_text = f"{title} {content}"
    # 제목·본문에 없는 숫자(날짜·인원·금액) = 지어낸 정보로 본다
    if set(_NUM_RE.findall(summary)) - set(_NUM_RE.findall(source_text)):
        return False
    # 제목·본문에 없는 영문 단어 (모델이 영어로 새는 경우)
    if {w.lower() for w in _LATIN_RE.findall(summary)} - {w.lower() for w in _LATIN_RE.findall(source_text)}:
        return False
    return True


# 요약 속 날짜: "11/9", "10월 28일", 범위 끝 "~30일"(앞 날짜의 월을 이어 씀). "2.5단계" 같은 소수와 헷갈려 "11.12"는 읽지 않음
_DATE_TOKEN_RE = re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일|(?<![\d./])(\d{1,2})\s*/\s*(\d{1,2})(?![\d./])|~\s*(\d{1,2})\s*일")


def latest_date_in(text: str, today: datetime) -> datetime | None:
    """요약에 적힌 날짜 중 가장 늦은 날. 월만 있는 표기("11월")는 판단하지 않는다."""
    latest, month = None, None
    for m in _DATE_TOKEN_RE.finditer(text):
        if m.group(1):
            month, day = int(m.group(1)), int(m.group(2))
        elif m.group(3):
            month, day = int(m.group(3)), int(m.group(4))
        elif month:
            day = int(m.group(5))
        else:
            continue
        try:
            d = today.replace(month=month, day=day, hour=23, minute=59)
        except ValueError:
            continue
        if d < today - timedelta(days=180):   # 11월에 쓴 "1/5"는 내년
            d = d.replace(year=d.year + 1)
        latest = d if latest is None or d > latest else latest
    return latest


def finalize(raw: str, title: str, content: str, today: datetime | None = None) -> str:
    """LLM 원문 응답 → "SKIP" 또는 저장할 요약. JSON이 깨졌으면 ValueError.

    PASS라도 요약에 적힌 마지막 날짜가 오늘보다 앞서면 SKIP (첫 로컬 실행에서
    "전시회 관람 · 11/9~11/12"가 11/16에 저장돼 추가, LLM이 날짜 비교를 자주 놓침)."""
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text).strip()
    if text.upper() == "SKIP":   # JSON 없이 SKIP만 답한 경우
        return "SKIP"
    data = json.loads(text)
    decision = str(data.get("decision", "")).strip().upper()
    if decision == "SKIP":
        return "SKIP"
    if decision != "PASS":
        raise ValueError(f"알 수 없는 판정: {decision!r}")
    summary = _clean(str(data.get("summary", "")))
    today = (today or datetime.now(KST)).astimezone(KST)
    last = latest_date_in(summary, today)
    if last and last < today:
        logger.info(f"⌛ 기간 지남({last:%m/%d}) → SKIP: {summary[:40]!r}")
        return "SKIP"
    if not is_valid_summary(summary, title, content):
        logger.info(f"✏️ 요약 검사 불통과 → 제목 기반 문구 사용: {summary[:40]!r}")
        return fallback_summary(title)
    if not _EMOJI_RE.match(summary):
        summary = f"{pick_emoji(f'{title} {summary}')} {summary}"
    return summary


# ─────────────────────────────────────────────
# 5. 진입점
# ─────────────────────────────────────────────
def judge_notice(title: str, content: str = "", source: str = "", is_center: bool = False) -> str:
    """공고 1건 판정. 반환값은 모듈 설명 참고 ("SKIP" / "ERROR" / 요약)."""
    name = provider()
    prompt = build_prompt(title, content, source, is_center)
    try:
        raw = _call_ollama(prompt) if name == "ollama" else _call_gemini(prompt)
        result = finalize(raw, title, content)
        logger.info(f"🤖 AI 판정({name}): {result[:50]}")
        return result
    except Exception as e:
        state["last_error"] = f"{name}: {e}"[:300]
        logger.error(f"❌ AI 요약 오류({name}): {e}")
        return "ERROR"
