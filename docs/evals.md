# Evals

Evaluate LLM outputs with scored metrics, thresholds, and historical tracking.

## What is an Eval?

A test produces **pass/fail**. An eval produces **scores** — numeric values (0.0–1.0) that measure output quality. Scores are aggregated across cases, tracked over time, and compared between runs.

ProTest evals use the same infrastructure as tests: fixtures, DI, parallelism, tags. An eval is a test that returns a value, scored by evaluators.

## Quick Start

```python
# evals/session.py
from typing import Annotated

from protest import ForEach, From
from protest.evals import EvalCase, EvalSession, evaluator
from protest.evals.evaluators import contains_keywords

cases = ForEach([
    EvalCase(inputs="Who is Marie?", expected="Marie, Resistance", name="lookup"),
    EvalCase(inputs="What is 2+2?", expected="4", name="math"),
])

session = EvalSession()

@session.eval(evaluators=[contains_keywords(keywords=["Marie"])])
async def chatbot(case: Annotated[EvalCase, From(cases)]) -> str:
    return await my_agent(case.inputs)
```

```bash
protest eval evals.session:session
```

## How It Works

`@session.eval()` wraps a function to run evaluators on its return value:

1. Your function receives case data via `ForEach`/`From` (same as parameterized tests)
2. It returns the output (string, object, anything)
3. ProTest passes the output to evaluators → scores
4. Scores determine pass/fail via thresholds
5. Aggregated stats appear in the terminal

The rest of the pipeline — fixtures, DI, parallelism, reporters — works identically to tests.

## EvalSession

`EvalSession` is a session configured for evals. History is enabled by default.

```python
from protest.evals import EvalSession, ModelInfo

session = EvalSession(
    model=ModelInfo(name="gpt-4o-mini"),    # tracked in history
    concurrency=4,                          # parallel eval cases
    metadata={"version": "1.0"},            # stored in history
)
```

## EvalCase

Typed dataclass for eval case data. Provides IDE autocompletion instead of untyped dicts.

```python
from protest.evals import EvalCase

cases = ForEach([
    EvalCase(inputs="What is 2+2?", expected="4", name="math"),
    EvalCase(inputs="Who is Napoleon?", expected="emperor, France", name="history"),
])
```

| Field | Type | Description |
|-------|------|-------------|
| `inputs` | `Any` | Input to your task function |
| `expected` | `Any` | Expected output (passed to evaluators as `ctx.expected_output`) |
| `name` | `str` | Case identifier (used in test IDs and history) |
| `evaluators` | `list` | Per-case evaluators (added to suite-level ones) |
| `metadata` | `dict` | Arbitrary metadata |

## Evaluators

An evaluator is a function decorated with `@evaluator` that receives an `EvalContext` and returns a verdict.

### Return Types

Evaluators return `bool` (simple verdict) or a `dataclass` (structured result). The framework reads fields by type:

| Field Type | Role |
|------------|------|
| `bool` | Verdict — pass/fail (`all(bool_fields)`) |
| `float` | Metric — aggregated in stats (mean/p50/p95) |
| `str` | Reason — displayed on failure, stored in history |

Returning `float`, `dict`, or any other type raises `TypeError`.

### Simple Evaluator

```python
@evaluator
def not_empty(ctx: EvalContext) -> bool:
    return bool(ctx.output.strip())
```

### Structured Evaluator

```python
from dataclasses import dataclass

@dataclass
class KeywordScores:
    keyword_recall: float      # metric → stats
    all_present: bool          # verdict → pass/fail
    detail: str = ""           # reason → shown on failure

@evaluator
def keyword_check(ctx: EvalContext, keywords: list[str], min_recall: float = 0.5) -> KeywordScores:
    found = [k for k in keywords if k.lower() in ctx.output.lower()]
    recall = len(found) / len(keywords)
    return KeywordScores(
        keyword_recall=recall,
        all_present=recall >= min_recall,
        detail=f"found {len(found)}/{len(keywords)}",
    )
```

The threshold (`min_recall`) is a parameter of the evaluator, not a framework concept. The evaluator decides the verdict.

### Async (LLM Judge)

```python
@dataclass
class JudgeResult:
    accuracy: float
    accurate_enough: bool
    reason: str = ""

@evaluator
async def llm_judge(ctx: EvalContext, rubric: str = "", min_score: float = 0.7) -> JudgeResult:
    result = await judge_agent.run(f"Evaluate: {ctx.output}\nCriteria: {rubric}")
    score = parse_score(result)
    return JudgeResult(accuracy=score, accurate_enough=score >= min_score, reason=result.explanation)
```

### Per-Case Thresholds

Different thresholds per case = different evaluator bindings:

```python
EvalCase(inputs="easy lookup", evaluators=[keyword_check(keywords=["paris"], min_recall=0.9)]),
EvalCase(inputs="hard causal", evaluators=[keyword_check(keywords=["paris"], min_recall=0.3)]),
```

### Using Evaluators

```python
# No params → use directly
evaluators=[not_empty]

# With params → call to bind
evaluators=[keyword_check(keywords=["python", "async"], min_recall=0.75)]

# Per-case evaluators (added to suite-level)
EvalCase(inputs="...", evaluators=[llm_judge(rubric="Check factual accuracy")])
```

### EvalContext

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Case name |
| `inputs` | `I` | Case inputs |
| `output` | `O` | Task return value |
| `expected_output` | `O \| None` | From `EvalCase.expected` |
| `metadata` | `Any` | From `EvalCase.metadata` |
| `duration` | `float` | Task execution time (seconds) |

