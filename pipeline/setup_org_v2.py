# -*- coding: utf-8 -*-
"""
FinDW-Bench 조직·인사 구축 v2 — ★위상은 우리 정의, 값은 실데이터★

v1 대비 변경:
  1. dim_employee 값을 **MySQL Employees 표본 DB**에서 표집 (CC BY-SA 3.0)
     — 이름·성별·생년·입사일이 합성에서 공개 실데이터로 교체
  2. fact_payroll을 **salaries 실제 급여 이력**으로 교체
     — v1의 임의 로그정규 파라미터 12개(`SPEC` 딕셔너리) 전량 제거
  3. ★직급은 조직 슬롯이 결정하고, 급여는 분위 매칭으로 실데이터에서 가져온다★
     → rank-monotone 급여가 '검증 대상'에서 '구성상 참'으로 바뀜
  4. ★bonus(성과급) 삭제★ — 원천이 없는 임의 생성값이었음.
     canary C-a와 골드보고서 G4는 급여기본(base_salary) t3로 이전한다.
  5. dim_employee.role_id 신설 — v1은 역할↔직원 매핑이 코드 상수(PERSONA 딕셔너리)에만
     존재했다. 16 페르소나를 DB에 명시한다.

위상(우리 정의)은 유지:
  Berka 접지  district 77 → 지점 77 · region 8 → 지역본부 8
  본점 계층    부문 > 부 > 팀   (공시 조직도 기반)
  직급 5단+1   팀원 · 팀장 · 부서장 · 본부장 · 부문장 · 행장

배정 원칙 — 랜덤이 아니라 **층화**:
  결정론적 고정: 16 페르소나 위치 · 컴플라이언스팀 정확히 3인 (canary C-b 조건)
  층화 랜덤    : 나머지 인원을 조직 레벨별 정원 안에서만 (seed 고정)

실행: python setup_org_v2.py            (bootstrap_findw_v2.py 이후)
사전: emp_csv/employees.csv · emp_csv/salaries.csv  (MySQL 덤프 → CSV 변환본)
"""
import sys, argparse, datetime as dt
import numpy as np
import duckdb

SEED = 42
ap = argparse.ArgumentParser()
ap.add_argument("--db", default="findw.duckdb")
ap.add_argument("--emp-csv", default="emp_csv")
ap.add_argument("--headcount", type=int, default=595)
args = ap.parse_args()

import findw_result as R                 # 결과 기록 모듈 (같은 폴더에 필요)
R.start("02_org", args.db)

rng = np.random.default_rng(SEED)
con = duckdb.connect(args.db)
def step(m): print(f"\n[D2-v2] {m}")
def ok_(b): return "OK" if b else "FAIL"
allok = True

# ── 0. 스키마 v2 (Layer 2 재정의: role_id 추가 / bonus 제거) ─────────────────
step("스키마 v2 — dim_employee.role_id 신설 · fact_payroll.bonus 제거")
con.execute("DROP TABLE IF EXISTS fact_payroll")
con.execute("DROP TABLE IF EXISTS trust_signal")
con.execute("DROP TABLE IF EXISTS dim_employee")
con.execute("DROP TABLE IF EXISTS dim_org")
con.execute("""CREATE TABLE dim_org(
  org_id INT PRIMARY KEY, org_name VARCHAR, org_level VARCHAR,
  parent_id INT, org_path VARCHAR, district_id INT)""")
con.execute("""CREATE TABLE dim_employee(
  emp_id VARCHAR PRIMARY KEY,
  src_emp_no INT,                  -- MySQL employees.emp_no (출처 추적)
  role_id VARCHAR,                 -- 16 평가 페르소나만 non-NULL
  name VARCHAR, gender VARCHAR, birth_date DATE, hire_date DATE,
  org_id INT)                      -- rank 없음: 조직 노드가 범위를 결정한다""")
con.execute("""CREATE TABLE fact_payroll(          -- bonus 없음 (v2에서 삭제)
  emp_id VARCHAR, pay_month DATE, base_salary DOUBLE,
  PRIMARY KEY(emp_id, pay_month))""")
