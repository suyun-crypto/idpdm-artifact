# -*- coding: utf-8 -*-
"""
06_derivation_v2.py — cl(F) 도출규칙 엔진 + obligation 검증기 + 평가 러너
스펙: 06_derivation_spec.md (2026-07-30, A5 확정: 세션 누적 in-scope, 원장=감사로그 파생 뷰)

규칙:
  R3 admissibility  4-conjunct: tier ≤ max_tier(role,attr) ∧ basis 행검사 ∧ cls ≤ clearance
                    (+ handling=escalate_required → escalation obligation)
  R1 유효 tier      0<n<k ∧ tier<3 → t_eff=3 재검사. clearance-relative 생략:
                    ∀s∈S_f grant_t3(u,attr,s) (ids 부재 시 scope 기반).
  R2-diff 차분      동일 attr·period, 양측 ids, S∩≠∅, S≠, 0<|S△|<k. 생략: ∀s∈△ grant_t3.
  R2-join 연결      익명 소수(ids·sid 부재, 0<n<k) × 동일 subject_type 신원 조각(|S_g|<k),
                    scope 경로 호환. 생략: ∀s∈S_g 양쪽 attr t3 자격.
  정의역            subject_type(attr) ∈ {직원, 고객}만 (조직·지역·시스템 제외).
  세션 누적          F_eff = 후보 ∪ ledger(u). 원장 조각은 보류 불가(기공개) → 후보 강제 보류.
  행동 공간          {release, withhold} + handling 승계(mask_pii/escalate) — 변조 없음 (D7).
  순서 불변식        released ∪ ledger 에 위험쌍·무자격 n<k 공개 없음 (개별 판정은 순서 의존).

구현 표준 (E4 승계): 결정론(난수 없음) · 전 케이스 상태 기록 · 원자적 저장 ·
헤더 문자열 단언 · frag-set 해시 · 기동 게이트 실패 시 즉시 중단.

설계 결정 (코드 확정 — 스펙 대조점 해소):
  ownership 행 의미론 = 본인 단독 조각(S_f={u} 또는 subject_id=u)만.  [C3]
  role 없는 일반 직원 = SELF_READABLE ownership t3 + RS public 2, clearance 1.  [C3 부속]
  tier ∈ {1,2,3}; t3 = 주체 식별 수준.  [C2]
  k 헤드라인 5, 스윕 {2,3,5,10,20}.  [C4]
  R2-diff 교집합 비공백 조건 = 30b 원문(△<k)의 보수 정밀화(disjoint 오탐 제거).  [C8]
  마스킹 = handling 승계만; R2 행동은 {release, withhold}.  [C9]
"""
import sys, os, io, json, hashlib, csv, itertools, tempfile
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "..", "findw.duckdb")
OUT = os.path.join(HERE, "out06")
os.makedirs(OUT, exist_ok=True)

import duckdb

K_HEAD = 5
K_SWEEP = [2, 3, 5, 10, 20]
PERSON_TYPES = {"직원", "고객"}          # R1·R2 정의역 (policy_attr.subject_type)
SUBJECT_DENIED = {"AL"}                  # 조항 우선 — 생략 불가
SELF_READABLE = {"ER", "PB", "PH"}

# ── 데이터 적재 (read_only, 결정론) ─────────────────────────────────────────
con = duckdb.connect(DB, read_only=True)

FRAGS = {}   # fid -> dict
for r in con.execute("""SELECT fragment_id, report_id, period, tier, attr, subject_scope,
        subject_id, subject_count, subject_ids, value, classification, handling, canary_flag
        FROM report_fragment ORDER BY fragment_id""").fetchall():
    fid = r[0]
    ids = frozenset(x.strip() for x in r[8].split(",")) if r[8] else None
    FRAGS[fid] = dict(fid=fid, rid=r[1], period=str(r[2]), tier=r[3], attr=r[4],
                      scope=r[5], sid=r[6], n=r[7], ids=ids, value=r[9],
                      cls=r[10], handling=r[11], canary=r[12])

