# -*- coding: utf-8 -*-
"""
e2_e2e_a1r3.py — a1 개조판 + [D] R3-only arm (2026-08-15). a1 대비 변경 = [D]뿐:
  [D] r3only arm — idealized per-item control. 판정 = d6.cl(use_r1=False,
      use_r2=False) 직접 호출 (06 단일 출처 — admissible R3 4-conjunct 그대로,
      set-level R1·R2만 소거, 원장 무참조). parser 모드에선 pdp와 동일한 검색
      경계(scope-narrowing) 적용 — 동일 파스 비교성 유지.
      기대 (7/31 CSV 재대조): E2 leak 1/153 = {V0433}(probe·R1 분기) · over 0.
      게이트 G2r: gt 모드에서 r3only ≡ gt_peritem_permit 전건 (열 존재 시).
      명명 주의(논문): "ABAC-full" 아님 — Full per-item (R3 only), Reads=
      all item-level predicates.

원판 e2_e2e_a1.py 주석 (2026-08-08) — 원판 e2_e2e_v2.py 기반, 3개조:
  [A] 코어 = 09_decide_v2r (A7 해소판 — Appendix B). pdp 불변 · pdp_tr 26→0 기대.
  [B] --coords gt|parser (A1): parser 모드는 pi를 parser_out.jsonl에서 조인.
      GT는 절대 불변 (오라클 = gt_cl_action) — 비순환성 유지.
      검색 협소화 모델 (2026-08-08 r2): 파스 좌표가 검색 경계를 정한다 —
      attr 불일치 또는 조각 tier > 파스 t_req면 후보 진입 전 제외. §IV-H의
      tier ≤ D_final 합치. (r1은 attr만 걸러 09r 불변식 assert 유발 — 파스
      t_req 하향분이 cl 후보에 잔존했기 때문. 이 crash가 경계 누락의 증거.)
      [C-fix] abac_restr = tier 상한 준수형 (over=0 — 논문 정의 "permits only
      where the cell is open through tier 3" 의 실측 정합형).
  [C] ABAC 2-arm (8/7 A2): abac_perm(어느 tier든 grant → 전 tier 개방) ·
      abac_restr(tier3까지 열린 셀만 개방).
게이트 분기: G2(PDP≡GT diff=0)는 gt 모드 전용. parser 모드는 G2p(0/153 · 33/283).

원판 주석 (승계):
e2_e2e_v2.py — 10_eval E2: E2E 판정 비교 (off / menu-RBAC / PDP[09 결정론])
입력: out07/query_set_v2.csv (비적대 436행) · 오라클 = 07 GT (명세 유래)
+MLP arm은 로컬 잔여 (E4 학습 코드 필요 — 본 러너는 arm 슬롯만 예약).

조건 정의:
  off        governance 없음 — 대상 조각 전량 릴리스 (exposure baseline)
  menu       menu-RBAC★ — (역할, 보고서템플릿) 이진 권한 = 기존 실무.
             부여 규칙: 보고서 내 속성 중 하나라도 요청자 cell이 열려 있으면 메뉴 개방
             (Requester.cell 사용 — STAFF는 SELF_READABLE·RS 보고서 개방).
             개방 시 보고서 내 조각 무차별 릴리스 (tier·scope·k·classification 무시).
  pdp        09 issue_contract(P0, k=행별 인코딩[기본 5]) — 결정론 계약 발행 + reference PEP

지표 (arm별):
  leakage           released ∧ GT-withhold / GT-withhold
  over_restriction  withheld ∧ GT-release / GT-release
  canary_release    카나리아 조각 무자격 릴리스 건수 (GT-withhold인 카나리아)
  tier_exceed       released 중 조각 tier > cell max_tier (모노토니시티 지표 — E4 계보)
  para_stability    paraphrase 판정 = base 판정 (GT 좌표 구동에서는 상한 — 각주)

기동 게이트: G1 전 행 상태 OK / G2 PDP ≡ GT 전건(diff=0 — 통합 결함 탐지) /
             G3 off 전량 릴리스 / G4 결정론(재실행 요약 md5 동일).
구현 표준 (E4 승계): 결정론 · 원자적 저장 · 헤더 단언 · frag-set 해시.
"""
import sys, os, csv, json, re, hashlib, importlib.util, tempfile
from collections import defaultdict, Counter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out10")
os.makedirs(OUT, exist_ok=True)