con.execute("""CREATE TABLE trust_signal(
  emp_id VARCHAR, signal_date DATE, logon_cnt INT, offhour_cnt INT,
  file_access_cnt INT, uts DOUBLE)""")

# ── 1. dim_org — 위상은 우리 정의, 지점·지역은 Berka 접지 ────────────────────
step("dim_org 구축 (본점 계층 = 우리 정의 / 지점 77·지역본부 8 = Berka 접지)")
rows, _oid = [], [0]
def add(name, level, parent, district=None):
    _oid[0] += 1
    ppath = next((r[4] for r in rows if r[0] == parent), "") if parent else ""
    rows.append((_oid[0], name, level, parent, f"{ppath}/{name}", district))
    return _oid[0]

root   = add("은행", "root", None)
g_fin  = add("재무지원부문", "group", root)
d_sus  = add("수신기획부", "dept", g_fin);  t_sus = add("수신팀", "team", d_sus); add("수신기획팀", "team", d_sus)
d_hr   = add("인사부", "dept", g_fin);      t_hro = add("인사운영팀", "team", d_hr); t_pay = add("급여팀", "team", d_hr)
d_fin  = add("재무기획부", "dept", g_fin);  t_acc = add("회계팀", "team", d_fin)
g_plan = add("전략기획부문", "group", root); d_pl = add("종합기획부", "dept", g_plan); add("기획팀", "team", d_pl)
g_risk = add("리스크관리부문", "group", root); d_rk = add("리스크관리부", "dept", g_risk); add("신용리스크팀", "team", d_rk)
g_biz  = add("영업본부", "group", root);    d_sal = add("영업부", "dept", g_biz); t_sal = add("영업관리팀", "team", d_sal)
d_cc   = add("고객센터", "dept", g_biz);    t_cc  = add("고객상담팀", "team", d_cc)
l_comp = add("준법감시인", "line", root);   d_cmp = add("윤리준법부", "dept", l_comp); t_cmp = add("컴플라이언스팀", "team", d_cmp)
l_ciso = add("정보보호최고책임자", "line", root); d_sec = add("정보보호부", "dept", l_ciso); t_sec = add("보안관제팀", "team", d_sec)
g_it   = add("IT본부", "group", root);      d_it = add("IT기획부", "dept", g_it); t_dw = add("DW팀", "team", d_it)

regions = [r[0] for r in con.execute("SELECT DISTINCT region FROM district ORDER BY 1").fetchall()]
first_branch = {}
for reg in regions:
    rh = add(f"{reg}지역본부", "regionhq", root)
    for i, (did, dname) in enumerate(con.execute(
            "SELECT district_id, name FROM district WHERE region=? ORDER BY district_id", [reg]).fetchall()):
        b = add(f"{dname}지점", "branch", rh, district=did)
        if i == 0: first_branch[reg] = (rh, b)
con.executemany("INSERT INTO dim_org VALUES (?,?,?,?,?,?)", rows)
n_br = con.execute("SELECT count(*) FROM dim_org WHERE org_level='branch'").fetchone()[0]
allok &= (n_br == 77)
print(f"  노드 {len(rows)}개 · 지점 {n_br} {ok_(n_br == 77)} · 지역본부 {len(regions)}")

# ── 2. 노드 점유 정원 — 직급 축 없음 ────────────────────────────────────────
step("노드 점유 정원 산출 (rank 축 삭제 — 조직 노드가 범위를 결정)")
# root/group/line/dept/regionhq = 1인 점유 (그 노드가 곧 그 사람의 scope_root)
# team/branch = 복수 인원
SINGLE = ("root", "group", "line", "dept", "regionhq")
slots = [oid for oid, _n, lvl, *_ in rows if lvl in SINGLE]
units  = [oid for oid, _n, lvl, *_ in rows if lvl in ("team", "branch")]
n_member = args.headcount - len(slots)
fixed = {t_cmp: 3}                    # 컴플라이언스팀 정확히 3인 (canary C-b 조건)
rest_units = [u for u in units if u not in fixed]
need = n_member - sum(fixed.values())
q, r = divmod(need, len(rest_units))
base = np.full(len(rest_units), q, dtype=int)
base[rng.permutation(len(rest_units))[:r]] += 1
assert base.sum() == need, (base.sum(), need)
alloc = dict(fixed); alloc.update(dict(zip(rest_units, base.tolist())))
for u, k in alloc.items():
    slots += [u] * int(k)
