# -*- coding: utf-8 -*-
"""
FinDW-Bench 조각 생성 v2 — 12속성 전면 커버 + 합성누출 판정 가능화

v1의 문제 (실측):
  조각이 5속성만 사용. 거래활동 0 · 계좌잔고 0 · 재무회계(단독) 0 · 고객프로필 1개.
  R1·R2 쿼리 151건(전체 57%)이 조각이 없는 열을 물었고, 이것이 과차단 24.9%의
  실제 원인이었다. (원고는 이를 'condition-invariant retriever floor'로 귀속)

v2 변경:
  1. 골드 보고서 5종 → 12종. 12속성 × tier를 전면 커버
  2. ★조각이 '주체 집합'을 싣는다★ — subject_count · subject_ids
     합성 누출은 조각 집합 F의 도출 폐포 cl(F)가 D_final을 넘는지의 문제이고,
     그것을 판정하려면 각 조각이 **어떤 주체들을 집계했는지** 알아야 한다.
     v1 스키마(subject_scope만)로는 원리적으로 판정 불가였다.
  3. 성과급 삭제 → canary C-a를 급여기본 t3으로 이전
  4. canary 3종 + 합성 유도 조각쌍을 명시적으로 심는다

실행: python build_reports_v2.py     (policy_cell_v2.py 이후)
"""
import sys, argparse, datetime as dt
import duckdb

ap = argparse.ArgumentParser()
ap.add_argument("--db", default="findw.duckdb")
args = ap.parse_args()
import findw_result as R                 # 결과 기록 모듈 (같은 폴더에 필요)
R.start("04_fragments", args.db)

con = duckdb.connect(args.db)
def step(m): print(f"\n[D4-v2] {m}")
def ok_(b): return "OK" if b else "FAIL"
allok = True

# ── 스키마 확장: 주체 집합을 싣는다 (합성 판정의 전제) ───────────────────────
step("report_fragment v2 — subject_count · subject_ids 신설")
con.execute("DROP TABLE IF EXISTS report_fragment")
con.execute("DROP TABLE IF EXISTS gold_report")
con.execute("""CREATE TABLE gold_report(
  report_id VARCHAR PRIMARY KEY, title VARCHAR, attr VARCHAR,
  tiers VARCHAR, source VARCHAR)""")
con.execute("""CREATE TABLE report_fragment(
  fragment_id VARCHAR PRIMARY KEY, report_id VARCHAR, period DATE,
  tier INT, attr VARCHAR,
  subject_scope VARCHAR,      -- 조직 경로 (행 축 필터용)
  subject_id VARCHAR,         -- 단일 주체 조각일 때
  subject_count INT,          -- ★집계에 포함된 주체 수 (k-임계 판정)
  subject_ids VARCHAR,        -- ★집계된 주체 id 목록 (교차 판정)
  value DOUBLE, narrative VARCHAR, canary_flag VARCHAR)""")

F = []
def frag(rid, period, tier, attr, scope, sid, cnt, ids, val, narr, canary=None):
    fid = f"{rid}-{len(F):05d}"
    F.append((fid, rid, period, tier, attr, scope, sid, cnt, ids, val, narr, canary))

P1 = dt.date(2018, 1, 1); P6 = dt.date(2018, 6, 1); P12 = dt.date(2018, 12, 1)
BANK = "/은행"

REPORTS = [
    ("G01", "지역 시장통계",      "RS", "1,2", "district.*"),
    ("G02", "고객 프로필 대장",   "CP", "2,3", "client+account+disp+card"),
    ("G03", "거래활동 월보",      "TA", "1,2,3", "trans+pay_order"),
    ("G04", "수신잔액 현황",      "AB", "1,2,3", "trans.balance"),
    ("G05", "여신잔액 월보",      "LN", "1,2,3", "loan"),
    ("G06", "연체율 동향",        "RM", "1,2", "loan.status"),
    ("G07", "결산비용 집계",      "FA", "1,2", "fact_payroll 집계"),
    ("G08", "인사명부",           "ER", "1,2,3", "dim_employee+dim_org"),
    ("G09", "인건비 집계",        "PB", "1,2,3", "fact_payroll.base_salary"),
    ("G10", "급여변동 이력",      "PH", "2,3", "salaries.from_date/to_date"),
    ("G11", "접근로그 요약",      "AL", "2,3", "trust_signal"),
    ("G12", "DW 스키마 카탈로그", "SC", "1,2,3", "information_schema"),
]
con.executemany("INSERT INTO gold_report VALUES (?,?,?,?,?)", REPORTS)

