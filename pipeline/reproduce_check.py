# -*- coding: utf-8 -*-
"""
reproduce_check.py — results/*.json 을 HANDOFF_2026-07-26_v2design.md §4 실측치와 대조

이전 세션(컨테이너) 실측 = 이번 실행(로컬) 이어야 한다. SEED=42 고정이므로
하나라도 어긋나면 원본 데이터나 스크립트가 다른 것이다.

사용법 (findw_v2 폴더에서):  python reproduce_check.py
"""
import glob, json, sys

# HANDOFF §4 "DB 최종 상태" + "조각 12속성 커버"
EXP_TABLES = {
    # L1 Berka 원본
    "district": 77, "account": 4500, "client": 5369, "disp": 5369,
    "loan": 682, "card": 892, "pay_order": 6471, "trans": 1056320,
    # L2 조직·인사
    "dim_org": 115, "dim_employee": 595, "fact_payroll": 7140, "trust_signal": 7140,
    # L3 거버넌스 (기여 레이어)
    "policy_attr": 12, "policy_cell": 85, "policy_classification": 4,
    "policy_clearance": 14, "gold_report": 12, "report_fragment": 2605,
}
EXP_FRAG_BY_ATTR = {
    "RS": 78, "TA": 78, "AB": 78, "LN": 139, "RM": 79, "CP": 138,
    "FA": 116, "ER": 712, "PB": 711, "PH": 175, "AL": 175, "SC": 126,
}

files = sorted(glob.glob("results/*.json"))
if not files:
    sys.exit("[중단] results/*.json 이 없습니다. 5단계를 먼저 실행하십시오.")

# 단계마다 DB가 누적되므로 뒤 단계 값이 최신이다
tables, key, stages = {}, {}, []
for f in files:
    d = json.load(open(f, encoding="utf-8"))
    stages.append((d.get("stage", f), d.get("passed"), d.get("elapsed_sec"), d.get("fail_lines")))
    db = d.get("db") or {}
    tables.update(db.get("tables") or {})
    key.update(db.get("key") or {})

allok = True

print("=== 단계 통과 여부 ===")
for st, ok, sec, fl in stages:
    allok &= (ok is True)
    print(f"  {st:20s} {'PASS' if ok else ('FAIL' if ok is False else 'INCOMPLETE'):10s} "
          f"{sec}s  {fl if fl else ''}")

print("\n=== 테이블 행수 (HANDOFF §4 대조) ===")
for t, exp in EXP_TABLES.items():
    got = tables.get(t)
    if got is None:
        print(f"  {t:22s} {'—':>10s}  확인불가 (json에 없음)")
        continue
    ok = (got == exp); allok &= ok
    print(f"  {t:22s} {got:>10,}  {'OK' if ok else f'MISMATCH (기대 {exp:,})'}")

print("\n=== 조각 12속성 커버 (합 2,605) ===")
raw = key.get("frag_by_attr")
if raw is None:
    print("  확인불가 — json 에 frag_by_attr 키가 없습니다")
else:
    got = dict((r[0], r[1]) for r in raw) if isinstance(raw, list) else dict(raw)
    total = 0
    for a, exp in EXP_FRAG_BY_ATTR.items():
        g = got.get(a)
        ok = (g == exp); allok &= ok
        total += g or 0
        print(f"  {a:4s} {('—' if g is None else g):>6}  {'OK' if ok else f'MISMATCH (기대 {exp})'}")
    zero = [a for a, v in got.items() if not v]
    print(f"  합계 {total:,}  ·  0개인 속성: {zero if zero else '없음 (v1은 3속성이 0이었다)'}")

for label, k in [("basis 분포", "basis_dist"), ("canary 지정", "canary"),
                 ("tier × classification", "tier_x_class")]:
    if k in key:
        print(f"\n=== {label} ===\n  {key[k]}")

print("\n" + ("재현 확인 — 이전 세션 실측치와 전부 일치합니다."
              if allok else
              "불일치 항목이 있습니다. 위 MISMATCH 를 확인하십시오."))
sys.exit(0 if allok else 1)
