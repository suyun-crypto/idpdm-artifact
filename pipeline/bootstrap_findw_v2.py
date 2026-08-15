# -*- coding: utf-8 -*-
"""
FinDW-Bench 부트스트랩 v2 — ★원 배포본(.asc) 직접 적재판★

v1 대비 변경:
  1. 출처를 제3자 미러(dnoeth TSV)에서 **PKDD'99 원 배포본(.asc)**으로 교체
  2. SHA-256 무결성 검증 추가 — 파일이 바뀌면 즉시 중단 (미러 무단 변경 탐지)
  3. ★버그 수정★ birth_date: 미러는 2자리 연도 피벗을 잘못 잡아 전 고객 +20년 오차.
     원본 birth_number(체코 rodné číslo 6자리)를 규칙대로 복호한다.
       YYMMDD, 여성은 월에 +50. 예: "706213" → 1970-12-13 여 (미러: 1990-12-13)
  4. 원본 값 보존: disp.type = OWNER/DISPONENT (미러는 O/D),
     trans.type = PRIJEM/VYDAJ/VYBER (미러는 C/D/P)

원 배포본 취득 (robots.txt로 자동 다운로드 불가 — 수동 취득 후 ./berka_asc/ 배치):
  http<repo>     (구 lisp.vse.cz/pkdd99/Challenge/)
  가이드 문서: .../berka.htm
  정본 학술 호스트: CTU Prague Relational Learning Repository
                    http<repo>   (구 relational.fit.cvut.cz)

실행: python bootstrap_findw_v2.py [--asc-dir berka_asc] [--db findw.duckdb]
"""
import os, sys, csv, hashlib, argparse, datetime as dt
import duckdb

# ── 원 배포본 SHA-256 (본 프로젝트가 검증한 값) ──────────────────────────────
EXPECTED_SHA256 = {
    "district.asc": "7f03cf3b9b82f0fdcc3abdf6cc716f145db8e9875c68e2d2e2f7151e9ecf4df3",
    "account.asc":  "58d7f50abd72e9b1a5568346f74bb54cd71224ee1db9f09a27d7cac563f38cc6",
    "client.asc":   "e435c6b92d246f4f0dfd5e2827469d745c06238714c32b3ffb415eebe794e1a7",
    "disp.asc":     "ebd801f77b6d322e8ebc08e52f188e7c8fca539325f85f57f8c73434da9d32d8",
    "loan.asc":     "68535f609a254aa7a3f03dd8e27dcb822b532df12a0d6046f0666b8dc0b8ae8e",
    "card.asc":     "fc669bde6adf6457d87421c0bfb218e9c384a7032c6accd348d207a405e72109",
    "order.asc":    "035930fa6acd2ca42a935e654b21e1bb260248f49b6dc6e7de6351b7c4d56d02",
    "trans.asc":    "75ab2f39df9d79d79c5c900de90ddd28248b689f214598ac9fa2ff0f574a70d2",
}

# ── 공표 스펙 (PKDD'99 가이드 + CTU 저장소 메타데이터) ───────────────────────
EXPECTED_ROWS = {"district": 77, "account": 4500, "client": 5369, "disp": 5369,
                 "loan": 682, "card": 892, "pay_order": 6471, "trans": 1056320}
EXPECTED_LOAN = {"successful": 606, "unsuccessful": 76}   # CTU 공표: A+C / B+D

def step(m): print(f"\n[FinDW-v2] {m}")
def ok_(b): return "OK" if b else "FAIL"

# ── 파서 유틸 ────────────────────────────────────────────────────────────────
def _n(v):
    """'?' 및 빈 문자열 → None (원본 결측 표기)"""
    v = v.strip()
    return None if v in ("", "?") else v

def yymmdd(v):
    """930705 → date(1993,7,5). card.issued는 '931107 00:00:00' 형식."""
    v = _n(v)
    if v is None: return None
    v = v.split()[0]
    y, m, d = int(v[0:2]), int(v[2:4]), int(v[4:6])
    return dt.date(1900 + y, m, d)

