# -*- coding: utf-8 -*-
"""
parser_run_v2.py — E1 파서 로컬 실행기 + E6 latency 측정 (08_parser_spec 준수)
배치: findw_v2/ 폴더 (constitution_v2.txt · deriv/query_set_v2.csv와 같은 트리).

실행:
  set OPENAI_API_KEY=...            (PowerShell: $env:OPENAI_API_KEY="...")
  python parser_run_v2.py                          # E1: 559행 파스 → parser_out.jsonl
  python parser_run_v2.py --latency                # E6: cold/warm latency (파스 완료 후)
  python parser_run_v2.py --model gpt-4.1          # 모델 핀 (기본 gpt-4.1 — judge와 동일 계열)

08 스펙 규율 구현:
  · 프롬프트 동결: constitution_v2.txt 해시 = 캐시 키 성분 + manifest 기재 (C14)
  · 캐시 키 = sha256(prompt)[:16] + sha256(query_text)[:16] — 프롬프트 변경 시 전량 무효화
  · 모든 질의 무조건 기록 (API 오류도 상태 코드와 함께 — 조용한 스킵 금지)
  · 원자적 저장 · manifest(prompt_hash·model·query_set_hash·cache_hits)
출력:
  parser_out.jsonl   (query_id별 π(q) — 08 스펙 §2 스키마)
  e1_run_manifest.json
  e6_latency.csv     (--latency 시: phase[cold|warm], query_id, ms)
이후 채점: python e1_parser_eval.py  (08 세션 산출 채점기 — 같은 폴더/경로 인자 확인)
"""
import os, sys, json, csv, time, hashlib, argparse, tempfile

ap = argparse.ArgumentParser()
ap.add_argument("--queryset", default= "query_set_v2.csv")
ap.add_argument("--constitution", default="constitution_v2.txt")
ap.add_argument("--out", default="parser_out.jsonl")
ap.add_argument("--cache-dir", default="parse_cache")
ap.add_argument("--model", default="gpt-4.1")
ap.add_argument("--latency", action="store_true",
                help="E6: cold 30건(캐시 우회 신규 호출) + warm 559건(캐시 적중) 측정")
ap.add_argument("--latency-n-cold", type=int, default=30)
args = ap.parse_args()

def sha16(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode("utf-8")).hexdigest()[:16]

PROMPT = open(args.constitution, encoding="utf-8").read()
PROMPT_HASH = sha16(PROMPT)
QS_BYTES = open(args.queryset, "rb").read()
QS_HASH = sha16(QS_BYTES)
rows = list(csv.DictReader(open(args.queryset, encoding="utf-8")))
assert len(rows) == 559 and "query_text_ko" in rows[0], "query_set 단언 실패"
os.makedirs(args.cache_dir, exist_ok=True)

FIELDS = ["attribute_group", "req_tier", "subject_relation", "subject_hint",
          "task_type", "stated_purpose", "injection_suspected", "ambiguous"]

try:
    from openai import OpenAI
    client = OpenAI()
except Exception as e:
    sys.exit(f"[중단] openai 패키지/키 확인: pip install openai · OPENAI_API_KEY 설정 ({e})")

def call_llm(qtext):
    """1질의 파스 — temperature 0, JSON 강제. 반환 (π dict|None, status, ms, model_str)."""
    t0 = time.perf_counter()
    try:
        r = client.chat.completions.create(
            model=args.model, temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": PROMPT},
                      {"role": "user", "content": qtext}])
        ms = (time.perf_counter() - t0) * 1000
        pi = json.loads(r.choices[0].message.content)
        missing = [f for f in FIELDS if f not in pi]
        if missing:
            return pi, f"SCHEMA_MISSING:{','.join(missing)}", ms, r.model
        return pi, "OK", ms, r.model
    except Exception as e:
        return None, f"API_ERROR:{type(e).__name__}", (time.perf_counter() - t0) * 1000, args.model

def cache_path(qtext):
    return os.path.join(args.cache_dir, f"{PROMPT_HASH}_{sha16(qtext)}.json")

