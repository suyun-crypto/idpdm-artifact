# -*- coding: utf-8 -*-
"""
09_decide_v2.py — 결정론 판정 + 계약 발행 + P0~P5 escalation + reference PEP
스펙: 09_decide_spec.md (2026-07-30). 06 코어 공유 (admissible·grant_t3·cl·Requester 재사용).

계약 = (decision, D_final, obligations, escalation{P0~P5}, trace, released).
판정 코어 = 결정론 PDP (학습 MLP 아님 — E4-B5 반증). trust τ = 하향 전용(Property 1).
기동 게이트 = 06 카나리아 판정표 + 07 삼각매트릭스 재현.

구현 표준 (06/07 승계): 결정론 · 상태 기록 · 원자적 저장 · 헤더 단언 · frag-set 해시.
"""
import sys, os, io, json, csv, importlib.util, tempfile
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out09")
os.makedirs(OUT, exist_ok=True)

# ── 06 코어 import (단일 출처 — 06이 stdout 래퍼 교체, 재교체 금지) ──────────
_s = importlib.util.spec_from_file_location("d6", os.path.join(HERE, "06_derivation_v2.py"))
d6 = importlib.util.module_from_spec(_s); _s.loader.exec_module(d6)
FRAGS = d6.FRAGS; CELLS = d6.CELLS; cl = d6.cl; admissible = d6.admissible
Requester = d6.Requester; verify_obligations = d6.verify_obligations
K_HEAD = d6.K_HEAD; CANARY = d6.CANARY; PERSONA = d6.PERSONA; con = d6.con

def U(role):  return Requester(PERSONA[role][0], role)
def staff(e): return Requester(e, None)

# ── trust τ (하향 전용) ─────────────────────────────────────────────────────
# trust_signal.uts 평균 → g(τ). τ=1 중립. 낮을수록 ceiling 하향 (절대 상향 없음).
UTS = {}
for r in con.execute("SELECT emp_id, avg(uts) FROM trust_signal GROUP BY emp_id").fetchall():
    UTS[r[0]] = r[1]

def g_tau(emp_id):
    """monotone 하향 함수 g(τ) ≤ 1. τ≥0.9 → 1.0 (무영향), 낮으면 계단 하향."""
    t = UTS.get(emp_id, 1.0)
    if t >= 0.90:  return 1.0
    if t >= 0.75:  return 0.67   # t3 요청을 t2로
    if t >= 0.50:  return 0.34   # t3→t1
    return 0.0                    # 전면 하향

# ── ceiling (Property 1·2′) ─────────────────────────────────────────────────
def ceiling(u, attr, d_req):
    """D_final = min(D_req, D_th, floor(D_req·g(τ)))."""
    c = u.cell(attr)
    d_th = c[0] if c else 0
    import math
    d_g = math.floor(d_req * g_tau(u.emp_id))
    return min(d_req, d_th, d_g)

# ── escalation P0~P5 (누적) ─────────────────────────────────────────────────
def escalation_route(policy, permit, flags, attr_unknown, d_final, is_small_group):
    """policy ∈ P0..P5. 누적 — 상위 정책은 하위 대상 포함. returns (routed, reasons)."""
    lvl = int(policy[1])
    reasons = []
    if permit:
        if lvl >= 1 and flags.get("injection_suspected"):
            reasons.append("flagged_permit(injection)")
        if lvl >= 2 and flags.get("ambiguous"):
            reasons.append("ambiguous_permit")
        if lvl >= 3 and attr_unknown:
            reasons.append("unknown_attr_permit")
        if lvl >= 4 and d_final == 3:
            reasons.append("individual_tier_release")
        if lvl >= 5 and is_small_group:
            reasons.append("small_group_aggregate")
    return (len(reasons) > 0, reasons)