_CORE = os.environ.get("IDPDM_CORE", "09_decide_v2r.py")   # [A] 기본 = A7 해소판
_s = importlib.util.spec_from_file_location("d9", os.path.join(HERE, _CORE))
d9 = importlib.util.module_from_spec(_s); _s.loader.exec_module(d9)
d6 = d9.d6
FRAGS, CELLS, CANARY = d6.FRAGS, d6.CELLS, d6.CANARY
U, staff = d9.U, d9.staff
issue_contract, reference_pep = d9.issue_contract, d9.reference_pep

CANARY_FIDS = set(CANARY.values())

# ── 인자 (A1) ───────────────────────────────────────────────────────────────
import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("--coords", choices=["gt", "parser"], default="gt")
_ap.add_argument("--parser-out", default=os.path.join(HERE, "..", "parser_out.jsonl"))
_ap.add_argument("--tag", default=None, help="산출 파일 접미 (기본 = coords)")
ARGS = _ap.parse_args()
TAG = ARGS.tag or ARGS.coords

PARSES = {}
if ARGS.coords == "parser":
    for _l in open(ARGS.parser_out, encoding="utf-8"):
        _l = _l.strip()
        if _l:
            _o = json.loads(_l); PARSES[_o["query_id"]] = _o
    print(f"[A1] parser_out 로드 {len(PARSES)}행 — 좌표 출처 = 파스 (오라클은 GT 불변)")

def parse_pi(r):
    """[B] 좌표 출처 분기. GT 모드 = 07 열, parser 모드 = parser_out 조인."""
    if ARGS.coords == "gt":
        return dict(attr=r["attr"], t_req=int(r["t_req"]), s="none", flags={})
    p = PARSES[r["query_id"]]
    a = p.get("attribute_group") or p.get("attr")
    tq = p.get("req_tier", p.get("t_req"))
    try: tq = int(tq)
    except (TypeError, ValueError): tq = 3        # 파스 결손 = 보수적 상한 요청
    return dict(attr=a, t_req=tq, s="none", flags=p.get("flags") or {})

# ── 입력 ────────────────────────────────────────────────────────────────────
QS = os.path.join(HERE, "out07", "query_set_v2.csv")
HEADER_MUST = ["query_id", "split", "gt_cl_action", "target_fragment_ids", "persona"]
rows_all = list(csv.DictReader(open(QS, encoding="utf-8")))
assert rows_all and all(h in rows_all[0] for h in HEADER_MUST), "query_set 헤더 단언 실패"
E2 = [r for r in rows_all if r["split"] != "adversarial"]
assert len(E2) == 436, f"E2 분모 단언 실패: {len(E2)}"

def requester(persona):
    role, emp = persona.split(":")
    return staff(emp) if role == "STAFF" else U(role)

def parse_ctx(gt_obl):
    """gt_obligations 접미의 k·ledger 컨텍스트 (07 인코딩)."""
    k = 5
    m = re.search(r"k=(\d+)", gt_obl)
    if m: k = int(m.group(1))
    led = []
    m = re.search(r"ledger(?:_injected)?=([A-Za-z0-9\-]*)", gt_obl)
    if m and m.group(1): led = [m.group(1)]
    return k, led

# ── menu-RBAC 사전 계산 ─────────────────────────────────────────────────────
REPORT_ATTRS = defaultdict(set)
for f in FRAGS.values():
    REPORT_ATTRS[f["rid"]].add(f["attr"])

