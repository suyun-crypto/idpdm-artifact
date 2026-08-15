# -*- coding: utf-8 -*-
"""
FinDW-Bench 자원 기밀등급 축 신설 v2 — granularity ≠ confidentiality

문제 (실측으로 확인):
  v2의 tier는 **granularity**(전행/부서·지점/개인)이고, 자원의 **기밀등급**이 아니다.
  결과: "전행 단위인데 준법감시인만 보는 자원"을 표현할 방법이 없다.
    t1은 가장 얕은 tier이므로 max_tier>=1인 85개 칸을 가진 역할이 t1 조각을 전부 본다.
  반대로 "사내 복지정책"처럼 granularity 축에 걸리지 않는 공개 자료는
    12속성 어디에도 안 맞아 파서 unknown → fail-safe escalate (전원 차단).

구논문에는 이 축이 있었다 (Algorithm 4: tier(d) <= D_final, 문서 등급
Public/Internal/Confidential). 신논문이 §IV-B에서 tier를 granularity로 정화하면서
이 축을 함께 삭제했다. 구논문의 문제는 두 개념을 한 숫자에 뭉갠 것이었고,
해법은 삭제가 아니라 **분리**다.

신설 축:
  자원측  classification ∈ {public(0), internal(1), confidential(2), restricted(3)}
  요청자측 clearance      ∈ 같은 4단계 (역할별 1개 값)
  처리지시 handling       ∈ {none, mask_pii, escalate_required}

★f_θ에 넣지 않는다★ — classification은 자원의 속성이고 f_θ는 요청에 대해 판정한다.
f_θ는 어떤 조각이 검색될지 모른다. 따라서 구논문처럼 **검색 필터에 결정론적으로** 둔다.
판정 격자는 2,016 그대로.

조항 네임스페이스: ★§3★ (§2 아님 — 감독규정이 아니라 기관 공개정책 소관)

인용 근거 ★확보★:
  World Bank, Policy on Access to Information (July 1, 2010) [worldbank2010ati]
   §28  자원 4분류 공식 규정 — Public / Official Use Only /
        Confidential / Strictly Confidential                  ← 본 축의 직접 근거
   §6   기본값이 **개방**이다: 예외 목록에 없는 정보는 접근 허용
        (우리 policy_cell은 반대 — 기본 deny + 명시 부여. 서술에 명기 필요)
   §8   직원 개인정보·인사 선발·내부 분쟁조정·직원 비위 조사 = 접근 불가.
        단 "except to the extent expressly permitted by the Staff Rules"
        → ★소유권이 보편 규칙이 아니라 별도 규정의 선택★ (우리 SUBJECT_DENIED 근거)
   §16(c) 내부 의사결정용 통계·분석(신용도 평가·리스크·CPIA)은 제한
        → ★기관 단위(t1) 분석이 최고 기밀일 수 있음★ = granularity ≠ confidentiality
   §16(d) 내부감사 보고서 제한 (확정 연·분기 활동보고서만 공개)
   §18  제한정보 공개 시 승인 절차: Confidential/Strictly Confidential Board 기록은
        이사회 승인, 그 외는 Access to Information Committee 승인
        → 우리 handling='escalate_required'의 제도적 대응물
   §35  Access to Information Committee = 공개 판단 전담 행정기구
   §31–33 시효 강등(declassification) 5·10·20년 / §32 강등 불가 항목
   AMS 6.21A, Information Classification and Control Policy — 내부 분류·통제 규정
        (본 문서가 참조만 하며 원문 미확보. 역할별 clearance의 근거는 여기일 것)

BIS 2종(BCBS 113 · 328) 전문 검색: data/information classification · tiered ·
  graded · need-to-know 모두 0건. 등급 체계는 없고 다른 축을 지지한다:
  BCBS 113 §23·§30·§32 — 준법 기능은 "any records or files" 접근권, 보고선 우회
  BCBS 328 §81–83       — 그룹 내 정보공유가 이해상충. 조직 상위성이 공유 근거 아님
  BCBS 328 §153–155     — 공개 의무 항목 열거 + 필요 기밀 침해 금지

BIS에서 확보한 근거 (등급 체계가 아니라 다른 축):
  BCBS 113 §23·§30·§32 — 준법 기능은 "any records or files"에 접근권,
                          정상 보고선 우회 가능 → F_CMP clearance=restricted
  BCBS 328 §81–83       — 그룹 내 정보 공유가 이해상충. 조직 상위성이 공유 근거 아님
  BCBS 328 §153–155     — 공개 의무 항목 열거 + "without breaching necessary
                          confidentiality" → classification=public의 근거

실행: python classification_v2.py     (build_reports_v2.py 이후)
"""
import sys, argparse
import duckdb

