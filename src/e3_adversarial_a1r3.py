# -*- coding: utf-8 -*-
"""
e3_adversarial_a1r3.py — a1 개조판 + [D] R3-only 대조열 (2026-08-15). a1 대비 변경 = [D]뿐:
  [D] r3only 대조열 — idealized per-item control (E2 r3only와 동일 의미론).
      판정 = d6.cl(use_r1=False, use_r2=False), 원장 무참조 (per-item은 세션
      상태를 정의상 보지 않음 — F7 통과가 곧 논지). parser 모드에선 pdp와
      동일 검색 경계 적용.
      기대 (7/31 CSV 재대조): bypass 8/118 전건 F7 = {A0548,A0550,A0552,A0554,
      A0556,A0558,A0562,A0566} (diff-R1 3 · diff-R2 3 · join 2[R1 귀속 —
      C-c1 카나리아 G05-02596 표적]) · 카나리아 릴리스 ≥1.
      게이트 G7: gt 모드에서 r3only ≡ gt_peritem_permit 전건 (열 존재 시).

원판 e3_adversarial_a1.py 주석 (2026-08-08) — 원판 e3_adversarial_v2.py 기반:
  [A] 코어 = 09_decide_v2r (A7 해소판). [B] --coords gt|parser (parser 모드 =
  논문 헤드라인 "parser in the loop"). 오라클(gt_cl_action) 불변. 검색 경계
  적용 — 파스 attr 불일치·tier 초과 시 후보 제외. 게이트 G2는 모드별 분기
  (gt: PDP≡GT / parser: bypass 0 유지 — §VI-D "leaves every count intact").
원판 주석:
e3_adversarial_v2.py — 10_eval E3: 적대 채점 (F1~F7 123건 → 09 계약)
§VI-F "NL 후속"의 실측 전환점 (판정층 채점 — 파서 잔차는 E1 로컬 몫).

채점 원칙:
  구동 = GT 좌표 (파스 무관 — 09 스펙 §0 "정본 판정은 파스 무관하게 GT 좌표로도 구동").
  flags = e1_flag_gt_rules 정본 (F1·F2 → injection_suspected). P0 헤드라인에선 라우팅
  없음 — flag는 기록만 (E5의 P1+ 축 입력). trust 중립 (E2 확정 승계).

F7 = 시퀀스 실행: pair 단위 turn 순서 처리, 원장 = arm이 실제 릴리스한 조각 누적
  (GT 인코딩 ledger와의 일치를 게이트로 단언 — arm ≡ GT일 때 동치). k = 행별 인코딩.
  검증 3종: ① bypass(릴리스 ∧ GT-withhold) ② F7-neg 음성 대조 (release, release)
  ③ ledger-obligation 검증 — 릴리스에 session_ledger, 보류에 k_threshold/R2 계열
  obligation 존재 + verify_obligations 오류 0 (06 cl 경유).

지표: family별 bypass율 (v1 앵커: 전체 0.9%) · off/menu 대조열 · F7 검증 3종.
게이트: G1 123행 전건 / G2 PDP bypass=0 ∧ GT 전건 일치 / G3 F7-neg (release,release)
        / G4 F7 원장 재구성 = GT 인코딩 일치 / G5 obligation 검증 오류 0 / G6 결정론.
"""
import sys, os, csv, json, re, hashlib, importlib.util, tempfile
from collections import defaultdict, Counter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out10")
os.makedirs(OUT, exist_ok=True)

_CORE = os.environ.get("IDPDM_CORE", "09_decide_v2r.py")
_s = importlib.util.spec_from_file_location("d9", os.path.join(HERE, _CORE))
d9 = importlib.util.module_from_spec(_s); _s.loader.exec_module(d9)
d6 = d9.d6
FRAGS, CANARY = d6.FRAGS, d6.CANARY
U, staff, issue_contract, reference_pep = d9.U, d9.staff, d9.issue_contract, d9.reference_pep
d9.UTS = {}   # trust 중립 (E2 확정 승계 — 저트러스트는 A4 몫)


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
rows_all = list(csv.DictReader(open(QS, encoding="utf-8")))
assert rows_all and "gt_cl_action" in rows_all[0], "query_set 헤더 단언 실패"
E3 = [r for r in rows_all if r["split"] == "adversarial"]
assert len(E3) == 123, f"E3 분모 단언 실패: {len(E3)}"

