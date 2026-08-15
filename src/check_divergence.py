# -*- coding: utf-8 -*-
"""
check_divergence.py — R3-only arm 사전 검증 (1단계)

목적: query_set_v2.csv에서 per-item↔set-level 분기(peritem=permit ∧ cl=withhold)
      9건을 실물 확인하고 규칙 귀속(gt_cl_rule)을 출력한다.

기대치 (2026-07-31 CSV 재대조 증보 기준):
  - 전체 559행
  - 분기 9건 = governed(probe) 1건 [V0433, F_SEC, ER t2, R1] + adversarial 8건
    [F7-diff-R1 3 · F7-diff-R2 3 · F7-join 2]
  - 확인 대상 긴장: 문서상 "R1 6 · R2-diff 3" vs 개별 분해 "R1 4 + R2-diff 3 +
    R2-link(join) 2" — gt_cl_rule 실물 표기로 판가름

사용법:
  cd <findw 루트>          (deriv\query_set_v2.csv 가 보이는 폴더)
  python check_divergence.py
  또는: python check_divergence.py <csv 경로>
"""

import sys
import pandas as pd

# ---------------------------------------------------------------- CSV 로드
CANDIDATES = [
    "deriv/query_set_v2.csv",
    "out07/query_set_v2.csv",
    "query_set_v2.csv",
]
path = sys.argv[1] if len(sys.argv) > 1 else None
if path is None:
    import os
    for c in CANDIDATES:
        if os.path.exists(c):
            path = c
            break
if path is None:
    print("[중단] query_set_v2.csv 를 찾지 못함. 경로를 인자로 주세요:")
    print("  python check_divergence.py 경로\\query_set_v2.csv")
    sys.exit(1)

df = pd.read_csv(path)
print(f"파일: {path}")
print(f"전체 행수: {len(df)}   (기대: 559)")
print()

# ------------------------------------------- 열 이름 자동 탐색 (스키마 방어)
cols = list(df.columns)
print("열 목록:", cols)
print()

def find_col(keywords, exclude=()):
    """키워드를 모두 포함하고 exclude를 포함하지 않는 첫 열 이름."""
    for c in cols:
        lc = c.lower()
        if all(k in lc for k in keywords) and not any(x in lc for x in exclude):
            return c
    return None

col_peritem = find_col(["peritem"], exclude=["tier"]) or find_col(["per_item"])
col_cl_act  = find_col(["cl", "action"]) or find_col(["cl", "verdict"])
col_rule    = find_col(["cl", "rule"]) or find_col(["rule"])
col_split   = find_col(["split"]) or find_col(["family"]) or find_col(["corpus"])
col_qid     = find_col(["query", "id"]) or find_col(["qid"]) or cols[0]

# peritem 열이 permit/deny 문자열이 아닐 수도 있으므로 값 확인
print("탐색된 열 매핑:")
print(f"  per-item 판정 : {col_peritem}")
print(f"  set-level 행동: {col_cl_act}")
print(f"  규칙 귀속     : {col_rule}")
print(f"  split         : {col_split}")
print(f"  query id      : {col_qid}")
print()

missing = [n for n, c in [("per-item", col_peritem), ("set-level", col_cl_act)] if c is None]
if missing:
    print(f"[중단] 필수 열을 못 찾음: {missing}")
    print("위 '열 목록'을 통째로 복사해서 알려주세요 — 스크립트를 열 이름에 맞춰 수정합니다.")
    sys.exit(1)

# 값 도메인 출력 (permit/deny 표기 확인)
print(f"{col_peritem} 값 분포:")
print(df[col_peritem].value_counts(dropna=False).to_string())
print()
print(f"{col_cl_act} 값 분포:")
print(df[col_cl_act].value_counts(dropna=False).to_string())
print()

# ------------------------------------------------------------ 분기 추출
pv = df[col_peritem].astype(str).str.lower()
cv = df[col_cl_act].astype(str).str.lower()

permit_mask   = pv.str.contains("permit") | pv.isin(["1", "true"])
withhold_mask = cv.str.contains("withhold") | cv.str.contains("deny")

d = df[permit_mask & withhold_mask]
print("=" * 60)
print(f"분기 건수 (peritem=permit ∧ cl=withhold): {len(d)}   (기대: 9)")
print("=" * 60)
print()

if col_split:
    print("split별 분해:   (기대: probe 1 + adversarial 8)")
    print(d.groupby(col_split).size().to_string())
    print()

show_cols = [c for c in [col_qid, col_split, col_rule] if c]
# obligation / family 계열 열이 있으면 같이 표시
for extra_kw in ["obligation", "attack", "f7", "subfamily"]:
    ec = find_col([extra_kw])
    if ec and ec not in show_cols:
        show_cols.append(ec)

print("분기 행 전체:")
print(d[show_cols].to_string(index=False))
print()

# ------------------------------------------------------------ 규칙 귀속 집계
if col_rule:
    print("규칙 귀속 집계:   (문서상 'R1 6 · R2-diff 3' vs 분해상 'R1 4 + R2-diff 3 + join 2' — 실물 판가름)")
    print(d[col_rule].value_counts(dropna=False).to_string())
    print()

# ------------------------------------------------------------ 판정 요약
ok_total = len(d) == 9
qids = d[col_qid].astype(str).tolist()
ok_v0433 = any("V0433" in q for q in qids)
print("-" * 60)
print(f"[{'PASS' if ok_total else 'FAIL'}] 분기 총수 == 9")
print(f"[{'PASS' if ok_v0433 else 'FAIL'}] V0433 포함 (governed 유일 분기)")
if ok_total and ok_v0433:
    print("→ 1단계 통과. 규칙 귀속 출력(위)을 확인 후 2단계(러너 arm 추가) 진행.")
else:
    print("→ 기대치 불일치. 출력 전체를 복사해서 공유 — 원인 규명 전 2단계 진행 금지.")
