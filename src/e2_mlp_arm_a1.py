# -*- coding: utf-8 -*-
"""
e2_mlp_arm_a1.py — 원판 e2_mlp_arm_v2.py의 로컬 재현판 (2026-08-08).
  변경 1곳: E4 코어 경로를 샌드박스 하드코딩 → 자동 탐색(E4DIR 환경변수 우선).
  판정·학습·게이트 로직 전부 원판 그대로. 코어는 이미 09_decide_v2r 사용.
원판 주석:
e2_mlp_arm_v2.py — 10_eval E2 4번째 arm: +MLP (E4 코드 재사용 — 학습 per-item 판정층)
구성 = E4 헤드라인 계보: MLP(128,128)+Clamp(λ=1, ownership_floor, basis_evidence) ·
calib 모드 τ(β=1%, 가시 보정 폴드) · 결정론 seed. 오라클/채점 = 07 GT (E2와 동일).

학습 신호: 판정 격자(build_grid) 가시 좌표 전량 (x=100% 교육) — 단,
  ① hidden = cell-holdout 질의가 행사하는 (role, attr) 셀 (봉인 = 미학습, sealed 계약)
  ② probe_kind 좌표 = 학습 제외 (E4 규율 — 문서화된 closure는 학습 대상 아님)
STAFF(무role) 질의 = 격자 밖 → 명세 선언 floor 관례(srel=own ∧ SELF_READABLE → 릴리스,
그 외 deny)로 판정. 관례 자체가 결정론 조항이므로 학습 실패로 계상하지 않음.

예상 실패면 (구조적 — E4-B5 서사의 E2 판):
  · 집합 수준 규칙(R1 n<k·R2 차분): per-item 격자에 부재 → 원리적 누출
  · classification 축: 로더 미적재(E4 실행 당시와 동일) → SAR 기밀장벽 누출
  · 봉인 셀: 미학습 예외 → B5 패턴
게이트: G1 전 행 판정 / G2 학습 성립(보정 폴드 비퇴화) / G3 결정론.
산출: out10/e2_mlp_results.csv · e2_mlp_summary.csv · e2_mlp_manifest.json
"""
import sys, os, csv, json, re, hashlib, importlib.util, tempfile
from collections import Counter

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

# [a1 2026-08-08] E4 코어 경로 — 원판은 샌드박스 절대경로 하드코딩(<repo>).
#   로컬 재현을 위해 환경변수 → 표준 후보 순 자동 탐색으로 교체.
#   e4_core_fixed_r2.py 는 동반 논문(B) 계열 코드 — A 아티팩트의 선택 구성요소.
def _find_e4():
    cands = [os.environ.get("E4DIR"),
             os.path.join(HERE, "..", "e4", "judge"),
             os.path.join(HERE, "..", "e4"),
             os.path.join(HERE, "e4")]
    for c in cands:
        if c and os.path.exists(os.path.join(c, "e4_core_fixed_r2.py")):
            return os.path.abspath(c)
    sys.exit("E4 코어(e4_core_fixed_r2.py) 미발견 — E4DIR 환경변수로 지정하거나\n"
             "  set E4DIR=<repo>  후 재실행.\n"
             "  (이 arm은 동반 논문 B의 학습 코드에 의존 — RUNBOOK §4 참조)")
E4DIR = _find_e4()
print(f"[a1] E4 코어 = {E4DIR}")
OUT = os.path.join(HERE, "out10")
os.makedirs(OUT, exist_ok=True)

sys.path.insert(0, E4DIR)
_se = importlib.util.spec_from_file_location("e4c", os.path.join(E4DIR, "e4_core_fixed_r2.py"))
e4c = importlib.util.module_from_spec(_se); sys.modules["e4c"] = e4c; _se.loader.exec_module(e4c)

_s9 = importlib.util.spec_from_file_location("r9", os.path.join(HERE, "09_decide_v2r.py"))
r9 = importlib.util.module_from_spec(_s9); _s9.loader.exec_module(r9)
d6 = r9.d6
FRAGS, CANARY = d6.FRAGS, d6.CANARY

DB = os.path.join(HERE, "..", "findw.duckdb")
QS = os.path.join(HERE, "out07", "query_set_v2.csv")
rows_all = list(csv.DictReader(open(QS, encoding="utf-8")))
E2 = [r for r in rows_all if r["split"] != "adversarial"]
assert len(E2) == 436, "E2 분모 단언 실패"

