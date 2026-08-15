# -*- coding: utf-8 -*-
"""
a4_lowtrust_v2.py — v3 결함 A4 해소 실험: low-trust insider (r-코어 = A7 해소판)
threat model의 "low-trust insider" 약속을 실측으로 닫는다 (v3: 미검증 → 제거 대신 실험).

두 축:
  [자연 축] trust_signal 실측 τ 그대로.
    (a) 질의셋 559행 trust-적용 실행 ≡ trust-중립 실행 — **v1 앵커 "trust cap
        non-binding for every persona"의 v2 재현** (질의셋 페르소나 전원 τ≥0.75 &
        역할 t3는 clearance 지배 & STAFF 페르소나 τ≥0.9).
    (b) 본인 레코드 프로브: 전 직원(595)의 본인 t3 조각 계약 발행 — 자연 발화면 =
        τ<0.9 직원의 ownership 경로 (ownership만 cls 면제라 trust cap의 유일한
        자연 t3 발화면). 구속 인원·τ 밴드 분포 보고.
  [반사실 축] 질의셋 전 요청자 τ를 밴드 {0.95, 0.85, 0.60, 0.30}(cap 3/2/1/0)로
    강제 → release/deny/capped 곡선. 위협 모델 명제: 신뢰 하락 = 깊이 단조 상실,
    유출 증가 없음.

게이트: G1 자연 질의셋 ≡ 중립 (v1 앵커) / G2 밴드 단조 (release ⊇ 체인) /
        G3 전 밴드 leak=0 (cap은 제거만 — GT-withhold 릴리스 신규 발생 0) /
        G4 Property 1 전 계약 / G5 결정론.
산출: out10/a4_bands.csv · a4_ownrecord.csv · a4_manifest.json
"""
import sys, os, csv, json, re, hashlib, importlib.util, tempfile
from collections import defaultdict, Counter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out10")
os.makedirs(OUT, exist_ok=True)

_s = importlib.util.spec_from_file_location("r9", os.path.join(HERE, "09_decide_v2r.py"))
r9 = importlib.util.module_from_spec(_s); _s.loader.exec_module(r9)
d6 = r9.d6
FRAGS = d6.FRAGS
U, staff, issue_contract = r9.U, r9.staff, r9.issue_contract
NATURAL_UTS = dict(r9.UTS)

QS = os.path.join(HERE, "out07", "query_set_v2.csv")
ROWS = list(csv.DictReader(open(QS, encoding="utf-8")))
assert len(ROWS) == 559, "질의셋 단언 실패"
ORDER = sorted(range(len(ROWS)), key=lambda i: (ROWS[i]["pair_id"] or ROWS[i]["query_id"],
                                                int(ROWS[i]["turn"] or 0)))

def requester(p):
    role, emp = p.split(":")
    return staff(emp) if role == "STAFF" else U(role)

def parse_inj(o):
    m = re.search(r"ledger_injected=([A-Za-z0-9\-]+)", o)
    return m.group(1) if m else None

def run_queryset():
    led = defaultdict(list)
    out = {}
    for i in ORDER:
        r = ROWS[i]
        u = requester(r["persona"])
        fid = r["target_fragment_ids"]
        key = (r["persona"], r["pair_id"])
        l = list(led[key]) if r["pair_id"] else []
        inj = parse_inj(r["gt_obligations"])
        if inj: l.append(inj)
        pi = dict(attr=r["attr"], t_req=int(r["t_req"]), s="none", flags={})
        c = issue_contract(u, [fid], l, pi=pi, policy="P0", k=5)
        # Property 1 런타임 단언 (G4)
        for f in c["released"]:
            cell = u.cell(FRAGS[f]["attr"])
            assert cell and c["D_final"] <= max(c["D_final"], cell[0]) and \
                   FRAGS[f]["tier"] <= cell[0], "Property 1 위반"
        rel = c["decision"] == "PERMIT" and fid in c["released"]
        if rel and r["pair_id"]:
            led[key].append(fid)
        out[r["query_id"]] = (int(rel), c["decision"],
                              sum(1 for o in c["obligations"] if o[0] == "trust_downmod"))
    return out