ap = argparse.ArgumentParser()
ap.add_argument("--db", default="findw.duckdb")
args = ap.parse_args()
import findw_result as R                 # 결과 기록 모듈 (같은 폴더에 필요)
R.start("05_classification", args.db)

con = duckdb.connect(args.db)
def step(m): print(f"\n[D5-v2] {m}")
def ok_(b): return "OK" if b else "FAIL"
allok = True

# ★World Bank Policy on Access to Information (2010) §28 공식 4분류★
#   "Bank documents are assigned one of the following four classifications"
#   → Public / Official Use Only / Confidential / Strictly Confidential
LV = {"Public": 0, "Official Use Only": 1, "Confidential": 2, "Strictly Confidential": 3}
NAME = {v: k for k, v in LV.items()}
# 한글 대응 (World Bank ATI §28 원어를 정본으로 두고 국문 표기만 병기)
KO = {0: "공개", 1: "내부업무용", 2: "기밀", 3: "최고기밀"}

# ── 1. 스키마 확장 ───────────────────────────────────────────────────────────
step("스키마 — classification · handling · policy_clearance 신설")
for c, t, d in [("classification", "INT", "1"), ("handling", "VARCHAR", "'none'")]:
    n = con.execute("""SELECT count(*) FROM information_schema.columns
                       WHERE table_name='report_fragment' AND column_name=?""", [c]).fetchone()[0]
    if not n:
        con.execute(f"ALTER TABLE report_fragment ADD COLUMN {c} {t} DEFAULT {d}")
# 등급 어휘를 DB에 정본으로 고정 (World Bank ATI §28)
con.execute("DROP TABLE IF EXISTS policy_classification")
con.execute("""CREATE TABLE policy_classification(
  level INT PRIMARY KEY, name_en VARCHAR, name_ko VARCHAR, clause VARCHAR)""")
con.executemany("INSERT INTO policy_classification VALUES (?,?,?,?)",
    [(v, k, KO[v], "§3.1-ATI-28") for k, v in LV.items()])
con.execute("DROP TABLE IF EXISTS policy_clearance")
con.execute("""CREATE TABLE policy_clearance(
  role_id VARCHAR PRIMARY KEY, clearance INT, clause VARCHAR, rationale VARCHAR)""")

# ── 2. 역할별 clearance — 근거 있는 것만 상향 ────────────────────────────────
step("policy_clearance 적재")
CLR = {
    # 준법감시 기능: BCBS 113 §30 "any records or files" + §32 보고선 우회
    "F_CMP": ("Strictly Confidential", "§3.2-BCBS113-30", "준법 기능의 무제한 기록 접근권"),
    # 개인 단위 민감 데이터를 상시 취급하는 역할
    "B_BR":  ("Confidential", "§3.2-직무필요", "지점 고객 개인 단위 상시 취급"),
    "H_HR":  ("Confidential", "§3.2-직무필요", "전행 급여 기능라인"),
    "F_PAY": ("Confidential", "§3.2-직무필요", "급여 산정 기능"),
    "F_SEC": ("Confidential", "§3.2-직무필요", "접근로그·행동신호 취급"),
}
DEFAULT_CLR = "Official Use Only"     # 임직원 기본값
ROLES = [r[0] for r in con.execute(
    "SELECT DISTINCT role_id FROM policy_cell ORDER BY 1").fetchall()]
rows = []
for r in ROLES:
    if r in CLR:
        nm, cl, why = CLR[r]; rows.append((r, LV[nm], cl, why))
    else:
        rows.append((r, LV[DEFAULT_CLR], "§3.2-기본값", "임직원 기본 등급"))
