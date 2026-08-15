# -*- coding: utf-8 -*-
"""
triple_gap_probe.py — 쌍별 폐쇄 한계의 실측 (06 부속 소실험, 2026-07-30 c)

질문: R2가 쌍별로 정확히 놓치는 3-조각 조합(컨테이너 + 개인 2)이 코퍼스에 몇 건 실재하고,
      단일 응답 / 세션 원장 경유 각각에서 실제로 도달 가능한가?

산술: 3조각 {h(집계, n), i1, i2(개인 ⊂ S_h)}가 쌍별 전부 안전 ⇔
      (h,i)쌍 △ = n-1 ≥ k ∧ (i1,i2) disjoint. 잔여 고립 ⇔ n-2 < k.
      ⇒ 구멍 조건: n = k+1 (정확히). 4조각 이상은 n ∈ {k+1, k+2} … 로 일반화.

측정 항목:
  T1. 구조 전수: attr별 n=k+1 컨테이너 수, 3중 조합 수, (m=3까지) 상위 조합 수.
  T2. 단일 응답 도달성: 세 조각을 동시에 R3 통과하면서 잔여에 t3 비자격인 요청자 존재? (0 예상 — 단언)
  T3. 원장 경유 도달성: F_SEC(ER t2 자격)에 개인 2건 원장 주입 + 팀 후보 →
      cl 판정 release(=쌍별 구멍의 실물 유출) 확인. R2-diff 쌍별 검사가 △=5≥k로 침묵함을 기록.
  T4. 기공개쌍 audit_alert 경로: 위험쌍 양쪽을 원장에 주입 → audit_alert obligation 발행 확인.
  T4b. 불변식 정밀화의 구성적 확인: 이번 판정이 공개한 조각이 개입한 위험 간선이 0건임을
      직접 검사. 구현이 보장하는 것은 전면 폐쇄가 아니라 「현재 판정이 새 위험을
      추가하지 않는다」이며, T4b가 그 명제 자체를 시험한다.
산출: triple_gap.csv (T1 전수) + triple_gap_demo.csv (T3 시연 실물)
      + triple_gap_t4_edges.csv (T4 위험 간선 계보) + 콘솔 판정 (T2~T4b).

계보 주석 (2026-08-04 재실행에서 확인):
      본 프로브의 T4는 2026-07-30 최초 실행 시 코어의 사후 불변식 단언
      (`assert not (use_r2 and e and e[0] == "risk")`)을 터뜨렸고, 그것이 불변식
      정밀화를 강제했다. 해소 루프는 원장-원장 쌍을 audit_alert로 이관하면서
      continue 하는데, 사후 단언만 `final = rel + ledger` 전체를 순회해 방금 감사로
      넘긴 쌍을 다시 위반으로 판정했기 때문이다. 평가 케이스에서는 원장-원장
      위험쌍이 발생하지 않아 그 모순이 드러나지 않았고, T4가 처음으로 그 경로를
      밟았다. 코어 패치(2026-08-04, cl() 사후 단언에 both_ledger 예외)로 해소.
      T4b는 그 이후에도 보호 범위가 줄지 않았음을 매 실행마다 재확인한다.

개정 2026-08-08 (A3): T5 블록 추가 — turn-order 순열(3!=6) × k∈{3,5} 강건성.
      T3의 시연을 "컨테이너 결정 + 개인 2 원장" 고정 구조에서 일반화하여,
      세 조각 {h, i1, i2} 중 어느 것이 '현재 결정(cand)'이고 나머지가 원장인지를
      6가지로 바꿔가며, 각 순서의 마지막 turn에서 누출이 완성되는지 판정한다.
      k=5는 n=6 밴드(h=ER컨테이너), k=3은 대응 밴드에서 경계 이동을 확인.
      §7-C [A3-PENDING] 강건성 1문장의 실측 근거. T1~T4b·산출 CSV 무변경.
개정 2026-08-04: T3가 컨테이너 fid와 n만 출력하고 개인 조각 id·subject set·쌍별 △를
      남기지 않아 논문 부록(§I "Demonstrated sequence")이 요구하는 실물을 아티팩트로
      제시할 수 없었음. T3 블록에 조각 3건의 id·tier·subject set, 쌍별 대칭차 3종,
      삼자 잔여 주체 목록 출력을 추가하고 동일 내용을 triple_gap_demo.csv로 저장.
      판정 로직·단언·T1/T2/T4는 무변경 — 결정론 산출물(triple_gap.csv) 동일 보장.
"""
import os, sys, csv, itertools, importlib.util
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("core", os.path.join(HERE, "06_derivation_v2.py"))
M = importlib.util.module_from_spec(spec)
sys.argv = [sys.argv[0], "--gate-only"]  # 게이트만 (평가 러너 재실행 방지)
try:
    spec.loader.exec_module(M)