### Built-in Evaluators

| Evaluator | Params | Returns |
|-----------|--------|---------|
| `contains_keywords` | `keywords, min_recall=0.0` | `keyword_recall: float`, `all_keywords_present: bool` |
| `contains_expected` | `case_sensitive=False` | `bool` |
| `does_not_contain` | `forbidden` | `no_forbidden_words: bool` |
| `not_empty` | — | `bool` |
| `max_length` | `max_chars=500` | `conciseness: float`, `within_limit: bool` |
| `min_length` | `min_chars=1` | `bool` |
| `matches_regex` | `pattern` | `bool` |
| `json_valid` | `required_keys=[]` | `valid_json: bool`, `has_required_keys: bool` |
| `word_overlap` | — | `overlap: float` (tracking-only) |

## Fixtures

Evals use the same fixture system as tests. Expensive setup (database, pipeline, graph) runs once and is shared across all cases.

```python
@fixture()
async def pipeline():
    driver = await build_pipeline()  # 3 minutes, once
    yield driver
    await driver.close()

session.bind(pipeline)

@session.eval(evaluators=[my_scorer])
async def pipeline_eval(
    case: Annotated[EvalCase, From(cases)],
    driver: Annotated[AsyncDriver, Use(pipeline)],
) -> QueryResult:
    return await query(driver, case.inputs)
```

## ModelInfo

`ModelInfo` is a **label for history tracking** — it does not configure or route to any model. It records which model produced the results so you can compare runs.

```python
session = EvalSession(model=ModelInfo(name="qwen-2.5"))
```

## Evaluator Errors

If an evaluator raises an exception (e.g. LLM judge timeout), the case is marked as **error** (not fail). The stack trace appears in the output. Scores from other evaluators that ran before the error are lost.

> **Tip:** For non-deterministic evaluators (LLM judges), catch exceptions in the evaluator and return a score indicating failure rather than letting them propagate.

## Multi-Model Sessions

Track which model produced each eval suite's results:

```python
pipeline_model = ModelInfo(name="qwen-2.5")
chat_model = ModelInfo(name="mistral-7b")

session = EvalSession(model=pipeline_model)

@session.eval(evaluators=[...], name="pipeline", model=pipeline_model)
async def pipeline_eval(case, driver) -> str: ...

@session.eval(evaluators=[...], name="chatbot", model=chat_model)
async def chatbot_eval(case, deps) -> str: ...
```

`protest history --runs` shows the model per suite:

```
#1   2026-03-28T09:14  57/81 (70%)  cb6f7bc
     pipeline             29/39 (74%)  qwen-2.5
     chatbot              10/21 (48%)  mistral-7b
```

## CLI

```bash
# Run evals
protest eval evals.session:session

# Parallelism
protest eval evals.session:session -n 4

# Filter by tag
protest eval evals.session:session --tag chatbot

# Filter by name
protest eval evals.session:session -k "lookup"

# Re-run failures only
protest eval evals.session:session --last-failed

# Verbosity: scores inline
protest eval evals.session:session -v

# Show eval inputs/output/expected on passing cases
protest eval evals.session:session --show-output

# Show captured log records
protest eval evals.session:session --show-logs
protest eval evals.session:session --show-logs=DEBUG
```

Flags are independent and combinable: `-v --show-output --show-logs`.

> **Note:** Failed eval cases always show inputs/output/expected — no flag needed.

## Output

### Default

```
   ✓   chatbot[lookup] (3.39s) facts_score=1.00 facts_ok=✓
   ✗   chatbot[causal]: facts_ok=False, LLMJudge=False

         Eval: chatbot (26 cases)
┏━━━━━━━━━━━━━┳━━━━━━┳━━━━━━┳━━━━━━┳━━━━━━┓
┃ Score       ┃ mean ┃  p50 ┃   p5 ┃  p95 ┃
┡━━━━━━━━━━━━━╇━━━━━━╇━━━━━━╇━━━━━━╇━━━━━━┩
│ facts_score │ 0.37 │ 0.00 │ 0.00 │ 1.00 │
└─────────────┴──────┴──────┴──────┴──────┘
  Passed: 14/26 (53.8%)
  Results: .protest/results/chatbot_20260329_091422
```

### Per-Case Results

Each eval case writes a markdown file to `.protest/results/<suite>_<timestamp>/`:

```
.protest/results/chatbot_20260329_091422/
├── lookup.md
├── causal.md
└── negative.md
```

## History

Eval results are persisted as JSONL in `.protest/history.jsonl`. Track trends across runs.

```bash
# Run list with per-suite breakdown
protest history --evals --runs

# Detailed view of latest run
protest history --evals --show

# Compare last two runs (fixed/regressed/new)
protest history --evals --compare
```

### Integrity Hashes

Each case in history carries two hashes:

- **`case_hash`** — hash of inputs + expected output. Changes when the test data changes.
- **`eval_hash`** — hash of evaluators + thresholds. Changes when the scoring criteria change.

`protest history --compare` uses these hashes to detect modified cases vs regressions. If a case's `eval_hash` changed between runs, it's reported as "scoring modified" rather than a real regression.

## Progress Output

For long-running fixtures, use `console.print` to show progress without polluting test capture:

```python
from protest import console

@fixture()
async def pipeline():
    for i, scene in enumerate(scenes):
        console.print(f"[cyan]pipeline:[/] importing {scene.name} ({i+1}/{len(scenes)})")
        await import_scene(scene)
    return driver
```

Messages appear inline in the reporter output. Rich markup is supported (stripped for ASCII).