print(f"  단독 점유 노드 {len(SINGLE)}종 → {sum(1 for o,_n,l,*_ in rows if l in SINGLE)}명")
print(f"  팀·지점 {len(units)}개 → {n_member}명 (컴플라이언스팀 3인 고정)")
print(f"  총 {len(slots)}명 (목표 {args.headcount}) {ok_(len(slots) == args.headcount)}")
allok &= (len(slots) == args.headcount)

# ── 3. MySQL Employees 표집 + 급여 분위 매칭 ─────────────────────────────────
step("MySQL Employees 표집 → 급여 분위로 직급 배정")
con.execute(f"""CREATE OR REPLACE TEMP TABLE src_emp AS SELECT * FROM
  read_csv('{args.emp_csv}/employees.csv', header=false, quote='''',
    columns={{'emp_no':'INT','birth_date':'DATE','first_name':'VARCHAR',
              'last_name':'VARCHAR','gender':'VARCHAR','hire_date':'DATE'}})""")
con.execute(f"""CREATE OR REPLACE TEMP TABLE src_sal AS SELECT * FROM
  read_csv('{args.emp_csv}/salaries.csv', header=false, quote='''',
    columns={{'emp_no':'INT','salary':'INT','from_date':'DATE','to_date':'DATE'}})""")
ns = con.execute("SELECT count(*) FROM src_emp").fetchone()[0]
nsal = con.execute("SELECT count(*) FROM src_sal").fetchone()[0]
print(f"  원천: employees {ns:,} · salaries {nsal:,}")
allok &= (ns == 300024 and nsal == 2844047)
print(f"  공표 행수 대조 {ok_(ns == 300024 and nsal == 2844047)}")

# 표집: 595명을 무작위 추출 후 **그 표본 안에서** 분위를 자른다.
# (300k 전체에서 상위 분위를 뽑으면 상급 직급 급여가 최고액에 몰려 분산이 사라진다)
con.execute(f"""CREATE OR REPLACE TEMP TABLE samp AS
  SELECT e.*, s.last_salary FROM src_emp e JOIN (
    SELECT emp_no, arg_max(salary, from_date) AS last_salary FROM src_sal GROUP BY 1
  ) s USING(emp_no)
  USING SAMPLE {args.headcount} ROWS (reservoir, {SEED})""")
n = con.execute("SELECT count(*) FROM samp").fetchone()[0]
print(f"  표집 {n}명 {ok_(n == args.headcount)}"); allok &= (n == args.headcount)

# ★급여-조직 무결합★ 급여로 직급을 정하지 않는다. 어떤 평가 성질도 급여 크기에
# 의존하지 않으므로(판정 입력은 role·attr·tier·srel), 무관한 두 원천을 결합하지 않는다.
samp = con.execute("SELECT emp_no, first_name, last_name, gender, birth_date, hire_date,"
                   " last_salary FROM samp").fetchall()
rng.shuffle(samp)
assert len(samp) == len(slots)