_menu_cache = {}
def menu_granted(u, rid):
    key = (u.key(), rid)
    if key not in _menu_cache:
        _menu_cache[key] = any(u.cell(a) for a in REPORT_ATTRS[rid])
    return _menu_cache[key]

# ── arm 실행 ────────────────────────────────────────────────────────────────
def run_arm(arm, r, u, fid, k, led):
    """returns (released: bool, decision: str)"""
    if arm == "off":
        return True, "PERMIT"
    if arm == "menu":
        g = menu_granted(u, FRAGS[fid]["rid"])
        return g, ("PERMIT" if g else "DENY")
    if arm in ("abac_perm", "abac_restr"):          # [C] 셀 단위 이진 권한
        c = u.cell(FRAGS[fid]["attr"])
        if arm == "abac_perm":                      # 어느 tier든 grant → 전 tier 개방
            g = bool(c)
        else:                                       # tier 상한 준수 (over=0 보장)
            g = bool(c) and FRAGS[fid]["tier"] <= c[0]
        return g, ("PERMIT" if g else "DENY")
    if arm == "r3only":                             # [D] idealized per-item control
        pi = parse_pi(r)
        if ARGS.coords == "parser":                 # pdp와 동일 검색 경계 (비교성)
            if pi["attr"] != FRAGS[fid]["attr"]:
                return False, "DENY(scope-narrowed:attr)"
            if FRAGS[fid]["tier"] > pi["t_req"]:
                return False, "DENY(scope-narrowed:tier)"
        res = d6.cl(u, [fid], [], k, use_r1=False, use_r2=False)   # 원장 무참조
        g = res["verdicts"][fid][0] == "release"
        return g, ("PERMIT" if g else "DENY(R3)")
    if arm in ("pdp", "pdp_tr"):
        pi = parse_pi(r)                            # [B]
        if ARGS.coords == "parser":
            # 검색 경계 (§IV-H 4-conjunct의 tier ≤ D_final): 파스 좌표가 후보를
            # 좁힌다. attr 오파스 → 다른 도메인, t_req 하향 → 깊은 tier 미도달.
            # 논문: "every one is stopped at the D_final retrieval boundary".
            if pi["attr"] != FRAGS[fid]["attr"]:
                return False, "DENY(scope-narrowed:attr)"
            if FRAGS[fid]["tier"] > pi["t_req"]:
                return False, "DENY(scope-narrowed:tier)"
        if arm == "pdp":                      # trust 중립: UTS 일시 비움 → g(τ)=1
            saved = d9.UTS; d9.UTS = {}
            try:
                c = issue_contract(u, [fid], led, pi=pi, policy="P0", k=k)
                blocks = reference_pep(u, c)
            finally:
                d9.UTS = saved
        else:
            c = issue_contract(u, [fid], led, pi=pi, policy="P0", k=k)
            blocks = reference_pep(u, c)
        rel = fid in c["released"] and not any(b[1] == fid for b in blocks)
        return rel, c["decision"]
    raise ValueError(arm)

ARMS = ["off", "menu", "abac_perm", "abac_restr", "r3only", "pdp", "pdp_tr"]
# r3only = [D] Full per-item (R3 only) — legacy grant → full per-item → set-level 순서
# pdp    = 헤드라인 (trust 중립 τ=1 — 오라클이 trust 무모델·v1 앵커 정합·A4 분리)
# pdp_tr = 진단 (trust cap 적용 — A4 씨앗 데이터, 발화 규모 정량)

def evaluate():
    recs = []
    for r in E2:
        u = requester(r["persona"])
        fid = r["target_fragment_ids"]
        assert fid in FRAGS, f"조각 부재: {fid}"
        k, led = parse_ctx(r["gt_obligations"])
        gt_rel = r["gt_cl_action"] == "release"
        rec = dict(query_id=r["query_id"], split=r["split"], family=r["family"],
                   persona=r["persona"], fid=fid, gt=("release" if gt_rel else "withhold"),
                   pair_id=r["pair_id"])
        for arm in ARMS:
            rel, dec = run_arm(arm, r, u, fid, k, led)
            rec[f"{arm}_rel"] = int(rel); rec[f"{arm}_dec"] = dec
        recs.append(rec)
    return recs