def birth_number(v):
    """체코 rodné číslo(6자리) → (birth_date, gender).
    YYMMDD. 여성은 월에 +50이 더해져 있다. 데이터셋 고객은 전원 1900년대 출생."""
    v = _n(v)
    if v is None: return None, None
    y, m, d = int(v[0:2]), int(v[2:4]), int(v[4:6])
    if m > 50:
        m -= 50; g = "F"
    else:
        g = "M"
    return dt.date(1900 + y, m, d), g

def read_asc(path):
    """원 배포본 형식: ';' 구분, CRLF, 헤더 1행, 문자열은 '"' 인용."""
    with open(path, encoding="latin-1", newline="") as f:
        rd = csv.reader((ln.replace("\r\n", "\n") for ln in f), delimiter=";", quotechar='"')
        header = next(rd)
        for row in rd:
            if row and any(c.strip() for c in row):
                yield row

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()

# ── 메인 ─────────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser()
ap.add_argument("--asc-dir", default="berka_asc")
ap.add_argument("--db", default="findw.duckdb")
ap.add_argument("--schema", default="schema.sql")
ap.add_argument("--record-hashes", action="store_true",
                help="EXPECTED_SHA256를 현재 파일 기준으로 출력하고 종료")
args = ap.parse_args()

import findw_result as R                 # 결과 기록 모듈 (같은 폴더에 필요)
R.start("01_bootstrap", args.db)

A = args.asc_dir
missing = [f for f in EXPECTED_SHA256 if not os.path.isfile(os.path.join(A, f))]
if missing:
    sys.exit(f"[중단] {A}/ 에 원본 파일 없음: {missing}\n"
             f"       원 배포본을 sorry.vse.cz/~berka/challenge/pkdd1999/ 에서 취득해 배치하십시오.")

# ── 1. 무결성 검증 ───────────────────────────────────────────────────────────
step("SHA-256 무결성 검증 (원 배포본 대조)")
actual = {f: sha256(os.path.join(A, f)) for f in EXPECTED_SHA256}
if args.record_hashes:
    print("\nEXPECTED_SHA256 = {")
    for f, h in actual.items(): print(f'    "{f}":{" "*(14-len(f))}"{h}",')
    print("}")
    sys.exit(0)
bad = []
for f, exp in EXPECTED_SHA256.items():
    if exp is None:
        print(f"  {f:14s}: {actual[f][:16]}… (미기록 — --record-hashes 로 고정 권장)")
    else:
        good = actual[f] == exp
        print(f"  {f:14s}: {actual[f][:16]}… {ok_(good)}")
        if not good: bad.append(f)
if bad:
    sys.exit(f"[중단] 해시 불일치: {bad} — 원본과 다른 파일입니다.")

# ── 2. 스키마 ────────────────────────────────────────────────────────────────
if os.path.exists(args.db):
    step(f"기존 {args.db} 삭제 후 재생성"); os.remove(args.db)
con = duckdb.connect(args.db)
con.execute(open(args.schema, encoding="utf-8").read())
step("스키마 생성 완료")

# ── 3. 적재 ──────────────────────────────────────────────────────────────────
step("원 배포본 적재 (DuckDB 벡터화 경로)")

def rc(fname, cols):
    """원본 .asc를 전 컬럼 VARCHAR로 읽는 read_csv 표현식.
    ';' 구분 · 헤더 1행 · '"' 인용 · CRLF. '?'와 ''는 TRY_CAST로 NULL 처리."""
    spec = ", ".join(f"'{c}':'VARCHAR'" for c in cols)
    return (f"read_csv('{A}/{fname}', delim=';', header=true, quote='\"', "
            f"columns={{{spec}}}, all_varchar=true, ignore_errors=false)")

