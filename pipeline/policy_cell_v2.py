# -*- coding: utf-8 -*-
"""
FinDW-Bench 정책 격자 v2 — basis-typed 배정표 + 부분순서 정적 검증

v1 대비 근본 변경:
  v1: policy_role_scope(role_id, attribute_group, max_tier)          — basis 없음
  v2: policy_cell(role_id, attr, max_tier, basis, clause)            — ★basis 신설★

  basis = 그 칸의 권한이 **어디서 오는가**. 상속 여부가 basis의 성질이다.
    hierarchy   서브트리 상속 O.  범위 = subtree(scope_root(role))
    functional  역할 전용, 조직 무관, 상속 X (기능·감독 라인)
    ownership   본인 레코드만. **주체가 직원인 속성에만 정의됨**
    public      공표 데이터 — 전 역할 동일
    (미열거)    deny

v1 명세 오류 두 건 정정:
  (1) "인사부장은 전 직원 급여 = 계층 권위" → 인사부의 scope_root는 인사부뿐이다.
      전행 급여는 **인사 기능라인**에서만 나온다 → basis=functional
  (2) ownership이 속성 무관하게 t3를 주던 구멍(v1 judge: `if srel=="own": return True,3`)
      → ownership은 주체가 직원인 4속성(인사명부·급여기본·급여이력·접근로그)에만 정의

축 삭제: rank (조직 노드와 중복 — 명세가 직급으로 열을 넓히지 않음)
축 추가: org_rel ∈ {self, in_subtree, outside} (판정층 입력)

실행: python policy_cell_v2.py     (setup_org_v2.py 이후)
"""
import sys, argparse, itertools
import duckdb

ap = argparse.ArgumentParser()
ap.add_argument("--db", default="findw.duckdb")
args = ap.parse_args()
import findw_result as R                 # 결과 기록 모듈 (같은 폴더에 필요)
R.start("03_policy", args.db)

con = duckdb.connect(args.db)
def step(m): print(f"\n[D3-v2] {m}")
def ok_(b): return "OK" if b else "FAIL"
allok = True

# ── 속성 12종 — 창고 스키마에서 도출 (주체 · 규율규범 · 관장부서 동치분할) ────
ATTRS = [
    # (코드, 이름, 주체유형, 원천)
    ("RS", "지역통계",   "지역",   "district.* (공표 통계)"),
    ("CP", "고객프로필", "고객",   "client + account + disp + card"),
    ("TA", "거래활동",   "고객",   "trans(amount·operation·k_symbol) + pay_order"),
    ("AB", "계좌잔고",   "고객",   "trans.balance"),
    ("LN", "여신",       "고객",   "loan(amount·duration·payments)"),
    ("RM", "리스크지표", "고객",   "loan.status 파생"),
    ("FA", "재무회계",   "조직",   "집계 파생 (원천 테이블 없음)"),
    ("ER", "인사명부",   "직원",   "dim_employee + dim_org"),
    ("PB", "급여기본",   "직원",   "fact_payroll.base_salary"),
    ("PH", "급여이력",   "직원",   "salaries.from_date/to_date"),
    ("AL", "접근로그",   "직원",   "trust_signal.*"),
    ("SC", "스키마",     "시스템", "information_schema (테이블 아님)"),
]
# ★소유권은 데이터의 성질이 아니라 (역할, 속성) 칸의 명세 선택이다★
# "주체가 나면 내가 볼 수 있다"는 규칙이 아니다. 반례:
#   · 성과평가 — 주체는 나이지만 상급자가 작성한 통제 기록이므로 피평가자에게 비공개
#   · SAR(의심거래보고) — 주체는 고객이지만 존재 자체를 알릴 수 없음 [FFIEC p.75]
#   · 314(a) 요청 — 대상자 명단 공유 금지 [FFIEC p.94]
#   · 접근로그·행동신호 — 보안 기능이 나를 평가한 위험 점수. 본인이 보면 지표 역공학·회피 가능
# 근거: 부여 = PIPA 35 / GDPR 15(열람권) · 부인 = GDPR 15 예외(내부 평가·조사) + FFIEC
SELF_READABLE = {"ER", "PB", "PH"}          # 소유권 부여 — 본인 열람이 권리인 속성
SUBJECT_DENIED = {"AL"}                     # 소유권 부인 — 주체여도 볼 수 없는 속성