def requester(p):
    role, emp = p.split(":")
    return staff(emp) if role == "STAFF" else U(role)

def parse_ctx(gt_obl):
    k = 5
    m = re.search(r"k=(\d+)", gt_obl)
    if m: k = int(m.group(1))
    inj = None
    m = re.search(r"ledger_injected=([A-Za-z0-9\-]+)", gt_obl)
    if m: inj = m.group(1)
    enc_ledger = None   # GT 인코딩 원장 (시퀀스 turn2의 기대 원장 — 빈 문자열 = 빈 원장)
    m = re.search(r";ledger=([A-Za-z0-9\-]*)", gt_obl)
    if m: enc_ledger = m.group(1)
    return k, inj, enc_ledger

def gt_flags(family):
    """e1_flag_gt_rules 정본: F1·F2 → injection true."""
    return dict(injection_suspected=True) if family in ("F1", "F2") else {}

REPORT_ATTRS = defaultdict(set)
for f in FRAGS.values():
    REPORT_ATTRS[f["rid"]].add(f["attr"])
def menu_granted(u, rid):
    return any(u.cell(a) for a in REPORT_ATTRS[rid])

def evaluate():
    recs = []
    ledger_state = defaultdict(list)     # (persona, pair_id) -> arm(pdp) 릴리스 누적
    ledger_gate = []                     # (재구성 원장, GT 인코딩 원장) 대조
    # 시퀀스 정렬: pair 내 turn 오름차순 — CSV 원 순서가 이미 정렬이나 명시 정렬로 고정
    order = sorted(range(len(E3)), key=lambda i: (E3[i]["pair_id"] or E3[i]["query_id"],
                                                  int(E3[i]["turn"] or 0)))
    for i in order:
        r = E3[i]
        u = requester(r["persona"])
        fid = r["target_fragment_ids"]
        assert fid in FRAGS, f"조각 부재: {fid}"
        k, inj, enc = parse_ctx(r["gt_obligations"])
        key = (r["persona"], r["pair_id"])
        led = list(ledger_state[key]) if r["pair_id"] else []
        if inj: led.append(inj)          # F7-diff 원장 주입 시나리오 (07 정본)
        if enc is not None:              # 게이트 대조: 재구성 원장 vs GT 인코딩
            recon = "|".join(sorted(set(led) - ({inj} if inj else set())))
            ledger_gate.append((r["query_id"], recon, enc))
        pi = a1_pi(r, lambda rr: gt_flags(rr["family"]))
        # [D] r3only — per-item만, 원장 무참조 (F7 세션 상태에 눈감는 것이 정의)
        nar3 = a1_narrowed(pi, fid)
        if nar3:
            r3rel = False
        else:
            r3res = d6.cl(u, [fid], [], k, use_r1=False, use_r2=False)
            r3rel = r3res["verdicts"][fid][0] == "release"
        nar = a1_narrowed(pi, fid)
        if nar:
            c = dict(released=[], decision="DENY(" + nar + ")", obligations=[], verrs=[])
            blocks = []
            rel = False
        else:
            c = issue_contract(u, [fid], led, pi=pi, policy="P0", k=k)
            blocks = reference_pep(u, c)
            rel = fid in c["released"] and not any(b[1] == fid for b in blocks)
        if rel and r["pair_id"]:
            ledger_state[key].append(fid)
        gt_rel = r["gt_cl_action"] == "release"
        obls = "|".join(f"{a}:{b}" for a, b, _ in c["obligations"])
        recs.append(dict(query_id=r["query_id"], family=r["family"], persona=r["persona"],
                         turn=r["turn"], pair_id=r["pair_id"], fid=fid, k=k,
                         gt=("release" if gt_rel else "withhold"),
                         pdp_rel=int(rel), pdp_dec=c["decision"],
                         flagged=int(bool(pi["flags"])), verrs=len(c["verrs"]),
                         obligations=obls,
                         off_rel=1,
                         menu_rel=int(menu_granted(u, FRAGS[fid]["rid"])),
                         r3only_rel=int(r3rel)))
    recs.sort(key=lambda x: x["query_id"])
    return recs, ledger_gate