def D6(col):
    """YYMMDD(6자리, 뒤에 시각이 붙어도 무방) → DATE. 고객·거래 전원 1900년대."""
    c = f"substr(trim({col}), 1, 6)"
    return (f"make_date(1900 + CAST(substr({c},1,2) AS INT), "
            f"CAST(substr({c},3,2) AS INT), CAST(substr({c},5,2) AS INT))")

# district — 헤더 A1..A16 (가이드 문서 명명). '?' 결측은 TRY_CAST로 NULL.
Acols = [f"A{i}" for i in range(1, 17)]
con.execute(f"""INSERT INTO district SELECT
  CAST(A1 AS INT), A2, A3,
  TRY_CAST(A4 AS INT),  TRY_CAST(A5 AS INT),  TRY_CAST(A6 AS INT),
  TRY_CAST(A7 AS INT),  TRY_CAST(A8 AS INT),  TRY_CAST(A9 AS INT),
  TRY_CAST(A10 AS DOUBLE), TRY_CAST(A11 AS DOUBLE),
  TRY_CAST(A12 AS DOUBLE), TRY_CAST(A13 AS DOUBLE),
  TRY_CAST(A14 AS INT), TRY_CAST(A15 AS INT), TRY_CAST(A16 AS INT)
FROM {rc('district.asc', Acols)}""")

con.execute(f"""INSERT INTO account SELECT
  CAST(account_id AS INT), CAST(district_id AS INT), {D6('date')}, frequency
FROM {rc('account.asc', ['account_id','district_id','frequency','date'])}""")

# client — ★birth_number 복호★ 여성은 월에 +50 (체코 rodné číslo)
con.execute(f"""INSERT INTO client SELECT
  CAST(client_id AS INT),
  make_date(1900 + CAST(substr(birth_number,1,2) AS INT),
            CASE WHEN CAST(substr(birth_number,3,2) AS INT) > 50
                 THEN CAST(substr(birth_number,3,2) AS INT) - 50
                 ELSE CAST(substr(birth_number,3,2) AS INT) END,
            CAST(substr(birth_number,5,2) AS INT)),
  CASE WHEN CAST(substr(birth_number,3,2) AS INT) > 50 THEN 'F' ELSE 'M' END,
  CAST(district_id AS INT)
FROM {rc('client.asc', ['client_id','birth_number','district_id'])}""")

con.execute(f"""INSERT INTO disp SELECT
  CAST(disp_id AS INT), CAST(client_id AS INT), CAST(account_id AS INT), type
FROM {rc('disp.asc', ['disp_id','client_id','account_id','type'])}""")

con.execute(f"""INSERT INTO loan SELECT
  CAST(loan_id AS INT), CAST(account_id AS INT), {D6('date')},
  CAST(amount AS DOUBLE), CAST(duration AS INT), CAST(payments AS DOUBLE), status
FROM {rc('loan.asc', ['loan_id','account_id','date','amount','duration','payments','status'])}""")

con.execute(f"""INSERT INTO card SELECT
  CAST(card_id AS INT), CAST(disp_id AS INT), type, {D6('issued')}
FROM {rc('card.asc', ['card_id','disp_id','type','issued'])}""")

con.execute(f"""INSERT INTO pay_order SELECT
  CAST(order_id AS INT), CAST(account_id AS INT),
  nullif(trim(bank_to),''), nullif(trim(account_to),''),
  CAST(amount AS DOUBLE), nullif(trim(k_symbol),'')
FROM {rc('order.asc', ['order_id','account_id','bank_to','account_to','amount','k_symbol'])}""")

con.execute(f"""INSERT INTO trans SELECT
  CAST(trans_id AS INT), CAST(account_id AS INT), {D6('date')},
  CAST(amount AS DOUBLE), CAST(balance AS DOUBLE),
  nullif(trim(type),''), nullif(trim(operation),''), nullif(trim(k_symbol),''),
  nullif(trim(bank),''), nullif(trim(account) ,'')
FROM {rc('trans.asc', ['trans_id','account_id','date','type','operation','amount','balance','k_symbol','bank','account'])}""")

