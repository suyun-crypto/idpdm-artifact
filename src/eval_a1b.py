# -*- coding: utf-8 -*-
"""
eval_a1b.py — A1b E5 운영곡선 (k-스윕 × P0~P5 라우팅). eval_a1 확장. (유실된 10_eval의 A1 특화 재작성판)
설계 근거: split plan §5-A1 · 06 코어 인터페이스 · query_set_v2.csv 실측 구조.

핵심 원칙:
  ① 좌표 스위치: --coords {gt,parser,both} — 결정층 '입력'만 바뀜.
  ② oracle 채점은 항상 GT(gt_cl_action) 기준 — 비순환성 고정.
  ③ 재현 게이트: gt-모드 앵커(iDPDM 0/153·0/283·0/118, menu 86/153, ungov 153/153)
     미재현 시 parser 결과를 headline으로 인정하지 않음 (gate=FAIL 기록).
  ④ iDPDM을 gt·parser 양 좌표로 같은 패스에 실행 → 행 단위 diff =
     파스 오류 1:1 귀속 분해표 (a1_parser_impact.csv).

실행 (findw_v2 루트에서):
  python eval_a1.py --coords both --out out_a1
전제: deriv\06_derivation_v2.py · findw.duckdb · parser_out.jsonl · query_set_v2.csv
주의: 06이 import 시 stdout을 UTF-8 래퍼로 교체 — 본 러너는 재교체하지 않음(07 교훈).
"""
import os, sys, csv, json, argparse, hashlib, tempfile, importlib.util
from collections import defaultdict, Counter

HERE = os.path.dirname(os.path.abspath(__file__))