CELLS = {(r[0], r[1]): (r[2], r[3], r[4]) for r in
         con.execute("SELECT role_id, attr, max_tier, basis, clause FROM policy_cell").fetchall()}
CLR = dict(con.execute("SELECT role_id, clearance FROM policy_clearance").fetchall())
STYPE = dict(con.execute("SELECT attr, subject_type FROM policy_attr").fetchall())

EMP_PATH = {r[0]: r[1] for r in con.execute(
    "SELECT e.emp_id, o.org_path FROM dim_employee e JOIN dim_org o USING(org_id)").fetchall()}
try:
    CLIENT_PATH = {str(r[0]): r[1] for r in con.execute("""
        SELECT DISTINCT d.client_id, o.org_path FROM disp d
        JOIN account a USING(account_id)
        JOIN dim_org o ON o.district_id = a.district_id AND o.org_level='branch'
        WHERE d.type='OWNER'""").fetchall()}
except Exception:
    # [artifact 2026-08-15] raw `disp` not shipped in the artifact DB;
    # identical mapping materialized at build time (make_artifact_db.py).
    # Full-DB behavior unchanged: the try path succeeds there.
    CLIENT_PATH = {str(r[0]): r[1] for r in con.execute(
        "SELECT client_id, org_path FROM client_org_path").fetchall()}
PERSONA = {r[0]: (r[1], r[2]) for r in con.execute("""
    SELECT e.role_id, e.emp_id, o.org_path FROM dim_employee e
    JOIN dim_org o USING(org_id) WHERE e.role_id IS NOT NULL""").fetchall()}

FRAGSET_HASH = hashlib.sha256(",".join(sorted(FRAGS)).encode()).hexdigest()[:16]

# ── 요청자 ──────────────────────────────────────────────────────────────────
class Requester:
    def __init__(self, emp_id, role_id=None):
        self.emp_id = emp_id
        self.role_id = role_id
        self.org_path = EMP_PATH[emp_id]
        self.clearance = CLR.get(role_id, 1)   # 미열거 역할·일반 직원 = 기본값 1 (§3.2-기본값)
    def cell(self, attr):
        if self.role_id and (self.role_id, attr) in CELLS:
            return CELLS[(self.role_id, attr)]
        if self.role_id is None:               # 일반 직원 — 보편 권리만 [설계 결정]
            if attr in SELF_READABLE:
                return (3, "ownership", "§2.1b-소유권(PIPA35/GDPR15)")
            if attr == "RS":
                return (2, "public", "§2.4-공표")
        return None
    def key(self):
        return f"{self.role_id or 'STAFF'}:{self.emp_id}"

def subj_path(token):
    """주체 토큰 → 소속 경로. 직원 E* / 고객 숫자·client#N."""
    t = token.replace("client#", "")
    if token in EMP_PATH: return EMP_PATH[token]
    return CLIENT_PATH.get(t)

