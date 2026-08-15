# -*- coding: utf-8 -*-
"""
e5_opcurve_a1.py — E5 개조판 (2026-08-08). 원판 e5_opcurve_v2.py 기반:
  [A] 코어 = 09_decide_v2r. [B] --coords gt|parser. parser 모드 기대 (논문 §VI-F):
  P4 review 8.9% · P5 14.8% (파서 과차단이 릴리스를 먼저 제거 → 부하 감소),
  k=20 over_silent 58 (isolated 24 + 파서 협소화 증분), (P0,k=5) over 34
  (= governed 33 + 적대 1: A0569 skip-control). 전 항목 2026-08-08 실측 확인.
원판 주석:
e5_opcurve_v2.py — 10_eval E5: 운영곡선 P0~P5 × k∈{2,3,5,10,20} (E4 그림 9 확장)
두 축 = 09의 escalation 정책(P0~P5 누적) × 06의 k 스윕. 전 질의 559행, trust 중립.

의미론:
  released_eff = (decision==PERMIT) ∧ fid∈released ∧ cipp 통과.
  decision==ESCALATE = 검토 라우팅 (릴리스 아님 — review 부담으로 계상).
  F7 시퀀스: pair 원장 = 콤보별 arm 실릴리스 누적 + 07 주입 원장.
  flags = e1_flag_gt_rules 정본: F1·F2 → injection / cell-holdout → ambiguous.
  GT 대조 = 정본 GT (행별 인코딩 k — 스윕 k와 무관). leak_vs_canon = "(P,k)로 운영 시
  정본 위반 릴리스가 얼마나 나는가", review = 검토 부담. k<정본이면 집계 조기 릴리스
  = leak 발생, k>정본이면 과보류 — 이것이 트레이드오프 곡선.

게이트: G1 (P0,k=5) = E2·E3 재현 (leak 0 · over-restr 0) /
        G2 policy 단조 (고정 k: release 비증가·escalate 비감소) /
        G3 k 단조 (고정 policy: release 비증가) / G4 결정론.
"""
import sys, os, csv, json, re, hashlib, importlib.util, tempfile
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out10")
os.makedirs(OUT, exist_ok=True)

_CORE = os.environ.get("IDPDM_CORE", "09_decide_v2r.py")
_s = importlib.util.spec_from_file_location("d9", os.path.join(HERE, _CORE))
d9 = importlib.util.module_from_spec(_s); _s.loader.exec_module(d9)
d6 = d9.d6
FRAGS = d6.FRAGS
U, staff, issue_contract, reference_pep = d9.U, d9.staff, d9.issue_contract, d9.reference_pep
d9.UTS = {}   # trust 중립 (E2 확정 승계)


# ── A1 인자 (2026-08-08 개조) ───────────────────────────────────────────────
import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("--coords", choices=["gt", "parser"], default="gt")
_ap.add_argument("--parser-out", default=os.path.join(HERE, "..", "parser_out.jsonl"))
_ap.add_argument("--tag", default=None)
ARGS = _ap.parse_args()
TAG = ARGS.tag or ARGS.coords
PARSES = {}
if ARGS.coords == "parser":
    for _l in open(ARGS.parser_out, encoding="utf-8"):
        _l = _l.strip()
        if _l:
            _o = json.loads(_l); PARSES[_o["query_id"]] = _o
    print(f"[A1] parser_out {len(PARSES)}행 — 좌표 = 파스 (오라클 GT 불변)")

def a1_pi(r, gt_flag_fn):
    """좌표 출처 분기. parser 모드에서도 flags는 GT 규칙 유지(파서 flag 실측은 E1 몫)."""
    if ARGS.coords == "gt":
        return dict(attr=r["attr"], t_req=int(r["t_req"]), s="none", flags=gt_flag_fn(r))
    p = PARSES[r["query_id"]]
    a = p.get("attribute_group") or p.get("attr")
    tq = p.get("req_tier", p.get("t_req"))
    try: tq = int(tq)
    except (TypeError, ValueError): tq = 3
    fl = dict(gt_flag_fn(r))
    for kk, vv in (p.get("flags") or {}).items():
        if vv: fl[kk] = True
    return dict(attr=a, t_req=tq, s="none", flags=fl)

