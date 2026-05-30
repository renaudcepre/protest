# Evals

Evaluate LLM outputs with scored metrics and historical tracking.

## Contents

- [What is an Eval?](#what-is-an-eval)
- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
- [EvalSuite](#evalsuite)
- [EvalCase](#evalcase)
- [Evaluators](#evaluators)
- [Fixtures](#fixtures)
- [ModelLabel](#modelinfo)
- [Judge](#judge)
- [TaskResult (SUT Usage Tracking)](#taskresult-sut-usage-tracking)
- [Usage Display](#usage-display)
- [Evaluator Errors](#evaluator-errors)
- [Name Collisions](#name-collisions)
- [Multi-Model Sessions](#multi-model-sessions)
- [CLI](#cli)
- [Output](#output)
- [History](#history)
- [Progress Output](#progress-output)

## What is an Eval?

A test produces **pass/fail**. An eval produces **scores** — numeric values (0.0–1.0) that measure output quality. Scores are aggregated across cases, tracked over time, and compared between runs.

ProTest evals use the same infrastructure as tests: fixtures, DI, parallelism, tags. An eval is a test that returns a value, scored by evaluators.

!!! tip "First-run expectations: don't expect 100% green"

    Unlike tests, evals are **expected to have failing cases** — that's
    the signal you're measuring. `protest eval` still exits 1 when any
    case fails a `Verdict` (so CI surfaces regressions), but the
    failures are not bugs, they're data points. The aggregate-stats
    table is designed for this — you watch the metrics drift over time.
    Every run is recorded to `.protest/history.jsonl` so the trend
    accumulates from day one (browsing and run-comparison tooling lands
    in a future release).

## Quick Start

```python
# evals/session.py
from typing import Annotated

from protest import ForEach, From, ProTestSession
from protest.evals import EvalCase, ModelLabel, evaluator
from protest.evals.evaluators import contains_keywords
from protest.evals import EvalSuite

cases = ForEach([
    EvalCase(inputs="Who is Marie?", expected="Marie, Resistance", name="lookup"),
    EvalCase(inputs="What is 2+2?", expected="4", name="math"),
])

session = ProTestSession()

chatbot_suite = EvalSuite("chatbot", model=ModelLabel(name="gpt-4o-mini"))
session.add_suite(chatbot_suite)

@chatbot_suite.eval(evaluators=[contains_keywords(keywords=["Marie"])])
async def chatbot(case: Annotated[EvalCase, From(cases)]) -> str:
    return await my_agent(case.inputs)
```

```bash
protest eval evals.session:session
```

## How It Works

`@suite.eval()` wraps a function to run evaluators on its return value:

1. Your function receives case data via `ForEach`/`From` (same as parameterized tests)
2. It returns the output (string, object, anything)
3. ProTest passes the output to evaluators → scores
4. Bool verdicts determine pass/fail
5. Aggregated stats appear in the terminal

The rest of the pipeline — fixtures, DI, parallelism, reporters — works identically to tests.

## EvalSuite

`EvalSuite` groups eval cases. It's the eval equivalent of `ProTestSuite` — it forces `kind=EVAL` and carries model/judge configuration. Model and judge are suite-level config: each suite declares which model produced its results and which judge scores them.

```python
from protest.evals import EvalSuite
from protest.evals import ModelLabel

chatbot_suite = EvalSuite("chatbot", model=ModelLabel(name="gpt-4o-mini"))
session.add_suite(chatbot_suite)

@chatbot_suite.eval(evaluators=[my_scorer])
async def chatbot(case: Annotated[EvalCase, From(cases)]) -> str:
    return await my_agent(case.inputs)
```

## EvalCase

Typed dataclass for eval case data. All eval cases **must** use `EvalCase` — plain dicts are not supported.

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
| `tags` | `list[str]` | First-class tags — flow to `protest eval --tag …` (see below) |
| `metadata` | `dict` | Arbitrary metadata, opaque to the framework |

### Why `EvalCase` and not a dict?

The runtime reads case data via attribute access (`case.expected`, `case.metadata`, `case.evaluators`), not by string key. A plain dict would compile fine but blow up at runtime, and you'd lose the IDE refactor/Ctrl+Click affordances. Making `EvalCase` a typed dataclass surfaces typos at import time and keeps the contract one obvious place — same trade-off as `Annotated[T, Use(fn)]` over pytest's name-based fixture lookup.

### Per-case `tags`

`EvalCase.tags` is a first-class field. Tags flow through the test collector and become first-class on the resulting `TestItem`, so `protest eval --tag slow` works out of the box. Use `metadata` for any other free-form annotation the framework should ignore.

```python
EvalCase(
    inputs="Long doc to summarize…",
    expected="…",
    name="long_doc_case",
    tags=["slow", "summarization"],
    metadata={"source_dataset": "v3"},  # opaque to the framework
)
```

```bash
protest eval evals.session:session --tag slow
protest eval evals.session:session --no-tag slow
```

## Evaluators

An evaluator is a function decorated with `@evaluator` that receives an `EvalContext` and returns a verdict. The decorator is mandatory: passing a plain function in `evaluators=[...]` raises `TypeError` at registration. The wrapping is what gives the evaluator its identity (used for hashing, history, reporting) and a typed `run(ctx)` method — there's no implicit conversion.

!!! info "If your eval task returns a non-string output"

    The built-in evaluators (`contains_keywords`, `not_empty`, `max_length`,
    `matches_regex`, `json_valid`, `word_overlap`) assume `ctx.output` is a
    string and call methods like `.lower()` on it. They drop in cleanly for
    summarization, chatbot replies, single-string completions, etc.

    For a structured output (`dict`, `dataclass`, `pydantic.BaseModel`, list
    of objects, …), the path is to write **custom evaluators** that
    pick the field they care about. A typical pattern:

    ```python
    @evaluator
    def category_matches_expected(ctx: EvalContext) -> CategoryMatch:
        expected = (ctx.expected_output or {}).get("category")
        actual = ctx.output.get("category")
        return CategoryMatch(category_matches=(expected == actual), ...)
    ```

    See *Structured Evaluator* below and *EvalContext* for the data
    you can read off `ctx`.

### Return Types

Evaluators return `bool` (simple verdict) or a `dataclass` (structured result). In dataclasses, annotate fields to tell the framework what each one is:

```python
from typing import Annotated
from protest.evals import Metric, Verdict, Reason
```

| Annotation | Role |
|------------|------|
| `Annotated[bool, Verdict]` | Verdict — pass/fail (`all(verdicts)`) |
| `Annotated[float, Metric]` | Metric — aggregated in stats (mean/p50/p95) |
| `Annotated[int, Metric]` | Metric — converted to float |
| `Annotated[str, Reason]` | Reason — displayed on failure, stored in history |

Unannotated fields are ignored by the runner — free metadata.

Returning `float`, `dict`, or any other non-dataclass/non-bool type raises `TypeError`.

### Tracking-Only Evaluators

A dataclass with `Metric` fields but no `Verdict` is tracking-only. The case always passes for this evaluator — it measures without gating.

```python
@dataclass
class OverlapMetrics:
    overlap: Annotated[float, Metric]

@evaluator
def word_overlap(ctx: EvalContext) -> OverlapMetrics:
    ...
```

In the terminal, tracking evaluators show with `·` instead of `✓`/`✗`:

```
✓  chatbot[lookup] (1.2s) keyword_recall=0.95 all_present=✓
·  chatbot[lookup]         overlap=0.80
```

### Simple Evaluator

```python
@evaluator
def not_empty(ctx: EvalContext) -> bool:
    return bool(ctx.output.strip())
```

### Structured Evaluator

```python
from dataclasses import dataclass
from typing import Annotated
from protest.evals import Metric, Verdict, Reason

@dataclass
class KeywordScores:
    keyword_recall: Annotated[float, Metric]
    all_present: Annotated[bool, Verdict]
    detail: Annotated[str, Reason] = ""

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

Use `ctx.judge()` for structured LLM evaluation (requires `judge=` on `EvalSuite`):

```python
@dataclass
class JudgeResult:
    accuracy: Annotated[float, Metric]
    accurate_enough: Annotated[bool, Verdict]
    reason: Annotated[str, Reason] = ""

@evaluator
async def llm_judge(ctx: EvalContext, rubric: str = "", min_score: float = 0.7) -> JudgeResult:
    return await ctx.judge(
        f"Evaluate this response on a 0-1 scale.\n\n"
        f"Response: {ctx.output}\nCriteria: {rubric}",
        JudgeResult,
    )
```

The judge handles structured output — no text parsing needed. See [Judge](#judge) for setup.

### Per-Case Thresholds

Different thresholds per case = different evaluator bindings:

```python
EvalCase(name="easy_lookup", inputs="easy lookup", evaluators=[keyword_check(keywords=["paris"], min_recall=0.9)]),
EvalCase(name="hard_causal", inputs="hard causal", evaluators=[keyword_check(keywords=["paris"], min_recall=0.3)]),
```

### ShortCircuit

Skip expensive evaluators (LLM judges) when cheap ones already fail:

```python
from protest.evals import ShortCircuit

evaluators=[
    not_empty,                                                  # always runs
    ShortCircuit([
        contains_keywords(keywords=["paris"], min_recall=0.5),  # 0ms — if fail → stop
        llm_judge(rubric="factual accuracy"),                   # 3s — skipped if above fails
    ]),
]
```

`ShortCircuit` is a group of ordered evaluators. The first `Verdict=False` stops the group. Evaluators outside the `ShortCircuit` always run.

Execution order — `evaluators=[a, ShortCircuit([b, c]), d]`:

```
a            ← always runs
├─ pass    → continue
└─ fail    → continue (a is outside the group, doesn't gate b/c)

[ShortCircuit group ──────────────────────────────────┐
  b          ← always runs (first in group)           │
  ├─ pass  → c                                        │
  └─ fail  → c skipped (Verdict=False stops group)    │
  c          ← runs only if b passed                  │
└─────────────────────────────────────────────────────┘

d            ← always runs (outside the group)
```

The list `evaluators=[…]` is sequential at the top level; a `ShortCircuit` is just a sub-group that may stop early. Use it to gate expensive evaluators (LLM judges) behind cheap ones (keyword/regex checks).

### Using Evaluators

```python
# No params → use directly
evaluators=[not_empty]

# With params → call to bind
evaluators=[contains_keywords(keywords=["python", "async"], min_recall=0.75)]

# Per-case evaluators (added to suite-level)
EvalCase(name="factual_accuracy_case", inputs="...", evaluators=[llm_judge(rubric="Check factual accuracy")])
```

### EvalContext

| Field / Method | Type | Description |
|----------------|------|-------------|
| `name` | `str` | Case name |
| `inputs` | `I` | Case inputs |
| `output` | `O` | Task return value |
| `expected_output` | `O \| None` | From `EvalCase.expected` |
| `metadata` | `Any` | From `EvalCase.metadata` |
| `duration` | `float` | Task execution time (seconds) |
| `judge(prompt, type)` | `async` | Call the configured LLM judge (see [Judge](#judge)) |
| `judge_call_count` | `int` | Number of judge calls made |

### Built-in Evaluators

| Evaluator | Params | Returns |
|-----------|--------|---------|
| `contains_keywords` | `keywords, min_recall=1.0` | `keyword_recall: float`, `all_keywords_present: bool` |
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

pipeline_suite = EvalSuite("pipeline")
session.add_suite(pipeline_suite)

@pipeline_suite.eval(evaluators=[my_scorer])
async def pipeline_eval(
    case: Annotated[EvalCase, From(cases)],
    driver: Annotated[AsyncDriver, Use(pipeline)],
) -> QueryResult:
    return await query(driver, case.inputs)
```

## ModelLabel

`ModelLabel` is a **passive label** that ProTest stores in the history alongside each run, so you can attribute results to a specific model and compare runs side-by-side. It does not route requests, set a temperature, pick a provider, or otherwise touch any LLM — the actual model wiring happens inside *your* task function (or the agent / SDK it calls).

```python
suite = EvalSuite("pipeline", model=ModelLabel(name="qwen-2.5"))
```

## Judge

A `Judge` is a protocol for LLM-as-judge evaluators. ProTest owns the interface — you plug in your LLM library.

### The Protocol

```python
class Judge(Protocol):
    async def judge(self, prompt: str, output_type: type[T]) -> JudgeResponse[T]: ...
```

Minimal contract: takes a prompt and a return type, returns a `JudgeResponse` wrapping the typed result with optional usage stats. All configuration (model, temperature, system prompt, max_tokens) lives in your implementation's constructor, not in the protocol.

### Writing a Judge

The `judge()` method returns a `JudgeResponse[T]` that wraps the output with optional usage stats:

```python
from pydantic_ai import Agent
from protest.evals import JudgeResponse

class PydanticAIJudge:
    name = "gpt-4o-mini"       # used in history
    provider = "openai"        # optional, used in history

    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0):
        self.model = model
        self.temperature = temperature

    async def judge(self, prompt: str, output_type: type[T]) -> JudgeResponse[T]:
        agent = Agent(self.model, output_type=output_type)
        result = await agent.run(prompt)
        usage = result.usage()
        return JudgeResponse(
            output=result.output,
            input_tokens=usage.request_tokens,
            output_tokens=usage.response_tokens,
            cost=usage.request_tokens * 0.15/1e6 + usage.response_tokens * 0.60/1e6,
        )
```

Tokens and cost are optional — omit them if your provider doesn't expose usage data:

```python
return JudgeResponse(output=result.output)  # tokens/cost = None, that's fine
```

### Configuring the Judge

```python
suite = EvalSuite(
    "pipeline",
    model=ModelLabel(name="qwen-2.5"),
    judge=PydanticAIJudge(model="gpt-4o-mini", temperature=0),
)
```

`JudgeInfo` (name, provider) is derived automatically from the instance for history tracking.

### Using the Judge in Evaluators

Evaluators access the judge via `ctx.judge()`:

```python
@dataclass
class JudgeResult:
    accurate: Annotated[bool, Verdict]
    reason: Annotated[str, Reason] = ""

@evaluator
async def llm_rubric(ctx: EvalContext, rubric: str = "") -> JudgeResult:
    return await ctx.judge(
        f"Evaluate this response.\n\nResponse: {ctx.output}\nCriteria: {rubric}",
        JudgeResult,  # structured output — no text parsing
    )
```

For simple verdicts, use `bool` or `str` as `output_type`:

```python
@evaluator
async def simple_judge(ctx: EvalContext) -> bool:
    return await ctx.judge(f"Is this a valid answer? {ctx.output}", bool)
```

### No Judge Configured

If an evaluator calls `ctx.judge()` and no judge was passed to `EvalSuite`, a `RuntimeError` is raised. This is treated as an **infrastructure error** (not a test failure), same as a fixture crash.

### Usage Tracking

Each call to `ctx.judge()` is counted. Tokens and cost from `JudgeResponse` are accumulated per case and flow to `EvalPayload`:

| Field | Description |
|-------|-------------|
| `judge_call_count` | Number of judge calls |
| `judge_input_tokens` | Total input tokens |
| `judge_output_tokens` | Total output tokens |
| `judge_cost` | Total cost (user-computed) |

These are available in history, letting you track LLM usage across runs.

## TaskResult (SUT Usage Tracking)

If your eval task calls an LLM, you can report usage by returning `TaskResult` instead of a plain value:

```python
from protest.evals import TaskResult

@chatbot_suite.eval(evaluators=[my_scorer])
async def chatbot(case: Annotated[EvalCase, From(cases)]) -> TaskResult[str]:
    result = await agent.run(case.inputs)
    usage = result.usage()
    return TaskResult(
        output=result.output,
        input_tokens=usage.request_tokens,
        output_tokens=usage.response_tokens,
        cost=usage.request_tokens * 0.10/1e6 + usage.response_tokens * 0.30/1e6,
    )
```

This is **opt-in** — returning a plain `str` still works. ProTest unwraps `TaskResult` transparently: evaluators see the plain output, usage stats flow to the reporter and history.

## Usage Display

When task or judge usage data is available, ProTest shows a summary after the eval stats:

```
  Passed: 16/26 (61.5%)
  Task: 45.2k in / 27.1k out, $0.0142
  Judge: 5 calls, 800 in / 400 out, $0.0030
```

Lines only appear when there is data. No `TaskResult` = no Task line. No judge configured = no Judge line.

## Evaluator Errors

If an evaluator raises an exception (e.g. LLM judge timeout), the case is marked as **error** (not fail). The stack trace appears in the output.

> **Tip:** For non-deterministic evaluators (LLM judges), catch exceptions in the evaluator and return a verdict indicating failure rather than letting them propagate.

## Name Collisions

Each `Verdict` / `Metric` / `Reason` field name from a dataclass evaluator
becomes a key in the per-case score dict (and in the history file). **Names
must be unique across all evaluators that run on the same case.**

If two evaluators emit a score under the same name (e.g. both have a
`detail` field), ProTest raises `ScoreNameCollisionError` at runtime so the
collision is loud instead of silently overwriting the duplicate. Rename the
colliding field — typically by prefixing with the evaluator's concept:

```python
@dataclass
class SummaryShape:
    summary_well_formed: Annotated[bool, Verdict]
    summary_detail: Annotated[str, Reason] = ""        # not just "detail"

@dataclass
class CategoryMatch:
    category_matches: Annotated[bool, Verdict]
    category_match_detail: Annotated[str, Reason] = ""  # not just "detail"
```

Why no auto-prefix? An evaluator's score name is what users grep for in
history, scripts, and the markdown artifacts. Auto-prefixing would mean the
same evaluator's `accuracy` field changes name (`fact_check.accuracy` vs
plain `accuracy`) depending on which other evaluators are wired in alongside
it — silently breaking downstream consumers when a new evaluator is added.
Failing loud and asking you to pick a stable, unique name keeps the score
identifiers stable across configurations.

## Multi-Model Sessions

Track which model produced each eval suite's results. Each `EvalSuite` can have its own model:

```python
session = ProTestSession()

pipeline_suite = EvalSuite("pipeline", model=ModelLabel(name="qwen-2.5"))
chatbot_suite = EvalSuite("chatbot", model=ModelLabel(name="mistral-7b"))

session.add_suite(pipeline_suite)
session.add_suite(chatbot_suite)

@pipeline_suite.eval(evaluators=[...])
async def pipeline_eval(case, driver) -> str: ...

@chatbot_suite.eval(evaluators=[...])
async def chatbot_eval(case, deps) -> str: ...
```

Each run records the model per suite in `.protest/history.jsonl`, so a
mixed-model session (e.g. `pipeline` on `qwen-2.5`, `chatbot` on
`mistral-7b`) keeps each suite's model alongside its scores.

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
   ✓   chatbot[lookup] (1.2s) keyword_recall=1.00 all_keywords_present=✓
   ✗   chatbot[math]: all_keywords_present=False
       │ inputs: What is 2+2?
       │ output: The answer is 4.
       │ expected: 4
       │ detail: found 0/1

           Eval: chatbot (2 cases)
┏━━━━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━┳━━━━━━┳━━━━━━┓
┃ Score           ┃ mean ┃  p50 ┃   p5 ┃  p95 ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━╇━━━━━━╇━━━━━━┩
│ keyword_recall  │ 0.50 │ 0.50 │ 0.00 │ 1.00 │
└─────────────────┴──────┴──────┴──────┴──────┘
  Passed: 1/2 (50.0%)
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

Every eval run is persisted as one JSONL entry in `.protest/history.jsonl`,
recorded from the first run so trends accumulate over time. Each entry holds
per-suite pass rates, per-case verdicts and scores, the model per suite, and
git metadata. Tooling to browse, trend and compare runs lands in a future
release; the file is a stable, schema-versioned format you can also read
yourself in the meantime.

### Integrity Hashes

Each case in history carries two hashes:

- **`case_hash`** — hash of inputs + expected output. Changes when the test data changes.
- **`eval_hash`** — hash of evaluators. Changes when the scoring criteria change.

These hashes are what lets a later comparison distinguish a real regression
from a definition change: when a case's `eval_hash` differs between two runs,
the score moved because the scoring criteria changed ("scoring modified"), not
because the system under test regressed.

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
