# Havoc: A-to-Z build guide

## 0. What you have and what is verified
The full project is in this folder. Verified in a sandbox: data generator, anomaly detector,
FAISS retriever (offline hashing embeddings), LangGraph agent loop (scripted fake LLM), FastAPI,
ruff lint, 20 pytest tests. **Not verified (no network there): real Groq calls, the real
Hugging Face model download, `docker build`.** Expect to fix small things on those three.

## 1. Setup (15 min)
```bash
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt -r requirements-hf.txt
pip install -e .
cp .env.example .env     # put your key from console.groq.com in GROQ_API_KEY
```
Check https://console.groq.com/docs/models and set `GROQ_MODEL` to a current model that supports
tool use. If the 70B model hits free-tier token limits, switch to a smaller one for dry runs.

## 2. Run order (do these in order, stop at the first failure)
1. `python scripts/generate_data.py` (data/ is already included; this regenerates it)
2. `pytest` (all green means the plumbing works)
3. `python scripts/evaluate.py --skip-llm` (retrieval + anomaly numbers, no API key needed)
4. `python scripts/build_index.py`
5. `python scripts/evaluate.py --limit 5 --sleep 3` (dry run with the real LLM; watch tokens)
6. `python scripts/evaluate.py --variants baseline,agent_no_rag,agent --sleep 3` (full run;
   resumable, rerun if rate limited)
7. `uvicorn havoc.api:app --reload`, open http://127.0.0.1:8000/docs, try `INC-001`
8. `docker build -t havoc . && docker run -p 8000:8000 --env-file .env havoc`
9. Paste `results/results.md` numbers into README.md, then:
   `git init && git add . && git commit -m "Havoc" && git remote add origin <url> && git push -u origin main`
   Check the Actions tab goes green.

## 3. How it works (you must be able to explain every box)
| File | Job | Key idea |
|---|---|---|
| `catalog.py` | 15 faults: metric signature, log lines, runbook text | the synthetic "world" |
| `datagen.py` | writes metrics, logs, runbooks, postmortems, incidents | seeded, so reproducible; labels in a separate file the agent never reads |
| `anomaly.py` | robust z-score (median/MAD) per metric + IsolationForest | z-score is explainable; IF is the multivariate view |
| `telemetry.py` | reads metrics/logs, groups log lines by template | log pattern summarisation keeps prompts short |
| `retrieval.py` | loaders -> chunking -> embeddings -> FAISS | returns best chunk per *document*; hashing embeddings for CI |
| `agent.py` | LangGraph: classify -> reason <-> tools -> report | LLM chooses tools; final JSON is validated with one repair retry |
| `schemas.py` | Pydantic `RCAReport` | root_cause_id must be a known label |
| `api.py` | `/health`, `/incidents`, `/triage` | agent built lazily, injectable for tests |
| `scripts/evaluate.py` | hit@k, onset detection, RCA accuracy, Wilson CIs | resumable cache |

## 4. Likely failures
| Symptom | Fix |
|---|---|
| `GROQ_API_KEY is not set` | create `.env` in the repo root |
| 429 / rate limit in evaluate | raise `--sleep`, use `--limit`, switch `GROQ_MODEL`; re-run resumes |
| model rejects tool calls / `tool_use_failed` | switch to a model that supports tool use |
| `ModuleNotFoundError: havoc` | `pip install -e .` inside the venv |
| index/embedding errors after changing model | delete `index/` and rebuild |
| Docker build slow | normal: CPU PyTorch plus model download |

## 5. Interview questions you should be able to answer
- Why robust z-score (median/MAD) rather than mean/std? Outliers inflate std; MAD resists them.
- Why train IsolationForest on the baseline window only? Novelty detection: learn "normal".
- Why does retrieval return one chunk per document? Avoid three chunks from the same runbook.
- Why separate the report step from the tool loop? Cleaner JSON, fewer tokens, easier validation.
- What does the baseline prove, and what doesn't it? It sees no telemetry, so beating it is
  expected. The agent vs agent-without-RAG gap is the more honest result.
- What are the weaknesses? Synthetic data written by one author, small n, label leakage risk.
- How would you take it to production? Prometheus/Loki tools, real incident history, human
  approval before remediation, tracing, guardrails.

## 6. Resume rules
Only quote numbers from your own `results/results.md`. Example form:
"Built Havoc, an agentic incident-triage assistant (LangGraph, FAISS RAG, Groq tool calling,
scikit-learn anomaly detection, FastAPI, Docker, CI). On 30 labelled synthetic incidents it
reached X% RCA accuracy vs Y% for a no-retrieval LLM baseline; retrieval hit@3 = Z%."
Remove AWS from the skills line unless you actually deploy to EC2.

## 7. Time plan
Setup + tests 30 min, evaluation dry run 30 min, full eval 30-60 min (rate limits), Docker/CI
30 min, README + push 30 min. Read every file once and run the interview questions before you apply.