def a1_narrowed(pi, fid):
    """검색 경계(§IV-H tier ≤ D_final): 파스 좌표가 후보를 좁힌다. gt 모드에선 항상 False."""
    if ARGS.coords != "parser":
        return None
    f = FRAGS[fid]
    if pi["attr"] != f["attr"]:
        return "scope-narrowed:attr"
    if f["tier"] > pi["t_req"]:
        return "scope-narrowed:tier"
    return None

QS = os.path.join(HERE, "out07", "query_set_v2.csv")
ROWS = list(csv.DictReader(open(QS, encoding="utf-8")))
assert len(ROWS) == 559 and "gt_cl_action" in ROWS[0], "query_set 단언 실패"

POLICIES = ["P0", "P1", "P2", "P3", "P4", "P5"]
KSWEEP = [2, 3, 5, 10, 20]

def requester(p):
    role, emp = p.split(":")
    return staff(emp) if role == "STAFF" else U(role)

def parse_inj(gt_obl):
    m = re.search(r"ledger_injected=([A-Za-z0-9\-]+)", gt_obl)
    return m.group(1) if m else None

def gt_flags(r):
    if r["family"] in ("F1", "F2"): return dict(injection_suspected=True)
    if r["split"] == "cell-holdout": return dict(ambiguous=True)
    return {}

ORDER = sorted(range(len(ROWS)), key=lambda i: (ROWS[i]["pair_id"] or ROWS[i]["query_id"],
                                                int(ROWS[i]["turn"] or 0)))

def run_combo(policy, k):
    led_state = defaultdict(list)
    out = {}
    for i in ORDER:
        r = ROWS[i]
        u = requester(r["persona"])
        fid = r["target_fragment_ids"]
        key = (r["persona"], r["pair_id"])
        led = list(led_state[key]) if r["pair_id"] else []
        inj = parse_inj(r["gt_obligations"])
        if inj: led.append(inj)
        pi = a1_pi(r, gt_flags)
        nar = a1_narrowed(pi, fid)
        if nar:
            c = dict(decision="DENY(" + nar + ")", released=[])
            rel = False
        else:
            c = issue_contract(u, [fid], led, pi=pi, policy=policy, k=k)
            blocks = reference_pep(u, c)
            rel = (c["decision"] == "PERMIT" and fid in c["released"]
                   and not any(b[1] == fid for b in blocks))
        if rel and r["pair_id"]:
            led_state[key].append(fid)
        out[r["query_id"]] = (rel, c["decision"])
    return out

def metrics(out):
    n = len(ROWS)
    rel = esc = deny = leak = over_sil = over_esc = 0
    for r in ROWS:
        v, dec = out[r["query_id"]]
        gt_rel = r["gt_cl_action"] == "release"
        if v: rel += 1
        elif dec == "ESCALATE": esc += 1
        else: deny += 1
        if v and not gt_rel: leak += 1
        if not v and gt_rel:
            if dec == "ESCALATE": over_esc += 1
            else: over_sil += 1
    n_wh = sum(1 for r in ROWS if r["gt_cl_action"] == "withhold")
    n_rl = n - n_wh
    return dict(release=rel, escalate=esc, deny=deny,
                release_rate=round(rel / n, 4), review_rate=round(esc / n, 4),
                leak=leak, leak_rate=round(leak / n_wh, 4),
                over_silent=over_sil, over_escal=over_esc,
                over_rate=round((over_sil + over_esc) / n_rl, 4))