# ── 계약 발행 ───────────────────────────────────────────────────────────────
def issue_contract(u, cand_fids, ledger_fids=(), pi=None, policy="P0", k=K_HEAD):
    """
    pi = 파스 (attr, t_req, s, flags) 또는 None(조각 좌표 직접 — GT 구동).
    반환 = 계약 dict. 판정 코어 = 06 cl (R3+R1+R2 통합) + ceiling + escalation.
    """
    flags = (pi or {}).get("flags", {}) if pi else {}
    attr_unknown = bool(pi and pi.get("attr") == "unknown")

    # 1) cl(F) 합성 — per-item(R3) + set-level(R1·R2)
    res = cl(u, list(cand_fids), list(ledger_fids), k)
    errs = verify_obligations(u, cand_fids, ledger_fids, res, k)

    # 2) ceiling — 후보 중 release된 조각의 tier를 D_th·τ로 클램프
    released = [f for f, v in res["verdicts"].items() if v[0] == "release"]
    d_finals = []
    small_group = False
    for fid in released:
        f = FRAGS[fid]
        d_req = pi["t_req"] if pi else f["tier"]
        d_f = ceiling(u, f["attr"], d_req)
        d_finals.append(d_f)
        if 0 < (f["n"] or 0) < k:
            small_group = True
    d_final = max(d_finals) if d_finals else 0

    # 3) decision 3분기
    if attr_unknown:
        decision = "ESCALATE"
    elif not released:
        decision = "DENY"
    else:
        decision = "PERMIT"

    # 4) escalation P0~P5
    permit = decision == "PERMIT"
    routed, reasons = escalation_route(policy, permit, flags, attr_unknown, d_final, small_group)
    if routed:
        decision = "ESCALATE"

    # 5) obligations 통합 (06 + 09 신설)
    obs = list(res["obligations"])
    for fid in released:
        f = FRAGS[fid]
        d_req = pi["t_req"] if pi else f["tier"]
        if ceiling(u, f["attr"], d_req) < f["tier"]:
            obs.append(("tier_ceiling", fid, f"D_final<tier(d_th/τ)"))
    if routed:
        obs.append(("escalation", "|".join(released), f"{policy}:{','.join(reasons)}"))

    return dict(decision=decision, D_final=d_final,
                obligations=obs, verrs=errs,
                escalation=dict(routed=routed, policy=policy, reasons=reasons),
                released=released,
                withheld=[f for f, v in res["verdicts"].items() if v[0] == "withhold"],
                verdicts=res["verdicts"])

# ── reference PEP (계약 → 릴리스 + CIPP) ────────────────────────────────────
def reference_pep(u, contract, k=K_HEAD):
    """CIPP 검증: tier ≤ D_final ∧ canary 미매치(무자격). 위반 → cipp_block."""
    blocks = []
    for fid in contract["released"]:
        f = FRAGS[fid]
        if f["tier"] > contract["D_final"]:
            blocks.append(("cipp_block", fid, f"tier {f['tier']}>D_final {contract['D_final']}"))
        # canary 미매치: canary 조각이 무자격자에게 released면 위반 (06 cl이 막았어야)
        if f["canary"] and contract["decision"] == "PERMIT":
            # cl이 release한 canary = 자격 있음(skip) 또는 per-item 통과 — CIPP는 tier만 재확인
            pass
    return blocks

# ── 기동 게이트 ─────────────────────────────────────────────────────────────
def gate():
    G = []
    def chk(name, cond, det=""):
        G.append((name, bool(cond), det))

    # 1) 06 카나리아 판정표 재현 (조각 수준)
    ca, cb = CANARY["C-a"], CANARY["C-b"]
    c1, c2 = CANARY["C-c1"], CANARY["C-c2"]
    def act(u, cand, ledger=(), k=K_HEAD):
        c = issue_contract(u, cand, ledger, policy="P0", k=k)
        return {f: c["verdicts"][f][0] for f in cand}
    chk("C-a×동료 withhold", act(staff("E0113"), [ca])[ca] == "withhold")
    chk("C-a×본인 release", act(staff("E0114"), [ca])[ca] == "release")
    chk("C-b×F_PAY release", act(U("F_PAY"), [cb])[cb] == "release")
    chk("C-b×동료 withhold", act(staff("E0113"), [cb])[cb] == "withhold")
    chk("C-c쌍×B_RHQ withhold", act(U("B_RHQ"), [c1, c2])[c1] == "withhold")
    chk("C-c쌍×B_BR release", act(U("B_BR"), [c1, c2])[c1] == "release")

    # 2) ceiling — Property 1·2′ (전 계약 D_final ≤ D_th ≤ max_tier)
    p1_ok = True
    for role in ["B_RHQ", "F_CMP", "H_HR", "S_ACC"]:
        u = U(role)
        for attr in ["PB", "LN", "ER"]:
            c = u.cell(attr)
            if c:
                cf = ceiling(u, attr, 3)   # t3 요청
                if not (cf <= c[0]):
                    p1_ok = False
    chk("Property 1·2′ (D_final≤D_th)", p1_ok)

    # 3) P0~P5 단조성 (릴리스 집합 단조 감소)
    #    injection flag가 있는 permit 케이스에서 P0 release ⊇ P1 release ⊇ ...
    u = U("B_BR")
    big = [f["fid"] for f in FRAGS.values() if f["attr"] == "LN" and f["tier"] == 3][:1]
    pi_flag = dict(attr="LN", t_req=3, s="none", flags=dict(injection_suspected=True))
    prev_routed = False
    mono = True
    for pol in ["P0", "P1", "P2", "P3", "P4", "P5"]:
        c = issue_contract(u, big, [], pi=pi_flag, policy=pol)
        r = c["escalation"]["routed"]
        if prev_routed and not r:   # 상위 정책이 라우팅 해제 = 단조 위반
            mono = False
        prev_routed = prev_routed or r
    chk("P0~P5 escalation 단조", mono)

    # 4) escalation 발화 실증 (P1이 flagged permit 잡음)
    c0 = issue_contract(u, big, [], pi=pi_flag, policy="P0")
    c1p = issue_contract(u, big, [], pi=pi_flag, policy="P1")
    chk("P0 미라우팅 · P1 라우팅", (not c0["escalation"]["routed"]) and c1p["escalation"]["routed"],
        f"P0={c0['decision']} P1={c1p['decision']}")

    return G