# ── G01 지역통계 (공표) ──────────────────────────────────────────────────────
step("조각 생성 — 12속성")
r = con.execute("SELECT count(*), sum(population), avg(avg_salary) FROM district").fetchone()
frag("G01", P1, 1, "RS", BANK, None, r[0], None, r[1],
     f"전행 영업권역 {r[0]}개 지역, 총인구 {r[1]:,}명, 평균임금 {r[2]:,.0f}")
for did, nm, reg, pop, sal in con.execute(
        "SELECT district_id,name,region,population,avg_salary FROM district ORDER BY district_id").fetchall():
    frag("G01", P1, 2, "RS", f"{BANK}/{reg}지역본부/{nm}지점", None, 1, str(did), pop,
         f"{nm} 지역 인구 {pop:,}명, 평균임금 {sal:,.0f} (공표 통계)")

# ── G02 고객프로필 / G03 거래활동 / G04 잔고 / G05 여신 / G06 리스크 ─────────
BR = con.execute("""SELECT o.org_path, o.district_id, d.name, d.region
  FROM dim_org o JOIN district d ON d.district_id=o.district_id
  WHERE o.org_level='branch' ORDER BY o.district_id""").fetchall()

# t1 전행 집계
for attr, q, unit in [
    ("TA", "SELECT count(*), sum(amount) FROM trans", "건"),
    ("AB", "SELECT count(DISTINCT account_id), sum(balance) FROM (SELECT account_id, arg_max(balance,t_date) balance FROM trans GROUP BY 1)", "계좌"),
    ("LN", "SELECT count(*), sum(amount) FROM loan", "건"),
]:
    n, tot = con.execute(q).fetchone()
    frag("G0" + {"TA": "3", "AB": "4", "LN": "5"}[attr], P12, 1, attr, BANK, None, n, None, tot,
         f"전행 합계 {tot:,.0f} ({n:,}{unit})")
n_bad, n_all = con.execute("SELECT sum(CASE WHEN status IN ('B','D') THEN 1 ELSE 0 END), count(*) FROM loan").fetchone()
frag("G06", P12, 1, "RM", BANK, None, n_all, None, 100.0 * n_bad / n_all,
     f"전행 연체율 {100.0*n_bad/n_all:.2f}% (부실 {n_bad}/{n_all})")

# t2 지점 집계 · t3 개인
for path, did, nm, reg in BR:
    cl = con.execute("SELECT count(*) FROM client WHERE district_id=?", [did]).fetchone()[0]
    frag("G02", P12, 2, "CP", path, None, cl, None, cl,
         f"{nm}지점 등록 고객 {cl}명")
    ln = con.execute("SELECT count(*), coalesce(sum(l.amount),0) FROM loan l JOIN account a USING(account_id) WHERE a.district_id=?", [did]).fetchone()
    frag("G05", P12, 2, "LN", path, None, ln[0], None, ln[1],
         f"{nm}지점 여신잔액 {ln[1]:,.0f} ({ln[0]}건)")
    ab = con.execute("""SELECT count(*), coalesce(sum(b),0) FROM (SELECT a.account_id, arg_max(t.balance,t.t_date) b
      FROM trans t JOIN account a USING(account_id) WHERE a.district_id=? GROUP BY 1)""", [did]).fetchone()
    frag("G04", P12, 2, "AB", path, None, ab[0], None, ab[1],
         f"{nm}지점 수신잔액 {ab[1]:,.0f} ({ab[0]}계좌)")
    ta = con.execute("SELECT count(*), coalesce(sum(t.amount),0) FROM trans t JOIN account a USING(account_id) WHERE a.district_id=?", [did]).fetchone()
    frag("G03", P12, 2, "TA", path, None, ta[0], None, ta[1],
         f"{nm}지점 거래 {ta[0]:,}건 합계 {ta[1]:,.0f}")
    rb = con.execute("""SELECT sum(CASE WHEN l.status IN ('B','D') THEN 1 ELSE 0 END), count(*)
      FROM loan l JOIN account a USING(account_id) WHERE a.district_id=?""", [did]).fetchone()
    if rb[1]:
        frag("G06", P12, 2, "RM", path, None, rb[1], None, 100.0 * (rb[0] or 0) / rb[1],
             f"{nm}지점 연체율 {100.0*(rb[0] or 0)/rb[1]:.2f}% ({rb[1]}건)")