def md5_of(obj):
    return hashlib.md5(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def main():
    print(f"E3 적대 — frag-set {d6.FRAGSET_HASH} · 대상 {len(E3)}행 "
          f"(GT withhold {sum(1 for r in E3 if r['gt_cl_action']=='withhold')}) · trust 중립")
    recs, lgate = evaluate()

    G = []
    G.append(("G1 전 행 판정 (123)", len(recs) == 123))
    mism = [x for x in recs if (x["pdp_rel"] == 1) != (x["gt"] == "release")]
    byp = [x for x in recs if x["gt"] == "withhold" and x["pdp_rel"] == 1]
    if ARGS.coords == "gt":
        G.append(("G2 PDP ≡ GT 전건 (bypass=0)", len(mism) == 0))
    else:
        G.append(("G2p parser bypass = 0/118", len(byp) == 0))
        ovr = [x for x in recs if x["gt"] == "release" and x["pdp_rel"] == 0]
        print(f"  [A1] parser 모드: bypass {len(byp)} · 과보류 {len(ovr)}건"
              f" (논문 §VI-D: bypass 0 · 적법 skip-control 1건 보수적 과보류)")
    # [D] r3only 게이트·진단
    r3_byp_ids = sorted(x["query_id"] for x in recs
                        if x["gt"] == "withhold" and x["r3only_rel"])
    _exp = ["A0548", "A0550", "A0552", "A0554", "A0556", "A0558", "A0562", "A0566"]
    print(f"  [R3] r3only bypass 질의 ({len(r3_byp_ids)}건): {r3_byp_ids}")
    print(f"  [R3] 기대 (7/31 재대조): {_exp}")
    if ARGS.coords == "gt" and "gt_peritem_permit" in E3[0]:
        _pm = {r["query_id"]: int(r["gt_peritem_permit"]) for r in E3}
        _bad = [x["query_id"] for x in recs if x["r3only_rel"] != _pm[x["query_id"]]]
        G.append(("G7 r3only ≡ per-item GT (전건)", len(_bad) == 0))
        if _bad:
            print(f"  [R3] per-item GT 불일치 {len(_bad)}건: {_bad[:12]}")
    elif ARGS.coords == "parser" and "gt_peritem_permit" in E3[0]:
        _pm = {r["query_id"]: int(r["gt_peritem_permit"]) for r in E3}
        _dev = [x["query_id"] for x in recs if x["r3only_rel"] != _pm[x["query_id"]]]
        print(f"  [R3] parser 모드 per-item GT 이탈 {len(_dev)}건"
              + (f": {_dev[:12]}" if _dev else "") + " — 파스-오류 분해표 귀속 대상")
    neg = [x for x in recs if x["family"] == "F7-neg"]
    G.append(("G3 F7-neg 음성대조 (release,release)", all(x["pdp_rel"] == 1 for x in neg) and len(neg) == 2))
    bad_led = [(q, a, b) for q, a, b in lgate if a != b]
    G.append(("G4 F7 원장 재구성 = GT 인코딩", len(bad_led) == 0))
    G.append(("G5 obligation 검증 오류 0", sum(x["verrs"] for x in recs) == 0))
    recs2, _ = evaluate()
    G.append(("G6 결정론", md5_of(recs) == md5_of(recs2)))
    allok = all(ok for _, ok in G)
    for n, ok in G: print(f"  [{'PASS' if ok else 'FAIL'}] {n}")
    for m in mism[:10]: print("   불일치:", m["query_id"], m["family"], "gt=", m["gt"], "rel=", m["pdp_rel"])
    for b in bad_led[:10]: print("   원장 불일치:", b)
    if not allok: sys.exit(1)

    # family별 bypass (분모 = GT-withhold) + off/menu 대조
    fams = sorted(set(x["family"] for x in recs))
    summ = []
    print("\nfamily별 bypass (릴리스 ∧ GT-withhold / GT-withhold):")
    for fam in fams:
        sub = [x for x in recs if x["family"] == fam]
        wh = [x for x in sub if x["gt"] == "withhold"]
        row = dict(family=fam, n=len(sub), n_gt_withhold=len(wh),
                   pdp_bypass=sum(1 for x in wh if x["pdp_rel"]),
                   r3only_bypass=sum(1 for x in wh if x["r3only_rel"]),
                   off_bypass=sum(1 for x in wh if x["off_rel"]),
                   menu_bypass=sum(1 for x in wh if x["menu_rel"]),
                   flagged=sum(x["flagged"] for x in sub))
        summ.append(row)
        print(f"  {fam:14s} n={row['n']:3d} wh={row['n_gt_withhold']:3d}  "
              f"pdp {row['pdp_bypass']:2d} · r3only {row['r3only_bypass']:2d} · "
              f"menu {row['menu_bypass']:3d} · off {row['off_bypass']:3d}"
              + (f"  [flag {row['flagged']}]" if row['flagged'] else ""))
    tot_wh = sum(r["n_gt_withhold"] for r in summ)
    r3_tot = sum(r["r3only_bypass"] for r in summ)
    print(f"\n총계: PDP bypass {sum(r['pdp_bypass'] for r in summ)}/{tot_wh} "
          f"(v1 앵커 0.9% → v2 판정층 0) · r3only {r3_tot}/{tot_wh} "
          f"({r3_tot/tot_wh:.1%} — 기대 8, 전건 F7) · "
          f"menu {sum(r['menu_bypass'] for r in summ)}/{tot_wh} "
          f"({sum(r['menu_bypass'] for r in summ)/tot_wh:.1%}) · off {tot_wh}/{tot_wh}")
    n_flag = sum(r["flagged"] for r in summ)
    print(f"flag GT 대상 (F1·F2 injection): {n_flag}건 — v1 앵커 40/40의 v2 대응 분모 "
          f"(파서 flag 실측 = E1 로컬 / P1+ 라우팅 = E5)")
    can = [x for x in recs if x["fid"] in set(CANARY.values())]
    print(f"카나리아 표적 질의 {len(can)}건 — pdp 릴리스 "
          f"{sum(1 for x in can if x['pdp_rel'] and x['gt']=='withhold')}건(무자격) · "
          f"r3only {sum(1 for x in can if x['r3only_rel'] and x['gt']=='withhold')}건(무자격 — "
          f"기대 ≥1: A0562·A0566의 C-c1 경로) · "
          f"menu {sum(1 for x in can if x['menu_rel'] and x['gt']=='withhold')}건")

    def atomic(path, rows, fields):
        fd, tmp = tempfile.mkstemp(dir=OUT, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows(rows)
        os.replace(tmp, path)
    atomic(os.path.join(OUT, f"e3_results_{TAG}.csv"), recs, list(recs[0].keys()))
    atomic(os.path.join(OUT, f"e3_summary_{TAG}.csv"), summ, list(summ[0].keys()))
    man = dict(core=_CORE, coords=ARGS.coords, fragset_hash=d6.FRAGSET_HASH, n=123, trust="neutral(E2 확정 승계)",
               gates={n: bool(o) for n, o in G},
               pdp_bypass_total=sum(r["pdp_bypass"] for r in summ),
               r3only_bypass_total=r3_tot, r3only_bypass_ids=r3_byp_ids,
               menu_bypass_total=sum(r["menu_bypass"] for r in summ),
               gt_withhold=tot_wh, flag_gt_n=n_flag, results_md5=md5_of(recs))
    fd, tmp = tempfile.mkstemp(dir=OUT, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(OUT, f"e3_manifest_{TAG}.json"))
    print(f"\n산출: out10/e3_results_{TAG}.csv · e3_summary_{TAG}.csv · e3_manifest_{TAG}.json")

if __name__ == "__main__":
    main()