# ── 배정표 — 미열거 칸은 deny 기본값 ────────────────────────────────────────
# (role, attr): (max_tier, basis, clause)
H = "hierarchy"; F = "functional"; O = "ownership"; P = "public"
GRANTS = {}

# 공표 데이터: 전 역할 동일 (정책이 '열린 것'도 명시한다는 바닥 사례)
ROLES = ["H_HRO","H_HR","H_GRP","S_DEP","S_DIV","S_ACC","B_BR","B_RHQ",
         "C_CC","F_SAL","F_PAY","F_CMP","F_SEC","F_DW"]
for r in ROLES:
    GRANTS[(r,"RS")] = (2, P, "§2.4-공표")

# ownership: 명세가 '본인 열람이 권리'라고 선언한 속성에만 부여
for r in ROLES:
    for a in SELF_READABLE:
        GRANTS[(r,a)] = (3, O, "§2.1b-소유권(PIPA35/GDPR15)")
# SUBJECT_DENIED 속성은 아무 칸도 만들지 않는다 = 주체 자신도 deny

# 지역 라인 — hierarchy가 실제로 상속되는 유일한 계통
for a in ("CP","TA","AB","LN"):
    GRANTS[("B_BR",a)] = (3, H, "§2.1a-계층권위")       # 자기 지점 고객 개인 단위
    GRANTS[("B_RHQ",a)] = (2, H, "§2.1a-계층권위")      # 지역 전체이지만 단위 집계까지
GRANTS[("B_BR","RM")]  = (2, H, "§2.1a-계층권위")
GRANTS[("B_RHQ","RM")] = (2, H, "§2.1a-계층권위")
for r in ("B_BR","B_RHQ"):
    GRANTS[(r,"ER")] = (3, H, "§2.1a-계층권위")         # 자기 서브트리 명부

# 본점 관리 계통 — 자기 서브트리 명부만. 업무 열은 직무가 연다.
for r in ("H_HRO","H_HR","H_GRP","S_DEP","S_DIV","S_ACC","C_CC","F_SAL","F_PAY","F_CMP","F_SEC"):
    GRANTS[(r,"ER")] = (3, H, "§2.1a-계층권위")

# 기능·감독 라인 (조직 무관, 상속 X)
GRANTS[("C_CC","CP")]  = (3, F, "§2.1c-FL0-고객접점")   # 콜센터: 전행 고객 프로필
GRANTS[("C_CC","TA")]  = (3, F, "§2.1c-FL0-고객접점")   # 거래내역까지
#   ★C_CC의 계좌잔고는 열지 않는다 — 기능라인이 열을 '좁게' 여는 사례
GRANTS[("S_DEP","AB")] = (1, F, "§2.1c-FL7-수신기획")   # 전행 수신 집계 (상품기획)
GRANTS[("S_DIV","AB")] = (1, F, "§2.1c-FL7-수신기획")
GRANTS[("S_DIV","RM")] = (1, F, "§2.1c-FL7-수신기획")
GRANTS[("F_SAL","LN")] = (2, F, "§2.1c-FL1-실적관장")   # 전 지점 실적, 개별 고객 X
GRANTS[("F_SAL","AB")] = (2, F, "§2.1c-FL1-실적관장")
GRANTS[("F_SAL","RM")] = (2, F, "§2.1c-FL1-실적관장")
GRANTS[("S_ACC","FA")] = (3, F, "§2.1c-FL8-재무회계")   # 결산 소관
GRANTS[("S_ACC","RM")] = (2, F, "§2.1c-FL8-재무회계")
GRANTS[("H_HR","PB")]  = (3, F, "§2.1c-FL2-인사라인")   # ★정정★ 계층 아님, 인사 기능라인
GRANTS[("H_HR","PH")]  = (3, F, "§2.1c-FL2-인사라인")
GRANTS[("H_HR","ER")]  = (3, F, "§2.1c-FL2-인사라인")
GRANTS[("H_HRO","ER")] = (3, F, "§2.1c-FL2-인사라인")   # 인사운영: 명부는 전행, 급여는 아님
GRANTS[("F_PAY","PB")] = (3, F, "§2.1c-FL2-급여팀")
GRANTS[("F_PAY","PH")] = (3, F, "§2.1c-FL2-급여팀")
GRANTS[("F_PAY","ER")] = (3, F, "§2.1c-FL2-급여팀")
for a in ("CP","TA","AB","LN","RM","FA","ER","PB","PH","AL"):
    GRANTS[("F_CMP",a)] = (3, F, "§2.1c-FL3-준법(사후감사로그)")
