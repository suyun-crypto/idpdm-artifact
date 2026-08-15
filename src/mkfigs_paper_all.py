#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mkfigs_paper_all.py — iDPDM 논문 전체 그림 일괄 생성 (2026-07-31)
=================================================================
본문·부록의 모든 그림을 한 번에 렌더한다. 두 부류:
  [다이어그램 — 데이터 불요, 항상 렌더]
    fig_idpdm_position.png    §I   개관 (정본 문구 수정 4건 반영: cell-bounded /
                                   latency 정본치 / C4 upward-rounding / PDP·D_final)
    fig_authority.png         §III/IV  권한 의미론 (compliance 문구 완화 + subset 명시)
    fig_findw_provenance.png  §V   3패널 provenance (--personnel mysql|synthetic)
  [데이터 그림 — 해당 CSV 지정 시 렌더, 미지정 시 SKIP]
    fig1_e4_b1_final_r2.png / fig2_structure_r2.png / fig3_e4_rho_dial_r2.png  §VI-E
    fig_e5_opsurface.png      §VI-F (--e5 e5_curve.csv)
    fig_e6_latency.png        §VI-H (--e6 e6_latency.csv)
    fig_transfer_gap_r2.png   부록 후보
모든 데이터 그림은 정본 앵커와 자동 대조(PASS/FAIL) → figs/verify_report.json.
FAIL 존재 시 종료 코드 1 (해당 그림 반입 금지).

사용 (findw_v2 루트에서 — 로컬 경로가 기본값으로 내장, 인자 불요):
  python mkfigs_paper_all.py
기본 경로 (2026-07-31 로컬 dir 실측):
  --runs e4/judge/runs_repaired_v2_final.csv
  --b5   e4/out_b5/b5rerun_findw_runs.csv   (run 단위 — summary 아님: CI 집계용)
  --e5   e5_curve.csv (루트)   /   --e6 e6_latency.csv   /   --out figs
