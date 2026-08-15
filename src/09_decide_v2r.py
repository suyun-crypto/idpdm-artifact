# -*- coding: utf-8 -*-
"""
09_decide_v2r.py — A7 해소판 판정 코어 (09_decide_v2 정본은 동결 유지, r = revision)
증보 2026-07-30g §B의 결함 2건 해소:

  A7-a  g(τ) 곱셈 floor(⌊D_req·g⌋, v3 Eq.2 셋째 항)의 t_req=1 역전
        → **절대 깊이 cap**으로 교체: D_final = min(D_req, D_th(u), T_cap(τ)).
        T_cap: τ≥0.90→3(무영향) / ≥0.75→2(개인 단위 상실) / ≥0.50→1(집계만) / else→0.
        의미론: 신뢰 하락 = 깊은(민감) tier부터 상실. v1 "trust cap" 문언의 직해.
        Property 1(D_final ≤ D_th) min 구조로 불변 성립.

  A7-b  decision 3분기가 ceiling 미참조 → PERMIT ∧ D_final=0 모순 계약 발행
        → trust 필터를 released에 선적용: released_eff = {f : tier(f) ≤ T_cap}.
        released_eff 공집합 → DENY. 발행 계약 불변식: PERMIT ⇒ ∀f∈released
        tier(f) ≤ D_final (cipp tier 검사는 방어선 중복으로 존치 — 발화 0이 정상).
        차단분은 obligation ("trust_downmod", fid, ...) 으로 기록.

패치 게이트: ① 구판 결함 재현 단언 (구코어: PERMIT∧cipp_block / r: 정합) ②
06 카나리아 판정표·07 삼각매트릭스·P0~P5 단조 = 09 게이트 전량 r-코어로 재실행 PASS.
API 표면 = 09와 동일 (d6·U·staff·UTS·issue_contract·reference_pep·g_tau[호환용]).
"""
import sys, os, math, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
_s = importlib.util.spec_from_file_location("d9base", os.path.join(HERE, "09_decide_v2.py"))
d9b = importlib.util.module_from_spec(_s); _s.loader.exec_module(d9b)

d6 = d9b.d6
FRAGS = d6.FRAGS
K_HEAD = d6.K_HEAD
cl, verify_obligations = d6.cl, d6.verify_obligations
U, staff = d9b.U, d9b.staff
reference_pep = d9b.reference_pep
escalation_route = d9b.escalation_route
UTS = dict(d9b.UTS)          # r 모듈 전역 — 실험이 덮어쓸 수 있음 (trust 중립 = {})

def T_cap(emp_id):
    """절대 깊이 상한 (A7-a). τ는 하향 전용 — cap ≤ 3, 절대 상향 없음."""
    t = UTS.get(emp_id, 1.0)
    if t >= 0.90: return 3
    if t >= 0.75: return 2
    if t >= 0.50: return 1
    return 0

def g_tau(emp_id):
    """호환용 (구 API) — r 의미론에서는 T_cap이 정본."""
    return {3: 1.0, 2: 0.67, 1: 0.34, 0: 0.0}[T_cap(emp_id)]

def ceiling(u, attr, d_req):
    """D_final 항 = min(D_req, D_th, T_cap) — 곱셈 floor 폐지 (A7-a)."""
    c = u.cell(attr)
    d_th = c[0] if c else 0
    return min(d_req, d_th, T_cap(u.emp_id))

def issue_contract(u, cand_fids, ledger_fids=(), pi=None, policy="P0", k=K_HEAD):
    """09 issue_contract의 r판 — 흐름 동일, trust 필터 선적용 + decision 정합 (A7-b)."""
    flags = (pi or {}).get("flags", {}) if pi else {}
    attr_unknown = bool(pi and pi.get("attr") == "unknown")

    res = cl(u, list(cand_fids), list(ledger_fids), k)
    errs = verify_obligations(u, cand_fids, ledger_fids, res, k)

    released_cl = [f for f, v in res["verdicts"].items() if v[0] == "release"]
    cap = T_cap(u.emp_id)
    trust_blocked = [f for f in released_cl if FRAGS[f]["tier"] > cap]
    released = [f for f in released_cl if FRAGS[f]["tier"] <= cap]

    d_finals = []
    small_group = False
    for fid in released:
        f = FRAGS[fid]
        d_req = pi["t_req"] if pi else f["tier"]
        d_finals.append(ceiling(u, f["attr"], d_req))
        if 0 < (f["n"] or 0) < k:
            small_group = True
    d_final = max(d_finals) if d_finals else 0

    # 불변식 (A7-b): PERMIT ⇒ 릴리스 전 건 tier ≤ D_final
    for fid in released:
        assert FRAGS[fid]["tier"] <= d_final, f"불변식 위반: {fid}"

    if attr_unknown:
        decision = "ESCALATE"
    elif not released:
        decision = "DENY"
    else:
        decision = "PERMIT"

    permit = decision == "PERMIT"
    routed, reasons = escalation_route(policy, permit, flags, attr_unknown, d_final, small_group)
    if routed:
        decision = "ESCALATE"

    obs = list(res["obligations"])
    for fid in trust_blocked:
        obs.append(("trust_downmod", fid, f"tier {FRAGS[fid]['tier']}>T_cap {cap}"))
    for fid in released:
        f = FRAGS[fid]
        d_req = pi["t_req"] if pi else f["tier"]
        if ceiling(u, f["attr"], d_req) < f["tier"]:
            obs.append(("tier_ceiling", fid, "D_final<tier(d_th/τ)"))
    if routed:
        obs.append(("escalation", "|".join(released), f"{policy}:{','.join(reasons)}"))

    wh = [f for f, v in res["verdicts"].items() if v[0] == "withhold"] + trust_blocked
    return dict(decision=decision, D_final=d_final,
                obligations=obs, verrs=errs,
                escalation=dict(routed=routed, policy=policy, reasons=reasons),
                released=released, withheld=wh,
                trust_blocked=trust_blocked, verdicts=res["verdicts"])