# ── R3 admissibility (4-conjunct) ───────────────────────────────────────────
def admissible(u, f):
    """returns (ok:bool, reason:str, obligations:list)"""
    c = u.cell(f["attr"])
    if c is None:
        return False, "R3:cell-miss(기본 deny)", []
    max_tier, basis, clause = c
    if f["tier"] > max_tier:
        return False, f"R3:tier {f['tier']}>{max_tier}", []
    # basis 행 검사
    if basis == "hierarchy":
        if not f["scope"].startswith(u.org_path):
            return False, "R3:row(hierarchy subtree 밖)", []
    elif basis == "ownership":
        own = (f["sid"] == u.emp_id) or (f["ids"] == frozenset([u.emp_id]))
        if not own:
            return False, "R3:row(ownership 본인 단독 아님)", []
    elif basis in ("functional", "public"):
        pass
    else:
        return False, f"R3:basis? {basis}", []
    # [설계 결정 — 06 확정] 분류 conjunct는 제3자 공개 통제(WB ATI §28)이며,
    # ownership basis의 본인 단독 SELF_READABLE 조각에는 주체 열람권(PIPA35/GDPR15)이
    # 우선한다 — 아니면 기본 clearance(1)인 전 직원의 소유권이 공허해짐.
    # SUBJECT_DENIED는 격자에 ownership 셀 자체가 없어 이 면제에 도달 불가(조항 우선 보존).
    self_own = (basis == "ownership" and f["attr"] in SELF_READABLE
                and ((f["sid"] == u.emp_id) or (f["ids"] == frozenset([u.emp_id]))))
    if f["cls"] > u.clearance and not self_own:
        return False, f"R3:cls {f['cls']}>{u.clearance}", []
    ob = []
    if f["handling"] == "escalate_required":
        ob.append(("escalation", f["fid"], "handling 승계"))
    elif f["handling"] == "mask_pii":
        ob.append(("mask_pii", f["fid"], "handling 승계"))
    return True, "R3:ok", ob

# ── grant_t3 (생략 조건의 원자 판정) ────────────────────────────────────────
def grant_t3(u, attr, subject_token):
    if attr in SUBJECT_DENIED:
        return False                       # 조항 우선 — 생략 불가
    c = u.cell(attr)
    if c is None or c[0] < 3:
        return False
    basis = c[1]
    if basis == "functional":
        return True
    if basis == "hierarchy":
        p = subj_path(subject_token)
        return bool(p) and p.startswith(u.org_path)
    if basis == "ownership":
        return subject_token == u.emp_id
    return False                            # public은 t3 부여 없음

def grant_t3_scope(u, attr, scope):
    """ids 부재 조각의 생략 판정 — scope 전체에 대한 t3 자격."""
    if attr in SUBJECT_DENIED:
        return False
    c = u.cell(attr)
    if c is None or c[0] < 3:
        return False
    basis = c[1]
    if basis == "functional":
        return True
    if basis == "hierarchy":
        return scope.startswith(u.org_path)
    return False

# ── R1 ──────────────────────────────────────────────────────────────────────
def r1_check(u, f, k):
    """R3 통과 조각에 적용. returns (action, reason, skip:bool)"""
    if STYPE.get(f["attr"]) not in PERSON_TYPES:
        return "release", "R1:정의역밖", False
    n = f["n"] or 0
    if not (0 < n < k) or f["tier"] >= 3:
        return "release", "R1:비대상", False
    # clearance-relative 생략
    if f["ids"] is not None:
        skip = all(grant_t3(u, f["attr"], s) for s in f["ids"])
    else:
        skip = grant_t3_scope(u, f["attr"], f["scope"])
    if skip:
        return "release", "R1:skip(권한상대)", True
    max_tier = u.cell(f["attr"])[0]
    if 3 > max_tier:
        return "withhold", f"R1:t_eff=3>{max_tier} (n={n}<k={k})", False
    # 승격은 일어났으나 요청자의 명시 셀이 t3 자격 — 조항 grant의 재검사 통과 (발화 없음).
    # skip(검사 생략)과 구별: 여기는 검사·승격 수행 후 흡수. SUBJECT_DENIED도 명시 셀
    # (예: F_CMP·F_SEC의 AL functional t3)로만 이 경로에 도달 — 조항 우선 보존.
    return "release", "R1:승격흡수(t_eff=3≤max)", False

# ── R2 간선 ─────────────────────────────────────────────────────────────────
def r2_diff_edge(u, f, g, k):
    if f["attr"] != g["attr"] or f["period"] != g["period"]:
        return None
    if STYPE.get(f["attr"]) not in PERSON_TYPES:
        return None
    A, B = f["ids"], g["ids"]
    if A is None or B is None or A == B or not (A & B):
        return None
    d = A ^ B
    if not (0 < len(d) < k):
        return None
    if all(grant_t3(u, f["attr"], s) for s in d):
        return ("skip", d)
    return ("risk", d)