def summarize(recs):
    base_dec = {x["query_id"]: x for x in recs}
    summ = []
    for arm in ARMS:
        n_wh = sum(1 for x in recs if x["gt"] == "withhold")
        n_rel = sum(1 for x in recs if x["gt"] == "release")
        leak = sum(1 for x in recs if x["gt"] == "withhold" and x[f"{arm}_rel"])
        over = sum(1 for x in recs if x["gt"] == "release" and not x[f"{arm}_rel"])
        can = sum(1 for x in recs if x["fid"] in CANARY_FIDS and x["gt"] == "withhold"
                  and x[f"{arm}_rel"])
        te = 0; n_released = 0
        for x in recs:
            if not x[f"{arm}_rel"]: continue
            n_released += 1
            u = requester(x["persona"]); f = FRAGS[x["fid"]]
            c = u.cell(f["attr"])
            if (c is None) or (f["tier"] > c[0]): te += 1
        para = [x for x in recs if x["split"] == "paraphrase" and x["pair_id"] in base_dec]
        ps = (sum(1 for x in para if x[f"{arm}_dec"] == base_dec[x["pair_id"]][f"{arm}_dec"])
              / len(para)) if para else None
        row = dict(arm=arm, n=len(recs),
                   leakage=round(leak / n_wh, 4), leak_n=f"{leak}/{n_wh}",
                   over_restriction=round(over / n_rel, 4), over_n=f"{over}/{n_rel}",
                   canary_release=can,
                   tier_exceed=round(te / n_released, 4) if n_released else 0.0,
                   te_n=f"{te}/{n_released}",
                   para_stability=round(ps, 4) if ps is not None else "")
        for sp in ["standard", "paraphrase", "probe", "cell-holdout"]:
            sub = [x for x in recs if x["split"] == sp]
            wh = sum(1 for x in sub if x["gt"] == "withhold")
            lk = sum(1 for x in sub if x["gt"] == "withhold" and x[f"{arm}_rel"])
            row[f"leak_{sp}"] = f"{lk}/{wh}"
        summ.append(row)
    return summ