def md5_of(o):
    return hashlib.md5(json.dumps(o, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def main():
    print(f"E5 운영곡선 — frag-set {d6.FRAGSET_HASH} · {len(ROWS)}행 × "
          f"{len(POLICIES)}정책 × {len(KSWEEP)}k = {len(POLICIES)*len(KSWEEP)}콤보 · trust 중립")
    curve = []
    outs = {}
    for k in KSWEEP:
        for pol in POLICIES:
            o = run_combo(pol, k)
            outs[(pol, k)] = o
            m = metrics(o)
            curve.append(dict(policy=pol, k=k, **m))
    for c in curve:
        if c["k"] in (2, 5, 20):
            print(f"  k={c['k']:2d} {c['policy']}  rel {c['release']:3d} ({c['release_rate']:.0%}) · "
                  f"review {c['escalate']:3d} ({c['review_rate']:.1%}) · deny {c['deny']:3d} · "
                  f"leak {c['leak']:2d} ({c['leak_rate']:.1%}) · over {c['over_silent']}+{c['over_escal']}e")

    # ── 게이트 ──
    G = []
    m05 = next(c for c in curve if c["policy"] == "P0" and c["k"] == 5)
    if ARGS.coords == "gt":
        G.append(("G1 (P0,k=5) = E2·E3 재현 (leak 0 · over 0)",
                  m05["leak"] == 0 and m05["over_silent"] == 0 and m05["over_escal"] == 0))
    else:
        # 분모 주의: E5는 559행 전체(적대 123 포함). governed 33 + 적대 1
        # (A0569 F7-join-skip, 보수적 tier 하향 — §VI-D "a single lawful
        # skip-control over-withheld") = 34. E2(436행)의 33과 정합.
        G.append(("G1p (P0,k=5) parser: leak 0 · over 34 (=33 governed + 1 adversarial)",
                  m05["leak"] == 0 and (m05["over_silent"] + m05["over_escal"]) == 34))
        p4 = next(c for c in curve if c["policy"] == "P4" and c["k"] == 5)
        p5 = next(c for c in curve if c["policy"] == "P5" and c["k"] == 5)
        print(f"  [A1] parser 모드 review: P4 {p4['review_rate']:.1%} · P5 {p5['review_rate']:.1%}"
              f"  (논문 8.9% · 14.8%)")
    mono_p = True
    for k in KSWEEP:
        rels = [set(q for q, (v, _) in outs[(p, k)].items() if v) for p in POLICIES]
        escs = [sum(1 for q, (v, d) in outs[(p, k)].items() if d == "ESCALATE") for p in POLICIES]
        for a, b in zip(rels, rels[1:]):
            if not b <= a: mono_p = False
        for a, b in zip(escs, escs[1:]):
            if b < a: mono_p = False
    G.append(("G2 policy 단조 (release⊇ · escalate↑)", mono_p))
    mono_k = True
    for p in POLICIES:
        rels = [set(q for q, (v, _) in outs[(p, k)].items() if v) for k in KSWEEP]
        for a, b in zip(rels, rels[1:]):
            if not b <= a: mono_k = False
    G.append(("G3 k 단조 (release⊇)", mono_k))
    G.append(("G4 결정론", md5_of(run_combo("P1", 5)) == md5_of(outs[("P1", 5)])))
    allok = all(ok for _, ok in G)
    for n, ok in G: print(f"  [{'PASS' if ok else 'FAIL'}] {n}")
    if not allok: sys.exit(1)

    def atomic(path, rows, fields):
        fd, tmp = tempfile.mkstemp(dir=OUT, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows(rows)
        os.replace(tmp, path)
    atomic(os.path.join(OUT, f"e5_curve_{TAG}.csv"), curve, list(curve[0].keys()))
    man = dict(core=_CORE, coords=ARGS.coords, fragset_hash=d6.FRAGSET_HASH, n=len(ROWS), policies=POLICIES, ksweep=KSWEEP,
               trust="neutral", gates={n: bool(o) for n, o in G}, curve_md5=md5_of(curve))
    fd, tmp = tempfile.mkstemp(dir=OUT, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(OUT, f"e5_manifest_{TAG}.json"))
    print(f"\n산출: out10/e5_curve_{TAG}.csv · e5_manifest_{TAG}.json")

if __name__ == "__main__":
    main()