GRANTS[("F_SEC","AL")] = (3, F, "§2.1c-FL4-정보보호(신호만)")
GRANTS[("F_SEC","ER")] = (2, F, "§2.1c-FL4-정보보호(신호만)")
GRANTS[("F_DW","SC")]  = (3, F, "§2.1c-FL6-관리무열람")

# ★H_GRP(재무지원부문) — 업무 열 전부 미열거. 조직 우위 ≠ 접근의 핵심 대비
#   (참고: 이 칸들을 f1으로 여는 안은 보류 — P3 대비 선명도를 위해 닫음)

# ── 테이블 생성·적재 ────────────────────────────────────────────────────────
step("v1 유산 제거")
# v1 테이블은 빈 껍데기로 남아도 재사용 위험이 있다. 특히 policy_functional_line은
# 어휘에 없는 값(trust_signal · schema)을 참조하는 자기모순 행 2개를 담고 있었고,
# query_set은 근거 없는 조항 §2.3-소집단상향을 rule_ref로 달고 있었다.
for t in ("policy_role_scope", "policy_functional_line", "query_set"):
    n = con.execute(f"SELECT count(*) FROM information_schema.tables "
                    f"WHERE table_name='{t}'").fetchone()[0]
    if n: con.execute(f"DROP TABLE {t}"); print(f"  DROP {t}")
print("  → 기능라인은 policy_cell의 basis='functional' 칸으로 표현된다 (별도 테이블 불필요)")

step("policy_cell 생성 (v1 policy_role_scope 대체)")
con.execute("DROP TABLE IF EXISTS policy_cell")
con.execute("DROP TABLE IF EXISTS policy_attr")
con.execute("""CREATE TABLE policy_attr(
  attr VARCHAR PRIMARY KEY, attr_name VARCHAR, subject_type VARCHAR, source VARCHAR)""")
con.execute("""CREATE TABLE policy_cell(
  role_id VARCHAR, attr VARCHAR, max_tier INT, basis VARCHAR, clause VARCHAR,
  PRIMARY KEY(role_id, attr))""")
con.executemany("INSERT INTO policy_attr VALUES (?,?,?,?)", ATTRS)
con.executemany("INSERT INTO policy_cell VALUES (?,?,?,?,?)",
                [(r, a, t, b, c) for (r, a), (t, b, c) in GRANTS.items()])

n_cell = len(GRANTS); n_total = len(ROLES) * len(ATTRS)
print(f"  속성 {len(ATTRS)}종 · 역할 {len(ROLES)}종 → 격자 {n_total}칸")
print(f"  열거된 칸 {n_cell} · deny 기본값 {n_total - n_cell}")
print(f"  판정 격자 = 14 × 12 × 4(tier) × 3(srel) × 3(org_rel) = "
      f"{len(ROLES)*len(ATTRS)*4*3*3:,}")