def atomic_csv(path, header, rows):
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    with os.fdopen(fd, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(header)
        for r in rows: w.writerow(r)
    os.replace(tmp, path)
    with open(path, encoding="utf-8-sig") as f:
        assert f.readline().strip() == ",".join(header), f"헤더 단언 실패: {path}"
    return len(rows)

def sha16(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for ch in iter(lambda: f.read(1 << 20), b""): h.update(ch)
    return h.hexdigest()[:16]

def load_core(core_path):
    spec = importlib.util.spec_from_file_location("deriv06", core_path)
    M = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(M)   # duckdb 로드·FRAGS/CELLS/PERSONA 구축 (stdout 래핑 포함)
    return M

def parse_ob_tail(ob):
    """gt_obligations 꼬리에서 (k, injected_fids) 추출. 예: '...|k=3;ledger_injected=G08-00980'"""
    k, inj = None, []
    if "|" in ob:
        tail = ob.rsplit("|", 1)[1]
        for part in tail.split(";"):
            part = part.strip()
            if part.startswith("k="):
                k = int(part[2:])
            elif part.startswith("ledger_injected="):
                v = part.split("=", 1)[1]
                inj = [x for x in v.split(",") if x]
            # 'ledger=' (누적 기대치)는 문서화 필드 — 시스템 원장은 arm 자체 누적 사용
    return k, inj

def mk_requester(M, persona):
    role, emp = (persona.split(":", 1) + [None])[:2] if ":" in persona else (None, persona)
    if role in (None, "", "STAFF"):
        return M.Requester(emp, None)
    return M.Requester(emp, role)

def decide_arm(M, arm, u, fid, attr_used, treq_used, ledger, k):
    """returns (released:bool, rule:str, reason:str)"""
    f = M.FRAGS[fid]
    if arm == "ungoverned":
        return True, "-", "no-governance"
    if arm == "menu":
        # report-template 이진: 해당 attr에 어떤 open cell이라도 있으면 전 tier 릴리스
        return (u.cell(f["attr"]) is not None), "menu", "template-level"
    # iDPDM: (1) D_final 후보 게이트 (파스 attr·tier — retrieval filter의 평가판)
    if attr_used == "unknown":
        return False, "C1", "unknown-attr→deny"
    cell = u.cell(attr_used)
    if cell is None:
        return False, "C1", f"cell-miss({attr_used})"
    d_final = min(int(treq_used), cell[0])          # τ=1 headline: min(t_req, D_th)
    if f["attr"] != attr_used:
        return False, "D_final", f"attr-scope({f['attr']}≠{attr_used})"   # retrieval 폭 축소
    if f["tier"] > d_final:
        return False, "D_final", f"tier {f['tier']}>{d_final}"
    # (2) cl(): R3(조각 자체 셀 재검 — Prop 2' 보존) + R1 + R2(원장)
    res = M.cl(u, [fid], list(ledger), k=k)
    act, rule, why = res["verdicts"][fid]
    return (act == "release"), rule, why


# ── P0~P5 escalation 라우팅 (09_decide_spec §3, 누적) ──
def escalation_routed(policy_idx, *, permit, inj, ambig, unknown_attr,
                      peritem_tier, is_r1_target):
    if not permit:
        return False
    r = False
    if policy_idx >= 1: r |= inj
    if policy_idx >= 2: r |= ambig
    if policy_idx >= 3: r |= unknown_attr
    if policy_idx >= 4: r |= (peritem_tier == 3)
    if policy_idx >= 5: r |= is_r1_target
    return r

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coords", choices=["gt", "parser", "both"], default="both")
    ap.add_argument("--core", default=os.path.join(HERE, "deriv", "06_derivation_v2.py"))
    ap.add_argument("--queries", default=os.path.join(HERE, "query_set_v2.csv"))
    ap.add_argument("--parser-out", default=os.path.join(HERE, "parser_out.jsonl"))
    ap.add_argument("--out", default=os.path.join(HERE, "out_a1b"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    M = load_core(a.core)
    rows = list(csv.DictReader(open(a.queries, encoding="utf-8-sig")))
    parses = {}
    with open(a.parser_out, encoding="utf-8") as f:
        for line in f:
            p = json.loads(line); parses[p["query_id"]] = p
    assert len(rows) == 559 and len(parses) == 559

    K_SWEEP = [2, 3, 5, 10, 20]
    P_POLICIES = [0, 1, 2, 3, 4, 5]
    modes = ["gt", "parser"] if a.coords == "both" else [a.coords]

    def is_session(r): return r["pair_id"].startswith("PR")
    order = sorted(range(len(rows)),
                   key=lambda i: (rows[i]["pair_id"] if is_session(rows[i]) else f"~{i:04d}",
                                  int(rows[i]["turn"] or 0)))

    sweep, review = [], []
    for mode in modes:
        for k5 in K_SWEEP:
            ledgers = defaultdict(set)
            per = []
            for i in order:
                r = rows[i]
                fid = r["target_fragment_ids"].strip()
                u = mk_requester(M, r["persona"])
                k_ov, injected = parse_ob_tail(r["gt_obligations"])
                p = parses[r["query_id"]]
                attr_used = r["attr"] if mode == "gt" else p["attribute_group"]
                treq_used = r["t_req"] if mode == "gt" else p["req_tier"]
                key = (mode, k5, r["pair_id"]) if is_session(r) else None
                led = set(injected) | (ledgers[key] if key else set(injected))
                rel, rule, why = decide_arm(M, "idpdm", u, fid, attr_used, str(treq_used), led, k5)
                if rel and key: ledgers[key].add(fid)
                gt_wh = (r["gt_cl_action"] != "release")
                leak = int(gt_wh and rel); over = int((not gt_wh) and (not rel))
                inj = bool(p.get("injection_suspected")); ambig = bool(p.get("ambiguous"))
                unk = (attr_used == "unknown")
                ptier = M.FRAGS[fid]["tier"]
                fn = M.FRAGS[fid].get("n")
                is_r1 = ("R1" in rule) or (fn is not None and str(fn).isdigit()
                                           and 0 < int(fn) < k5)
                per.append((leak, over, rel, inj, ambig, unk, ptier, is_r1, gt_wh, r["query_id"]))
            wh = sum(x[8] for x in per); rl = len(per) - wh
            lk = sum(x[0] for x in per); ov = sum(x[1] for x in per)
            sweep.append([mode, k5, lk, f"{100*lk/max(wh,1):.1f}", ov,
                          f"{100*ov/max(rl,1):.1f}", wh, rl])
            for P in P_POLICIES:
                routed = leak_routed = 0
                for x in per:
                    rt = escalation_routed(P, permit=x[2], inj=x[3], ambig=x[4],
                                           unknown_attr=x[5], peritem_tier=x[6], is_r1_target=x[7])
                    routed += int(rt)
                    leak_routed += int(rt and x[0])
                review.append([mode, k5, f"P{P}", routed, f"{100*routed/len(per):.1f}",
                               lk - leak_routed])
    atomic_csv(os.path.join(a.out, "a1b_ksweep.csv"),
               ["coords","k","leak_n","leak_pct","over_n","over_pct","withhold","release"], sweep)
    atomic_csv(os.path.join(a.out, "a1b_review.csv"),
               ["coords","k","policy","review_n","review_pct","leak_after_route"], review)

    gate = []
    def gk(mode,k):
        for s in sweep:
            if s[0]==mode and s[1]==k: return s
    ok = True
    if "gt" in modes:
        a5 = gk("gt",5)
        ok &= (a5[2]==0 and a5[4]==0); gate.append(["gt anchor k5 leak0/over0", a5[2], a5[4]])
        k2 = gk("gt",2); ok &= (k2[2] > 0); gate.append(["gt k=2 leak>0", k2[2], k2[3]])
        k20 = gk("gt",20); gate.append(["gt k=20 over_n", k20[4], ""])
        mono_all = True
        for mode in modes:
            for k5 in K_SWEEP:
                seq = [int(r[3]) for r in review if r[0]==mode and r[1]==k5]
                mono_all &= all(seq[j] <= seq[j+1] for j in range(len(seq)-1))
        ok &= mono_all
        gate.append(["P0..P5 review 단조성", "PASS" if mono_all else "FAIL", ""])
    atomic_csv(os.path.join(a.out, "a1b_gate.csv"), ["check","v1","v2"], gate)

    man = dict(experiment="A1b", coords=a.coords, k_sweep=K_SWEEP, policies=P_POLICIES,
               queryset_hash=sha16(a.queries), parser_out_hash=sha16(a.parser_out),
               fragset_hash=M.FRAGSET_HASH, gate="PASS" if ok else "FAIL")
    with open(os.path.join(a.out, "a1b_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)

    print("\n═══ k-스윕 (iDPDM) ═══")
    for s in sweep: print(" ", s)
    print("\n═══ review load (P0~P5, k=5) ═══")
    for r in review:
        if r[1]==5: print(" ", r)
    print(f"\n게이트: {'PASS' if ok else 'FAIL'}")
    for c in gate: print("  ", c)
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