# ── 패치 게이트 ─────────────────────────────────────────────────────────────
def patch_gate():
    G = []
    # ① 구판 결함 재현 단언 (τ=0.84 E_S_ACC, RS t_req=1 — 30g §B 실물 케이스)
    u = U("S_ACC")
    fid = next(f["fid"] for f in FRAGS.values() if f["attr"] == "RS" and f["tier"] == 1)
    pi = dict(attr="RS", t_req=1, s="none", flags={})
    co = d9b.issue_contract(u, [fid], [], pi=pi, policy="P0")
    bo = d9b.reference_pep(u, co)
    old_defect = (co["decision"] == "PERMIT" and co["D_final"] == 0 and len(bo) > 0)
    G.append(("구코어 A7 재현 (PERMIT∧D_final=0∧cipp)", old_defect))
    cr = issue_contract(u, [fid], [], pi=pi, policy="P0")
    br = reference_pep(u, cr)
    G.append(("r코어 t1 정합 (PERMIT∧D_final=1∧cipp 0)",
              cr["decision"] == "PERMIT" and cr["D_final"] == 1 and not br))
    # ② cap 구속의 심각도 정렬 — 자연 케이스: τ<0.9 일반직원의 본인 t3 레코드
    #    (역할 페르소나 2명의 t3는 clearance=1이 지배 — ownership basis만 cls 면제라
    #     trust cap의 자연 발화면은 저신뢰 직원 73명의 본인 레코드. A4 모집단과 동일.)
    low = next(r[0] for r in d6.con.execute(
        """SELECT emp_id FROM (SELECT emp_id, avg(uts) a FROM trust_signal GROUP BY emp_id)
           WHERE a < 0.9 AND emp_id NOT LIKE 'E\\_%' ESCAPE '\\' ORDER BY emp_id""").fetchall())
    fid3 = next(f["fid"] for f in FRAGS.values() if f["tier"] == 3
                and (f["sid"] == low or (f["ids"] and low in f["ids"])))
    us = staff(low)
    assert d6.admissible(us, FRAGS[fid3])[0], "전제 실패: 본인 조각 admissible"
    c3 = issue_contract(us, [fid3], [], pi=None, policy="P0")
    G.append(("r코어 t3 차단 (자연 저신뢰: DENY+trust_downmod)",
              c3["decision"] == "DENY" and any(o[0] == "trust_downmod" for o in c3["obligations"])))
    # ③ 09 게이트 전량 r-코어 재실행 (monkeypatch)
    sav_ic, sav_ce = d9b.issue_contract, d9b.ceiling
    d9b.issue_contract, d9b.ceiling = issue_contract, ceiling
    try:
        G9 = d9b.gate()
        tri = d9b.triangle_check(os.path.join(HERE, "out07", "triangle_matrix.csv"))
    finally:
        d9b.issue_contract, d9b.ceiling = sav_ic, sav_ce
    G.append(("09 게이트 전 칸 (r-코어)", all(ok for _, ok, _ in G9)))
    G.append(("07 삼각매트릭스 18행 (r-코어)", tri == []))
    return G

if __name__ == "__main__":
    print(f"09r — frag-set {d6.FRAGSET_HASH} · A7-a(T_cap)·A7-b(decision 정합)")
    G = patch_gate()
    allok = all(ok for _, ok in G)
    for n, ok in G:
        print(f"  [{'PASS' if ok else 'FAIL'}] {n}")
    sys.exit(0 if allok else 1)