for b in (H, F, O, P):
    print(f"    basis={b:11s} {sum(1 for v in GRANTS.values() if v[1]==b):4d}칸")

step("검증 0: 조항 네임스페이스 가드")
# 층 분리를 조항 번호로 강제한다:
#   §1 조직모델 / §2 자격 격자(감독규정 인용) / §3 도출 규칙(SDC 인용)
#   §4 상한·허용성(Property 1-3) / §5 canary·프로브 / §6 에스컬레이션
# policy_cell은 '자격'만 담는다 → 조항은 반드시 §2로 시작.
# v1의 §2.3-소집단상향은 인원수 조건(도출 규칙)을 자격 조항으로 위장한 것이었고,
# 인용 문서 셋 중 어느 것도 최소 셀 크기를 다루지 않는다는 점에서 근거가 없었다.
bad_ns = con.execute("""SELECT DISTINCT clause FROM policy_cell
                        WHERE clause NOT LIKE '§2%'""").fetchall()
allok &= (len(bad_ns) == 0)
print(f"  §2 밖 조항 참조: {len(bad_ns)} {ok_(len(bad_ns)==0)}")
for (c_,) in bad_ns: print(f"    위반: {c_}")
banned = con.execute("""SELECT DISTINCT clause FROM policy_cell
                        WHERE clause LIKE '%2.3%' OR clause LIKE '%소집단%'""").fetchall()
allok &= (len(banned) == 0)
print(f"  금지 조항(§2.3 · 소집단) 참조: {len(banned)} {ok_(len(banned)==0)}")
print("  ※ 인원수 임계는 §3 도출 규칙의 파라미터이며 자격 격자에 넣지 않는다.")

step("검증 1: 소유권은 명세 선언 — 자동 부여가 아닌가")
bad = con.execute("""SELECT c.role_id, c.attr FROM policy_cell c JOIN policy_attr a USING(attr)
                     WHERE c.basis='ownership' AND a.subject_type <> '직원'""").fetchall()
allok &= (len(bad) == 0)
print(f"  주체≠직원인데 ownership: {len(bad)} {ok_(len(bad)==0)}  (v1의 own 구멍)")

# ★주체-부인 확인★ 주체가 본인이어도 열람 불가인 속성이 실제로 닫혀 있는가
den = sorted(SUBJECT_DENIED)
q = con.execute(f"""SELECT attr, count(*) FROM policy_cell
                    WHERE attr IN ({','.join(chr(39)+a+chr(39) for a in den)})
                      AND basis='ownership' GROUP BY 1""").fetchall()
allok &= (len(q) == 0)
print(f"  주체-부인 속성 {den}에 ownership 칸: {len(q)} {ok_(len(q)==0)}")
for a in den:
    who = con.execute("SELECT role_id, max_tier, basis FROM policy_cell WHERE attr=? ORDER BY 1",
                      [a]).fetchall()
    nm = next(n for c_, n, *_ in ATTRS if c_ == a)
    print(f"    {a}({nm}) 열람 가능 역할: {[(r, f't{t}', b[:4]) for r, t, b in who]}")
    print(f"      → 본인({den}의 주체)은 자기 기록을 볼 수 없다. 통제 기능만 본다.")
print(f"  소유권 부여 속성: {sorted(SELF_READABLE)} (PIPA35/GDPR15)")
print(f"  소유권 부인 속성: {den} (GDPR15 예외 · FFIEC p.75·p.94 패턴)")

step("검증 2: 역할 부분순서 — org_path에서 기계 도출")
ORG = dict(con.execute("""SELECT e.role_id, o.org_path FROM dim_employee e
  JOIN dim_org o USING(org_id) WHERE e.role_id IS NOT NULL""").fetchall())