def r2_join_edge(u, f, g, k):
    """f = 익명 소수, g = 신원 조각 (방향 있음)."""
    if STYPE.get(f["attr"]) not in PERSON_TYPES:
        return None
    if STYPE.get(f["attr"]) != STYPE.get(g["attr"]):
        return None
    if f["ids"] is not None or f["sid"] is not None:
        return None
    if not (0 < (f["n"] or 0) < k):
        return None
    if g["ids"] is None or not (0 < len(g["ids"]) < k):
        return None
    a, b = f["scope"], g["scope"]
    if not (a.startswith(b) or b.startswith(a)):
        return None
    if all(grant_t3(u, f["attr"], s) and grant_t3(u, g["attr"], s) for s in g["ids"]):
        return ("skip", g["ids"])
    return ("risk", g["ids"])

# ── cl(F) — 판정 합성 ───────────────────────────────────────────────────────
def cl(u, cand_fids, ledger_fids, k=K_HEAD, use_r1=True, use_r2=True):
    """returns dict: verdicts{fid:(action, rule, reason)}, obligations[], edges[], invariant"""
    verdicts, obligations, edges = {}, [], []
    ledger = [FRAGS[x] for x in ledger_fids]
    # 1) R3
    surv = []
    for fid in cand_fids:
        f = FRAGS[fid]
        ok, why, ob = admissible(u, f)
        if not ok:
            verdicts[fid] = ("withhold", "R3", why)
        else:
            surv.append(f); obligations += ob
            verdicts[fid] = ("release", "R3", why)   # 잠정
    # 2) R1
    if use_r1:
        kept = []
        for f in surv:
            act, why, skip = r1_check(u, f, k)
            if act == "withhold":
                verdicts[f["fid"]] = ("withhold", "R1", why)
                obligations.append(("k_threshold", f["fid"], why))
            else:
                if skip:
                    verdicts[f["fid"]] = ("release", "R1skip", why)
                kept.append(f)
        surv = kept
    # 3) R2 — F_eff = surv ∪ ledger
    if use_r2:
        F_eff = surv + ledger
        led = set(ledger_fids)
        # 위험 간선 수집 (결정론 순서: fid 정렬 쌍)
        risk = []
        for f, g in itertools.combinations(sorted(F_eff, key=lambda x: x["fid"]), 2):
            e = r2_diff_edge(u, f, g, k)
            if e:
                edges.append(("diff", f["fid"], g["fid"], e[0], len(e[1])))
                if e[0] == "risk": risk.append((f["fid"], g["fid"], "R2-diff"))
            for a, b in ((f, g), (g, f)):
                e2 = r2_join_edge(u, a, b, k)
                if e2:
                    edges.append(("join", a["fid"], b["fid"], e2[0], len(e2[1])))
                    if e2[0] == "risk": risk.append((a["fid"], b["fid"], "R2-join"))
        # 해소: 원장 보류 불가 → 후보 강제; 후보-후보는 결정론 우선순위
        withheld = set()
        def alive(x): return x not in withheld and (x in led or verdicts.get(x, ("release",))[0] == "release")
        for a, b, rule in sorted(risk):
            if not (alive(a) and alive(b)):
                continue
            if a in led and b in led:
                # 기공개 쌍 — 통제 시점 상실 (평가에선 미발생; 발생 시 감사 obligation만)
                obligations.append(("audit_alert", f"{a}|{b}", rule + ":기공개쌍"))
                continue
            if a in led: victim = b
            elif b in led: victim = a
            else:
                fa, fb = FRAGS[a], FRAGS[b]
                ta = 3 if (fa["ids"] is None and 0 < (fa["n"] or 0) < k) else fa["tier"]
                tb = 3 if (fb["ids"] is None and 0 < (fb["n"] or 0) < k) else fb["tier"]
                victim = a if (ta, -(fa["n"] or 0), a) > (tb, -(fb["n"] or 0), b) else b
            withheld.add(victim)
            other = b if victim == a else a
            verdicts[victim] = ("withhold", rule, f"{rule} vs {other}" + (" (ledger)" if other in led else ""))
            obligations.append(("k_threshold", victim, f"{rule}:{other}"))
    # 4) 공개분 원장 기재 obligation
    for fid, (act, rule, why) in verdicts.items():
        if act == "release":
            obligations.append(("session_ledger", fid, "공개 기재"))
    # 5) 고정점·불변식 단언
    rel = [FRAGS[x] for x, v in verdicts.items() if v[0] == "release"]
    final = rel + ledger
    # 2026-08-04: 사후 불변식을 위 해소 루프(원장-원장 쌍 → audit_alert + continue)와
    #   정합화. 해소 루프는 기공개 쌍을 감사 소관으로 이관하는데 사후 단언만 전면
    #   폐쇄를 요구해 서로 모순이었다 (평가 케이스에서는 원장-원장 위험쌍이 발생하지
    #   않아 드러나지 않음).
    #   보장하는 불변식의 정확한 형태 = 「현재 판정이 새 위험을 추가하지 않는다」
    #   — 신규 공개가 개입한 쌍 한정. 보호 범위는 줄지 않는다: 한쪽이라도 이번 판정의
    #   release면 both_ledger가 거짓이므로 단언이 그대로 적용된다.
    #   최초 발견: triple_gap_probe.py T4 (2026-07-30). 상시 검증: 동 파일 T4b.
    #   논문: 부록 I "the invariant ... is accordingly narrower than blanket closure".
    led_final = set(ledger_fids)
    for f, g in itertools.combinations(final, 2):
        both_ledger = f["fid"] in led_final and g["fid"] in led_final
        e = r2_diff_edge(u, f, g, k)
        assert both_ledger or not (use_r2 and e and e[0] == "risk"), \
            f"불변식 위반(diff): {f['fid']},{g['fid']}"
        for a, b in ((f, g), (g, f)):
            e2 = r2_join_edge(u, a, b, k)
            assert both_ledger or not (use_r2 and e2 and e2[0] == "risk"), \
                f"불변식 위반(join): {a['fid']},{b['fid']}"
    if use_r1:
        for f in rel:
            act, why, skip = r1_check(u, f, k)
            assert act == "release", f"불변식 위반(R1 잔존): {f['fid']}"
    return dict(verdicts=verdicts, obligations=obligations, edges=edges)