def parse_one(qtext, force_fresh=False):
    cp = cache_path(qtext)
    if not force_fresh and os.path.exists(cp):
        t0 = time.perf_counter()
        d = json.load(open(cp, encoding="utf-8"))
        return d["pi"], d["status"], (time.perf_counter() - t0) * 1000, d["model"], True
    pi, status, ms, model = call_llm(qtext)
    fd, tmp = tempfile.mkstemp(dir=args.cache_dir, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(dict(pi=pi, status=status, ms=ms, model=model), fh, ensure_ascii=False)
    os.replace(tmp, cp)
    return pi, status, ms, model, False

def main_parse():
    outs, hits, model_seen = [], 0, set()
    t_start = time.time()
    for i, r in enumerate(rows, 1):
        pi, status, ms, model, hit = parse_one(r["query_text_ko"])
        hits += hit; model_seen.add(model)
        rec = dict(query_id=r["query_id"], status=status, model=model,
                   latency_ms=round(ms, 1), cache_hit=hit)
        rec.update({f: (pi or {}).get(f) for f in FIELDS})
        outs.append(rec)
        if i % 50 == 0 or i == len(rows):
            n_err = sum(1 for o in outs if o["status"] != "OK")
            print(f"  {i}/{len(rows)}  cache_hit {hits}  err {n_err}  "
                  f"({time.time()-t_start:.0f}s)", flush=True)
    fd, tmp = tempfile.mkstemp(dir=".", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        for o in outs:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")
    os.replace(tmp, args.out)
    n_err = sum(1 for o in outs if o["status"] != "OK")
    man = dict(prompt_hash=PROMPT_HASH, model=args.model, model_seen=sorted(model_seen),
               query_set_hash=QS_HASH, fragset_hash="f8e3611da9d8e1d8",
               n_queries=len(outs), n_error=n_err, cache_hits=hits,
               revision_history="constitution_v2 동결본 1판 (개정 시 여기 궤적 기록)")
    fd, tmp = tempfile.mkstemp(dir=".", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, "e1_run_manifest.json")
    print(f"완료 — {args.out} · e1_run_manifest.json  (오류 {n_err}건: 상태 코드로 기록됨)")
    print(f"다음: python e1_parser_eval.py  →  e1_scores.csv · e1_manifest.json")

def main_latency():
    """E6 — v1 프로토콜: cold(신규 호출) vs warm(캐시 적중). 파스 완주 후 실행."""
    import statistics as st
    recs = []
    cold = rows[:: max(1, len(rows) // args.latency_n_cold)][: args.latency_n_cold]
    print(f"cold {len(cold)}건 (캐시 우회 신규 호출)…")
    for r in cold:
        _, status, ms, _, _ = parse_one(r["query_text_ko"], force_fresh=True)
        recs.append(dict(phase="cold", query_id=r["query_id"], status=status, ms=round(ms, 1)))
    print(f"warm {len(rows)}건 (캐시 적중)…")
    for r in rows:
        _, status, ms, _, hit = parse_one(r["query_text_ko"])
        recs.append(dict(phase="warm", query_id=r["query_id"], status=status, ms=round(ms, 3)))
        assert hit or status.startswith("API_ERROR"), "warm 단계에 캐시 미스 — 파스 먼저 완주할 것"
    fd, tmp = tempfile.mkstemp(dir=".", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["phase", "query_id", "status", "ms"])
        w.writeheader(); w.writerows(recs)
    os.replace(tmp, "e6_latency.csv")
    for ph in ("cold", "warm"):
        v = sorted(x["ms"] for x in recs if x["phase"] == ph and x["status"] == "OK")
        if v:
            print(f"  {ph:4s}: n={len(v)}  p50={st.median(v):.1f}ms  "
                  f"p95={v[int(0.95*len(v))-1]:.1f}ms  mean={st.mean(v):.1f}ms")
    print("완료 — e6_latency.csv  (※ 판정·집행은 로컬 결정론 — generation 제외 명기 = B11)")

if __name__ == "__main__":
    print(f"parser_run_v2 — model={args.model} · prompt_hash={PROMPT_HASH} · qs_hash={QS_HASH}")
    main_latency() if args.latency else main_parse()
