#!/usr/bin/env python3
"""rcheck — 한국어 보고서 규칙 점검기 (표준 라이브러리만).

report-rules 스킬의 규칙 가운데 기계로 셀 수 있는 것을 전수 점검한다.
판단이 필요한 항목(논증 구조·근거의 크기·제언의 실행성)은 점검하지 않는다 —
그건 스킬의 점검 모드에서 사람(또는 Claude)이 점검표로 판정한다.

사용:
  python3 rcheck.py check 초안.md --type research        # 점검 리포트(마크다운)
  python3 rcheck.py check 초안.hwpx --type advisory --json
  python3 rcheck.py stats 초안.hwpx 최종본.hwpx           # 문체 지표 비교(전후 대조)
  python3 rcheck.py selftest

--type: common(기본) | research | brief | advisory
입력: .md .txt .hwpx .docx
종료 코드: 0 = [필수] 0건, 1 = [필수] 1건 이상, 2 = 입력 오류
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import zipfile
from dataclasses import dataclass, field, asdict
from pathlib import Path

VERSION = "1.0.0"
TYPES = ("common", "research", "brief", "advisory")

# ───────────────────────── 입력 ─────────────────────────

def _xml_paragraphs(xml: str, p_tag: str, t_tag: str) -> list[str]:
    out = []
    for m in re.finditer(rf"<{p_tag}\b[^>]*>(.*?)</{p_tag}>", xml, re.S):
        body = m.group(1)
        # 문단 안 중첩 문단(표 셀)은 따로 잡히므로 텍스트 노드만 모은다
        texts = re.findall(rf"<{t_tag}\b[^>]*>(.*?)</{t_tag}>", body, re.S)
        s = "".join(re.sub(r"<[^>]+>", "", t) for t in texts)
        s = (s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
               .replace("&apos;", "'").replace("&amp;", "&"))
        if s.strip():
            out.append(s)
    return out


def load_lines(path: Path) -> list[str]:
    suf = path.suffix.lower()
    if suf in (".md", ".txt", ".markdown"):
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    if suf == ".hwpx":
        lines: list[str] = []
        with zipfile.ZipFile(path) as z:
            secs = sorted(n for n in z.namelist() if re.match(r"Contents/section\d+\.xml$", n))
            for n in secs:
                xml = z.read(n).decode("utf-8", errors="replace")
                # 표 셀 문단이 바깥 문단과 겹치지 않게 가장 안쪽 문단 단위로 자른다
                lines += _xml_paragraphs(re.sub(r"<hp:p\b", "\n<hp:p", xml), "hp:p", "hp:t")
        return _dedupe_nested(lines)
    if suf == ".docx":
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
        return _xml_paragraphs(xml, "w:p", "w:t")
    raise ValueError(f"지원하지 않는 형식: {suf} (.md .txt .hwpx .docx)")


def _dedupe_nested(lines: list[str]) -> list[str]:
    # 비탐욕 매칭으로 바깥 문단이 안쪽 문단 텍스트를 이어붙인 줄이 생길 수 있어 제거
    out = []
    for i, s in enumerate(lines):
        if i + 1 < len(lines) and len(s) > len(lines[i + 1]) and s.endswith(lines[i + 1]) and len(lines[i + 1]) > 8:
            continue
        out.append(s)
    return out


# ───────────────────────── 규칙 ─────────────────────────

@dataclass
class Finding:
    rule: str
    level: str          # 필수 | 권고 | 참고
    line: int
    excerpt: str
    note: str


@dataclass
class Rule:
    rid: str
    title: str
    level: str
    ref: str            # 규칙 파일 절
    pattern: str | None = None
    note: str = ""
    types: tuple = TYPES
    skip_label_lines: bool = False


def R(*a, **k):
    return Rule(*a, **k)


WORD_RULES: list[Rule] = [
    R("HEDGE", "판단 유보어", "필수", "공통 §2.1",
      r"사료(된다|됨|되며|되어)|것으로 판단된다|것으로 보인다|것으로 보임|것으로 생각된다|생각된다|것 같다|것 같음",
      "근거가 있으면 단언, 약하면 무엇이 약한지 밝힌다. (자문의견서의 요구 문장은 '~하면 좋을 것으로 판단함' 허용 — 판단 문장인지 확인)"),
    R("TAIL", "'이는 ~를 반영/의미함' 해설 꼬리", "권고", "공통 §4.4 · 연구 §3.1",
      r"이는\s.{0,60}?(?:반영|의미)(?:함|한다|하는 것|하고)",
      "꼬리를 지우고 앞 문장에서 끝낸다. 해석이 새 정보이면 (시사점) 줄로 독립"),
    R("XREF", "괄호 안 장·절 상호참조", "필수", "공통 §7.3",
      r"\((?:[^()]{0,20}(?:제\s?[0-9ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\s?[장절](?:\s?제?\s?[0-9]+\s?절)?|[0-9ⅠⅡⅢⅣⅤⅥⅦ]+\.[0-9]+(?:\.[0-9]+)?\s?절)[^()]{0,30}|[^()]{0,30}(?:에서|를)\s?(?:상술|후술|자세히 다)[^()]{0,10})\)",
      "괄호에는 인용만. 필요하면 문장 성분으로(\"제Ⅲ장에서 다룬다\")"),
    R("TRACE", "작업 흔적", "필수", "공통 §7.3",
      r"utm_source|chatgpt\.com|\]\(https?://|⟪|⟫|〔(?:검증|색인확인|2차|확인 필요|보강 필요|구체화 필요|추정|가정|사용자 확인|합산금지)[^〕]*〕|_workspace|\b\w+\.md\b|이번 보완에서|피드백 주신|TODO|FIXME",
      "배포 전 전수 제거(작업 초안이면 무시)"),
    R("DASH2", "한 줄에 두 문장을 대시로 이음", "권고", "공통 §3.3",
      r"^\s*[□○ㅇ◯\-·•*]?\s*\S.{24,}?(?:다|함|임|음|됨)\s?[—―]\s?\S.{3,}(?:다|함|임|음|됨)\.?\s*$",
      "두 줄로 나누거나 한 문장으로 합친다"),
    R("COUNT", "개수 수사", "참고", "공통 §4.4",
      r"(?<![0-9])(?:두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s?(?:가지|갈래|함정|실천|원칙|측면|축|층위|유형)",
      "구조를 예고하는 개수('네 가지 요구')·공식 명칭('13대 과제')은 허용. 수사로 쓴 개수('여덟 함정')만 뺀다"),
    R("CONTRAST", "'X가 아니라 Y'·'~에 그치지 않고' 대비 구문", "참고", "공통 §4.4",
      r"단순(?:히|한)?\s?.{0,20}?(?:아니라|그치지 않고)|(?:이|가)\s아니라\s|에 그치지 않고",
      "문서당 1~2회까지"),
    R("TRANSLATIONESE", "번역투", "권고", "공통 §4.2",
      r"에 있어서|하는 것이 가능하|되어지|보여지|에 의해\s?\S+(?:되|된)|정박|원산지|고용량 생산|준산업적 규모",
      "우리말 구문으로"),
    R("BANNED", "지목된 낱말·상투어", "권고", "공통 §4.3",
      r"압박한다|압박하는|압박하고|종언|기능 정지|시간축 불일치|이행요건 미충족|논리적이고 설득력 있는|박차를 가|의 전유물|급변하는|시대를 맞아|오늘날|연구에 따르면|전문가들은|로 알려져 있|신중한 접근|다각도의 검토|다각도로 검토|종합적으로 고려|추가 검토가 필요",
      "대체어를 쓰거나 구체적 사실로 바꾼다"),
    R("VAGUE", "빈 수식어·애매한 양", "참고", "공통 §1.2 · §4.3",
      r"다양한|체계적(?:인|으로)|종합적(?:인|으로)|효과적(?:인|으로)|혁신적(?:인|으로)|대체로|대부분|상당(?:한|히)|어느 정도",
      "대상·기준·수치로 바꿀 수 있는지 확인"),
    R("SUPERLATIVE", "최상급·전칭", "참고", "공통 §2.3",
      r"유일(?:한|하다|함|의)|완전히|최초(?:로|의)|세계 최고|모든\s",
      "비교 범위를 밝혔는지 확인(\"본 장이 비교한 다섯 문서 가운데\")"),
    R("QUOTE_MARK", "부호: ▲·『』·둥근 따옴표", "권고", "공통 §5",
      r"▲|『|』",
      "▲→△, 『』 쓰지 않음"),
    R("DATE", "날짜 표기", "권고", "공통 §5",
      r"(?<!\d)\d{4}-\d{1,2}-\d{1,2}(?!\d)|(?<!\d)\d{4}\.\s?0\d\.|(?<!\d)\d{4}\.\s?\d{1,2}\.\s?\d{1,2}(?![.\d])",
      "`2026. 9. 23.` — 온점·한 타 띄움, 월·일의 0 생략, 끝 온점"),
    R("SPACING", "띄어쓰기(의존명사 붙여 씀)", "권고", "공통 §5",
      r"[가-힣](?:할|될|있을|없을|볼|줄)수(?:\s|있|없|도)|\d+여개|[가-힣]것(?:이다|으로|을|은)(?![가-힣])",
      "'할 수', '40여 개', '하는 것' — 오탐 가능, 문맥 확인"),
    R("ORDER", "지시형 '~할 것'·'~바람'", "권고", "자문 §3.2 · 공통 §2.2",
      r"(?:할|될|둘|줄|볼|쓸|낼|뺄) 것\.?\s*$|바람\.?\s*$",
      "상대에게 요구하는 문장은 제안형('~할 필요가 있음', '~하면 좋을 것으로 판단함')",
      types=("advisory", "brief", "common")),
    R("DAECHE", "개조식 문서의 '~다.' 종결", "권고", "공통 §3.1",
      r"[가-힣](?:다|니다)\.\s*$",
      "정책·기획보고서·브리프·의견서는 ~함/~임. 학술 성격 장이면 무시",
      types=("research", "brief", "advisory")),
    R("META", "의견서 메타 표(검토자·검토일)", "참고", "자문 §2",
      r"검토\s?(?:대상|범위|자|일)\s*[:|]",
      "제목 + 날짜·작성자 한 줄로",
      types=("advisory",)),
]

# 「」 안에 법령·문서명이 아닌 개념이 들어갔는지 (휴리스틱)
DOC_SUFFIX = re.compile(
    r"(법|법률|령|규칙|규정|고시|훈령|예규|조례|계획|기본계획|전략|방안|대책|로드맵|보고서|백서|편람|길잡이|지침|가이드|매뉴얼|협약|선언|헌장|원칙|의정서|"
    r"Act|Plan|Strategy|Report|사업|프로그램|과제|조사|통계|지표|현황|안|서|집|록|報)$"
)

# ───────────────────────── 점검 ─────────────────────────

LABEL_DASH = re.compile(r"^\s*[□○ㅇ◯●\-·•➊-➓①-⑳*]*\s*\([^)]{1,30}\)\s*[—―]")


def check(lines: list[str], dtype: str) -> dict:
    findings: list[Finding] = []
    text = "\n".join(lines)
    nchar = len(re.sub(r"\s", "", text)) or 1

    for i, raw in enumerate(lines, 1):
        s = raw.rstrip()
        if not s.strip() or s.lstrip().startswith(("```", "|---")):
            continue
        for r in WORD_RULES:
            if dtype not in r.types:
                continue
            for m in re.finditer(r.pattern, s):
                if r.rid == "XREF" and re.match(r"^\s*[□○ㅇ◯●\-·•*]?\s*$", s[:m.start()]):
                    continue  # 줄 머리 라벨 '(효과성, 제4장)'은 허용
                findings.append(Finding(r.rid, r.level, i, _clip(s, m.start(), m.end()), r.note))
                break
        for m in re.finditer(r"「([^」]{1,60})」", s):
            inner = re.sub(r"\s*\([^)]*\)$", "", m.group(1).strip())
            if not DOC_SUFFIX.search(inner) and not re.search(r"제\d+조", inner):
                findings.append(Finding("BRACKET", "참고", i, _clip(s, m.start(), m.end()),
                                        "「」는 법령·계획·문서·보고서명에만. 개념·이슈는 ' ' (문서명이면 무시)"))

    # 문서 단위 지표
    REF = re.compile(r"^\s*(\[\d+\]|\d+\)|[A-Z][a-z]+,)|https?://|\.(kr|org|com|go\.kr)\b")
    body_lines = [l for l in lines if not REF.search(l) and len(l.strip()) > 3]
    body_text = "\n".join(body_lines)
    dashes = [(i, l) for i, l in enumerate(lines, 1) if re.search(r"[—―]", l) and not REF.search(l) and len(l.strip()) > 3]
    tail_dashes = [(i, l) for i, l in dashes if not LABEL_DASH.search(l)]
    dash_rate = len(re.findall(r"[—―]", body_text)) / (len(re.sub(r"\s", "", body_text)) or 1) * 10000
    limit = {"research": 6, "brief": 3, "advisory": 2, "common": 6}[dtype]
    if dash_rate > limit:
        for i, l in tail_dashes[:15]:
            findings.append(Finding("EMDASH", "필수", i, _clip(l, l.find("—") if "—" in l else l.find("―"), None),
                                    f"긴 대시 1만 자당 {dash_rate:.1f}회(기준 {limit}회 이하). 꼬리 해설 대시를 끊거나 지운다. 라벨 대시 '(라벨) — 부제'는 허용"))

    contrast_n = sum(1 for f in findings if f.rule == "CONTRAST")
    if contrast_n <= 2:
        findings = [f for f in findings if f.rule != "CONTRAST"]

    curly = len(re.findall(r"‘[^’\d][^’]*’", text)); straight = len(re.findall(r"'[^'\n]{1,40}'", text))
    if curly and straight:
        findings.append(Finding("QUOTEMIX", "참고", 0, f"둥근 ‘’ {curly}곳 · 곧은 '' {straight}곳",
                                "한 문서 안에서 따옴표 모양을 하나로"))
    bold = len(re.findall(r"\*\*[^*\n]+\*\*", text))
    if bold > max(5, nchar // 2000):
        findings.append(Finding("BOLD", "권고", 0, f"굵게 {bold}곳",
                                "본문 볼드 남발. 제목·양식이 정한 자리만(브리프 양식이면 수치·라벨 3~4곳/문단)"))

    st = stats(lines)
    if dtype in ("research", "brief", "advisory") and st["다_종결_비율"] > 0.15:
        findings.append(Finding("STYLE", "권고", 0, f"~다. 종결 {st['다_종결_비율']:.0%}",
                                "개조식 문서인데 서술체 비중이 높다(학술 성격 장이면 무시)"))
    if dtype == "brief" and st["줄길이_중앙값"] > 80:
        findings.append(Finding("LINELEN", "참고", 0, f"줄 중앙값 {st['줄길이_중앙값']}자",
                                "브리프는 40~60자 중앙값이 관측치"))

    order = {"필수": 0, "권고": 1, "참고": 2}
    findings.sort(key=lambda f: (order[f.level], f.rule, f.line))
    return {"version": VERSION, "type": dtype, "stats": st,
            "counts": {k: sum(1 for f in findings if f.level == k) for k in order},
            "findings": [asdict(f) for f in findings]}


def _clip(s: str, a: int, b: int | None, w: int = 28) -> str:
    b = len(s) if b is None else b
    lo, hi = max(0, a - w), min(len(s), b + w)
    return ("…" if lo else "") + s[lo:hi].strip() + ("…" if hi < len(s) else "")


def stats(lines: list[str]) -> dict:
    body = [l.strip() for l in lines if len(l.strip()) >= 20 and not l.strip().startswith(("|", "#", "```"))]
    text = "\n".join(lines)
    nchar = len(re.sub(r"\s", "", text)) or 1
    ends_da = sum(1 for l in body if re.search(r"[가-힣]다\.?$", l))
    ends_ham = sum(1 for l in body if re.search(r"(함|임|음|됨|있음|없음|필요)\.?$", l))
    lens = [len(l) for l in body] or [0]
    per10k = lambda pat: round(len(re.findall(pat, text)) / nchar * 10000, 1)
    return {
        "글자수": nchar,
        "본문줄수": len(body),
        "줄길이_평균": round(statistics.mean(lens), 1),
        "줄길이_중앙값": int(statistics.median(lens)),
        "다_종결_비율": round(ends_da / (len(body) or 1), 3),
        "함임음_종결_비율": round(ends_ham / (len(body) or 1), 3),
        "긴대시_만자당": round(len(re.findall(r"[—―]", "\n".join(body))) / (len(re.sub(r"\s", "", "\n".join(body))) or 1) * 10000, 1),
        "홑낫표_만자당": per10k(r"「"),
        "라벨줄_비율": round(sum(1 for l in body if re.match(r"^[□○ㅇ◯\-·•➊-➓\s]*\(", l)) / (len(body) or 1), 3),
        "판단유보_만자당": per10k(r"사료|것으로 보인다|것으로 판단된다|생각된다"),
        "이는반영꼬리_만자당": per10k(r"이는\s.{0,50}?(반영|의미)"),
    }


# ───────────────────────── 출력 ─────────────────────────

def render_md(path: str, res: dict) -> str:
    c = res["counts"]
    out = [f"# 규칙 점검 — {Path(path).name}", "",
           f"유형: `{res['type']}` · rcheck {res['version']} · **[필수] {c['필수']} / [권고] {c['권고']} / [참고] {c['참고']}**", "",
           "기계로 셀 수 있는 항목만 점검했다. 논증·근거·제언의 질은 스킬 점검표로 따로 판정한다.", "",
           "## 문체 지표", "", "| 지표 | 값 |", "|---|---|"]
    out += [f"| {k} | {v} |" for k, v in res["stats"].items()]
    out += ["", "## 지적", ""]
    if not res["findings"]:
        out.append("지적 없음.")
    cur = None
    for f in res["findings"]:
        key = (f["level"], f["rule"])
        if key != cur:
            cur = key
            rule = next((r for r in WORD_RULES if r.rid == f["rule"]), None)
            title = rule.title if rule else {"BRACKET": "「」 오용", "EMDASH": "긴 대시 과다", "BOLD": "볼드 남발",
                                             "STYLE": "종결형 불일치", "LINELEN": "줄 길이", "QUOTEMIX": "따옴표 혼용"}.get(f["rule"], f["rule"])
            ref = f" ({rule.ref})" if rule else ""
            out += ["", f"### [{f['level']}] {title}{ref}", f"_{f['note']}_", ""]
        loc = f"L{f['line']}" if f["line"] else "문서"
        out.append(f"- {loc}: {f['excerpt']}")
    return "\n".join(out) + "\n"


def render_stats(paths: list[str], sts: list[dict]) -> str:
    names = [Path(p).name for p in paths]
    out = ["| 지표 | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for k in sts[0]:
        out.append(f"| {k} | " + " | ".join(str(s[k]) for s in sts) + " |")
    return "\n".join(out) + "\n"


# ───────────────────────── 자체검사 ─────────────────────────

SELFTEST = [
    ("이 정책은 효과가 있는 것으로 사료된다.", "HEDGE"),
    ("4단 연계 구조를 채택하고 있으며, 이는 글로벌 인식을 반영함", "TAIL"),
    ("공공재 성격을 지님(제2장 제1절에서 상술함)", "XREF"),
    ("출처 https://a.go.kr/x?utm_source=chatgpt.com", "TRACE"),
    ("□ 연구개발 예산이 최근 5년간 정체되어 부족함 — 인력도 함께 줄어 연구실 유지가 곤란함", "DASH2"),
    ("정책의 네 가지 함정을 살펴봄", "COUNT"),
    ("연구에 있어서 중요함", "TRANSLATIONESE"),
    ("규제가 산업을 압박한다", "BANNED"),
    ("▲ 첫째 항목", "QUOTE_MARK"),
    ("「근거 기반 사업관리 체계」의 토대를 제공함", "BRACKET"),
    ("2026-09-23 회의", "DATE"),
    ("2026-10-01까지 제출함", "DATE"),
    ("설명할수 있음", "SPACING"),
    ("'○○ 사회' 대신 「AI 학습데이터 무단 사용」이 문제", "BRACKET"),
]
NEGATIVE = [
    "「인공지능 발전과 신뢰 기반 조성 등에 관한 기본법」 제12조",
    "□ (추진 배경) — 부제는 허용",
    "2026. 9. 23.(수) 회의",
    "13대 과제를 선정함",
    "□ (효과성, 제4장) 지원사업의 성과요인을 분석함",
    "과학기술정보통신부(2024.12.18.), 보도자료",
    "연평균 10.9% 증가(’19~’23년)",
    "□ 첫째, 통합성임 — 선행연구가 분리해 다루던 질문들을 연결함",
    "「제1차 국가전략기술 육성 기본계획(’24~’28)」",
    "근거가 명확하므로 단언함",
]


def selftest() -> int:
    ok = True
    for s, rid in SELFTEST:
        got = {f["rule"] for f in check([s], "advisory")["findings"]}
        if rid not in got:
            ok = False
            print(f"✗ {rid} 미탐: {s}  → {got}")
    for s in NEGATIVE:
        got = {f["rule"] for f in check([s], "research")["findings"]} - {"STYLE", "EMDASH"}
        if got:
            ok = False
            print(f"✗ 오탐: {s} → {got}")
    print("selftest", "통과" if ok else "실패", f"({len(SELFTEST)}+{len(NEGATIVE)}항목)")
    return 0 if ok else 1


# ───────────────────────── CLI ─────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="규칙 점검")
    c.add_argument("file")
    c.add_argument("--type", choices=TYPES, default="common")
    c.add_argument("--json", action="store_true")
    c.add_argument("-o", "--out", help="리포트 저장 경로(.md)")
    s = sub.add_parser("stats", help="문체 지표(여러 파일 비교)")
    s.add_argument("files", nargs="+")
    sub.add_parser("selftest")
    a = ap.parse_args(argv)

    if a.cmd == "selftest":
        return selftest()
    try:
        if a.cmd == "stats":
            sts = [stats(load_lines(Path(f))) for f in a.files]
            print(render_stats(a.files, sts))
            return 0
        res = check(load_lines(Path(a.file)), a.type)
    except (OSError, ValueError, zipfile.BadZipFile, KeyError) as e:
        print(f"입력 오류: {e}", file=sys.stderr)
        return 2
    out = json.dumps(res, ensure_ascii=False, indent=1) if a.json else render_md(a.file, res)
    if a.out:
        Path(a.out).write_text(out, encoding="utf-8")
        print(f"저장: {a.out} — [필수] {res['counts']['필수']} / [권고] {res['counts']['권고']} / [참고] {res['counts']['참고']}")
    else:
        print(out)
    return 1 if res["counts"]["필수"] else 0


if __name__ == "__main__":
    sys.exit(main())