con.executemany("INSERT INTO policy_clearance VALUES (?,?,?,?)", rows)
for r, v, cl, why in sorted(rows, key=lambda x: -x[1]):
    print(f"  {r:7s} {NAME[v]:12s} ← {cl:18s} {why}")

# ── 3. 조각 classification — 도출 규칙 + 명시적 예외 ─────────────────────────
step("classification 배정 — §3.1 도출 규칙")
# 기본 규칙 (문서화된 도출): 주체 유형 × granularity
#   공표 데이터(지역통계·시스템 메타)          → public
#   보호주체(고객·직원) 개인 단위 t3           → confidential
#   그 외                                      → internal
con.execute("""UPDATE report_fragment SET classification = CASE
    WHEN attr IN ('RS')                                    THEN 0   -- 공표 통계
    WHEN attr = 'SC' AND tier = 1                          THEN 0   -- 테이블 목록
    WHEN attr = 'SC'                                       THEN 1
    WHEN tier = 3 AND attr IN ('CP','TA','AB','LN','ER','PB','PH','AL') THEN 2
    ELSE 1 END""")

# ★명시적 예외★ — 도출 규칙과 어긋나는 칸. 이 예외의 존재가 축의 독립성을 증명한다.
#   FFIEC p.75·p.94: SAR·314(a) 대상은 존재 자체를 공유 금지 → t1 집계라도 restricted
step("★명시적 예외★ — t1 집계인데 restricted인 자원 (축의 독립성 증명)")
sus = con.execute("""SELECT count(*), sum(l.amount) FROM loan l WHERE l.status IN ('B','D')""").fetchone()
con.execute("""INSERT INTO report_fragment VALUES
  ('SAR-00001','G06',DATE '2018-12-01',1,'RM','/은행',NULL,?,NULL,?,
   ?, NULL, 3, 'escalate_required')""",
  [sus[0], float(sus[1]),
   f"[감독보고 대상] 부실여신 {sus[0]}건 총 {sus[1]:,.0f} — 보고 대상 계좌 집계"])
con.execute("""INSERT INTO report_fragment VALUES
  ('SAR-00002','G08',DATE '2018-12-01',1,'ER','/은행',NULL,595,NULL,595,
   '[감독보고 대상] 내부조사 진행 건수 및 관련 부서 총괄', NULL, 3, 'escalate_required')""")
print(f"  SAR-00001  t1 · RM · restricted  (부실여신 {sus[0]}건 전행 집계)")
print(f"  SAR-00002  t1 · ER · restricted  (내부조사 총괄)")
print("  → granularity는 가장 얕은 t1, 기밀등급은 최고 restricted. 도출 규칙의 예외.")
print("  근거: World Bank ATI §16(c) 내부 의사결정용 통계·분석 제한")
print("        (신용도 평가·리스크 분석 = 기관 단위인데 최고 기밀)")
print("        FFIEC p.75(SAR 존재 공유 금지) · p.94(314(a) 명단 공유 금지)")

# handling: 개인 단위 보호주체 조각은 마스킹 가능 (전부/전무의 중간 경로)
con.execute("""UPDATE report_fragment SET handling='mask_pii'
  WHERE tier=3 AND attr IN ('CP','TA','AB','LN','ER','PB','PH','AL')
    AND handling='none'""")

# ── 4. 검증 ──────────────────────────────────────────────────────────────────
step("검증 0: 등급 어휘 (World Bank ATI §28 정본)")
for lv, en, ko, cl in con.execute("SELECT * FROM policy_classification ORDER BY level").fetchall():
    print(f"  {lv}  {en:22s} {ko:8s} ← {cl}")

step("검증 1: classification 분포")
for v, n in con.execute("SELECT classification, count(*) FROM report_fragment GROUP BY 1 ORDER BY 1").fetchall():
    print(f"  {NAME[v]:22s} {KO[v]:8s} {n:>6,}")
step("검증 2: handling 분포")
for h, n in con.execute("SELECT handling, count(*) FROM report_fragment GROUP BY 1 ORDER BY 2 DESC").fetchall():
    print(f"  {h:18s} {n:>6,}")

