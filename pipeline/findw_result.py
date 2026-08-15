# -*- coding: utf-8 -*-
"""
FinDW-Bench v2 — 실행 결과 기록 모듈 (5개 단계 스크립트가 공용으로 import)

역할:
  1. 스크립트의 모든 출력을 화면에 그대로 보여주면서 동시에 results/<단계>.log 에 저장
  2. 종료 시 DB 상태를 조회해 results/<단계>.json 에 구조화 기록
  3. 조기 종료(sys.exit, 예외, 해시 불일치 등)에도 atexit로 반드시 기록

각 단계 스크립트는 두 줄만 추가한다:
    import findw_result as R
    R.start("01_bootstrap", args.db)      # 인자 파싱 직후
    ...
    R.finish(allok)                        # sys.exit 직전 (생략해도 atexit가 처리)

결과 파일 (results/ 폴더에 자동 생성):
  results/<단계>.log    — 화면 출력 전문 (사람이 읽는 용도)
  results/<단계>.json   — 통과여부 · DB 지표 · 실행환경 (기계 판독 / 단계 간 비교용)
"""
import atexit, io, json, os, platform, sys, datetime as dt

RESULT_DIR = "results"
_state = {"stage": None, "db": None, "ok": None, "buf": None, "orig": None, "t0": None}


class _Tee:
    """화면과 버퍼에 동시 출력."""
    def __init__(self, orig, buf):
        self.orig, self.buf = orig, buf
    def write(self, s):
        self.orig.write(s); self.buf.write(s)
    def flush(self):
        self.orig.flush()


def start(stage, db_path):
    os.makedirs(RESULT_DIR, exist_ok=True)
    _state.update(stage=stage, db=db_path, ok=None,
                  buf=io.StringIO(), orig=sys.stdout, t0=dt.datetime.now())
    sys.stdout = _Tee(_state["orig"], _state["buf"])
    atexit.register(_dump)


def finish(ok):
    _state["ok"] = bool(ok)


def _db_metrics(db):
    """DB 테이블별 행수 + 단계별 핵심 지표. DB가 없거나 조회 실패해도 죽지 않는다."""
    m = {"tables": {}, "key": {}}
    if not db or not os.path.exists(db):
        m["error"] = f"DB 파일 없음: {db}"
        return m
    try:
        import duckdb
        c = duckdb.connect(db, read_only=True)
    except Exception as e:
        m["error"] = f"DB 연결 실패: {e}"
        return m
    try:
        tabs = [r[0] for r in c.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main' ORDER BY 1").fetchall()]
        for t in tabs:
            try:
                m["tables"][t] = c.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
            except Exception:
                m["tables"][t] = None

        def q(key, sql):
            try:
                m["key"][key] = c.execute(sql).fetchall()
            except Exception:
                pass

        q("loan_status", "SELECT status, count(*) FROM loan GROUP BY 1 ORDER BY 1")
        q("client_first3", "SELECT client_id, birth_date, gender FROM client "
                           "ORDER BY client_id LIMIT 3")
        q("personas", "SELECT role_id, org_id FROM dim_employee "
                      "WHERE role_id IS NOT NULL ORDER BY 1")
        q("dim_employee_cols", "SELECT column_name FROM information_schema.columns "
                               "WHERE table_name='dim_employee' ORDER BY ordinal_position")
        q("payroll_cols", "SELECT column_name FROM information_schema.columns "
                          "WHERE table_name='fact_payroll' ORDER BY ordinal_position")
        q("basis_dist", "SELECT basis, count(*) FROM policy_cell GROUP BY 1 ORDER BY 1")
        q("attrs", "SELECT attr, attr_name, subject_type FROM policy_attr ORDER BY attr")
        q("frag_by_attr", "SELECT attr, count(*) FROM report_fragment GROUP BY 1 ORDER BY 1")
        q("frag_by_tier", "SELECT attr, tier, count(*) FROM report_fragment "
                          "GROUP BY 1,2 ORDER BY 1,2")
        q("canary", "SELECT canary_flag, count(*) FROM report_fragment "
                    "WHERE canary_flag IS NOT NULL GROUP BY 1 ORDER BY 1")
        q("classification", "SELECT classification, count(*) FROM report_fragment "
                            "GROUP BY 1 ORDER BY 1")
        q("handling", "SELECT handling, count(*) FROM report_fragment GROUP BY 1 ORDER BY 1")
        q("clearance", "SELECT role_id, clearance FROM policy_clearance ORDER BY 1")
        q("tier_x_class", "SELECT tier, classification, count(*) FROM report_fragment "
                          "GROUP BY 1,2 ORDER BY 1,2")
    finally:
        c.close()
    return m


def _dump():
    if _state["stage"] is None:
        return
    stage = _state["stage"]
    # stdout 복원 (중복 호출 방지)
    if _state["orig"] is not None:
        sys.stdout = _state["orig"]
    log_text = _state["buf"].getvalue() if _state["buf"] else ""
    _state["stage"] = None                       # 재진입 차단

    log_path = os.path.join(RESULT_DIR, f"{stage}.log")
    json_path = os.path.join(RESULT_DIR, f"{stage}.json")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(log_text)

    ok = _state["ok"]
    payload = {
        "stage": stage,
        "passed": ok,
        "note": None if ok is not None else "finish() 미호출 — 조기 종료 또는 예외",
        "started_at": _state["t0"].isoformat() if _state["t0"] else None,
        "finished_at": dt.datetime.now().isoformat(),
        "elapsed_sec": round((dt.datetime.now() - _state["t0"]).total_seconds(), 1)
                       if _state["t0"] else None,
        "fail_lines": [ln.strip() for ln in log_text.splitlines() if "FAIL" in ln],
        "env": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "cwd": os.getcwd(),
            "db": _state["db"],
        },
        "db": _db_metrics(_state["db"]),
    }
    try:
        import duckdb; payload["env"]["duckdb"] = duckdb.__version__
    except Exception:
        pass
    try:
        import numpy; payload["env"]["numpy"] = numpy.__version__
    except Exception:
        pass

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

    mark = "PASS" if ok else ("FAIL" if ok is False else "INCOMPLETE")
    print(f"\n[결과 기록] {mark}  →  {log_path} · {json_path}")
