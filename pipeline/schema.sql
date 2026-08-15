-- ============================================================
-- FinDW-Bench Schema v0.1  (규정집 policy_spec v1.0 준거)
-- Layer 1: Berka 원본 (실데이터) / Layer 2: 조직·급여 (CERT+합성)
-- Layer 3: 거버넌스 (정책·조각·canary) — 본 연구의 기여 레이어
-- ============================================================

-- ---------- Layer 1: Berka core (real anonymized bank data) ----------
CREATE TABLE district(  -- 77 rows → 지점(branch)으로 재해석
  district_id INT PRIMARY KEY, name VARCHAR, region VARCHAR,
  population INT, muni_lt500 INT, muni_500_2k INT, muni_2k_10k INT, muni_gt10k INT,
  n_cities INT, ratio_urban DOUBLE, avg_salary DOUBLE,
  unemp95 DOUBLE, unemp96 DOUBLE, entrepreneurs_per_1k INT, crimes95 INT, crimes96 INT);

CREATE TABLE account(
  account_id INT PRIMARY KEY, district_id INT REFERENCES district(district_id),
  open_date DATE, frequency VARCHAR);

CREATE TABLE client(
  client_id INT PRIMARY KEY, birth_date DATE, gender VARCHAR,
  district_id INT REFERENCES district(district_id));

CREATE TABLE disp(
  disp_id INT PRIMARY KEY, client_id INT REFERENCES client(client_id),
  account_id INT REFERENCES account(account_id), type VARCHAR);

CREATE TABLE loan(
  loan_id INT PRIMARY KEY, account_id INT REFERENCES account(account_id),
  grant_date DATE, amount DOUBLE, duration INT, payments DOUBLE, status VARCHAR);

CREATE TABLE card(
  card_id INT PRIMARY KEY, disp_id INT REFERENCES disp(disp_id),
  type VARCHAR, issue_date DATE);

CREATE TABLE pay_order(
  order_id INT PRIMARY KEY, account_id INT REFERENCES account(account_id),
  bank_to VARCHAR, account_to VARCHAR, amount DOUBLE, k_symbol VARCHAR);

CREATE TABLE trans(
  trans_id INT PRIMARY KEY, account_id INT REFERENCES account(account_id),
  t_date DATE, amount DOUBLE, balance DOUBLE, t_type VARCHAR,
  operation VARCHAR, k_symbol VARCHAR, bank VARCHAR, account_partner VARCHAR);

-- ---------- Layer 2: 조직·직원·급여 (CERT topology + 합성) ----------
CREATE TABLE dim_org(          -- KDB 위상 재스킨: 부문>본부>부>팀 + 지역본부>지점(=district)
  org_id INT PRIMARY KEY, org_name VARCHAR, org_level VARCHAR,  -- group/division/dept/team/regionhq/branch
  parent_id INT, org_path VARCHAR,                               -- '/은행/재무지원부문/수신기획부/수신팀'
  district_id INT);                                              -- branch일 때만 (Berka 연결)

CREATE TABLE dim_employee(
  emp_id VARCHAR PRIMARY KEY, cert_user_id VARCHAR,              -- CERT r4.2 매핑
  name VARCHAR, org_id INT REFERENCES dim_org(org_id),
  rank VARCHAR,                                                  -- 팀원/팀장/부서장/본부장/부문장/부행장/행장
  hire_date DATE);

CREATE TABLE fact_payroll(     -- 합성 (공시 평균 접지, seed 고정)
  emp_id VARCHAR REFERENCES dim_employee(emp_id), pay_month DATE,
  base_salary DOUBLE, bonus DOUBLE, PRIMARY KEY(emp_id, pay_month));

CREATE TABLE trust_signal(     -- CERT 행동로그 → UTS 입력
  emp_id VARCHAR, signal_date DATE, logon_cnt INT, offhour_cnt INT,
  file_access_cnt INT, uts DOUBLE);

-- ---------- Layer 3: 거버넌스 (기여 레이어) ----------
CREATE TABLE policy_role_scope(  -- 규정집 §2.2 열 축 매트릭스
  role_id VARCHAR, attribute_group VARCHAR, max_tier INT,
  PRIMARY KEY(role_id, attribute_group));

CREATE TABLE policy_functional_line(  -- 규정집 §2.1(c) 기능·감독 라인 (닫힌 목록)
  line_id VARCHAR PRIMARY KEY, role_pattern VARCHAR,
  scope_desc VARCHAR, attribute_group VARCHAR, max_tier INT, condition VARCHAR);

CREATE TABLE gold_report(       -- 규정집 §3
  report_id VARCHAR PRIMARY KEY, title VARCHAR, tier INT,
  dept_scope VARCHAR, attribute_group VARCHAR, subject_scope VARCHAR, gen_sql VARCHAR);

CREATE TABLE report_fragment(   -- 인증 보고서 조각 (검색 대상)
  fragment_id VARCHAR PRIMARY KEY, report_id VARCHAR REFERENCES gold_report(report_id),
  period DATE, dept_scope VARCHAR, tier INT, attribute_group VARCHAR,
  subject_scope VARCHAR, subject_id VARCHAR,
  table_html VARCHAR, narrative VARCHAR, canary_flag VARCHAR);  -- NULL/C-a/C-b/C-c

CREATE TABLE query_set(         -- 평가 쿼리 (split 라벨 포함)
  query_id VARCHAR PRIMARY KEY, nl_text VARCHAR, role_id VARCHAR,
  split VARCHAR,                -- standard/paraphrase/heldout/adversarial/probe
  gt_permit BOOLEAN, gt_tier INT, gt_rule_ref VARCHAR);  -- 판정 근거 조항 (규정집 §)