pairs = [(u, v) for u, v in itertools.permutations(ROLES, 2)
         if ORG[u] != ORG[v] and ORG[u].startswith(ORG[v] + "/")]
print(f"  조직 비교가능 쌍 (v가 u의 진조상): {len(pairs)}쌍")
for u, v in pairs: print(f"    {u:7s} ⊂ {v:7s}   {ORG[u]}  ⊂  {ORG[v]}")

step("검증 3: authority–access 분리 — 봉쇄 셀 분류")
def cell(r, a): return GRANTS.get((r, a), (0, None, None))
conf = []
for u, v in pairs:
    for a, *_ in ATTRS:
        tu, bu, cu = cell(u, a); tv, bv, cv = cell(v, a)
        if tu > tv:
            kind = ("깊이역전(SDC)" if bu == H and bv == H else
                    "직무가열연다"   if bu == F and bv is None else
                    "기타")
            conf.append((kind, u, v, a, tu, tv, bu, bv, cu))
print(f"  ★봉쇄 셀 {len(conf)}개★ — 하위가 상위보다 넓은 칸 (조직 우위 ≠ 접근)")
from collections import Counter
kc = Counter(c[0] for c in conf)
for k, n in kc.items(): print(f"    기제 '{k}': {n}칸")
print()
for kind, u, v, a, tu, tv, bu, bv, cu in conf:
    nm = next(n for c, n, *_ in ATTRS if c == a)
    print(f"    [{kind:12s}] {u:7s}({a}:{tu},{(bu or 'deny')[:4]}) > "
          f"{v:7s}({a}:{tv},{(bv or 'deny')[:4]})  {nm:6s} ← {cu}")
# 모든 봉쇄 셀은 조항 근거를 가져야 한다 (이것이 실제 요구사항)
noclause = [c for c in conf if not c[8]]
allok &= (len(noclause) == 0)
print(f"\n  조항 근거 없는 봉쇄 셀: {len(noclause)} {ok_(len(noclause)==0)}")
print("  ※ 트리 위 단조성은 v2에서 성립하지 않는다 — 그것이 본 논문의 발견이다.")
print("    'hierarchy 안에서는 단조' 같은 조건은 요구하지 않는다 (깊이·폭 상충).")

step("검증 5: 대조쌍 성립 확인")
CONTRASTS = [
    ("P1 비교불가", "B_BR", "LN", "F_SAL", "LN", "지점=깊고좁음 vs 영업부=얕고넓음"),
    ("P2 깊이역전", "B_BR", "LN", "B_RHQ", "LN", "상위가 개인단위 못 봄"),
    ("P3 상속끊김", "H_HR", "PB", "H_GRP", "PB", "부문장이 부서장보다 좁음"),
    ("P5 직무가열연다", "H_HRO", "PB", "F_PAY", "PB", "같은 부, 다른 팀"),
    ("P6 좁게여는기능", "C_CC", "CP", "C_CC", "AB", "프로필 O 잔고 X"),
    ("P8 관리무열람", "F_DW", "SC", "F_DW", "PB", "스키마 O 값 X"),
    ("P9 신호만", "F_SEC", "AL", "F_SEC", "AB", "로그 O 업무값 X"),
]
for lbl, r1, a1, r2, a2, desc in CONTRASTS:
    t1, b1, c1 = cell(r1, a1); t2, b2, c2 = cell(r2, a2)
    d = f"{r1}.{a1}=({t1},{b1 or 'deny'})  vs  {r2}.{a2}=({t2},{b2 or 'deny'})"
    good = (t1, b1, c1) != (t2, b2, c2)
    allok &= good
    print(f"  {lbl:14s} {ok_(good)}  {d}")
    print(f"                    → {desc}")

con.close()
step("✅ 완료 — 다음: build_reports_v2 (조각 12속성 커버)" if allok else "❌ 검증 실패")
R.finish(allok)
sys.exit(0 if allok else 1)
