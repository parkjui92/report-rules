# report-rules

**한국어 보고서 작성 규칙 + 초안 점검기** — 정책연구보고서·기획보고서, 브리프·추진계획(안)·보고자료, 자문의견서·검토의견서를 위한 Claude Code 스킬.

- **규칙 4권**: 공통 / 연구보고서 / 브리프·추진계획(안) / 자문의견서
- **점검기 `rcheck.py`**: 기계로 셀 수 있는 규칙 20여 종을 초안 전체에 돌려 `[필수]/[권고]/[참고]` 리포트를 낸다. `.md` `.hwpx` `.docx` 입력, 표준 라이브러리만
- **자기 규칙 만들기**: 세션 피드백 채굴 스크립트와 초안→최종본 대조 절차 — 이 규칙을 만든 방법 그대로

## 무엇이 다른가

보고서 작성 요령은 많지만 대부분 원칙 나열이다. 이 규칙은 **한 연구자가 AI 초안을 직접 고친 흔적**에서 뽑았다.

| 근거 | 규모 |
|---|---|
| 저자가 마무리한 보고서·브리프·의견서의 초안→최종본 대조 | 약 45건 |
| AI 작업 세션에서 저자가 한 지적·승인 | 856건 정독 |
| 기존 규칙 파일 통합(충돌 23건 판정) | 18종 |
| 외부 표준 원문 대조 — 법령 조문, 행정안전부 「행정업무운영 편람」·「정책연구관리 업무편람」, 국립국어원 『쉬운 공문서 쓰기 길잡이』, RAND·HKS·DHS·IDRC·ODI 등 | 쪽수까지 확인 ([docs/sources.md](docs/sources.md)) |

실측에서 나온 규칙 예:
- **판단은 단언하되, 상대에게 요구하는 문장만 제안형으로** — 저자는 의견서에서 `~할 것`을 `~하면 좋을 것으로 판단함`으로 바꿨지만, 보고서의 판단 문장에는 `사료됨`을 한 번도 쓰지 않았다
- **긴 대시(—) 꼬리 해설이 AI 초안의 가장 뚜렷한 표지** — 저자 최종본 1만 자당 0.9~5.1회, AI 초안 11.5~50회. 한 보고서에서 208개를 57개로 줄였다
- **「」는 법령·문서명에만, 개념은 ' '** · **추정 수치는 합산식과 항별 출처를 한 줄로** · **내부 작업자료(RFP·회의록·메일)는 출처가 아니다**

## 설치

```bash
git clone https://github.com/parkjui92/report-rules.git ~/.claude/skills/report-rules
```
Claude Code가 보고서·의견서 작업에서 스킬을 불러온다. 스크립트만 쓸 수도 있다.

## 점검기

```bash
python3 scripts/rcheck.py check 초안.hwpx --type research          # research | brief | advisory | common
python3 scripts/rcheck.py check 의견서.md --type advisory -o 점검.md
python3 scripts/rcheck.py stats 초안.hwpx 최종본.hwpx               # 문체 지표 전후 비교
python3 scripts/rcheck.py selftest
```
예시: `python3 scripts/rcheck.py check examples/sample_draft.md --type brief`

점검기는 **오탐이 있다**(특히 「」·띄어쓰기·최상급). 판단이 필요한 항목(논증 구조·근거의 크기·제언의 실행성)은 점검하지 않는다 — 규칙 파일의 점검표로 따로 판정한다.

## 내 규칙 만들기

이 규칙은 한 사람의 문체다. 자기 문서에서 다시 뽑으면 더 잘 맞는다 → [docs/build-your-own.md](docs/build-your-own.md)

```bash
python3 scripts/mine_feedback.py -o feedback.md        # Claude Code 세션 기록에서 내 지적 모으기
python3 scripts/rcheck.py stats 초안.hwpx 최종본.hwpx   # 내가 고친 방향 재기
```

## 범위 밖
학술논문(학회 투고 규정이 따로 있다), 슬라이드, 정부 R&D 제안서(평가지표 대응이 따로 있다).

## 라이선스
MIT (스크립트와 규칙 문서). 인용한 법령·공공 편람·외부 가이드는 이 저장소에 포함하지 않았고 각자의 이용 조건을 따른다 — [docs/sources.md](docs/sources.md)의 링크에서 받는다.