# ── obligation 검증기 (독립 패스) ───────────────────────────────────────────
def verify_obligations(u, cand, ledger, res, k=K_HEAD):
    errs = []
    obs = res["obligations"]
    obset = defaultdict(list)
    for kind, ref, why in obs: obset[kind].append((ref, why))
    for fid, (act, rule, why) in res["verdicts"].items():
        f = FRAGS[fid]
        if act == "release":
            if not any(r == fid for r, _ in obset["session_ledger"]):
                errs.append(f"원장 기재 누락: {fid}")
            if f["handling"] == "mask_pii" and not any(r == fid for r, _ in obset["mask_pii"]):
                errs.append(f"mask_pii 승계 누락: {fid}")
            if f["handling"] == "escalate_required" and not any(r == fid for r, _ in obset["escalation"]):
                errs.append(f"escalation 승계 누락: {fid}")
        if act == "withhold" and rule in ("R1", "R2-diff", "R2-join"):
            if not any(r == fid for r, _ in obset["k_threshold"]):
                errs.append(f"k-임계 obligation 누락: {fid} ({rule})")
            if rule.startswith("R2"):
                refd = [w for r, w in obset["k_threshold"] if r == fid]
                for w in refd:
                    other = w.split(":")[-1]
                    if other not in set(cand) | set(ledger):
                        errs.append(f"R2 참조 무효: {fid} -> {other}")
    return errs