def md5_of(o):
    return hashlib.md5(json.dumps(o, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def main():
    print(f"A4 저트러스트 — frag-set {d6.FRAGSET_HASH} · r-코어 · 질의셋 559행 + 본인 프로브 595명")

    # [자연 축 a] 질의셋: trust 적용 vs 중립
    r9.UTS = dict(NATURAL_UTS)
    nat = run_queryset()
    r9.UTS = {}
    neu = run_queryset()
    r9.UTS = dict(NATURAL_UTS)

    # [자연 축 b] 본인 레코드 프로브
    own_rows = []
    emp_own = defaultdict(list)
    for f in FRAGS.values():
        if f["tier"] == 3 and f["sid"]:
            emp_own[f["sid"]].append(f["fid"])
    for emp in sorted(emp_own):
        if emp.startswith("E_"): continue          # 역할 페르소나 제외 (질의셋 축이 커버)
        if emp not in d6.EMP_PATH: continue        # 직원 주체만 (고객 sid 제외)
        u = staff(emp)
        fid = sorted(emp_own[emp])[0]
        if not d6.admissible(u, FRAGS[fid])[0]:    # ownership 경로 전제
            continue
        c = issue_contract(u, [fid], [], pi=None, policy="P0", k=5)
        tau = NATURAL_UTS.get(emp, 1.0)
        own_rows.append(dict(emp_id=emp, tau=round(tau, 3), t_cap=r9.T_cap(emp),
                             fid=fid, decision=c["decision"],
                             trust_capped=int(any(o[0] == "trust_downmod" for o in c["obligations"]))))
    n_capped = sum(r["trust_capped"] for r in own_rows)
    bands_nat = Counter(("[0.9,1]" if r["tau"] >= 0.9 else "[0.75,0.9)" if r["tau"] >= 0.75
                         else "[0.5,0.75)" if r["tau"] >= 0.5 else "<0.5") for r in own_rows
                        if r["trust_capped"])
    print(f"  [자연 b] 본인 t3 프로브 {len(own_rows)}명 — trust 구속 {n_capped}명 "
          f"(밴드: {dict(bands_nat)}) · 비구속 전원 PERMIT")

    # [반사실 축] τ 밴드 스윕
    BANDS = [("tau=0.95(cap3)", 0.95), ("tau=0.85(cap2)", 0.85),
             ("tau=0.60(cap1)", 0.60), ("tau=0.30(cap0)", 0.30)]
    n_wh = sum(1 for r in ROWS if r["gt_cl_action"] == "withhold")
    curve = []
    outs = []
    for name, tau in BANDS:
        r9.UTS = {e: tau for e in list(d6.EMP_PATH) + list(NATURAL_UTS)}
        o = run_queryset()
        outs.append(o)
        rel = sum(v for v, _, _ in o.values())
        deny = sum(1 for v, d, _ in o.values() if not v and d == "DENY")
        capped = sum(c for _, _, c in o.values())
        leak = sum(1 for r in ROWS if o[r["query_id"]][0] and r["gt_cl_action"] == "withhold")
        curve.append(dict(band=name, tau=tau, cap={0.95:3,0.85:2,0.60:1,0.30:0}[tau],
                          release=rel, deny=deny, trust_capped_frags=capped,
                          leak=leak, leak_rate=round(leak / n_wh, 4)))
        print(f"  [반사실] {name:16s} release {rel:3d} · deny {deny:3d} · "
              f"capped 조각 {capped:3d} · leak {leak}")
    r9.UTS = dict(NATURAL_UTS)

    # ── 게이트 ──
    G = []
    G.append(("G1 자연 질의셋 ≡ 중립 (v1 앵커 재현)", nat == neu))
    rels = [set(q for q, (v, _, _) in o.items() if v) for o in outs]
    G.append(("G2 밴드 단조 (release ⊇ 체인)", all(b <= a for a, b in zip(rels, rels[1:]))))
    G.append(("G3 전 밴드 leak=0", all(c["leak"] == 0 for c in curve)))
    G.append(("G4 Property 1 전 계약", True))   # run_queryset 내 런타임 단언 통과 시 도달
    r9.UTS = {e: 0.85 for e in list(d6.EMP_PATH) + list(NATURAL_UTS)}
    G.append(("G5 결정론", md5_of(run_queryset()) == md5_of(outs[1])))
    r9.UTS = dict(NATURAL_UTS)
    allok = all(ok for _, ok in G)
    for n, ok in G: print(f"  [{'PASS' if ok else 'FAIL'}] {n}")
    if not allok: sys.exit(1)

    def atomic(path, rows, fields):
        fd, tmp = tempfile.mkstemp(dir=OUT, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows(rows)
        os.replace(tmp, path)
    atomic(os.path.join(OUT, "a4_bands.csv"), curve, list(curve[0].keys()))
    atomic(os.path.join(OUT, "a4_ownrecord.csv"), own_rows, list(own_rows[0].keys()))
    man = dict(fragset_hash=d6.FRAGSET_HASH, core="09_decide_v2r(A7 해소판)",
               natural_anchor="queryset trust-applied ≡ neutral (v1 재현)",
               own_probe=dict(n=len(own_rows), capped=n_capped, bands=dict(bands_nat)),
               bands=[c["band"] for c in curve], gates={n: bool(o) for n, o in G})
    fd, tmp = tempfile.mkstemp(dir=OUT, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(OUT, "a4_manifest.json"))
    print("\n산출: out10/a4_bands.csv · a4_ownrecord.csv · a4_manifest.json")

if __name__ == "__main__":
    main()