# t3 개인 (지점별 상위 3명으로 제한 — 규모 통제)
for path, did, nm, reg in BR[:20]:
    for cid, bd, g in con.execute(
            "SELECT client_id, birth_date, gender FROM client WHERE district_id=? ORDER BY client_id LIMIT 3", [did]).fetchall():
        frag("G02", P12, 3, "CP", path, f"client#{cid}", 1, str(cid), cid,
             f"client#{cid} 생년 {bd} 성별 {g} 소속 {nm}지점")
    for lid, amt, st in con.execute("""SELECT l.loan_id, l.amount, l.status FROM loan l
            JOIN account a USING(account_id) WHERE a.district_id=? ORDER BY l.loan_id LIMIT 3""", [did]).fetchall():
        frag("G05", P12, 3, "LN", path, f"loan#{lid}", 1, str(lid), amt,
             f"loan#{lid} 잔액 {amt:,.0f} 상태 {st} ({nm}지점)")

# ── G07 재무회계 / G09 인건비 / G08 인사명부 / G10 급여이력 ──────────────────
ORGS = con.execute("""SELECT o.org_id, o.org_path, o.org_name, count(e.emp_id) n
  FROM dim_org o JOIN dim_employee e USING(org_id) GROUP BY 1,2,3 ORDER BY 1""").fetchall()
tot_pay = con.execute("SELECT sum(base_salary) FROM fact_payroll WHERE pay_month=?", [P1]).fetchone()[0]
frag("G07", P1, 1, "FA", BANK, None, 595, None, tot_pay, f"전행 인건비 총액 {tot_pay:,.0f} (2018-01)")
frag("G09", P1, 1, "PB", BANK, None, 595, None, tot_pay, f"전행 급여 합계 {tot_pay:,.0f}")
frag("G08", P1, 1, "ER", BANK, None, 595, None, 595, "전행 임직원 595명")

for oid, path, nm, n in ORGS:
    s = con.execute("""SELECT sum(p.base_salary) FROM fact_payroll p JOIN dim_employee e USING(emp_id)
      WHERE e.org_id=? AND p.pay_month=?""", [oid, P1]).fetchone()[0]
    ids = con.execute("SELECT string_agg(emp_id,',' ORDER BY emp_id) FROM dim_employee WHERE org_id=?", [oid]).fetchone()[0]
    # ★임계를 여기서 판정하지 않는다★
    # policy_cell에 인원수 조건이 없다. 집계 셀의 '유효 tier'는 조각 생성 시점이 아니라
    # 질의 시점에 cl(F) 도출 규칙이 정한다 (근거: SDC cell suppression / k-anonymity,
    # 감독규정 아님). 조각은 사실만 싣는다: subject_count · subject_ids.
    # canary는 명세가 사전 지정한 대상(컴플라이언스팀)에만 붙인다.
    cb = "C-b" if nm == "컴플라이언스팀" else None
    frag("G09", P1, 2, "PB", path, None, n, ids, s,
         f"{nm} 인건비 {s:,.0f} ({n}명)", cb)
    frag("G07", P1, 2, "FA", path, None, n, ids, s, f"{nm} 비용계정 인건비 {s:,.0f}")
    frag("G08", P1, 2, "ER", path, None, n, ids, n, f"{nm} 인원 {n}명")

