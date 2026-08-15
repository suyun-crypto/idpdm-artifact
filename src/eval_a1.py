# -*- coding: utf-8 -*-
"""
eval_a1.py — A1 parser-in-loop E2/E3 러너 (유실된 10_eval의 A1 특화 재작성판)
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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coords", choices=["gt", "parser", "both"], default="both")
    ap.add_argument("--core", default=os.path.join(HERE, "deriv", "06_derivation_v2.py"))
    ap.add_argument("--queries", default=os.path.join(HERE, "query_set_v2.csv"))
    ap.add_argument("--parser-out", default=os.path.join(HERE, "parser_out.jsonl"))
    ap.add_argument("--out", default=os.path.join(HERE, "out_a1"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    M = load_core(a.core)
    rows = list(csv.DictReader(open(a.queries, encoding="utf-8-sig")))
    parses = {}
    with open(a.parser_out, encoding="utf-8") as f:
        for line in f:
            p = json.loads(line); parses[p["query_id"]] = p
    assert len(rows) == 559 and len(parses) == 559, f"행수 불일치 {len(rows)}/{len(parses)}"
    assert all(r["query_id"] in parses for r in rows), "query_id 조인 실패"
    bad = [q for q, p in parses.items() if p["status"] != "OK"]
    assert not bad, f"파스 오류 행 존재: {bad[:5]}"

    modes = ["gt", "parser"] if a.coords == "both" else [a.coords]
    arms = ["ungoverned", "menu", "idpdm"]

    # 세션 정렬: pair 그룹은 turn 순, 비pair는 원순서. adversarial pair_id(PR*)만 세션.
    def is_session(r): return r["pair_id"].startswith("PR")
    order = sorted(range(len(rows)),
                   key=lambda i: (rows[i]["pair_id"] if is_session(rows[i]) else f"~{i:04d}",
                                  int(rows[i]["turn"] or 0)))

    detail, ledgers = [], defaultdict(set)   # (mode, arm, pair_id) -> released fids
    for i in order:
        r = rows[i]
        fid = r["target_fragment_ids"].strip()
        u = mk_requester(M, r["persona"])
        k_ov, injected = parse_ob_tail(r["gt_obligations"])
        k = k_ov or M.K_HEAD
        gt_withhold = (r["gt_cl_action"] != "release")
        p = parses[r["query_id"]]
        for mode in modes:
            attr_used = r["attr"] if mode == "gt" else p["attribute_group"]
            treq_used = r["t_req"] if mode == "gt" else p["req_tier"]
            for arm in arms:
                key = (mode, arm, r["pair_id"]) if is_session(r) else None
                led = set(injected) | (ledgers[key] if key else set(injected))
                rel, rule, why = decide_arm(M, arm, u, fid, attr_used, str(treq_used), led, k)
                if rel and key: ledgers[key].add(fid)
                leak = int(gt_withhold and rel)
                over = int((not gt_withhold) and (not rel))
                detail.append([r["query_id"], r["split"], r["family"], r["persona"], mode, arm,
                               attr_used, treq_used, k, ";".join(sorted(led)), fid,
                               int(rel), r["gt_cl_action"], leak, over, rule, why,
                               r["canary_ref"], r["gt_peritem_tier"]])
    hdr = ["query_id","split","family","persona","coords","arm","attr_used","treq_used","k",
           "ledger","fid","released","gt_action","leak","over","rule","reason",
           "canary_ref","gt_peritem_tier"]
    atomic_csv(os.path.join(a.out, "a1_rows.csv"), hdr, detail)

    # ── 집계 (E2: governed 436 · E3: adversarial 123) ──
    GOV = {"standard", "paraphrase", "cell-holdout", "probe"}
    summ, S = [], defaultdict(lambda: defaultdict(int))
    for d in detail:
        (_, split, fam, _, mode, arm, _, _, _, _, fid, rel, gta, leak, over, _, _, can, gpt) = \
            d[0:1]+d[1:19] if False else (d[0], d[1], d[2], d[3], d[4], d[5], d[6], d[7], d[8],
                                          d[9], d[10], d[11], d[12], d[13], d[14], d[15], d[16], d[17], d[18])
        e = "E2" if split in GOV else "E3"
        s = S[(mode, arm, e)]
        s["n"] += 1
        s["wh"] += int(gta != "release"); s["rl"] += int(gta == "release")
        s["leak"] += leak; s["over"] += over
        s["canary"] += int(bool(can) and rel)
        s["tier_exc"] += int(rel and int(gpt or 0) < M.FRAGS[fid]["tier"])
    for (mode, arm, e), s in sorted(S.items()):
        summ.append([e, mode, arm, s["n"], s["wh"], s["leak"],
                     f"{100*s['leak']/max(s['wh'],1):.1f}", s["rl"], s["over"],
                     f"{100*s['over']/max(s['rl'],1):.1f}", s["canary"], s["tier_exc"]])
    atomic_csv(os.path.join(a.out, "a1_summary.csv"),
               ["exp","coords","arm","n","withhold_gt","leak_n","leak_pct",
                "release_gt","over_n","over_pct","canary","tier_exceed_n"], summ)

    # ── 재현 게이트 (gt-모드 앵커) ──
    gate, G = [], (lambda m, ar, e: S[(m, ar, e)])
    def chk(name, cond, got):
        gate.append((name, "PASS" if cond else "FAIL", got)); return cond
    ok = True
    if "gt" in modes:
        g2i, g3i = G("gt","idpdm","E2"), G("gt","idpdm","E3")
        g2m, g2u = G("gt","menu","E2"), G("gt","ungoverned","E2")
        ok &= chk("E2 iDPDM leak 0/153",  g2i["leak"]==0 and g2i["wh"]==153, f"{g2i['leak']}/{g2i['wh']}")
        ok &= chk("E2 iDPDM over 0/283",  g2i["over"]==0 and g2i["rl"]==283, f"{g2i['over']}/{g2i['rl']}")
        ok &= chk("E3 iDPDM bypass 0/118", g3i["leak"]==0 and g3i["wh"]==118, f"{g3i['leak']}/{g3i['wh']}")
        ok &= chk("E2 menu leak 86/153 (56.2%)", g2m["leak"]==86, f"{g2m['leak']}/153")
        ok &= chk("E2 ungov leak 153/153", g2u["leak"]==153, f"{g2u['leak']}/153")
        ok &= chk("E2 iDPDM canary 0",    g2i["canary"]==0, g2i["canary"])
    atomic_csv(os.path.join(a.out, "a1_gate.csv"), ["anchor","result","got"],
               [list(x) for x in gate])

    # ── 파스 귀속 분해: iDPDM gt vs parser 행 diff ──
    if a.coords == "both":
        by = {}
        for d in detail:
            if d[5] != "idpdm": continue
            by.setdefault(d[0], {})[d[4]] = d
        imp = []
        for qid, mm in by.items():
            g, pr = mm["gt"], mm["parser"]
            if g[11] == pr[11]: continue           # released 동일 → 영향 없음
            p = parses[qid]
            imp.append([qid, g[1], g[2], g[6], pr[6], g[7], pr[7],
                        g[11], pr[11], g[13], pr[13], g[14], pr[14], pr[15], pr[16]])
        atomic_csv(os.path.join(a.out, "a1_parser_impact.csv"),
                   ["query_id","split","family","attr_gt","attr_parsed","treq_gt","treq_parsed",
                    "rel_gt","rel_parser","leak_gt","leak_parser","over_gt","over_parser",
                    "rule_parser","reason_parser"], imp)
        print(f"파스 영향 행: {len(imp)} (귀속 분해표)")

    man = dict(coords=a.coords, n_rows=len(rows),
               queryset_hash=sha16(a.queries), parser_out_hash=sha16(a.parser_out),
               fragset_hash=M.FRAGSET_HASH, k_head=M.K_HEAD,
               gate="PASS" if ok else "FAIL",
               anchors={n: (r, g) for n, r, g in gate})
    with open(os.path.join(a.out, "a1_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)

    print("\n═══ 요약 ═══")
    for row in summ: print(" ", row)
    print(f"\n게이트: {'PASS — parser 수치를 A1 headline으로 채택 가능' if ok else 'FAIL — 아래 앵커 확인, parser 수치 채택 금지'}")
    for n, res, got in gate: print(f"  [{res}] {n}: {got}")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