except SystemExit as e:
    if e.code not in (0, None): raise

FRAGS, STYPE, PT, K = M.FRAGS, M.STYPE, M.PERSON_TYPES, M.K_HEAD
print(f"\n=== 쌍별 폐쇄 한계 실측 (k={K}) ===")

# T1: 구조 전수 — 컨테이너(t2, ids) × 그 부분집합 개인(t3) 조합
t3_by_subj = defaultdict(dict)   # attr -> subject -> fid
for f in FRAGS.values():
    if STYPE.get(f["attr"]) in PT and f["tier"] == 3 and f["ids"] and len(f["ids"]) == 1:
        t3_by_subj[f["attr"]][next(iter(f["ids"]))] = f["fid"]

rows, t1 = [], defaultdict(int)
holes = []
for f in sorted(FRAGS.values(), key=lambda x: x["fid"]):
    if STYPE.get(f["attr"]) not in PT or f["tier"] != 2 or not f["ids"]:
        continue
    n = len(f["ids"])
    inds = sorted(s for s in f["ids"] if s in t3_by_subj[f["attr"]])
    for m in (2, 3):
        # 쌍별 전부 안전 ⇔ n-1 ≥ k ; 잔여 고립 ⇔ 0 < n-m < k
        if n - 1 >= K and 0 < n - m < K and len(inds) >= m:
            cnt = len(list(itertools.combinations(inds, m)))
            rows.append([f["attr"], f["fid"], n, m, n - m, cnt])
            t1[(f["attr"], m)] += cnt
            if m == 2 and not holes:
                holes.append((f, [t3_by_subj[f["attr"]][s] for s in inds[:2]]))