for t in ("district","account","client","disp","loan","card","pay_order","trans"):
    print(f"  {t:10s}: {con.execute(f'SELECT count(*) FROM {t}').fetchone()[0]:>9,}")
print("  ※ birth_number 복호 · disp.type=OWNER/DISPONENT · trans.type=PRIJEM/VYDAJ/VYBER 원문 보존")

# ── 4. 검증 ──────────────────────────────────────────────────────────────────
step("검증 1/4: 행 수 (공표 스펙 대조)")
allok = True
for t, exp in EXPECTED_ROWS.items():
    n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    allok &= (n == exp)
    print(f"  {t:10s}: {n:>9,}  {ok_(n == exp)}" + ("" if n == exp else f" (기대 {exp:,})"))

step("검증 2/4: FK 무결성 (고아 = 0)")
for lbl, q in [
    ("trans→account",   "SELECT count(*) FROM trans t LEFT JOIN account a USING(account_id) WHERE a.account_id IS NULL"),
    ("loan→account",    "SELECT count(*) FROM loan l LEFT JOIN account a USING(account_id) WHERE a.account_id IS NULL"),
    ("disp→client",     "SELECT count(*) FROM disp d LEFT JOIN client c USING(client_id) WHERE c.client_id IS NULL"),
    ("disp→account",    "SELECT count(*) FROM disp d LEFT JOIN account a USING(account_id) WHERE a.account_id IS NULL"),
    ("card→disp",       "SELECT count(*) FROM card c LEFT JOIN disp d USING(disp_id) WHERE d.disp_id IS NULL"),
    ("account→district","SELECT count(*) FROM account a LEFT JOIN district d USING(district_id) WHERE d.district_id IS NULL"),
    ("client→district", "SELECT count(*) FROM client c LEFT JOIN district d USING(district_id) WHERE d.district_id IS NULL"),
]:
    n = con.execute(q).fetchone()[0]; allok &= (n == 0)
    print(f"  {lbl:17s}: {n} orphans {ok_(n == 0)}")

step("검증 3/4: 의미 수준 (CTU 공표 통계)")
r = dict(con.execute("SELECT status, count(*) FROM loan GROUP BY 1").fetchall())
succ, fail = r["A"] + r["C"], r["B"] + r["D"]
allok &= (succ == EXPECTED_LOAN["successful"] and fail == EXPECTED_LOAN["unsuccessful"])
print(f"  successful loans (A+C): {succ}  {ok_(succ == 606)}  (CTU 공표 606)")
print(f"  unsuccessful     (B+D): {fail}  {ok_(fail == 76)}  (CTU 공표 76)")
n = con.execute("SELECT count(*) FROM district WHERE unemp95 IS NULL OR crimes95 IS NULL").fetchone()[0]
allok &= (n == 1)
print(f"  원본 '?' 결측 행 (Jesenik): {n}  {ok_(n == 1)}")

step("검증 4/4: birth_number 복호 (미러 버그 회귀 방지)")
CASES = [(1, dt.date(1970, 12, 13), "F"), (2, dt.date(1945, 2, 4), "M"), (3, dt.date(1940, 10, 9), "F")]
for cid, exp_d, exp_g in CASES:
    d, g = con.execute("SELECT birth_date, gender FROM client WHERE client_id=?", [cid]).fetchone()
    good = (d == exp_d and g == exp_g); allok &= good
    print(f"  client {cid}: {d} {g}  {ok_(good)}  (기대 {exp_d} {exp_g})")

con.close()
step("✅ 완료 — 다음: setup_org_v2.py" if allok else "❌ 검증 실패 — 위 FAIL 확인")
R.finish(allok)
sys.exit(0 if allok else 1)