# ── 케이스 실행 헬퍼 ────────────────────────────────────────────────────────
CANARY = {f["canary"]: f["fid"] for f in FRAGS.values() if f["canary"] in ("C-a", "C-b")}
CC = sorted(f["fid"] for f in FRAGS.values() if f["canary"] == "C-c")
CANARY["C-c1"], CANARY["C-c2"] = CC[1], CC[0]  # G05-02596=익명(LN), G02-02597=신원(CP)
# 주의: 정렬상 G02 < G05 — 의미 기준 재지정
CANARY["C-c1"] = "G05-02596"; CANARY["C-c2"] = "G02-02597"
SAR = ["SAR-00001", "SAR-00002"]

def U(role):  # 페르소나 요청자
    return Requester(PERSONA[role][0], role)
def staff(emp_id):
    return Requester(emp_id, None)

def run_case(case_id, u, cand, ledger=(), k=K_HEAD, use_r1=True, use_r2=True):
    res = cl(u, list(cand), list(ledger), k, use_r1, use_r2)
    errs = verify_obligations(u, cand, ledger, res, k)
    return dict(case=case_id, u=u.key(), k=k, cand=list(cand), ledger=list(ledger),
                res=res, verrs=errs)

# ── 기동 게이트: 기대 판정표 자가 검증 ──────────────────────────────────────
def gate():
    ca, cb, c1, c2 = CANARY["C-a"], CANARY["C-b"], CANARY["C-c1"], CANARY["C-c2"]
    colleague = "E0113"   # C-a 대상 E0114의 동료 (비본인 일반 직원)
    G = []
    def exp(cid, u, cand, ledger, want, **kw):
        r = run_case(cid, u, cand, ledger, **kw)
        got = {fid: r["res"]["verdicts"][fid][0] for fid in cand}
        rules = {fid: r["res"]["verdicts"][fid][1] for fid in cand}
        ok = got == want and not r["verrs"]
        G.append((cid, ok, got, rules, want, r["verrs"]))
        return r
    exp("G1 C-a×동료",   staff(colleague), [ca], [], {ca: "withhold"})
    exp("G2 C-a×본인",   staff("E0114"),   [ca], [], {ca: "release"})
    exp("G3 C-a×H_HR",   U("H_HR"),        [ca], [], {ca: "release"})
    exp("G4 C-b×F_PAY",  U("F_PAY"),       [cb], [], {cb: "release"})   # R1 skip 실증
    exp("G5 C-b×동료",   staff(colleague), [cb], [], {cb: "withhold"})
    exp("G6 C-b×F_CMP",  U("F_CMP"),       [cb], [], {cb: "release"})
    exp("G7 C-c1×B_RHQ", U("B_RHQ"),       [c1], [], {c1: "withhold"})  # R1 발화
    exp("G8 C-c1×F_SAL", U("F_SAL"),       [c1], [], {c1: "withhold"})
    exp("G9 C-c1×B_BR",  U("B_BR"),        [c1], [], {c1: "release"})   # skip
    exp("G10 C-c쌍×B_RHQ", U("B_RHQ"), [c1, c2], [], {c1: "withhold", c2: "withhold"})
    exp("G11 C-c쌍×B_BR",  U("B_BR"),  [c1, c2], [], {c1: "release", c2: "release"})
    exp("G12 SAR×F_CMP", U("F_CMP"), [SAR[0]], [], {SAR[0]: "release"})
    exp("G13 SAR×S_ACC", U("S_ACC"), [SAR[0]], [], {SAR[0]: "withhold"})
    exp("G14 SAR×H_HR",  U("H_HR"),  [SAR[1]], [], {SAR[1]: "withhold"})
    # 세션 누적 (원장 주입 — 승인 경위 가정 명시)
    team_er = "G08-00646"  # 컴플라이언스팀 ER t2 (n=3) — 실행 시 fid 검증
    ind_er = None          # E0027 ER t3 — 게이트 초기화에서 탐색
    for f in FRAGS.values():
        if f["attr"] == "ER" and f["tier"] == 2 and f["ids"] and "E_F_CMP" in f["ids"] and f["n"] == 3:
            team_er = f["fid"]
        if f["attr"] == "ER" and f["tier"] == 3 and f["sid"] == "E0027":
            ind_er = f["fid"]
    assert ind_er, "게이트 준비 실패: E0027 ER t3 조각 미발견"
    # R2-diff 고유 발화 영역 = △ < k ≤ n (k=5면 n=3<k라 R1이 선점 — 심층 방어의 실물).
    # 팀 n=3, △=2 → k=3에서 R1 침묵(3<3 거짓)·R2-diff 발화. [코퍼스 실측 발견 — 논문 반영]
    exp("G15 세션diff F_SEC", U("F_SEC"), [team_er], [ind_er], {team_er: "withhold"}, k=3)
    exp("G16 G15교환",        U("F_SEC"), [ind_er], [team_er], {ind_er: "withhold"}, k=3)  # R3 — 불변식 유지
    exp("G17a join(R1on)",  U("B_RHQ"), [c1], [c2], {c1: "withhold"})
    exp("G17b join(R1off)", U("B_RHQ"), [c1], [c2], {c1: "withhold"}, use_r1=False)   # R2-join 단독
    # 음성 대조군
    neg = [f["fid"] for f in FRAGS.values() if f["attr"] == "ER" and f["tier"] == 2
           and f["ids"] and f["n"] >= K_HEAD][:2]
    exp("G18 음성 disjoint", U("F_SEC"), [neg[0]], [neg[1]], {neg[0]: "release"})
    big_pb = [f["fid"] for f in FRAGS.values() if f["attr"] == "PB" and f["tier"] == 2
              and f["n"] >= K_HEAD][:2]
    exp("G19 음성 2턴 PB", U("F_PAY"), [big_pb[0]], [big_pb[1]], {big_pb[0]: "release"})
    # 판정 규칙 정밀 단언 (행동뿐 아니라 어느 규칙이 잡았는지)
    want_rules = {"G7 C-c1×B_RHQ": "R1", "G8 C-c1×F_SAL": "R1",
                  "G15 세션diff F_SEC": "R2-diff", "G16 G15교환": "R3",
                  "G17a join(R1on)": "R1", "G17b join(R1off)": "R2-join",
                  "G5 C-b×동료": "R3", "G13 SAR×S_ACC": "R3"}
    allok = True
    print("=" * 78); print("기동 게이트 — 카나리아 기대 판정표 자가 검증")
    for cid, ok, got, rules, want, verrs in G:
        wr = want_rules.get(cid)
        rok = True
        if wr:
            tgt = [fid for fid in got if got[fid] == "withhold"] or list(got)
            rok = any(rules[t] == wr for t in tgt)
        mark = "PASS" if (ok and rok) else "FAIL"
        allok &= (ok and rok)
        print(f"  [{mark}] {cid:24s} got={got} rule={rules}" + (f" verrs={verrs}" if verrs else ""))
    print(f"게이트 판정: {'전 칸 PASS' if allok else '실패 — 중단'}")
    if not allok:
        sys.exit(1)
    return True

if __name__ == "__main__":
    print(f"frag-set hash = {FRAGSET_HASH} · 조각 {len(FRAGS)} · 격자 {len(CELLS)}칸 · k_head={K_HEAD}")
    gate()
    if "--gate-only" in sys.argv:
        sys.exit(0)
    import importlib.util
    spec = importlib.util.spec_from_file_location("ev", os.path.join(HERE, "eval06.py"))
    ev = importlib.util.module_from_spec(spec); spec.loader.exec_module(ev)
    ev.main(sys.modules[__name__])