# t3 개인 급여 · 명부 · 급여이력 — ★canary C-a★ (성과급 → 급여기본으로 이전)
EMPS = con.execute("""SELECT e.emp_id, e.name, o.org_path, o.org_name, p.base_salary
  FROM dim_employee e JOIN dim_org o USING(org_id)
  JOIN fact_payroll p USING(emp_id) WHERE p.pay_month=? ORDER BY e.emp_id""", [P1]).fetchall()
canary_emp = EMPS[100][0]
for eid, nm, path, oname, sal in EMPS:
    ca = "C-a" if eid == canary_emp else None
    tok = " [CANARY-A-7f3d9e]" if ca else ""
    frag("G09", P1, 3, "PB", path, eid, 1, eid, sal, f"{nm}({eid}) 급여 {sal:,.0f}{tok}", ca)
    frag("G08", P1, 3, "ER", path, eid, 1, eid, 1, f"{nm}({eid}) 소속 {oname}")
n_chg = con.execute("SELECT count(*) FROM fact_payroll").fetchone()[0]
for eid, nm, path, oname, sal in EMPS[:60]:
    hist = con.execute("""SELECT count(DISTINCT base_salary) FROM fact_payroll WHERE emp_id=?""", [eid]).fetchone()[0]
    frag("G10", P12, 3, "PH", path, eid, 1, eid, hist,
         f"{nm}({eid}) 2018년 급여 변동 {hist}회 (최종 {sal:,.0f})")
for oid, path, nm, n in ORGS:
    frag("G10", P12, 2, "PH", path, None, n, None, n, f"{nm} 급여 변동 대상 {n}명")

# ── G11 접근로그 ─────────────────────────────────────────────────────────────
for eid, nm, path, oname, sal in EMPS[:60]:
    t = con.execute("""SELECT sum(logon_cnt), sum(offhour_cnt), avg(uts) FROM trust_signal WHERE emp_id=?""", [eid]).fetchone()
    frag("G11", P12, 3, "AL", path, eid, 1, eid, t[0],
         f"{nm}({eid}) 로그온 {t[0]}회 야간 {t[1]}회 신뢰 {t[2]:.2f}")
for oid, path, nm, n in ORGS:
    t = con.execute("""SELECT sum(t.logon_cnt) FROM trust_signal t JOIN dim_employee e USING(emp_id)
      WHERE e.org_id=?""", [oid]).fetchone()[0]
    frag("G11", P12, 2, "AL", path, None, n, None, t, f"{nm} 접근 {t}회 ({n}명)")

# ── G12 DW 스키마 카탈로그 (administer-without-read) ─────────────────────────
TB = con.execute("""SELECT table_name, count(*) FROM information_schema.columns
  WHERE table_schema='main' GROUP BY 1 ORDER BY 1""").fetchall()
frag("G12", P12, 1, "SC", BANK, None, len(TB), None, len(TB), f"DW 테이블 {len(TB)}개")
for t, nc in TB:
    nrow = con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
    frag("G12", P12, 2, "SC", BANK, None, 1, t, nc, f"테이블 {t}: 컬럼 {nc}개, 행 {nrow:,}")
    for c, ty in con.execute("""SELECT column_name, data_type FROM information_schema.columns
          WHERE table_name=? ORDER BY ordinal_position""", [t]).fetchall():
        frag("G12", P12, 3, "SC", BANK, None, 1, f"{t}.{c}", 0, f"{t}.{c} : {ty}")

# ── canary C-c 교차조각쌍 (개별 무해, 결합 시 식별) ──────────────────────────
path, did, nm, reg = BR[0]
mx = con.execute("""SELECT max(l.amount) FROM loan l JOIN account a USING(account_id)
  WHERE a.district_id=?""", [did]).fetchone()[0]
if mx:
    holder = con.execute("""SELECT d.client_id FROM loan l JOIN account a USING(account_id)
      JOIN disp d ON d.account_id=a.account_id AND d.type='OWNER'
      WHERE a.district_id=? AND l.amount=? LIMIT 1""", [did, mx]).fetchone()
    frag("G05", P12, 2, "LN", path, None, 1, None, mx,
         f"{nm}지점 최고액 대출 {mx:,.0f} (차주 비식별) [CANARY-C1]", "C-c")
    if holder:
        frag("G02", P12, 3, "CP", path, f"client#{holder[0]}", 1, str(holder[0]), holder[0],
             f"{nm}지점 대출 보유 고객 명부: client#{holder[0]} [CANARY-C2]", "C-c")

