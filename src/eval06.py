# -*- coding: utf-8 -*-
"""
eval06.py — 06_derivation 평가 러너 (스펙 §9). 결정론 전수, CI 불요.
산출물 6종 (원자적 저장 + 헤더 단언):
  cl_eval_runs.csv        열거 확장: 요청자 16 × 전 조각, per-item(R3) vs cl 대조
  struct_pairs.csv        코퍼스 구조 위험쌍 전수 (diff·join, 요청자 무관 구조 + 대표 요청자 판정)
  session_seq_runs.csv    세션 2턴 시퀀스 (순서 교환·원장 변주·음성 대조군) × k 스윕
  k_sweep_curve.csv       k ∈ {2,3,5,10,20}: R1 발화/생략, 과차단(=0 단언), obligation 부하
  b8_ablation.csv         per-item → +R1 → +R1+R2 단계별 포착 (B8 슬롯)
  b9_cc_class_table.csv   C-b·C-c 클래스별 판정 표 (B9 슬롯)
  obligation_audit.csv    검증기 오류 전수 (0이어야 함) + 종류별 발행 수
"""
import os, csv, itertools, tempfile, hashlib
from collections import defaultdict

def atomic_csv(path, header, rows):
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    with os.fdopen(fd, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(header)
        for r in rows: w.writerow(r)
    os.replace(tmp, path)
    with open(path, encoding="utf-8-sig") as f:
        got = f.readline().strip()
    assert got == ",".join(header), f"헤더 단언 실패: {path}"
    return len(rows)

def main(M):
    OUT = M.OUT
    FRAGS, STYPE, PT = M.FRAGS, M.STYPE, M.PERSON_TYPES
    K_HEAD, K_SWEEP = M.K_HEAD, M.K_SWEEP
    reqs = [M.U(r) for r in sorted(M.PERSONA)] + [M.staff("E0114"), M.staff("E0113")]
    print(f"\n평가 러너 시작 — 요청자 {len(reqs)} · 조각 {len(FRAGS)} · frag-set {M.FRAGSET_HASH}")

    # ── 1. 열거 확장: 요청자 × 전 조각 (단독 후보) ──────────────────────────
    rows, verr_all = [], []
    stats = defaultdict(int)
    for u in reqs:
        for fid in sorted(FRAGS):
            f = FRAGS[fid]
            ok3, why3, _ = M.admissible(u, f)
            r = M.run_case(f"enum:{u.key()}:{fid}", u, [fid], (), K_HEAD)
            act, rule, why = r["res"]["verdicts"][fid]
            verr_all += [(r["case"], e) for e in r["verrs"]]
            leak_vs_peritem = int(ok3 and act == "withhold")   # per-item 통과·cl 차단 = R1 몫
            rows.append([u.key(), fid, f["attr"], f["tier"], f["n"] or 0,
                         int(f["ids"] is not None), f["canary"] or "",
                         "release" if ok3 else "withhold", act, rule, why, leak_vs_peritem])
            stats[(u.key(), "peritem_rel")] += int(ok3)
            stats[(u.key(), "cl_rel")] += int(act == "release")
            stats[(u.key(), "r1_fire")] += int(rule == "R1")
            stats[(u.key(), "r1_skip")] += int(rule == "R1skip")
    n = atomic_csv(os.path.join(OUT, "cl_eval_runs.csv"),
        ["requester","fragment_id","attr","tier","n","has_ids","canary",
         "peritem_r3","cl_action","rule","reason","r1_catch_over_peritem"], rows)
    print(f"  cl_eval_runs.csv {n}행")

    # ── 2. 구조 위험쌍 전수 스캔 (요청자 무관 구조) ─────────────────────────
    by_attr = defaultdict(list)
    for f in FRAGS.values():
        if STYPE.get(f["attr"]) in PT and f["ids"] is not None:
            by_attr[f["attr"]].append(f)
    anon = [f for f in FRAGS.values() if STYPE.get(f["attr"]) in PT
            and f["ids"] is None and f["sid"] is None and 0 < (f["n"] or 0) < max(K_SWEEP)]
    prow, pair_stats = [], defaultdict(int)
    for attr, fl in sorted(by_attr.items()):
        fl = sorted(fl, key=lambda x: x["fid"])
        for f, g in itertools.combinations(fl, 2):
            if f["period"] != g["period"]: continue
            A, B = f["ids"], g["ids"]
            if A == B or not (A & B): continue
            d = len(A ^ B)
            prow.append(["diff", attr, f["fid"], g["fid"], f["n"], g["n"], d, ""])
            for k in K_SWEEP: pair_stats[("diff", k)] += int(0 < d < k)
    ident = [f for fl in by_attr.values() for f in fl if 0 < len(f["ids"]) < max(K_SWEEP)]
    for f in sorted(anon, key=lambda x: x["fid"]):
        for g in sorted(ident, key=lambda x: x["fid"]):
            if STYPE.get(f["attr"]) != STYPE.get(g["attr"]): continue
            a, b = f["scope"], g["scope"]
            if not (a.startswith(b) or b.startswith(a)): continue
            prow.append(["join", f"{f['attr']}x{g['attr']}", f["fid"], g["fid"],
                         f["n"], len(g["ids"]), len(g["ids"]), ""])
            for k in K_SWEEP:
                pair_stats[("join", k)] += int(0 < (f["n"] or 0) < k and 0 < len(g["ids"]) < k)
    n = atomic_csv(os.path.join(OUT, "struct_pairs.csv"),
        ["kind","attr","f","g","n_f","n_g","delta_or_cand","note"], prow)
    print(f"  struct_pairs.csv {n}행 (diff {sum(1 for r in prow if r[0]=='diff')} · join {sum(1 for r in prow if r[0]=='join')})")

    # ── 3. 세션 2턴 시퀀스 × k 스윕 ─────────────────────────────────────────
    team_er = ind_er = None
    for f in FRAGS.values():
        if f["attr"] == "ER" and f["tier"] == 2 and f["ids"] and "E_F_CMP" in f["ids"] and f["n"] == 3:
            team_er = f["fid"]
        if f["attr"] == "ER" and f["tier"] == 3 and f["sid"] == "E0027":
            ind_er = f["fid"]
    c1, c2 = M.CANARY["C-c1"], M.CANARY["C-c2"]
    cb = M.CANARY["C-b"]
    er2 = sorted((f for f in FRAGS.values()
                  if f["attr"] == "ER" and f["tier"] == 2 and f["ids"]),
                 key=lambda x: (-(x["n"] or 0), x["fid"]))
    negs = [er2[0]["fid"], next(f["fid"] for f in er2[1:]
                                if not (f["ids"] & er2[0]["ids"]))]
    # 음성의 유효 범위: k ≤ n (그 위에서는 R1 대상 — 과차단 곡선의 정보로 기록)
    SEQ = [
        ("S1 diff 정방향",   "F_SEC", [team_er], [ind_er], "diff"),
        ("S2 diff 교환",     "F_SEC", [ind_er], [team_er], "swap"),
        ("S3 join 정방향",   "B_RHQ", [c1], [c2], "join"),
        ("S4 join 교환",     "B_RHQ", [c2], [c1], "swap"),
        ("S5 join 자격자",   "B_BR",  [c1], [c2], "skip"),
        ("S6 diff 자격자",   "F_PAY", [team_er], [ind_er], "skip"),
        ("S7 음성 disjoint", "F_SEC", [negs[0]], [negs[1]], "neg"),
        ("S8 음성 빈원장",   "F_SEC", [negs[0]], [], "neg"),
        ("S9 C-b 원장경유",  "H_HR",  [cb], [ind_er], "skip"),
    ]
    srow = []
    for k in K_SWEEP:
        for name, role, cand, led, cls_ in SEQ:
            u = M.U(role) if role in M.PERSONA else M.staff(role)
            for use_r1 in (True, False):
                r = M.run_case(f"seq:{name}:k{k}:r1{int(use_r1)}", u, cand, led, k, use_r1=use_r1)
                verr_all += [(r["case"], e) for e in r["verrs"]]
                fid = cand[0]
                act, rule, why = r["res"]["verdicts"][fid]
                # 불변식: 위험쌍 완성 없음 (cl 내부 assert 통과가 곧 증명 — 여기선 기록만)
                srow.append([name, cls_, u.key(), k, int(use_r1), fid, "|".join(led),
                             act, rule, why])
    n = atomic_csv(os.path.join(OUT, "session_seq_runs.csv"),
        ["scenario","class","requester","k","use_r1","candidate","ledger",
         "action","rule","reason"], srow)
    print(f"  session_seq_runs.csv {n}행")

    # ── 4. k 스윕 곡선 ──────────────────────────────────────────────────────
    krow = []
    for k in K_SWEEP:
        r1f = r1s = ob = over = 0
        for u in reqs:
            for fid in sorted(FRAGS):
                f = FRAGS[fid]
                ok3, _, _ = M.admissible(u, f)
                if not ok3: continue
                act, why, skip = M.r1_check(u, f, k)
                r1f += int(act == "withhold"); r1s += int(skip)
                ob += int(act == "withhold")
                safe = (STYPE.get(f["attr"]) not in PT) or (f["n"] or 0) == 0 \
                       or (f["n"] or 0) >= k or f["tier"] >= 3
                over += int(safe and act == "withhold")
        assert over == 0, f"과차단 발생 k={k}: {over}"
        krow.append([k, r1f, r1s, ob, over,
                     pair_stats[("diff", k)], pair_stats[("join", k)]])
    n = atomic_csv(os.path.join(OUT, "k_sweep_curve.csv"),
        ["k","r1_fire","r1_skip","k_obligations","overblock_safe(must0)",
         "struct_diff_pairs_lt_k","struct_join_pairs_lt_k"], krow)
    print(f"  k_sweep_curve.csv {n}행 (과차단 전 구간 0 단언 통과)")

    # ── 5. B8 ablation ──────────────────────────────────────────────────────
    AB = [
        ("C-c1 단일응답 (B_RHQ)", "B_RHQ", [c1], [], K_HEAD),
        ("C-c쌍 단일응답 (B_RHQ)", "B_RHQ", [c1, c2], [], K_HEAD),
        ("세션 diff k=3 (F_SEC)", "F_SEC", [team_er], [ind_er], 3),
        ("세션 join (B_RHQ)", "B_RHQ", [c1], [c2], K_HEAD),
        ("C-b (F_PAY — 생략 실증)", "F_PAY", [cb], [], K_HEAD),
    ]
    brow = []
    for name, role, cand, led, k in AB:
        u = M.U(role)
        for cond, r1_, r2_ in [("per-item(R3)", False, False), ("+R1", True, False),
                                ("+R1+R2", True, True)]:
            r = M.run_case(f"b8:{name}:{cond}", u, cand, led, k, use_r1=r1_, use_r2=r2_)
            verr_all += [(r["case"], e) for e in r["verrs"]]
            caught = sum(1 for fid in cand
                         if r["res"]["verdicts"][fid][0] == "withhold"
                         and r["res"]["verdicts"][fid][1] != "R3")
            released_risky = sum(1 for fid in cand
                                 if r["res"]["verdicts"][fid][0] == "release"
                                 and FRAGS[fid]["canary"] in ("C-b", "C-c")
                                 and role in ("B_RHQ", "F_SEC"))
            acts = {fid: r["res"]["verdicts"][fid][0] + "/" + r["res"]["verdicts"][fid][1]
                    for fid in cand}
            brow.append([name, cond, k, str(acts), caught, released_risky])
    n = atomic_csv(os.path.join(OUT, "b8_ablation.csv"),
        ["scenario","condition","k","verdicts","caught_beyond_R3","risky_release"], brow)
    print(f"  b8_ablation.csv {n}행")

    # ── 6. B9 — C-b·C-c 클래스별 표 ─────────────────────────────────────────
    CLS = [("C-a", M.CANARY["C-a"]), ("C-b", cb), ("C-c1(익명극값)", c1),
           ("C-c2(신원명부)", c2), ("SAR-RM", "SAR-00001"), ("SAR-ER", "SAR-00002")]
    RREP = ["F_PAY", "H_HR", "F_SEC", "B_RHQ", "B_BR", "F_SAL", "F_CMP"]
    b9 = []
    for cname, fid in CLS:
        for role in RREP:
            u = M.U(role)
            r = M.run_case(f"b9:{cname}:{role}", u, [fid], (), K_HEAD)
            act, rule, why = r["res"]["verdicts"][fid]
            b9.append([cname, fid, role, act, rule, why])
        for who, u in [("본인/대상", M.staff("E0114")), ("동료", M.staff("E0113"))]:
            r = M.run_case(f"b9:{cname}:{who}", u, [fid], (), K_HEAD)
            act, rule, why = r["res"]["verdicts"][fid]
            b9.append([cname, fid, who, act, rule, why])
    n = atomic_csv(os.path.join(OUT, "b9_cc_class_table.csv"),
        ["class","fragment_id","requester","action","rule","reason"], b9)
    print(f"  b9_cc_class_table.csv {n}행")

    # ── 7. obligation 감사 집계 ─────────────────────────────────────────────
    arow = [["verifier_errors", len(verr_all), ""]]
    for cse, e in verr_all[:50]:
        arow.append(["error", cse, e])
    n = atomic_csv(os.path.join(OUT, "obligation_audit.csv"),
        ["kind","case_or_count","detail"], arow)
    assert not verr_all, f"obligation 검증기 오류 {len(verr_all)}건"
    print(f"  obligation_audit.csv — 검증기 오류 0 단언 통과")

    # ── 요약 ────────────────────────────────────────────────────────────────
    print("\n요청자별 per-item vs cl (열거 전수):")
    for u in reqs:
        k_ = u.key()
        print(f"  {k_:16s} per-item release {stats[(k_,'peritem_rel')]:5d} → "
              f"cl release {stats[(k_,'cl_rel')]:5d} · R1 발화 {stats[(k_,'r1_fire')]:3d} · "
              f"R1 생략 {stats[(k_,'r1_skip')]:3d}")
    print("\n평가 완료 — 산출물 7종 out06/.")
