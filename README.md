# iDPDM — Artifact

Anonymized artifact for *iDPDM: Inference-Time Dynamic Disclosure Control for
Enterprise Generative AI* (under review). It contains everything needed to
reproduce every headline number in the paper — the declarative policy
specification in executable form, the derived FinDW database, the frozen
parser prompt with its revision history, all query sets and canary
definitions, the decision core and evaluation runners with fixed seeds, run
outputs with manifests, and the parse cache, so **no API key or network
access is required** for any parser-in-loop number.

## Requirements

Python 3.11+ and `pip install -r requirements.txt` (DuckDB and pandas).
All stages are deterministic; runs complete in minutes on commodity hardware.

## Layout

| Folder | Contents |
|---|---|
| `spec/` | `constitution_v2.txt` — the frozen parser prompt (clauses C1–C6); `prompt_revisions.json` — the three disclosed revision hashes (r0 `d53760b479` → r1 `451ae980e9` → r2 `0203837a48`, frozen) with one-line rationale each. Parse caches are keyed by prompt hash, so runs cannot mix revisions. |
| `pipeline/` | The loader: rebuilds the full FinDW database from the original public banking corpus (Berka, PKDD 2000) — schema, organization, policy grid, classification, gold reports. The raw corpus itself is **not redistributed** (see Data provenance). |
| `src/` | Decision core (`09_decide_v2r.py`; `09_decide_v2.py` is the superseded core kept **only** to reproduce the appendix's trust-cap before/after) and all evaluation runners and probes. |
| `data/` | `findw_artifact.duckdb` — the derived FinDW state (fragments, policy grid, gold reports, organizational dimension, personnel layer, and the materialized `client_org_path` mapping) with the raw corpus tables removed; `parse_cache/` — 1,392 cached parses keyed by prompt hash. |
| `results/` | Every run output with its manifest. `out10/*_r3` are the canonical seven-arm runs behind Table V; manifests record the pinned model version, fragment- and query-set hashes, seeds, and software versions. |

## Quick start

Run from the artifact root, in order. Each step prints its gates; a run is
valid only if every gate reports PASS.

```
python src/check_divergence.py               # GT integrity: exactly 9 per-item/set-level divergences
python src/e2_e2e_a1r3.py --coords gt        # E2, oracle coordinates (gates G1–G4, G2a, G2r)
python src/e2_e2e_a1r3.py --coords parser    # E2, parser in the loop (cache-served)
python src/e3_adversarial_a1r3.py --coords gt      # E3 (gates incl. G7)
python src/e3_adversarial_a1r3.py --coords parser
python src/e5_opcurve_a1.py                  # E5 operating curves (P × k sweep)
python src/e1_parser_eval_r3.py              # E1 parser scoring against shipped parser_out.jsonl
python src/triple_gap_probe.py               # pairwise-boundary enumeration + constructed demo
python src/mkfigs_paper_all.py               # regenerates the paper figures
```

The shipped derived database is sufficient for every step above — verified
by re-running E2 with all gates against it. The raw corpus is needed only to
rebuild the database from scratch via `pipeline/`.

## Headline numbers → artifact

| Paper claim | Where it reproduces |
|---|---|
| Table V, iDPDM (E2E): leak 0/153, over-restriction 33/283 (11.7%), canary 0 | `results/out10/e2_summary_parser_r3.csv` |
| Table V, Full per-item (R3) idealized control: 0.7% (1 leak = the single governed at-ceiling small-group probe); gate G2r asserts r3only ≡ per-item ground truth on every row | `results/out10/e2_summary_gt_r3.csv`, `e2_results_gt_r3.csv` |
| Table V, legacy grants: menu 56.2 (86), ABAC-perm 56.2 (86), ABAC-restr 47.1 (72), over-restriction 0 | same summaries, arm rows |
| E3: bypass 0/118 (iDPDM); per-item control admits 8/118 — every session-composition turn and nothing else, incl. both linkage-canary releases (gate G7); flags 40/40 | `results/out10/e3_*_r3.*` |
| E1: attribute 94.9% (407/429, all residuals authorization-equivalent), subject relation 100% form-level (476/476) + 83/83 deferred, F5 stability 50% (10/20) | `results/` E1 outputs + `parser_out.jsonl` |
| E5 anchor (P0, k=5): zero leakage, zero review; k=2 leaks 6 session-differencing pairs; k=20 over-withholds 24/58 | E5 sweep outputs + `out_a1b/` |
| Pairwise boundary: 1,500 three-fragment / 2,330 four-fragment susceptible combinations; none single-response reachable; constructed ledger counterexample | `results/out06/triple_gap*.csv` |

## Reproducibility notes

- **Determinism.** Scoring never calls a model; the parser is served from
  `parse_cache/` under the frozen prompt hash. Every runner re-checks its
  gates and refuses to write outputs on gate failure.
- **Superseded numbers.** Corrections made before submission are disclosed
  in the paper itself (e.g., the earlier 24.9% over-restriction figure, the
  trust-cap revision, the 27 false blocks from an unconditional promotion
  rule). The old decision core is shipped solely so the before/after is
  checkable.
- **MLP+ceil arm.** Table V's learned-judgment row verifies from the
  shipped frozen predictions and outputs (`e2_mlp_*`); end-to-end retraining
  belongs to the companion submission's artifact.

## Data provenance and licensing

- Banking data: the Czech retail-banking corpus (Berka, PKDD 2000
  Discovery Challenge), released anonymized for research use. It is **not
  redistributed here**; `pipeline/` reconstructs FinDW from the original
  public release. The shipped database contains only derived artifacts
  (fragments, aggregates, the organizational dimension).
- Personnel layer: re-keyed rank-monotonically from the MySQL Employees
  sample database (CC BY-SA 3.0). No real individual appears; trust signals
  are synthetic.
- Organization: instantiated from a real institution's published chart down
  to team level; the institution is not named anywhere in this artifact.

## Anonymity

This artifact is anonymized for double-blind review. Absolute paths and
environment identifiers are masked as `<repo>` in shipped files.