# ── 4. 페르소나 16종 고정 배치 (층화의 결정론적 부분) ────────────────────────
reg0 = regions[0]; rh0, br0 = first_branch[reg0]
PERSONA = [                       # (role_id, org_id, 설명) — 노드 하나가 역할 하나
    ("H_HRO",  t_hro,  "인사운영팀"),
    ("H_HR",   d_hr,   "인사부 (부 단위)"),
    ("H_GRP",  g_fin,  "재무지원부문 (부문 단위)"),
    ("S_DEP",  t_sus,  "수신팀"),
    ("S_DIV",  d_sus,  "수신기획부 (부 단위)"),
    ("S_ACC",  t_acc,  "회계팀"),
    ("B_BR",   br0,    "지점"),
    ("B_RHQ",  rh0,    "지역본부"),
    ("C_CC",   t_cc,   "고객상담팀"),
    ("F_SAL",  t_sal,  "본부 영업부 (기능라인)"),
    ("F_PAY",  t_pay,  "급여팀 (기능라인)"),
    ("F_CMP",  t_cmp,  "컴플라이언스팀 (감독라인)"),
    ("F_SEC",  t_sec,  "정보보호부 (감독라인)"),
    ("F_DW",   t_dw,   "DW팀 (관리무열람)"),
]
step(f"페르소나 {len(PERSONA)}종 고정 배치 + 나머지 층화 배정")

# 페르소나가 요구하는 슬롯을 먼저 예약
emps, used = [], set()
def take_slot(org_id):
    for i, o in enumerate(slots):
        if i not in used and o == org_id:
            used.add(i); return i
    return None
persona_slot = {}
for rid, oid, desc in PERSONA:
    i = take_slot(oid)
    if i is None: sys.exit(f"[중단] 페르소나 {rid}({desc}) 슬롯 없음 — org_id={oid}")
    persona_slot[rid] = i

# 급여 내림차순 표본을 직급 서열대로 슬롯에 대응 (i번째 슬롯 ↔ i번째 표본)
for i, oid in enumerate(slots):
    e = samp[i]
    rid = next((r for r, s in persona_slot.items() if s == i), None)
    emps.append((f"E_{rid}" if rid else f"E{i:04d}", e[0], rid,
                 f"{e[1]} {e[2]}", e[3], e[4], e[5], oid))
con.executemany("INSERT INTO dim_employee VALUES (?,?,?,?,?,?,?,?)", emps)
print(f"  직원 {len(emps)}명 (페르소나 {len(PERSONA)} · 나머지 {len(emps)-len(PERSONA)})")

# ── 5. fact_payroll — 실제 급여 이력 (bonus 없음) ────────────────────────────
step("fact_payroll — salaries 실제 이력 적재 (bonus 삭제)")
con.execute("""CREATE OR REPLACE TEMP TABLE map AS
  SELECT emp_id, src_emp_no FROM dim_employee""")
# 2018년 12개월 그리드 × 직원. 해당 월에 유효한 급여 레코드가 있으면 그 값,
# 없으면(퇴직자 등 기간 미포함) 그 직원의 최종 급여를 사용한다.
con.execute("""CREATE OR REPLACE TEMP TABLE last_sal AS
  SELECT emp_no, arg_max(salary, from_date) AS last_salary FROM src_sal GROUP BY 1""")
con.execute("""CREATE OR REPLACE TEMP TABLE grid AS
  SELECT m.emp_id, m.src_emp_no, d.mo::DATE AS pay_month
  FROM map m CROSS JOIN (SELECT unnest(generate_series(
       DATE '2018-01-01', DATE '2018-12-01', INTERVAL 1 MONTH)) AS mo) d""")
con.execute("""CREATE OR REPLACE TEMP TABLE eff AS
  SELECT g.emp_id, g.pay_month, s.salary,
         row_number() OVER (PARTITION BY g.emp_id, g.pay_month ORDER BY s.from_date DESC) rn
  FROM grid g JOIN src_sal s ON s.emp_no = g.src_emp_no
  WHERE g.pay_month >= s.from_date AND g.pay_month < s.to_date""")
con.execute("""INSERT INTO fact_payroll
  SELECT g.emp_id, g.pay_month,
         coalesce(e.salary, l.last_salary)
  FROM grid g
  LEFT JOIN (SELECT emp_id, pay_month, salary FROM eff WHERE rn = 1) e
         ON e.emp_id = g.emp_id AND e.pay_month = g.pay_month
  JOIN last_sal l ON l.emp_no = g.src_emp_no""")