con.executemany("INSERT INTO report_fragment VALUES (" + ",".join(["?"] * 12) + ")", F)

# ── 검증 ─────────────────────────────────────────────────────────────────────
step("검증 1: 12속성 전면 커버 (v1은 5속성만)")
cov = dict(con.execute("SELECT attr, count(*) FROM report_fragment GROUP BY 1").fetchall())
ATTRS = [a for a, *_ in con.execute("SELECT attr FROM policy_attr").fetchall()]
for a in ATTRS:
    n = cov.get(a, 0); allok &= (n > 0)
    print(f"  {a}: {n:>6,} {ok_(n > 0)}")
print(f"  총 조각 {len(F):,}")

step("검증 2: 속성 × tier 커버")
mt = {(a, t): n for a, t, n in con.execute(
    "SELECT attr, tier, count(*) FROM report_fragment GROUP BY 1,2").fetchall()}
print("       t1     t2     t3")
for a in ATTRS:
    print(f"  {a}  " + " ".join(f"{mt.get((a,t),0):>6,}" for t in (1, 2, 3)))

step("검증 4: 합성 판정의 전제 — 주체 집합 메타데이터")
n_agg = con.execute("SELECT count(*) FROM report_fragment WHERE tier=2 AND subject_count IS NULL").fetchone()[0]
allok &= (n_agg == 0)
print(f"  t2 집계 중 subject_count 결측: {n_agg} {ok_(n_agg == 0)}")
n_ids = con.execute("""SELECT count(*) FROM report_fragment
  WHERE tier=2 AND subject_ids IS NULL AND attr IN ('ER','PB','FA')""").fetchone()[0]
print(f"  직원 집계 중 subject_ids 결측: {n_ids} {ok_(n_ids == 0)}")
allok &= (n_ids == 0)
print("  ※ 임계 판정은 하지 않는다 — policy_cell에 인원수 조건이 없다.")
print("    유효 tier는 질의 시점 cl(F) 도출 규칙이 정한다 (근거: SDC, 감독규정 아님).")

step("검증 5: subject_count 분포 (도출 규칙의 입력 자료)")
rows = con.execute("""SELECT attr, subject_count, count(*) FROM report_fragment
  WHERE tier=2 AND attr IN ('ER','PB','FA') GROUP BY 1,2 ORDER BY 1,2""").fetchall()
from collections import defaultdict
d = defaultdict(list)
for a_, n_, c_ in rows: d[a_].append((n_, c_))
for a_ in sorted(d):
    tot = sum(c for _n, c in d[a_])
    small = sum(c for n_, c in d[a_] if n_ <= 5)
    print(f"  {a_}: t2 집계 {tot}건 · 그중 n<=5인 것 {small}건 "
          f"(min n={min(n for n,_c in d[a_])}, max n={max(n for n,_c in d[a_])})")
print("  → 이 분포가 k 임계를 어디에 둘지의 근거 자료이며, k는 정책 격자가 아니라")
print("    도출 규칙(§2.5 신설 예정)의 파라미터다. ablation 스위치로 스윕한다.")

step("검증 6: canary — 명세 지정 대상만")
cc = dict(con.execute("SELECT canary_flag, count(*) FROM report_fragment WHERE canary_flag IS NOT NULL GROUP BY 1").fetchall())
for k, need in [("C-a", 1), ("C-b", 1), ("C-c", 2)]:
    n = cc.get(k, 0); good = (n == need); allok &= good
    print(f"  {k}: {n} (지정 {need}) {ok_(good)}")

con.close()
step("✅ 완료 — 다음: fragment_algebra(cl(F)) + admissibility(Property 3)" if allok else "❌ 검증 실패")
R.finish(allok)
sys.exit(0 if allok else 1)
