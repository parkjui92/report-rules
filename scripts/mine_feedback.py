#!/usr/bin/env python3
"""mine_feedback — Claude Code 세션 기록에서 '내가 준 문체 피드백'을 뽑는다 (표준 라이브러리만).

자기 규칙을 만들 때 첫 재료다. 세션 기록(~/.claude/projects/*/*.jsonl)에서
사용자 발화만 꺼내고, 지적·교정 신호어가 든 것을 골라 프로젝트(cwd)별로 모은다.

사용:
  python3 mine_feedback.py -o feedback.md                  # 신호어 필터(기본)
  python3 mine_feedback.py --all -o all_msgs.md            # 전체 발화
  python3 mine_feedback.py --since 2026-06-01 --signals "번역투,AI티,개조식"
  python3 mine_feedback.py --root /다른/경로/projects

개인정보: 결과 파일에는 대화 원문이 들어간다. 공유·공개하지 말고, 규칙으로 옮길 때는
제3자 이름·기관명을 역할명으로 바꿔라.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

DEFAULT_SIGNALS = [
    "하지 마", "하지말", "말고", "빼줘", "빼자", "삭제", "바꿔", "고쳐", "다시",
    "너무", "이상해", "어색", "어려워", "어렵고", "모호", "부실", "길어", "짧아",
    "번역투", "AI티", "AI 티", "AI가 쓴", "그럴듯", "방어적", "단정", "과장", "오바",
    "개조식", "두괄식", "문체", "표현", "워딩", "단어", "용어",
    "근거", "출처", "검증", "할루시네이션", "수치", "합산",
    "양식", "편집", "서식", "파란색", "볼드", "표 말고", "삽도",
    "좋아", "좋다", "이대로", "잘했", "오케이",
]
SKIP_PREFIX = ("<", "[Request interrupted", "Caveat:", "/")


def user_texts(rec: dict) -> list[str]:
    if rec.get("type") != "user":
        return []
    msg = rec.get("message") or {}
    c = msg.get("content")
    if isinstance(c, str):
        return [c]
    out = []
    if isinstance(c, list):
        for b in c:
            if isinstance(b, dict) and b.get("type") == "text":
                out.append(b.get("text", ""))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(Path.home() / ".claude" / "projects"))
    ap.add_argument("--since", help="YYYY-MM-DD 이후 발화만")
    ap.add_argument("--signals", help="쉼표로 구분한 신호어(기본 목록 대체)")
    ap.add_argument("--all", action="store_true", help="신호어 필터 없이 전체")
    ap.add_argument("--maxlen", type=int, default=600, help="이보다 긴 발화(붙여넣기)는 제외")
    ap.add_argument("-o", "--out", default="feedback.md")
    a = ap.parse_args()

    signals = [s.strip() for s in a.signals.split(",")] if a.signals else DEFAULT_SIGNALS
    by_cwd: dict[str, list[tuple[str, str]]] = defaultdict(list)
    seen: set[str] = set()
    total = kept = 0
    for f in sorted(Path(a.root).glob("*/*.jsonl")):
        for line in f.open(encoding="utf-8", errors="replace"):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = (rec.get("timestamp") or "")[:10]
            if a.since and ts and ts < a.since:
                continue
            for t in user_texts(rec):
                t = t.strip()
                if not t or t.startswith(SKIP_PREFIX) or len(t) > a.maxlen:
                    continue
                total += 1
                if not a.all and not any(s in t for s in signals):
                    continue
                key = re.sub(r"\s+", " ", t)
                if key in seen:
                    continue
                seen.add(key)
                kept += 1
                by_cwd[rec.get("cwd") or f.parent.name].append((ts, key))

    lines = [f"# 피드백 채굴 결과", "",
             f"- 원천: `{a.root}` · 사용자 발화 {total}건 중 {kept}건 · 필터: {'없음' if a.all else '신호어 ' + str(len(signals)) + '개'}",
             "- 다음 단계: 같은 지적이 여러 프로젝트·날짜에 반복되는 것을 규칙 후보로 묶는다(`docs/build-your-own.md` 2단계)", ""]
    for cwd in sorted(by_cwd, key=lambda k: -len(by_cwd[k])):
        lines += [f"## {Path(cwd).name or cwd} ({len(by_cwd[cwd])}건)", ""]
        for ts, t in sorted(by_cwd[cwd]):
            lines.append(f"- `{ts}` {t}")
        lines.append("")
    Path(a.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"저장: {a.out} — {kept}/{total}건, 프로젝트 {len(by_cwd)}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