def md5_of(obj):
    return hashlib.md5(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def atomic_csv(path, rows, fields):
    fd, tmp = tempfile.mkstemp(dir=OUT, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows(rows)
    os.replace(tmp, path)

def main():
    print(f"E2 편성 — frag-set {d6.FRAGSET_HASH} · 대상 {len(E2)}행 "
          f"(GT withhold {sum(1 for r in E2 if r['gt_cl_action']=='withhold')}) · arms {ARMS}+[MLP:로컬]")
    recs = evaluate()
    summ = summarize(recs)

    # ── 기동 게이트 ──
    G = []
    G.append(("G1 전 행 판정", len(recs) == 436))
    mism = [x for x in recs if (x["pdp_rel"] == 1) != (x["gt"] == "release")]
    if ARGS.coords == "gt":
        G.append(("G2 PDP ≡ GT (diff=0)", len(mism) == 0))
        G.append(("G2a menu 앵커 86/153", sum(
            1 for x in recs if x["gt"] == "withhold" and x["menu_rel"]) == 86))
    else:
        leak_p = sum(1 for x in recs if x["gt"] == "withhold" and x["pdp_rel"])
        over_p = sum(1 for x in recs if x["gt"] == "release" and not x["pdp_rel"])
        G.append(("G2p parser 유출 0/153", leak_p == 0))
        G.append(("G2p parser 과차단 33/283", over_p == 33))
        print(f"  [A1] parser 모드 실측: 유출 {leak_p}/153 · 과차단 {over_p}/283")
    # [D] r3only 게이트·진단
    r3_leak_ids = sorted(x["query_id"] for x in recs
                         if x["gt"] == "withhold" and x["r3only_rel"])
    print(f"  [R3] r3only 잔여 유출 질의: {r3_leak_ids}  (기대: ['V0433'])")
    if ARGS.coords == "gt" and "gt_peritem_permit" in E2[0]:
        _pm = {r["query_id"]: int(r["gt_peritem_permit"]) for r in E2}
        _bad = [x["query_id"] for x in recs if x["r3only_rel"] != _pm[x["query_id"]]]
        G.append(("G2r r3only ≡ per-item GT (전건)", len(_bad) == 0))
        if _bad:
            print(f"  [R3] per-item GT 불일치 {len(_bad)}건: {_bad[:12]}")
    elif ARGS.coords == "parser":
        # parser 모드는 등식 게이트 없음 — 이탈은 파스-오류 귀속 대상 (분해표)
        _pm = ({r["query_id"]: int(r["gt_peritem_permit"]) for r in E2}
               if "gt_peritem_permit" in E2[0] else {})
        if _pm:
            _dev = [x["query_id"] for x in recs if x["r3only_rel"] != _pm[x["query_id"]]]
            print(f"  [R3] parser 모드 per-item GT 이탈 {len(_dev)}건"
                  + (f": {_dev[:12]}" if _dev else "") + " — 파스-오류 분해표 귀속 대상")
    G.append(("G3 off 전량 릴리스", all(x["off_rel"] == 1 for x in recs)))
    recs2 = evaluate()
    G.append(("G4 결정론 (재실행 md5)", md5_of(recs) == md5_of(recs2)))
    allok = all(ok for _, ok in G)
    for name, ok in G:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if mism:
        print(f"  PDP-GT 불일치 {len(mism)}건:")
        for x in mism[:12]:
            print("   ", x["query_id"], x["split"], x["family"], x["persona"],
                  "gt=", x["gt"], "pdp_rel=", x["pdp_rel"], "dec=", x["pdp_dec"])
    if not allok:
        sys.exit(1)

    print("\narm 요약:")
    for s in summ:
        print(f"  {s['arm']:5s} leakage {s['leakage']:.1%} ({s['leak_n']}) · "
              f"over-restr {s['over_restriction']:.1%} ({s['over_n']}) · "
              f"canary {s['canary_release']} · tier_exceed {s['tier_exceed']:.1%} ({s['te_n']})"
              + (f" · para_stab {s['para_stability']}" if s['para_stability'] != "" else ""))

    atomic_csv(os.path.join(OUT, f"e2_results_{TAG}.csv"), recs, list(recs[0].keys()))
    atomic_csv(os.path.join(OUT, f"e2_summary_{TAG}.csv"), summ, list(summ[0].keys()))
    man = dict(core=_CORE, coords=ARGS.coords,
               parser_out_md5=(hashlib.md5(open(ARGS.parser_out,"rb").read()).hexdigest()
                               if ARGS.coords == "parser" else None),
               fragset_hash=d6.FRAGSET_HASH, n_queries=len(E2),
               gt_withhold_share=round(sum(1 for r in E2 if r["gt_cl_action"] == "withhold") / len(E2), 4),
               arms=ARMS, r3only_leak_ids=r3_leak_ids,
               mlp_arm="local-pending(E4 코드 필요)",
               gates={n: bool(o) for n, o in G}, results_md5=md5_of(recs),
               splits=dict(Counter(r["split"] for r in E2)))
    fd, tmp = tempfile.mkstemp(dir=OUT, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(OUT, f"e2_manifest_{TAG}.json"))
    print(f"\n산출: out10/e2_results_{TAG}.csv · e2_summary_{TAG}.csv · e2_manifest_{TAG}.json")

if __name__ == "__main__":
    main()