파일이 없는 축은 SKIP (에러 아님). 다른 경로면 해당 인자로 덮어쓰기.
열 이름이 다르면 COLMAP에 실제 이름 추가.
"""
import argparse, hashlib, json, sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Ellipse

VERIFY = []
def check(name, ok, detail):
    VERIFY.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}"); return ok
def skip(msg): print(f"  [SKIP] {msg}")

# ═════════════════ 다이어그램 공통 헬퍼 ═════════════════
def bx(ax, x, y, w, h, fc="#f4f4fb", ec="#333", lw=1.4, r=1.2):
    p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                       fc=fc, ec=ec, lw=lw, zorder=2)
    ax.add_patch(p); return p
def tx(ax, x, y, s, fs=9, c="#222", w="normal", ha="center", va="center", fam=None, st="normal"):
    ax.text(x, y, s, fontsize=fs, color=c, fontweight=w, ha=ha, va=va,
            family=fam or "sans-serif", style=st, zorder=3)
def ar(ax, p, q, c="#444", lw=1.4, dashed=False, rad=0.0):
    # zorder 2.5: 박스(2) 위·텍스트(3) 아래 — 불투명 배경 박스에 화살표가 가려지던 버그 수정 (2026-07-31)
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=13, lw=lw,
                 color=c, linestyle="--" if dashed else "-",
                 connectionstyle=f"arc3,rad={rad}", zorder=2.5))
def canvas(w, h):
    fig, ax = plt.subplots(figsize=(w, h)); ax.set_xlim(0, 100); ax.set_ylim(0, 100)
    ax.axis("off"); return fig, ax

# ═════════════════ 1) §I 개관 — 정본 문구 반영판 ═════════════════
def fig_position(out):
    # v2 레이아웃 (2026-07-31): 상하 압축 · 하단 테제 → LaTeX 캡션 이동 · FinDW/계약
    # 스트립 충돌 해소 · 하단 여백 최소화 (ylim을 콘텐츠 범위로 절단).
    fig, ax = plt.subplots(figsize=(16.2, 6.9)); ax.set_xlim(0, 100); ax.axis("off")
    # 제목 복원 (v14 — 사용자 미감 판정: 제목이 상단 균형의 닻 역할. 캡션과의 중복은
    # 허용 — 논문 반입 시 제거 원하면 아래 한 줄 주석 처리).
    tx(ax, 2, 97, "Where does disclosure policy live?", 15, w="bold", ha="left")
    for x, t, sub, hl in (
        (2,  "(a) in model weights", "per-domain adapters; policy update = re-finetune;\nnot auditable, dies with the base model", False),
        (35, "(b) in prompts / guardrails", "instructions to the model; bypassable by\ninjection; no formal properties", False),
        (68, "(c) in a decision layer — this work", "policy grid outside the model; auditable,\nprovably fail-safe & cell-bounded;\ndecision+enforcement ~ms, model-agnostic", True)):
        # (c) = 거버넌스 박스와 동일 보라 — "같은 것"의 색 신호 (2026-07-31; 붉은색은
        # 본 그림에서 위협·escalation 의미로 기사용이라 배제. 세대 화살표는 사실 아님 —
        # 외부 정책 엔진 계보가 최고령 — 설계 공간 병렬 유지)
        bx(ax, x, 81, 30, 12, fc="#f6effb" if hl else "#f2f2f2",
           ec="#6a1fa8" if hl else "#999", lw=2.4 if hl else 1.2)
        tx(ax, x+15, 90, t, 11.5, w="bold", c="#6a1fa8" if hl else "#555")
        tx(ax, x+15, 85.2, sub, 8.2, c="#6a1fa8" if hl else "#666")
    # 거버넌스 박스 (상단과 3만 이격) + (c)→거버넌스 연결 (동일체 표시)
    bx(ax, 15, 29, 52, 49, fc="#faf7fd", ec="#6a1fa8", lw=2.2, r=1.8)
    ar(ax, (80, 80.7), (58, 78.4), c="#6a1fa8", dashed=True, lw=1.8, rad=0.12)
    tx(ax, 73.5, 79.6, "this work — expanded below", 8.4, c="#6a1fa8", st="italic")
    tx(ax, 17, 74.5, "iDPDM governance layer", 14, c="#6a1fa8", w="bold", ha="left")
    tx(ax, 17, 71, "model-agnostic · policy defined in a versioned specification, not in weights\n"
                   "+ clamped learned interpolation where the specification is silent (escalation for the rest)",
       8.4, c="#6a1fa8", ha="left")
    bx(ax, 1, 41, 11, 14, fc="#fff", ec="#333")  # 요청자 = §III 위협모델의 authenticated employee (AI agent 표기 제거 — 스코프 밖 행위자)
    tx(ax, 6.5, 51.5, "Analyst", 10.5, w="bold")
    tx(ax, 6.5, 48.3, "(authenticated\nemployee)", 7.9, c="#555")
    tx(ax, 6.5, 44, "NL query +\nrole context", 8)
    ar(ax, (12, 48), (17, 52))
    # 모듈 행 v15 (2026-07-31): 박스 규격 통일(3주 박스 h=26 동일·폭 비례) + retrieval
    # 확폭(6→8, 우측 여백 2 확보) + 소형 폰트 일괄 상향 (8→8.6 / 7.2~7.9→8~9)
    bx(ax, 17, 40, 12.5, 26, fc="#eef3fb", ec="#28518f", lw=1.6)
    tx(ax, 23.2, 62.5, "CTPP parser (LLM)", 10, c="#28518f", w="bold")
    tx(ax, 23.2, 54.5, "reads semantics only\nrecords stated purpose\nflags injection\nnever outputs permit", 8.6)
    tx(ax, 23.2, 43.5, "cold ~1 s · warm 0.2 ms", 8, fam="monospace", c="#555")
    ar(ax, (29.5, 52), (31.8, 52), lw=1.8)
    bx(ax, 32, 46, 9, 12, fc="#fff", ec="#333")
    tx(ax, 36.5, 52, "(attr, tier,\nsubject-\nrelation)", 8.6, fam="monospace")
    ar(ax, (41, 52), (43.3, 52), lw=1.8)
    bx(ax, 43.5, 40, 11, 26, fc="#eefaf0", ec="#1d7a3a", lw=1.6)
    tx(ax, 49, 62.5, "PDP decision", 10, c="#1d7a3a", w="bold")
    tx(ax, 49, 53.5, "policy grid / T_cap(\u03c4)\ndeterministic\nnever sees NL\nfail-safe default", 8.6)
    tx(ax, 49, 43.5, "~1 ms", 8, fam="monospace", c="#555")
    ar(ax, (54.5, 52), (56.8, 52), lw=1.8)
    bx(ax, 57, 40, 8, 26, fc="#fdf6ea", ec="#b8720f", lw=1.6)
    tx(ax, 61, 61.5, "tier-filtered\nretrieval", 9, c="#b8720f", w="bold")
    tx(ax, 61, 51.5, "certified\nfragments\n\u2264 D_final", 8.6)
    tx(ax, 61, 43.5, "~1 ms", 8, fam="monospace", c="#555")
    # FinDW 실린더 제거 (2026-07-31 사용자 판정): FinDW = 평가 테스트베드(§V 자산)이지
    # iDPDM 구성요소가 아님 — 거버넌스 박스 내 표기는 경계 오독 유발. retrieval 박스의
    # "certified fragments ≤ D_final"이 데이터 측면 전달. 빈 밴드만큼 세로 재압축.
    tx(ax, 40, 32.5, "prompt injection: parsed as data, cannot steer the decision (C3)", 8, c="#b03030")
    # 계약 스트립 제거 (2026-07-31 사용자 판정): Property/조항 번호는 §IV 몫 — intro
    # 수준에서는 (c) 박스 부제("provably fail-safe & cell-bounded")로 충분. 인젝션
    # 주석의 (C3)만 유지 (위협 서사의 단일 앵커).
    # 우측 체인 (v12: +6 추가 상향 — 체인이 모듈 행 높이대에 정렬, 하단 기준선 = 거버넌스 박스)
    bx(ax, 72, 64, 14, 12, fc="#e8f3f9", ec="#1e6e96", lw=1.6)
    tx(ax, 79, 72.5, "Pre-trained LLM", 10, c="#1e6e96", w="bold")
    tx(ax, 79, 68, "(frozen) · generation only", 8, st="italic")
    ar(ax, (65.2, 54), (72, 67), lw=1.6); ar(ax, (86, 70), (93, 70))
    tx(ax, 95.5, 70, "Output", 12, w="bold", st="italic", ha="center")
    bx(ax, 72, 49.5, 14, 10, fc="#fff", ec="#333"); ar(ax, (79, 64), (79, 59.5))
    tx(ax, 79, 56, "output validation", 9.5, w="bold"); tx(ax, 79, 52.5, "canary screen · tier audit", 8)
    bx(ax, 72, 35, 14, 10, fc="#fbeeee", ec="#b03030", lw=1.6); ar(ax, (79, 49.5), (79, 45))
    tx(ax, 79, 41.5, "escalation queue", 9.5, c="#b03030", w="bold")
    tx(ax, 79, 38, "flagged permits \u2192 human review", 8)
    tx(ax, 79, 32.2, "defense in depth: grid \u2192 flagged-permit review \u2192 canary", 8, c="#555")
    ax.set_ylim(27.5, 99.5)
    fig.savefig(Path(out)/"fig_idpdm_position.png", dpi=200, bbox_inches="tight", pad_inches=0.06)
    plt.close(fig)
    print("  [OK] fig_idpdm_position.png (v2 압축 레이아웃 — 테제는 §I 캡션으로 이동)")

# ═════════════════ 2) §III/IV 권한 의미론 ═════════════════
def fig_authority(out):
    fig, ax = canvas(12.5, 6.2)
    bx(ax, 3, 12, 56, 82, fc="none", ec="#999", lw=1.2, r=2)
    tx(ax, 31, 90, "Management hierarchy", 12, c="#444")
    chain1 = ["Division head", "Group head", "Dept head", "Team member"]
    chain2 = [None, "Regional HQ head", "Branch manager", "Branch staff"]
    ys = [76, 58, 40, 22]
    for i, y in enumerate(ys):
        bx(ax, 7, y, 20, 9, fc="#eeeefb", ec="#4444aa", lw=1.5)
        tx(ax, 17, y+4.5, chain1[i], 10, c="#333")
        if i: ar(ax, (17, ys[i-1]), (17, y+9))
        if chain2[i]:
            bx(ax, 34, y, 20, 9, fc="#eeeefb", ec="#4444aa", lw=1.5)
            tx(ax, 44, y+4.5, chain2[i], 10, c="#333")
            if i > 1: ar(ax, (44, ys[i-1]), (44, y+9))
    ax.plot([27, 44, 44], [80.5, 80.5, 67], color="#555", lw=1.4)  # division→RHQ
    ar(ax, (44, 67.2), (44, 67.1))
    # 우측 목적 조건부 라인 — compliance 문구 완화 + subset 명시
    rows = [("HQ sales dept", "functional line: aggregates only, t1\u2013t2", 74),
            ("Compliance line", "clause-scoped read, audit-logged", 50),
            ("Security line", "access logs, never values", 26)]
    for t, sub, y in rows:
        bx(ax, 66, y, 30, 13, fc="#fdf1ea", ec="#c2571a", lw=1.6)
        tx(ax, 81, y+8.6, t, 11, c="#a34310", w="bold"); tx(ax, 81, y+4, sub, 8.6, c="#a34310")
        ar(ax, (66, y+6.5), (59.5, y+6.5), c="#c2571a", dashed=True, lw=1.8)
    tx(ax, 50, 6.5, "solid = authority inherited down the chain;  dashed = purpose-based scope, conditioned and not inherited\n"
                    "(illustrative subset of the specification's four supervisory lines)", 9, c="#444")
    fig.savefig(Path(out)/"fig_authority.png", dpi=200, bbox_inches="tight"); plt.close(fig)
    print("  [OK] fig_authority.png (compliance 완화·subset 명시 반영)")

# ═════════════════ 3) §V provenance 3패널 ═════════════════
def _table(ax, x, y, w, title, rows, count, fc, ec, fs=7.2):
    h = 3.2 + 2.6*len(rows) + 2.6
    bx(ax, x, y, w, h, fc="#fff", ec=ec, lw=1.4)
    bx(ax, x, y+h-3.2, w, 3.2, fc=fc, ec=ec, lw=1.4)
    tx(ax, x+1.2, y+h-1.6, title, fs+1.2, w="bold", ha="left", fam="monospace", st="italic")
    for i, (l, r) in enumerate(rows):
        yy = y+h-3.2-2.6*(i+0.65)
        tx(ax, x+1.2, yy, l, fs, ha="left", fam="monospace")
        tx(ax, x+w-1.2, yy, r, fs, ha="right", fam="monospace", c="#555")
    tx(ax, x+w-1.2, y+1.3, count, fs, ha="right", fam="monospace", c="#555")
    return (x, y, w, h)

def fig_provenance(out, personnel="mysql"):
    fig, ax = canvas(17.5, 10.5)
    # A 패널
    bx(ax, 1, 3, 60, 94, fc="none", ec="#2b4fa0", lw=2, r=2)
    tx(ax, 3, 93.5, "A · REAL BANKING DATA", 14, c="#2b4fa0", w="bold", ha="left")
    t_disp   = _table(ax, 3, 74, 15, "fin_disp", [("client_id","FK"),("account_id","FK"),("disp_type","CHAR")], "5,369 rows", "#dfe7f7", "#2b4fa0")
    t_card   = _table(ax, 3, 60, 15, "fin_card", [("disp_id","FK"),("card_type","CHAR")], "892 rows", "#dfe7f7", "#2b4fa0")
    t_loan   = _table(ax, 3, 45, 15, "fin_loan", [("account_id","FK"),("amount","DEC"),("status","CHAR")], "682 rows", "#dfe7f7", "#2b4fa0")
    t_order  = _table(ax, 3, 32, 15, "fin_order", [("account_id","FK"),("amount","DEC")], "6,471 rows", "#dfe7f7", "#2b4fa0")
    t_trans  = _table(ax, 3, 14, 15, "fin_trans", [("*trans_id","INT"),("account_id","FK"),("amount","DEC"),("+7 cols","\u2026")], "1,056,320 rows", "#dfe7f7", "#2b4fa0")
    t_client = _table(ax, 23, 66, 16, "fin_client", [("*client_id","INT"),("district_id","FK"),("birth_date","DATE")], "5,369 rows", "#dfe7f7", "#2b4fa0")
    t_acct   = _table(ax, 23, 34, 16, "fin_account", [("*account_id","INT"),("district_id","FK"),("frequency","CHAR")], "4,500 rows", "#dfe7f7", "#2b4fa0")
    t_dist   = _table(ax, 43, 50, 16, "fin_district", [("*district_id","INT"),("district_name","VC"),("region","VC"),("avg_salary","DEC"),("+12 cols","\u2026")], "77 rows", "#dfe7f7", "#2b4fa0")
    for a, b in ((t_disp, t_client), (t_card, t_disp), (t_loan, t_acct), (t_order, t_acct), (t_trans, t_acct)):
        ar(ax, (a[0]+a[2], a[1]+a[3]/2), (b[0], b[1]+b[3]/2), c="#666", lw=1.1)
    ar(ax, (t_client[0]+16, t_client[1]+4), (t_dist[0], t_dist[1]+t_dist[3]-4), c="#666", lw=1.1)
    ar(ax, (t_acct[0]+16, t_acct[1]+t_acct[3]-4), (t_dist[0], t_dist[1]+4), c="#666", lw=1.1)
    bx(ax, 41, 33, 18, 9, fc="#f7ecfb", ec="#8b2fbf", lw=1.5)
    tx(ax, 50, 39.5, "data-anchored mapping", 8.6, c="#8b2fbf", w="bold")
    tx(ax, 50, 35.8, "branch = district (1:1, 77)\nregional HQ = region (8)", 8, c="#8b2fbf")
    tx(ax, 31, 8.5, "Czech retail-banking corpus (Berka, PKDD 2000) — 8 tables · FKs intact", 11, c="#2b4fa0")
    # B 패널
    bx(ax, 63, 55, 36, 42, fc="none", ec="#1d7a3a", lw=2, r=2)
    tx(ax, 65, 93.5, "B · REAL ORGANIZATIONAL TOPOLOGY", 12.5, c="#1d7a3a", w="bold", ha="left")
    tx(ax, 65, 90.3, "published org chart of a major bank + Berka-anchored regional line", 8, c="#1d7a3a", ha="left")
    t_org = _table(ax, 66, 70, 17, "dim_org", [("*org_id","INT"),("parent_id","FK self"),("org_type","hq/rhq/br/team"),("district_id","FK\u2192Berka"),("region","FK\u2192Berka")], "115 nodes", "#e2f2e6", "#1d7a3a")
    ar(ax, (t_dist[0]+t_dist[2], t_dist[1]+t_dist[3]/2), (66, t_org[1]+6), c="#8b2fbf", lw=2)
    tx(ax, 85, 78, "chairman (published chart)\n\u251c business groups 10\n\u2502 \u2514 divisions 8 — depts 65\n\u2502   \u2514 teams: consistent w/ chart\n\u2514 regional HQs 8 = regions\n  \u2514 branches 77 = districts", 7.6, ha="left", fam="monospace", c="#1d7a3a")
    # C 패널 — personnel 분기
    bx(ax, 63, 3, 36, 49, fc="none", ec="#b8720f", lw=2, r=2)
    if personnel == "mysql":
        hdr, sub = "C · PERSONNEL LAYER", "names/rosters/payroll re-keyed from MySQL Employees\nsample DB (CC BY-SA 3.0) · rank-monotone · seed-fixed"
        note = "rank-monotone re-keying ·\ntrust signals synthetic\n(indicator taxonomy of \u00a7IV-D)"
    else:
        hdr, sub = "C · SYNTHETIC PERSONNEL LAYER", "values generated per policy specification (seed-fixed)"
        note = "rank-monotone payroll ·\nindicator-taxonomy signals ·\nall values synthetic"
    tx(ax, 65, 48.5, hdr, 12.5, c="#b8720f", w="bold", ha="left")
    tx(ax, 65, 44.6, sub, 7.8, c="#b8720f", ha="left")
    t_emp = _table(ax, 65, 24, 16, "dim_employee", [("*emp_id","INT"),("org_id","FK\u2192dim_org"),("role\u00b7rank","persona"),("trust \u03c4","\u2208[0,1]")], "595 rows", "#fbeedd", "#b8720f")
    t_pay = _table(ax, 84, 28, 14, "fact_payroll", [("emp_id","FK"),("period","monthly\u00d712"),("base_salary","DEC")], "7,140 = 595\u00d712", "#fbeedd", "#b8720f")  # bonus 삭제 (마스터 §6 — 02 setup_org)
    t_sig = _table(ax, 84, 11, 14, "trust_signal", [("emp_id","FK"),("indicator","taxon."),("value","synthetic")], "", "#fbeedd", "#b8720f")
    ar(ax, (t_org[0]+6, t_org[1]), (t_emp[0]+6, t_emp[1]+t_emp[3]), c="#1d7a3a", lw=1.8)
    ar(ax, (81, t_emp[1]+t_emp[3]/2), (84, t_pay[1]+t_pay[3]/2), c="#666", lw=1.1)
    ar(ax, (81, t_emp[1]+3), (84, t_sig[1]+t_sig[3]/2), c="#666", lw=1.1)
    tx(ax, 66, 9, note, 8.4, c="#b8720f", ha="left")
    fig.savefig(Path(out)/"fig_findw_provenance.png", dpi=200, bbox_inches="tight"); plt.close(fig)
    print(f"  [OK] fig_findw_provenance.png (personnel={personnel})")

# ═════════════════ E4·E5·E6 데이터 그림 ═════════════════
COLMAP = {
    "structure": ["structure","mask_structure","masking","b_family","family","B"],
    "coverage": ["coverage","x","x_pct","spec_coverage","visible_frac"],
    "rho": ["rho","closed_world_frac","cw_frac"], "lam": ["lambda","lam","clamp_lambda"],
    "mode": ["mode","threshold_mode","tau_mode","operating_mode"],
    "condition": ["condition","arm","model","judge"],
    "seed": ["seed","train_seed"], "mask_rep": ["mask_rep","rep","mask_seed","replication","mask_id"],
    "recovery": ["recovery","entitled_recovery","recovery_at_beta","rec_at_beta"],
    "fp": ["fp","false_permit","fp_rate","realized_fp"],
    "escalation": ["escalation","escalation_load","escal_load","abstain","abstain_frac","review_load"],
    "recovery_incl": ["recovery_incl","availability_incl","avail_incl_escalation","effective_recovery","recovery_with_escalation","recovery_with_escal"],
    "lam": ["lambda","lam","clamp_lambda"],
    "beta": ["beta","fp_budget"],
    # E5
    "policy": ["policy","escalation_policy","p","pol"], "k": ["k","k_threshold","k_small_group"],
    "leak": ["leak","leakage","leak_rate","leak_n"], "review": ["review","review_load","review_rate","review_n","escalated"],
    "over": ["over","over_restriction","over_withhold","overblock","over_n"],
    # E6
    "regime": ["regime","path","cache","cache_state","cold_warm","phase"],
    "status": ["status","http_status","ok"],
    "latency_ms": ["latency_ms","ms","elapsed_ms","parse_ms","latency"],
    "stage": ["stage","phase","component"],
}
VOCAB = {"mode_calib": {"calib","calibrated","visible","deploy","deployable"},
         "mode_oracle": {"oracle","oracle_bound","upper","attainable"},
         "cond_mlpceil": {"mlp+ceil","mlp_ceil","mlpceil","ceil","clamped"},
         "struct": {"b1":"B1","random":"B1","b2":"B2","role_row":"B2","rows":"B2",
                    "b3":"B3","attr_col":"B3","columns":"B3","b4":"B4p","b4p":"B4p","b4'":"B4p",
                    "b4prime":"B4p","functional_line":"B4p","b5":"B5","clause":"B5","clause_exception":"B5"}}
ANCH = {"calibB1": {20:0.0,40:15.0,60:33.2,80:37.8}, "oracleB1_80":65.6,
        "esc80": (89.2,37.8), "dial": {0.0:37.8,0.25:19.7,1.0:18.1},
        "B5o":6.3, "B5c":47.5, "B5fp":9.2,
        "tf": {"B1":(0.26,0.65),"B2":(0.0,0.26),"B3":(1.3,6.0),"B4p":(3.0,7.7)},
        "e5": {"anchor":(0.0,0.0,0.0), "k2_leak":2.2, "P2k5":0.4, "P4k5":14.7, "P5k5":20.9},
        "e6": {"cold_p50":971,"cold_p95":1425,"warm_p50":0.2,"warm_p95":6.9}}

def resolve(df, needed, optional=()):
    low = {c.lower(): c for c in df.columns}; got = {}
    for f in list(needed)+list(optional):
        hit = next((low[c.lower()] for c in COLMAP[f] if c.lower() in low), None)
        if hit: got[f] = hit
    miss = [f for f in needed if f not in got]
    return got, miss
def to_pct(s):
    s = pd.to_numeric(s, errors="coerce")
    return s*100.0 if s.max(skipna=True) is not None and s.max(skipna=True) <= 1.5 else s
def loadcsv(path, needed, optional=()):
    df = pd.read_csv(path); cols, miss = resolve(df, needed, optional)
    print(f"\n■ {path}: {len(df)}행"); [print(f"    {k:<12} \u2190 '{v}'") for k, v in cols.items()]
    if miss:
        print(f"  !! 미해결 필드 {miss} — 사용 가능 열: {list(df.columns)}"); sys.exit(2)
    return df, cols
def norm_e4(df, cols):
    o = pd.DataFrame()
    if "structure" in cols: o["structure"] = df[cols["structure"]].map(lambda v: VOCAB["struct"].get(str(v).strip().lower().replace(" ","_")))
    if "coverage" in cols:
        o["coverage"] = pd.to_numeric(df[cols["coverage"]], errors="coerce")
        if o["coverage"].max() <= 1.0: o["coverage"] *= 100
    for f in ("rho","seed","mask_rep","lam","beta"):
        if f in cols: o[f] = pd.to_numeric(df[cols[f]], errors="coerce")
    for f in ("mode","condition"):
        if f in cols: o[f] = df[cols[f]].astype(str).str.strip().str.lower()
    for f in ("recovery","fp","escalation","recovery_incl"):
        if f in cols: o[f] = to_pct(df[cols[f]])
    return o
def agg(g, col="recovery"):
    v = g[col].dropna().to_numpy(float)
    if not len(v): return np.nan, np.nan
    return v.mean(), (1.96*v.std(ddof=1)/np.sqrt(len(v)) if len(v) > 1 else 0.0)
def sel(d, st=None, mode=None, rho=None):
    if st is not None: d = d[d["structure"] == st]
    if mode == "calib": d = d[d["mode"].isin(VOCAB["mode_calib"])]
    if mode == "oracle": d = d[d["mode"].isin(VOCAB["mode_oracle"])]
    if rho is not None and "rho" in d: d = d[np.isclose(d["rho"], rho)]
    if "condition" in d: d = d[d["condition"].map(lambda c: any(k in c for k in VOCAB["cond_mlpceil"]))]
    if "lam" in d: d = d[np.isclose(d["lam"], 1.0)]
    if "beta" in d: d = d[np.isclose(d["beta"], 1.0) | np.isclose(d["beta"], 0.01)]
    return d

def b5sel(b5, mode):
    """B5 재실행 파일에서 헤드라인 운영점만: mode + ρ=0 + λ=1 + β=1% + clamp arm."""
    d = b5
    if "mode" in d: d = d[d["mode"].isin(VOCAB[f"mode_{mode}"])]
    if "rho" in d: d = d[np.isclose(d["rho"], 0.0)]
    if "lam" in d: d = d[np.isclose(d["lam"], 1.0)]
    if "beta" in d: d = d[np.isclose(d["beta"], 1.0) | np.isclose(d["beta"], 0.01)]
    if "condition" in d: d = d[d["condition"].map(lambda c: any(k in c for k in VOCAB["cond_mlpceil"]))]
    return d

def fig_e4_1(df, out):
    xs = [20,40,60,80]; fig, ax = plt.subplots(figsize=(6.4,4.4)); ser = {}
    for mode, st in (("calib",dict(ls="-",marker="o",label="MLP+ceil calibrated (deployable)")),
                     ("oracle",dict(ls="--",marker="s",label="MLP+ceil oracle (upper bound)"))):
        m, lo, hi = [], [], []
        for x in xs:
            d = sel(df,"B1",mode,0.0).loc[lambda d: np.isclose(d["coverage"],x)]
            mu, hw = agg(d); m.append(mu); lo.append(mu-hw); hi.append(mu+hw)
        ser[mode] = m; ax.plot(xs, m, **st); ax.fill_between(xs, lo, hi, alpha=0.18)
    ax.axhline(0, color="k", lw=2, label="PDP-deny")
    d80 = sel(df,"B1","calib",0.0).loc[lambda d: np.isclose(d["coverage"],80)]
    load, _ = agg(d80,"escalation") if "escalation" in d80 else (np.nan,np.nan)
    incl, _ = agg(d80,"recovery_incl") if "recovery_incl" in d80 else (np.nan,np.nan)
    if np.isfinite(incl):
        ax.annotate(f"escalation \u2192 {incl:.1f}%\n(load {load:.1f}%)", xy=(80, ser["calib"][-1]),
                    xytext=(50,82), arrowprops=dict(arrowstyle="->",lw=1), fontsize=9)
    ax.set_xlabel("specification coverage x (%)"); ax.set_ylabel("entitled recovery @ \u03b2=1% (%)")
    ax.set_title("B1 (random masking), \u03c1=0 open-world, \u03bb=1"); ax.set_xticks(xs)
    ax.set_ylim(-3,100); ax.legend(loc="upper left", fontsize=9)
    fig.tight_layout(); fig.savefig(Path(out)/"fig1_e4_b1_final_r2.png", dpi=200); plt.close(fig)
    for x, v in ANCH["calibB1"].items():
        check(f"e4-1 calib x={x}", abs(ser["calib"][xs.index(x)]-v) <= 0.35, f"{ser['calib'][xs.index(x)]:.2f} vs {v}")
    check("e4-1 oracle x=80", abs(ser["oracle"][-1]-ANCH["oracleB1_80"]) <= 0.35, f"{ser['oracle'][-1]:.2f} vs 65.6")
    if np.isfinite(incl):
        check("e4-1 escalation@80", abs(incl-89.2) <= 0.6 and abs(load-37.8) <= 0.6, f"incl {incl:.1f}/load {load:.1f} vs 89.2/37.8")
    else: skip("e4-1 escalation@80: recovery_incl 열 부재 — 주석 생략")

def fig_e4_2(df, b5, out):
    structs = ["B1","B2","B3","B4p","B5"]
    lbl = {"B1":"B1 random","B2":"B2 role row","B3":"B3 attr column","B4p":"B4' functional line","B5":"B5 clause exception"}
    fig, axes = plt.subplots(2,1,figsize=(7.2,7.6)); b5v = {}
    for ax, mode in zip(axes, ("oracle","calib")):
        for i, xc in enumerate((40,80)):
            ms, hs = [], []
            for st in structs:
                if st == "B5":
                    mu, hw = agg(b5sel(b5, mode))
                    b5v[mode] = mu
                else:
                    mu, hw = agg(sel(df,st,mode,0.0).loc[lambda d: np.isclose(d["coverage"],xc)])
                ms.append(mu); hs.append(hw)
            ax.bar(np.arange(5)+(i-0.5)*0.38, ms, width=0.36, yerr=hs, capsize=3, label=f"x={xc}%")
        ax.set_xticks(range(5)); ax.set_xticklabels([lbl[s] for s in structs], rotation=12)
        ax.set_ylabel("entitled-recovery @ \u03b2=1% (%)")
        ax.set_title(("oracle" if mode == "oracle" else "calibrated")+"-selected threshold"
                     + ("  (B5 bar = apparent recovery at fp 9.2%)" if mode == "calib" else ""))
        ax.legend()
    fig.suptitle("Hiding-structure asymmetry (MLP+ceil); B5 column from the single-pass rerun")
    fig.tight_layout(); fig.savefig(Path(out)/"fig2_structure_r2.png", dpi=200); plt.close(fig)
    check("e4-2 B5 oracle", abs(b5v.get("oracle",np.nan)-6.3) <= 0.35, f"{b5v.get('oracle',float('nan')):.2f} vs 6.3")
    check("e4-2 B5 calib", abs(b5v.get("calib",np.nan)-47.5) <= 0.6, f"{b5v.get('calib',float('nan')):.2f} vs 47.5")
    if "fp" in b5:
        fp, _ = agg(b5sel(b5, "calib"), "fp")
        check("e4-2 B5 calib fp", abs(fp-9.2) <= 0.6, f"{fp:.2f} vs 9.2")

def fig_e4_3(df, out):
    rhos = [0.0,0.25,1.0]; fig, ax = plt.subplots(figsize=(6.6,4.4)); vals = {}
    for mode, st in (("calib",dict(ls="-",marker="o",label="calibrated")),
                     ("oracle",dict(ls="--",marker="o",label="oracle bound"))):
        m, h = [], []
        for r in rhos:
            mu, hw = agg(sel(df,"B1",mode,r).loc[lambda d: np.isclose(d["coverage"],80)])
            m.append(mu); h.append(hw)
        vals[mode] = m; ax.errorbar(rhos, m, yerr=h, capsize=3, **st)
        for r, v in zip(rhos, m): ax.annotate(f"{v:.1f}",(r,v),textcoords="offset points",xytext=(0,7),fontsize=9)
    ax.axhline(0,color="r",lw=2,label="PDP-deny")
    ax.annotate("collapse is asymptotic, not constructiv<repo> grant pairs stay outside \u03c1's label domain",
                xy=(1.0,vals["calib"][-1]), xytext=(0.26,9), fontsize=9,
                arrowprops=dict(arrowstyle="->",lw=0.8,color="gray"))
    ax.set_xlabel("\u03c1  (fraction of unenumerated pairs taught as explicit deny)")
    ax.set_ylabel("Recovery @ \u03b2 = 1% (%)"); ax.set_xticks(rhos); ax.legend()
    ax.set_title("Open/closed-world dial (B1, x=80, \u03bb=1) — corrected lineage")
    fig.tight_layout(); fig.savefig(Path(out)/"fig3_e4_rho_dial_r2.png", dpi=200); plt.close(fig)
    for r, v in ANCH["dial"].items():
        check(f"e4-3 calib \u03c1={r}", abs(vals["calib"][rhos.index(r)]-v) <= 0.35, f"{vals['calib'][rhos.index(r)]:.2f} vs {v}")
    check("e4-3 oracle \u03c1=0", abs(vals["oracle"][0]-65.6) <= 0.35, f"{vals['oracle'][0]:.2f} vs 65.6")

def fig_tf(df, b5, out):
    fig, ax = plt.subplots(figsize=(5.8,5.4)); pts = []
    for st in ("B1","B2","B3","B4p"):
        for x in (20,40,60,80):
            fo, _ = agg(sel(df,st,"oracle",0.0).loc[lambda d: np.isclose(d["coverage"],x)],"fp")
            fc, _ = agg(sel(df,st,"calib",0.0).loc[lambda d: np.isclose(d["coverage"],x)],"fp")
            if np.isfinite(fo) and np.isfinite(fc):
                pts.append((st,x,fo,fc)); ax.scatter(fo,fc,s=28)
                ax.annotate(f"{st},{x}",(fo,fc),fontsize=7,textcoords="offset points",xytext=(4,3))
    if "fp" in b5:
        fo, _ = agg(b5sel(b5, "oracle"), "fp")
        fc, _ = agg(b5sel(b5, "calib"), "fp")
        pts.append(("B5",100,fo,fc)); ax.scatter(fo,fc,s=36)
        ax.annotate("B5",(fo,fc),fontsize=8,textcoords="offset points",xytext=(4,3))
    lim = max(4.0, max((max(p[2],p[3]) for p in pts), default=4.0)*1.1)
    ax.plot([0,lim],[0,lim],"k--",lw=1)
    ax.set_xlabel("realized false-permit, oracle-selected \u03c4 (%)")
    ax.set_ylabel("realized false-permit, visible-calibrated \u03c4 (%)")
    ax.set_title("Threshold transfer gap\n(points above the diagonal: \u03b2 cannot be held\nwithout hidden-region labels)", fontsize=10)
    fig.tight_layout(); fig.savefig(Path(out)/"fig_transfer_gap_r2.png", dpi=200); plt.close(fig)
    for st, (lo, hi) in ANCH["tf"].items():
        vs = [p[3] for p in pts if p[0] == st]
        ok = bool(vs) and all((lo-0.15 <= v <= hi+0.15) or v <= 0.05 for v in vs)  # 0 = 전면 기권 자명 준수 (정본 "trivially 0% at x=20")
        check(f"tf calib-fp {st}", ok, f"{[f'{v:.2f}' for v in vs]} vs [{lo},{hi}] (0=기권)")
    b5c = [p[3] for p in pts if p[0] == "B5"]
    if b5c: check("tf calib-fp B5", abs(b5c[0]-9.2) <= 0.6, f"{b5c[0]:.2f} vs 9.2")

def fig_e5(path, out):
    df, cols = loadcsv(path, ["policy","k","leak","review"], optional=["over"])
    pol = df[cols["policy"]].astype(str).str.upper().str.strip()
    k = pd.to_numeric(df[cols["k"]], errors="coerce")
    def rate(col, denom):
        v = pd.to_numeric(df[col], errors="coerce")
        name = col.lower()
        if "rate" in name or "pct" in name:                      # 이미 비율/퍼센트
            return v*100 if v.max() <= 1.5 else v
        if v.max() <= 1.5: return v*100                          # 0~1 비율
        if (v.dropna() % 1 == 0).all():                          # 정수 = 건수
            print(f"    (주) '{col}' = 건수로 판독 → /{denom} 변환 (leak 분모=withhold 271 · review 분모=559)")
            return v/denom*100
        return v
    leak, review = rate(cols["leak"], 271), rate(cols["review"], 559)
    D = pd.DataFrame(dict(policy=pol, k=k, leak=leak, review=review))
    pols = ["P0","P1","P2","P3","P4","P5"]; ks = sorted(D["k"].dropna().unique())
    fig, (a1, a2) = plt.subplots(1,2,figsize=(11,4.4))
    M = np.array([[D[(D.policy==p)&(D.k==kk)]["review"].mean() for kk in ks] for p in pols])
    im = a1.imshow(M, aspect="auto", cmap="Blues")   # 논문 톤 정합 (2026-07-31 — 난색→한색)
    a1.set_xticks(range(len(ks))); a1.set_xticklabels([int(x) for x in ks])
    a1.set_yticks(range(6)); a1.set_yticklabels(pols)
    vmax = np.nanmax(M) if np.isfinite(M).any() else 1.0
    for i in range(6):
        for j in range(len(ks)):
            if np.isfinite(M[i,j]):
                a1.text(j, i, f"{M[i,j]:.1f}", ha="center", va="center", fontsize=7.5,
                        color="white" if M[i,j] > 0.55*vmax else "#1a2a3a")  # 짙은 셀 가독성
    # 앵커 셀 (P0, k=5) 테두리 마커 (2026-07-31)
    if 5 in ks:
        from matplotlib.patches import Rectangle
        a1.add_patch(Rectangle((ks.index(5)-0.5, -0.5), 1, 1, fill=False, ec="#c0392b", lw=2.2))
        a1.annotate("anchor", (ks.index(5), -0.5), xytext=(0, 6), textcoords="offset points",
                    ha="center", fontsize=8, color="#c0392b")
    a1.set_xlabel("small-group threshold k"); a1.set_ylabel("escalation policy")
    a1.set_title("review load (% of 559 queries)"); fig.colorbar(im, ax=a1, shrink=0.85)
    lk = D.groupby("k")["leak"].mean()
    a2.plot(lk.index, lk.values, marker="o")
    for kk, v in lk.items(): a2.annotate(f"{v:.1f}",(kk,v),textcoords="offset points",xytext=(0,7),fontsize=8)
    a2.set_xlabel("small-group threshold k"); a2.set_ylabel("leakage (% of withhold GT)")
    a2.set_title("leakage vs k (policy-invariant)"); a2.set_xticks([int(x) for x in ks])
    fig.suptitle("E5 operating surface: escalation policy \u00d7 k (anchor P0, k=5)")
    fig.tight_layout(); fig.savefig(Path(out)/"fig_e5_opsurface.png", dpi=200); plt.close(fig)
    g = lambda p, kk, col: D[(D.policy==p)&(np.isclose(D.k,kk))][col].mean()
    check("e5 anchor (P0,k5)", abs(g("P0",5,"leak")) <= 0.15 and abs(g("P0",5,"review")) <= 0.15,
          f"leak {g('P0',5,'leak'):.2f}/review {g('P0',5,'review'):.2f} vs 0/0")
    check("e5 k=2 leak", abs(D[np.isclose(D.k,2)]["leak"].mean()-2.2) <= 0.3, f"{D[np.isclose(D.k,2)]['leak'].mean():.2f} vs 2.2")
    for p, v in (("P2",0.4),("P4",14.7),("P5",20.9)):
        check(f"e5 {p}@k5 review", abs(g(p,5,"review")-v) <= 0.3, f"{g(p,5,'review'):.2f} vs {v}")
    pv = D[np.isclose(D.k,5)].groupby("policy")["leak"].mean()
    check("e5 deny 정책 불변", pv.max()-pv.min() <= 0.15, f"k=5 leak 범위 {pv.min():.2f}~{pv.max():.2f}")

def fig_e6(path, out):
    df, cols = loadcsv(path, ["regime","latency_ms"], optional=["stage","status"])
    if "status" in cols:   # 성공 요청만 (실패 행은 latency 왜곡)
        st = df[cols["status"]].astype(str).str.lower()
        ok = st.str.contains("200") | st.isin(["ok","success","hit","miss","true"])
        if ok.any(): df = df[ok]
    reg = df[cols["regime"]].astype(str).str.lower().str.strip()
    lat = pd.to_numeric(df[cols["latency_ms"]], errors="coerce")
    if "stage" in cols and cols["stage"] != cols["regime"]:
        stg = df[cols["stage"]].astype(str).str.lower()
        if stg.str.contains("parse").any():
            m = stg.str.contains("parse"); reg, lat = reg[m], lat[m]   # 파스 스테이지만
    cold = lat[reg.str.contains("cold")].dropna(); warm = lat[reg.str.contains("warm")].dropna()
    if cold.median() < 10: cold, warm = cold*1000, warm*1000       # 초 단위 → ms
    # percentile 규약 = 정본 산출 코드와 문자 동일 (parser_run_v2.py:144 확인, 2026-07-31):
    #   sorted(ms of status==OK)[int(q*n)-1]  — n=30에서 v[27]=1425.3 = 정본 p95 1,425.
    # (선형 보간이면 1,906 — v[27]~v[28] 간극 874ms. 상위 2건 2,299/2,406ms는 실재 호출로
    #  히스토그램에 그대로 표시됨 — 규약이 값을 숨기지 않음.)
    def pct(v, q):
        v = np.sort(np.asarray(v)); n = len(v)
        return v[max(int(q/100*n) - 1, 0)]
    fig, ax = plt.subplots(figsize=(7.0,4.2))
    ax.hist(cold, bins=20, alpha=0.65, label=f"cold (forced miss, n={len(cold)})")
    ax.hist(np.clip(warm,0.05,None), bins=np.logspace(np.log10(0.05),np.log10(max(20,warm.max())),25),
            alpha=0.65, label=f"warm (cache hit, n={len(warm)})")
    ax.set_xscale("log"); ax.set_xlabel("parse-stage latency (ms, log)"); ax.set_ylabel("requests")
    for v, t in ((pct(cold,50),"cold p50"),(pct(warm,50),"warm p50")):
        ax.axvline(v, ls="--", lw=1, color="k"); ax.annotate(f"{t} {v:.1f}",(v,ax.get_ylim()[1]*0.9),fontsize=8,rotation=90,va="top")
    ax.set_title("E6: parse-stage latency, cold vs warm (decide/enforce local, ~1 ms; generation excluded)")
    ax.legend(); fig.tight_layout(); fig.savefig(Path(out)/"fig_e6_latency.png", dpi=200); plt.close(fig)
    c50, c95 = pct(cold,50), pct(cold,95)
    w50, w95 = pct(warm,50), pct(warm,95)
    A = ANCH["e6"]
    check("e6 cold p50/p95", abs(c50-A["cold_p50"]) <= 30 and abs(c95-A["cold_p95"]) <= 80, f"{c50:.0f}/{c95:.0f} vs 971/1425")
    check("e6 warm p50/p95", abs(w50-A["warm_p50"]) <= 0.3 and abs(w95-A["warm_p95"]) <= 2.0, f"{w50:.2f}/{w95:.2f} vs 0.2/6.9")

# ═════════════════ main ═════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="figs")
    ap.add_argument("--personnel", choices=["mysql","synthetic"], default="mysql",
                    help="provenance C 패널 출처 (ETL 확인 결과에 맞출 것; 기본 = 조립 정본 md의 MySQL)")
    ap.add_argument("--runs", default="e4/judge/runs_repaired_v2_final.csv")
    ap.add_argument("--b5",   default="e4/out_b5/b5rerun_findw_runs.csv")
    ap.add_argument("--e5",   default="e5_curve.csv")   # findw_v2 루트 (2026-07-31 사용자 배치)
    ap.add_argument("--e6",   default="e6_latency.csv")
    ap.add_argument("--skip-diagrams", action="store_true")
    a = ap.parse_args()
    # 기본 경로는 존재할 때만 사용 (없으면 해당 축 SKIP)
    for f in ("runs", "b5", "e5", "e6"):
        p = getattr(a, f)
        if p and not Path(p).exists():
            print(f"  [경로 없음 → SKIP 예정] --{f} {p}")
            setattr(a, f, None)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    print("── 다이어그램 (데이터 불요) ──")
    if a.skip_diagrams: skip("다이어그램 생략 (--skip-diagrams)")
    else:
        fig_position(out); fig_authority(out); fig_provenance(out, a.personnel)
    print("\n── 데이터 그림 ──")
    if a.runs and a.b5:
        df, cols = loadcsv(a.runs, ["structure","coverage","rho","mode","condition","recovery","fp","escalation"],
                           optional=["recovery_incl","lam","beta"])
        print("  ※ 헤드라인 필터 적용: λ=1 · β=1% · (B5는 +ρ=0)")
        runs = norm_e4(df, cols)
        b5df, b5c = loadcsv(a.b5, ["mode","recovery","fp"],
                            optional=["structure","rho","lam","beta","condition","seed"])
        b5 = norm_e4(b5df, b5c)
        fig_e4_1(runs, out); fig_e4_2(runs, b5, out); fig_e4_3(runs, out); fig_tf(runs, b5, out)
    else: skip("E4 4종: --runs/--b5 미지정")
    if a.e5: fig_e5(a.e5, out)
    else: skip("E5 운영면: --e5 미지정")
    if a.e6: fig_e6(a.e6, out)
    else: skip("E6 latency: --e6 미지정")
    rep = {"inputs": {p: hashlib.sha256(Path(p).read_bytes()).hexdigest()[:16]
                      for p in (a.runs, a.b5, a.e5, a.e6) if p and Path(p).exists()},
           "personnel": a.personnel, "verify": VERIFY}
    (out/"verify_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2))
    fails = [v for v in VERIFY if v["status"] == "FAIL"]
    print(f"\n── 대조: {len(VERIFY)-len(fails)} PASS / {len(fails)} FAIL → {out/'verify_report.json'}")
    if fails: print("!! FAIL 그림 반입 금지 — 입력 계보 확인."); sys.exit(1)

if __name__ == "__main__":
    main()