# ── 좌표 사상 ───────────────────────────────────────────────────────────────
def coord(r):
    role, emp = r["persona"].split(":")
    fid = r["target_fragment_ids"]; f = FRAGS[fid]
    u = r9.staff(emp) if role == "STAFF" else r9.U(role)
    srel = "own" if (f["sid"] == u.emp_id or (f["ids"] and u.emp_id in f["ids"])) else "none"
    sc = f["scope"] or ""
    if sc == u.org_path: org = "self"
    elif sc.startswith(u.org_path + "/"): org = "in_subtree"
    else: org = "outside"
    return role, emp, f, srel, org

def main():
    spec = e4c.load_spec_duckdb(DB)
    grid = e4c.build_grid(spec)
    print(f"+MLP arm — {spec.summary()}")

    # hidden = cell-holdout 질의의 (role, attr) 셀 (역할 페르소나분)
    hidden = set()
    for r in E2:
        if r["split"] != "cell-holdout": continue
        role = r["persona"].split(":")[0]
        if role != "STAFF" and (role, r["attr"]) in {(c[0], c[1]) for c in
                zip(spec.cells["role"], spec.cells["attr"])}:
            hidden.add((role, r["attr"]))
    print(f"봉인 셀(hidden) = {sorted(hidden)}")

    hid_mask = e4c.hidden_row_mask(grid, hidden)
    probe_mask = grid.df["probe_kind"].notna().to_numpy()
    train_all = ~hid_mask & ~probe_mask
    y = grid.df["permit"].to_numpy().astype(int)

    seed = e4c.stable_seed("e2mlp", "v2", d6.FRAGSET_HASH)
    rng = np.random.default_rng(seed)
    idx = np.where(train_all)[0]
    rng.shuffle(idx)
    n_cal = max(1, int(0.2 * len(idx)))
    cal_idx, tr_idx = idx[:n_cal], idx[n_cal:]

    model = e4c.fit_model(grid.X[tr_idx], y[tr_idx], seed=seed)
    p_cal = e4c.predict_proba(model, grid.X[cal_idx])
    tau = e4c._sweep_tau(p_cal, y[cal_idx].astype(bool), 0.01)
    if isinstance(tau, tuple): tau = tau[0]
    clamp = e4c.Clamp(lam=1)
    allow, floor = clamp.build(grid, hidden)
    p_all = e4c.predict_proba(model, grid.X)
    pred_all = (p_all >= tau) & allow

    # G2 학습 성립: 보정 폴드에서 비퇴화 (calib fp ≤ 5%·recall ≥ 80%)
    cp = (p_cal >= tau)
    fp = ((cp) & (y[cal_idx] == 0)).sum() / max(1, (y[cal_idx] == 0).sum())
    rc = ((cp) & (y[cal_idx] == 1)).sum() / max(1, (y[cal_idx] == 1).sum())
    print(f"seed={seed} · τ(calib,β=1%)={tau:.3f} · 보정 폴드 fp={fp:.2%} recall={rc:.2%} · clamp={clamp.tag()}")

    gidx = {}
    for i, (ro, at, t, sr, og) in enumerate(zip(grid.df["role"], grid.df["attr"],
            grid.df["t_req"], grid.df["srel"], grid.df["org_rel"])):
        gidx[(ro, at, int(t), sr, og)] = i

    def run_query(r):
        role, emp, f, srel, org = coord(r)
        if role == "STAFF":   # 격자 밖 — 명세 선언 floor 관례
            rel = (srel == "own" and f["attr"] in spec.self_readable)
            return int(rel), "floor"
        key = (role, r["attr"], int(r["t_req"]), srel, org)
        i = gidx.get(key)
        if i is None:
            return 0, "no-coord"
        return int(pred_all[i]), f"grid:{'H' if hid_mask[i] else 'V'}"

    recs = []
    for r in E2:
        rel, path = run_query(r)
        recs.append(dict(query_id=r["query_id"], split=r["split"], family=r["family"],
                         persona=r["persona"], fid=r["target_fragment_ids"],
                         gt=r["gt_cl_action"], gt_rule=r["gt_cl_rule"],
                         mlp_rel=rel, path=path))

    def md5_of(o):
        return hashlib.md5(json.dumps(o, sort_keys=True).encode()).hexdigest()
    G = [("G1 전 행 판정", len(recs) == 436),
         ("G2 학습 성립 (fp≤5% ∧ recall≥80%)", fp <= 0.05 and rc >= 0.80)]
    # G3 결정론: 동일 seed 재적합 → 동일 예측
    m2 = e4c.fit_model(grid.X[tr_idx], y[tr_idx], seed=seed)
    G.append(("G3 결정론 (재적합 예측 동일)",
              bool(np.array_equal(e4c.predict_proba(m2, grid.X) >= tau, p_all >= tau))))
    for n, ok in G: print(f"  [{'PASS' if ok else 'FAIL'}] {n}")
    if not all(ok for _, ok in G): sys.exit(1)

    # ── 지표 (E2 arm 공통 산식) ──
    n_wh = sum(1 for x in recs if x["gt"] == "withhold")
    n_rl = len(recs) - n_wh
    leak = [x for x in recs if x["gt"] == "withhold" and x["mlp_rel"]]
    over = [x for x in recs if x["gt"] == "release" and not x["mlp_rel"]]
    can = sum(1 for x in recs if x["fid"] in set(CANARY.values())
              and x["gt"] == "withhold" and x["mlp_rel"])
    te = nrel = 0
    for x in recs:
        if not x["mlp_rel"]: continue
        nrel += 1
        role, emp, f, srel, org = coord(next(r for r in E2 if r["query_id"] == x["query_id"]))
        u = r9.staff(emp) if role == "STAFF" else r9.U(role)
        c = u.cell(f["attr"])
        if c is None or f["tier"] > c[0]: te += 1
    print(f"\nmlp   leakage {len(leak)/n_wh:.1%} ({len(leak)}/{n_wh}) · "
          f"over-restr {len(over)/n_rl:.1%} ({len(over)}/{n_rl}) · canary {can} · "
          f"tier_exceed {te/max(1,nrel):.1%} ({te}/{nrel})")
    print("leak 분해 (gt_cl_rule):", dict(Counter(x["gt_rule"] for x in leak)))
    print("leak 분해 (split):", dict(Counter(x["split"] for x in leak)))
    hold = [x for x in recs if x["split"] == "cell-holdout"]
    print("cell-holdout 7행 판별점:")
    for x in hold:
        ok = (x["mlp_rel"] == 1) == (x["gt"] == "release")
        print(f"  {x['query_id']} {x['family']:14s} gt={x['gt']:8s} mlp={'rel' if x['mlp_rel'] else 'deny'} "
              f"[{x['path']}] {'일치' if ok else '★오판'}")
    print("over-restr 분해 (split):", dict(Counter(x["split"] for x in over)))

    summ = [dict(arm="mlp", n=len(recs), leakage=round(len(leak)/n_wh, 4),
                 leak_n=f"{len(leak)}/{n_wh}", over_restriction=round(len(over)/n_rl, 4),
                 over_n=f"{len(over)}/{n_rl}", canary_release=can,
                 tier_exceed=round(te/max(1, nrel), 4), te_n=f"{te}/{nrel}",
                 holdout_wrong=sum(1 for x in hold if (x["mlp_rel"] == 1) != (x["gt"] == "release")),
                 leak_by_rule=json.dumps(dict(Counter(x["gt_rule"] for x in leak)), ensure_ascii=False))]

    def atomic(path, rows, fields):
        fd, tmp = tempfile.mkstemp(dir=OUT, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows(rows)
        os.replace(tmp, path)
    atomic(os.path.join(OUT, "e2_mlp_results.csv"), recs, list(recs[0].keys()))
    atomic(os.path.join(OUT, "e2_mlp_summary.csv"), summ, list(summ[0].keys()))
    man = dict(fragset_hash=d6.FRAGSET_HASH, seed=int(seed), tau=float(tau),
               clamp=clamp.tag(), hidden_cells=sorted(map(list, hidden)),
               calib=dict(fp=round(float(fp), 4), recall=round(float(rc), 4)),
               gates={n: bool(o) for n, o in G}, results_md5=md5_of(recs))
    fd, tmp = tempfile.mkstemp(dir=OUT, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(OUT, "e2_mlp_manifest.json"))
    print("\n산출: out10/e2_mlp_results.csv · e2_mlp_summary.csv · e2_mlp_manifest.json")

if __name__ == "__main__":
    main()