npay = con.execute("SELECT count(*) FROM fact_payroll").fetchone()[0]
ncov = con.execute("SELECT count(*) FROM eff WHERE rn=1").fetchone()[0]
print(f"  급여 {npay:,}행 (기대 {args.headcount * 12:,})")
print(f"    실제 이력 적용 {ncov:,}행 · 최종급여 투영 {npay - ncov:,}행 (퇴직자 기간 미포함분)")
allok &= (npay == args.headcount * 12)

# ── 6. trust_signal — CERT 지표 분류만 차용, 값은 합성 (v1과 동일·정직 서술) ─
step("trust_signal (CERT 지표 분류 차용 · 값은 합성)")
ts = []
for (eid, *_r) in con.execute("SELECT emp_id FROM dim_employee").fetchall():
    off_prone = rng.random() < 0.12
    for m in range(1, 13):
        logon = int(rng.poisson(22)); off = int(rng.poisson(6 if off_prone else 1))
        fa = int(rng.poisson(120))
        uts = float(np.clip(1.0 - 0.06 * off / max(logon, 1) * 10 - 0.001 * max(fa - 200, 0), 0.1, 1.0))
        ts.append((eid, dt.date(2018, m, 1), logon, off, fa, round(uts, 3)))
con.executemany("INSERT INTO trust_signal VALUES (?,?,?,?,?,?)", ts)
print(f"  신호 {len(ts):,}행")

# ── 7. 검증 ──────────────────────────────────────────────────────────────────
step("검증 1/4: rank 축 삭제 · 급여-조직 무결합 확인")
n = con.execute("""SELECT count(*) FROM information_schema.columns
                   WHERE table_name='dim_employee' AND column_name='rank'""").fetchone()[0]
allok &= (n == 0); print(f"  rank 컬럼 잔존: {n} {ok_(n == 0)}")
lv = con.execute("""SELECT o.org_level, count(*) c, median(p.base_salary) m
  FROM dim_employee e JOIN dim_org o USING(org_id)
  JOIN fact_payroll p USING(emp_id) WHERE p.pay_month='2018-01-01'
  GROUP BY 1 ORDER BY 3 DESC""").fetchall()
print("  조직 레벨별 급여 중앙값 (결합하지 않았으므로 순서는 임의):")
for l, cn, m in lv: print(f"    {l:9s} {cn:4d}명  {m:>10,.0f}")

step("검증 2/4: canary C-b 조건 (컴플라이언스팀 = 3인)")
n = con.execute("""SELECT count(*) FROM dim_employee e JOIN dim_org o USING(org_id)
                   WHERE o.org_name='컴플라이언스팀'""").fetchone()[0]
allok &= (n == 3); print(f"  컴플라이언스팀 {n}인 {ok_(n == 3)}")

step("검증 3/4: 페르소나 배치")
pr = con.execute("""SELECT e.role_id, o.org_level, o.org_path FROM dim_employee e
  JOIN dim_org o USING(org_id) WHERE e.role_id IS NOT NULL ORDER BY e.role_id""").fetchall()
allok &= (len(pr) == len(PERSONA))
print(f"  배치 {len(pr)}/{len(PERSONA)} {ok_(len(pr) == len(PERSONA))}")
for rid, lvl, path in pr: print(f"    {rid:8s} {lvl:9s} {path}")

step("검증 4/4: FK · 급여 결측")
for lbl, q in [
    ("직원→조직 고아", "SELECT count(*) FROM dim_employee e LEFT JOIN dim_org o USING(org_id) WHERE o.org_id IS NULL"),
    ("급여 없는 직원", "SELECT count(*) FROM dim_employee e LEFT JOIN fact_payroll p USING(emp_id) WHERE p.emp_id IS NULL"),
    ("bonus 컬럼 잔존", "SELECT count(*) FROM information_schema.columns WHERE table_name='fact_payroll' AND column_name='bonus'"),
]:
    n = con.execute(q).fetchone()[0]; allok &= (n == 0)
    print(f"  {lbl:16s}: {n} {ok_(n == 0)}")

con.close()
step("✅ 완료 — 다음: policy_cell(basis 배정표) + build_reports_v2" if allok else "❌ 검증 실패")
R.finish(allok)
sys.exit(0 if allok else 1)