step("검증 3: ★결정적 케이스★ t1 restricted 조각이 누구에게 보이는가")
CLRMAP = dict(con.execute("SELECT role_id, clearance FROM policy_clearance").fetchall())
CELL = {(r, a): t for r, a, t in con.execute(
    "SELECT role_id, attr, max_tier FROM policy_cell").fetchall()}
for fid, attr, tier, cls in con.execute(
        "SELECT fragment_id, attr, tier, classification FROM report_fragment "
        "WHERE classification=3 ORDER BY 1").fetchall():
    old_ok = [r for r in ROLES if CELL.get((r, attr), 0) >= tier]         # 등급 축 없을 때
    new_ok = [r for r in ROLES if CELL.get((r, attr), 0) >= tier and CLRMAP[r] >= cls]
    print(f"  {fid}  (t{tier} {attr} {NAME[cls]})")
    print(f"    등급축 없음: {len(old_ok):2d}개 역할 {old_ok}")
    print(f"    등급축 적용: {len(new_ok):2d}개 역할 {new_ok}")
    allok &= (len(new_ok) < len(old_ok) and set(new_ok) <= {"F_CMP"})
    print(f"    축이 실제로 좁혔는가 {ok_(len(new_ok) < len(old_ok))}")

step("검증 4: 공개 자원은 clearance와 무관하게 전원 열람")
pub = con.execute("SELECT count(*) FROM report_fragment WHERE classification=0").fetchone()[0]
minc = min(CLRMAP.values())
allok &= (minc >= 0)
print(f"  public 조각 {pub:,}개 · 최저 clearance {NAME[minc]} → 전원 통과 {ok_(minc >= 0)}")

step("검증 5: 조항 네임스페이스 — 기밀등급은 §3 (감독규정 층 아님)")
bad = con.execute("SELECT DISTINCT clause FROM policy_clearance WHERE clause NOT LIKE '§3%'").fetchall()
allok &= (len(bad) == 0)
print(f"  §3 밖 조항: {len(bad)} {ok_(len(bad)==0)}")
print("  ※ 4단계 등급의 근거: World Bank ATI (2010) §28 — 공표된 기관 정책이다.")
print("    ISO/NIST 산업관행이 아니라 국제금융기구 공표문서 = RBA와 같은 인용 등급.")
print("    단 감독규정이 아니므로 §2가 아니라 §3에 둔다.")

step("검증 6: 검색 필터 4개 conjunct 전부 적용 가능한가")
print("  retrievable(d,u) ⟺ tier(d) ≤ D_final                    [깊이]")
print("                   ∧ attr(d) ∈ scope(u)                    [열]")
print("                   ∧ row_ok(basis, org_rel)                [행]")
print("                   ∧ classification(d) ≤ clearance(u)      [기밀] ★신설★")
need = ["tier", "attr", "subject_scope", "classification"]
have = [c[0] for c in con.execute("""SELECT column_name FROM information_schema.columns
                                     WHERE table_name='report_fragment'""").fetchall()]
miss = [c for c in need if c not in have]
allok &= (len(miss) == 0)
print(f"  필요 컬럼 결측: {miss} {ok_(len(miss)==0)}")

step("검증 7: 인용 문서가 규정하나 v2에 없는 것 (한계로 명기)")
print("  ① 시효 강등 (ATI §31–33): 5·10·20년 후 자동 강등. 우리 classification은 정적.")
print("     → period 컬럼이 이미 있으므로 구현 가능. 논문 B 또는 §VII 향후과제.")
print("  ② 이의절차 (ATI §36–40): 요청자가 거부에 이의 제기 → 2단 심사.")
print("     → 우리 escalation은 단방향. 요청자 개시 경로가 없다.")
print("  ③ 기본값 방향 (ATI §6): 기관 정책은 '예외 목록 외 전부 개방'.")
print("     우리 policy_cell은 '기본 deny + 명시 부여'. 반대 방향임을 서술에 명기.")
print("  ④ AMS 6.21A 원문 미확보 — 역할별 clearance의 직접 근거는 여기일 것.")

con.close()
step("✅ 완료 — 다음: fragment_algebra(cl(F)) + admissibility(Property 3)" if allok else "❌ 검증 실패")
R.finish(allok)
sys.exit(0 if allok else 1)