path = os.path.join(M.OUT, "triple_gap.csv")
import tempfile
fd, tmp = tempfile.mkstemp(dir=M.OUT, suffix=".tmp")
with os.fdopen(fd, "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.writer(fh); w.writerow(["attr","container","n","m_individuals","residual","combinations"])
    for r in rows: w.writerow(r)
os.replace(tmp, path)
print(f"T1 구조 전수 → triple_gap.csv {len(rows)}행")
for (attr, m), c in sorted(t1.items()):
    print(f"   attr={attr} m={m}: 조합 {c}건 (컨테이너 n∈{{{K+1 if m==2 else f'{K+1},{K+2}'}}})")
assert holes, "n=k+1 컨테이너 미발견 — 코퍼스 전제 확인 필요"

# T2: 단일 응답 도달성 (0 단언)
reach_single = 0
for f, ifids in ((f, i) for f, i in holes for _ in [0]):
    pass
for f in [h[0] for h in holes]:
    inds = sorted(s for s in f["ids"] if s in t3_by_subj[f["attr"]])
    for u in [M.U(r) for r in sorted(M.PERSONA)] + [M.staff("E0114"), M.staff("E0113")]:
        ok_h = M.admissible(u, f)[0]
        if not ok_h: continue
        for i1, i2 in itertools.combinations(inds, 2):
            f1, f2 = FRAGS[t3_by_subj[f["attr"]][i1]], FRAGS[t3_by_subj[f["attr"]][i2]]
            if M.admissible(u, f1)[0] and M.admissible(u, f2)[0]:
                resid = f["ids"] - {i1, i2}
                if not all(M.grant_t3(u, f["attr"], s) for s in resid):
                    reach_single += 1
print(f"T2 단일 응답 도달 가능 유출: {reach_single}건 " +
      ("✓ (자격 구조가 전면 차단 — 단언 통과)" if reach_single == 0 else "✗ 예상 밖!"))
assert reach_single == 0

# T3: 원장 경유 도달성 — F_SEC × ER 컨테이너 n=6
er_holes = [h for h in holes if h[0]["attr"] == "ER"]
demo = er_holes[0] if er_holes else holes[0]
h, (i1, i2) = demo[0], demo[1]
u = M.U("F_SEC")
r = M.run_case("T3", u, [h["fid"]], [i1, i2], K)
act, rule, why = r["res"]["verdicts"][h["fid"]]
pair_delta = len(h["ids"]) - 1

# --- 시연 실물 (2026-08-04 추가): 조각 3건의 id·subject set, 쌍별 △, 삼자 잔여
S_h = set(h["ids"])
S_1 = set(FRAGS[i1]["ids"] or [])
S_2 = set(FRAGS[i2]["ids"] or [])
residual = sorted(S_h - S_1 - S_2)
print(f"T3 원장 경유 (F_SEC, 컨테이너 {h['fid']} n={len(S_h)}, 원장 개인 2건):")
print(f"   container  {h['fid']}  attr={h['attr']} tier={h['tier']} "
      f"n={len(S_h)} subjects={sorted(S_h)}")
print(f"   ledger#1   {i1}  attr={FRAGS[i1]['attr']} tier={FRAGS[i1]['tier']} "
      f"subjects={sorted(S_1)}")
print(f"   ledger#2   {i2}  attr={FRAGS[i2]['attr']} tier={FRAGS[i2]['tier']} "
      f"subjects={sorted(S_2)}")
print(f"   쌍별 △: (h,i1)={len(S_h ^ S_1)}  (h,i2)={len(S_h ^ S_2)}  "
      f"(i1,i2)={len(S_1 ^ S_2)}  vs k={K}  → 전 쌍 ≥k 이므로 R2-diff 침묵")
print(f"   삼자 잔여: {residual} ({len(residual)}명 < k={K}) → 고립")
print(f"   cl 판정 = {act}/{rule} — 쌍별 △={pair_delta}≥k={K}로 R2-diff 침묵, "
      f"잔여 {len(residual)}명<k 고립 = **쌍별 구멍의 실물 유출** (한계 실측)")

demo_path = os.path.join(M.OUT, "triple_gap_demo.csv")
fd, tmp = tempfile.mkstemp(dir=M.OUT, suffix=".tmp")
with os.fdopen(fd, "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.writer(fh)
    w.writerow(["role", "fragment_id", "attr", "tier", "n_subjects", "subjects",
                "delta_vs_container", "k", "verdict", "rule"])
    w.writerow(["container", h["fid"], h["attr"], h["tier"], len(S_h),
                ";".join(sorted(S_h)), "", K, act, rule])
    w.writerow(["ledger_1", i1, FRAGS[i1]["attr"], FRAGS[i1]["tier"], len(S_1),
                ";".join(sorted(S_1)), len(S_h ^ S_1), K, "", ""])
    w.writerow(["ledger_2", i2, FRAGS[i2]["attr"], FRAGS[i2]["tier"], len(S_2),
                ";".join(sorted(S_2)), len(S_h ^ S_2), K, "", ""])
    w.writerow(["residual", "", h["attr"], "", len(residual),
                ";".join(residual), "", K, "isolated", ""])
os.replace(tmp, demo_path)
print(f"   → triple_gap_demo.csv 저장 (시연 실물 4행)")

assert act == "release", "예상과 다름 — 쌍별 규칙이 잡았다면 산술 재검토"

# T4: 기공개쌍 audit_alert
team = M.CANARY and None
tf = itf = None
for f in FRAGS.values():
    if f["attr"] == "ER" and f["tier"] == 2 and f["ids"] and f["n"] == 3 and "E_F_CMP" in f["ids"]:
        tf = f["fid"]
    if f["attr"] == "ER" and f["tier"] == 3 and f["sid"] == "E0027":
        itf = f["fid"]
r = M.run_case("T4", M.U("F_SEC"), [], [tf, itf], 3)
alerts = [o for o in r["res"]["obligations"] if o[0] == "audit_alert"]
print(f"T4 기공개 위험쌍 (k=3, 원장에 팀+개인): audit_alert {len(alerts)}건 발행 "
      + ("✓" if alerts else "✗ 미발행!"))
assert alerts

# --- T4b (2026-08-04 추가): 불변식의 정확한 형태를 명제로 검사
#     주장 = 「현재 판정이 새 위험을 추가하지 않는다」(신규 공개 개입 쌍 한정).
#     전면 폐쇄가 아니라는 점이 논문 부록 I의 한계 문장이며, 여기서 실행으로 확인한다.
led_t4 = {tf, itf}
released_t4 = sorted(fid for fid, (a, _, _) in r["res"]["verdicts"].items() if a == "release")
risk_edges = [e for e in r["res"]["edges"] if e[3] == "risk"]
new_risk = [e for e in risk_edges if not (e[1] in led_t4 and e[2] in led_t4)]
print(f"T4b 불변식 정밀화 검사 — 위험 간선 {len(risk_edges)}건, "
      f"이번 판정의 공개 조각 {len(released_t4)}건")
for e in risk_edges:
    both = e[1] in led_t4 and e[2] in led_t4
    print(f"   {e[0]:4s} {e[1]} x {e[2]} (|delta|={e[4]}) — "
          + ("양단 원장: 통제 시점 상실 -> 감사 이관" if both
             else "신규 공개 개입 -> 차단 대상"))
print(f"   이번 판정이 새로 만든 위험: {len(new_risk)}건 "
      + ("✓" if not new_risk else "✗"))
print("   => 구현이 보장하는 불변식 = 「현재 판정이 새 위험을 추가하지 않는다」;")
print("      전면 폐쇄가 아님 (원장-원장 쌍은 감사 소관). 2026-07-30 T4가 강제한 정밀화이며,")
print("      그 이전 코어에서는 본 케이스가 사후 단언을 터뜨렸다 (계보: 파일 상단 주석).")
assert not new_risk, "신규 공개가 개입한 위험 간선 존재 — 정밀화 범위를 넘어섬"

t4_path = os.path.join(M.OUT, "triple_gap_t4_edges.csv")
fd, tmp = tempfile.mkstemp(dir=M.OUT, suffix=".tmp")
with os.fdopen(fd, "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.writer(fh)
    w.writerow(["edge_kind", "fid_a", "fid_b", "risk", "delta_size",
                "a_in_ledger", "b_in_ledger", "disposition"])
    for e in r["res"]["edges"]:
        a_led, b_led = e[1] in led_t4, e[2] in led_t4
        if e[3] != "risk":
            disp = "not_risk"
        elif a_led and b_led:
            disp = "audit_alert (control point already passed)"
        else:
            disp = "blocked (current decision intervenes)"
        w.writerow([e[0], e[1], e[2], e[3], e[4], a_led, b_led, disp])
os.replace(tmp, t4_path)
print(f"   -> triple_gap_t4_edges.csv 저장 ({len(r['res']['edges'])}행)")

# ============================================================
# T5 (A3, 2026-08-08): turn-order 순열 × k 강건성
#   불변식 후보: "세 조각의 도착 순서와 무관하게, 마지막 조각의 결정 시점에
#   누출이 완성된다 (앞 두 조각은 원장, 현재 조각이 세 번째)."
#   순열: {h,i1,i2}의 3!=6 순서. 각 순서의 마지막을 cand, 앞 둘을 ledger로 cl() 호출.
#   완성 판정: cand가 release되고 3자 잔여 <k 로 고립이 실현되는가.
# ============================================================
import itertools as _it, tempfile as _tf
print("\n=== T5 turn-order 순열 × k 강건성 (A3) ===")
u5 = M.U("F_SEC")
t5_rows, t5_summary = [], {}

def _pick_triple(kk):
    """n=kk+1 컨테이너 + 그 부분집합 개인 2건 (없으면 None)."""
    for f in sorted(FRAGS.values(), key=lambda x: x["fid"]):
        if STYPE.get(f["attr"]) not in PT or f["tier"] != 2 or not f["ids"]:
            continue
        if len(f["ids"]) != kk + 1:
            continue
        inds = sorted(s for s in f["ids"] if s in t3_by_subj[f["attr"]])
        if len(inds) >= 2:
            return f["fid"], t3_by_subj[f["attr"]][inds[0]], t3_by_subj[f["attr"]][inds[1]]
    return None

for k5 in (5, 3):
    trip_sel = _pick_triple(k5)
    if trip_sel is None:
        print(f"  k={k5} [n={k5+1}]: 해당 밴드 트리플 부재 — 스킵 (코퍼스에 n={k5+1} 컨테이너 없음)")
        t5_summary[k5] = (None, 0)
        continue
    hfid, i1_5, i2_5 = trip_sel
    trip = [hfid, i1_5, i2_5]
    S_all = {fid: set(FRAGS[fid]["ids"] or []) for fid in trip}
    per_k = []
    for perm in _it.permutations(trip):
        *led, cur = perm                 # 앞 두 조각 = 원장, 마지막 = 현재 결정
        r5 = M.cl(u5, [cur], list(led), k=k5)
        act5, rule5, why5 = r5["verdicts"][cur]
        # 3자 잔여 = 컨테이너 subjects - (개인 두 조각 subjects). 순서 무관 집합연산.
        resid5 = sorted(S_all[hfid] - S_all[i1_5] - S_all[i2_5])
        # "누출 완성" = 마지막이 컨테이너이고 그것이 release되어 잔여<k 고립이 실현
        cur_is_container = (cur == hfid)
        leaked = (act5 == "release" and cur_is_container and 0 < len(resid5) < k5)
        # 개인 조각이 마지막인 순서: 그 개인은 R3 자격이면 release되나 '고립'은
        #   컨테이너가 이미 원장에 있을 때만 성립 → 동일 잔여를 원장측에서 실현
        led_has_container = (hfid in led)
        leak_via_ledger = (act5 == "release" and not cur_is_container
                           and led_has_container and 0 < len(resid5) < k5)
        completed = leaked or leak_via_ledger
        per_k.append(completed)
        t5_rows.append([k5, "→".join(perm), cur, "container" if cur_is_container else "individual",
                        act5, rule5, len(resid5), int(completed), why5[:40]])
    t5_summary[k5] = (sum(per_k), len(per_k))
    band = f"n={k5+1} (k+1)"
    print(f"  k={k5} [{band}]: 6순열 중 누출 완성 {sum(per_k)}/6 "
          + ("✓ 전 순열 동일" if sum(per_k) == 6 else
             f"— 순서 의존 (완성 {sum(per_k)}건)"))
    for row in t5_rows[-6:]:
        mark = "LEAK" if row[7] else "safe"
        print(f"     {row[1]:36s} last={row[3]:10s} {row[4]:7s} resid={row[6]} [{mark}]")

# 판정 문장 (원고 §7-C 직결)
k5_full = (all(c == n for c, n in t5_summary.values() if c is not None)
           and any(c is not None for c, _ in t5_summary.values()))
if k5_full:
    print("  ⇒ 불변: 6순열 × k∈{3,5} 전부에서 누출이 마지막 turn에 완성 — "
          "경계는 도착 순서와 무관 (산술적 필연).")
else:
    print("  ⇒ 순서 의존 관측 — 불변식을 순서 조건부로 정밀화 필요 (분기표 참조).")

t5_path = os.path.join(M.OUT, "triple_gap_t5_permutations.csv")
_fd, _tmp = _tf.mkstemp(dir=M.OUT, suffix=".tmp")
with os.fdopen(_fd, "w", newline="", encoding="utf-8-sig") as _fh:
    _w = csv.writer(_fh)
    _w.writerow(["k","permutation","last_fragment","last_role","verdict","rule",
                 "residual_size","leak_completed","reason"])
    for row in t5_rows: _w.writerow(row)
os.replace(_tmp, t5_path)
print(f"  → triple_gap_t5_permutations.csv 저장 ({len(t5_rows)}행)")

print("\n판정: 쌍별 한계는 n=k+1에서 실재·정량화됨 / 단일 응답은 자격 구조가 전면 차단 /"
      "\n      도달 경로는 원장 경유 유일 / 기공개쌍은 audit_alert로 감사 이관 /"
      "\n      보장 불변식은 전면 폐쇄가 아니라 「현재 판정이 새 위험을 추가하지 않는다」(T4b).")