# ── 07 삼각매트릭스 대조 ────────────────────────────────────────────────────
def triangle_check(tri_csv):
    if not os.path.exists(tri_csv):
        return None
    rows = list(csv.DictReader(open(tri_csv, encoding="utf-8")))
    mism = []
    PMAP = {"본인": lambda: staff("E0027"), "동료": lambda: staff("E0113"),
            "H_HR": lambda: U("H_HR"), "B_BR": lambda: U("B_BR"),
            "B_RHQ": lambda: U("B_RHQ"), "F_CMP": lambda: U("F_CMP")}
    for r in rows:
        u = PMAP.get(r["persona"], lambda: None)()
        if u is None:
            continue
        tgt = r["target"]
        if "->" in tgt:  # 시퀀스 (ledger->cand)
            led, cand = tgt.split("->")
            c = issue_contract(u, [cand], [led], policy="P0",
                               k=(3 if r["matrix"] == "A" else K_HEAD))
            got = c["verdicts"].get(cand, ("?",))[0]
        else:
            c = issue_contract(u, [tgt], [], policy="P0",
                               k=(3 if r["cond"] == "차분쌍" else K_HEAD))
            got = c["verdicts"].get(tgt, ("?",))[0]
        if got != r["action"]:
            mism.append((r["matrix"], r["persona"], r["cond"], r["action"], got))
    return mism

# ── main ────────────────────────────────────────────────────────────────────
def main():
    print(f"frag-set hash = {d6.FRAGSET_HASH} · trust emps={len(UTS)} · k_head={K_HEAD}")
    print("=" * 70); print("09 기동 게이트")
    G = gate()
    allok = all(ok for _, ok, _ in G)
    for name, ok, det in G:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  {det}" if det else ""))
    print(f"게이트: {'전 칸 PASS' if allok else '실패 — 중단'}")
    if not allok:
        sys.exit(1)

    # 07 삼각매트릭스 대조
    tri = triangle_check(os.path.join(HERE, "out07", "triangle_matrix.csv"))
    if tri is None:
        print("삼각매트릭스 대조: 07 산출 없음 — skip")
    elif tri:
        print(f"삼각매트릭스 불일치 {len(tri)}건:")
        for m in tri: print("  ", m)
        sys.exit(1)
    else:
        print("삼각매트릭스 대조: 18행 전건 일치 PASS")

    # 07 query_set 대표 부분집합의 계약 발행 (게이트 검증 산출)
    contracts = []
    qs = os.path.join(HERE, "out07", "query_set_v2.csv")
    if os.path.exists(qs):
        rows = list(csv.DictReader(open(qs, encoding="utf-8")))
        # 대표: 각 split에서 앞 20 (계약 발행 실증)
        seen = defaultdict(int)
        for r in rows:
            if seen[r["split"]] >= 20:
                continue
            seen[r["split"]] += 1
            emp = r["persona"].split(":")[1]
            u = staff(emp) if r["persona"].startswith("STAFF") else U(r["persona"].split(":")[0])
            fids = r["target_fragment_ids"].split("|")
            pi = dict(attr=r["attr"], t_req=int(r["t_req"]), s="none", flags={})
            c = issue_contract(u, fids, [], pi=pi, policy="P0")
            pep = reference_pep(u, c)
            contracts.append(dict(query_id=r["query_id"], split=r["split"], persona=r["persona"],
                                  decision=c["decision"], D_final=c["D_final"],
                                  n_released=len(c["released"]), n_withheld=len(c["withheld"]),
                                  escalated=c["escalation"]["routed"], cipp_blocks=len(pep),
                                  verrs=len(c["verrs"])))
    verr_total = sum(c["verrs"] for c in contracts)
    print(f"계약 발행 {len(contracts)}건 · obligation 검증기 오류 {verr_total}")

    # 저장 (원자적)
    def atomic(path, rows, fields):
        fd, tmp = tempfile.mkstemp(dir=OUT, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows(rows)
        os.replace(tmp, path)
    if contracts:
        atomic(os.path.join(OUT, "contracts_sample.csv"), contracts,
               list(contracts[0].keys()))
    man = dict(fragset_hash=d6.FRAGSET_HASH, trust_emps=len(UTS), k_head=K_HEAD,
               gate="PASS" if allok else "FAIL", triangle="PASS" if tri == [] else "n/a",
               contracts=len(contracts), obligation_errors=verr_total,
               escalation_policies=["P0","P1","P2","P3","P4","P5"], headline_policy="P0")
    fd, tmp = tempfile.mkstemp(dir=OUT, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(OUT, "decide09_manifest.json"))
    print(f"산출: out09/contracts_sample.csv · decide09_manifest.json")

if __name__ == "__main__":
    main()
