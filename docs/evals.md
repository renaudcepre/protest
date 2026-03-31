# Evals

Evaluate LLM outputs with scored metrics and historical tracking.

## What is an Eval?

A test produces **pass/fail**. An eval produces **scores** — numeric values (0.0–1.0) that measure output quality. Scores are aggregated across cases, tracked over time, and compared between runs.

ProTest evals use the same infrastructure as tests: fixtures, DI, parallelism, tags. An eval is a test that returns a value, scored by evaluators.

## Quick Start

```python
# evals/session.py
from typing import Annotated

from protest import ForEach, From
from protest.evals import EvalCase, EvalSession, ModelInfo, evaluator
from protest.evals.evaluators import contains_keywords

cases = ForEach([
    EvalCase(inputs="Who is Marie?", expected="Marie, Resistance", name="lookup"),
    EvalCase(inputs="What is 2+2?", expected="4", name="math"),
])

session = EvalSession(model=ModelInfo(name="gpt-4o-mini"))

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
4. Bool verdicts determine pass/fail
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

Use `ctx.judge()` for structured LLM evaluation (requires `judge=` on `EvalSession`):

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
EvalCase(inputs="easy lookup", evaluators=[keyword_check(keywords=["paris"], min_recall=0.9)]),
EvalCase(inputs="hard causal", evaluators=[keyword_check(keywords=["paris"], min_recall=0.3)]),
```

### ShortCircuit

Skip expensive evaluators (LLM judges) when cheap ones already fail:

```python
from protest.evals import ShortCircuit

evaluators=[
    not_empty,                                     # always runs
    ShortCircuit([
        contains_expected_facts(min_score=0.3),    # 0ms — if fail → stop
        llm_judge(rubric="factual accuracy"),       # 3s — skipped if above fails
    ]),
]
```

`ShortCircuit` is a group of ordered evaluators. The first `Verdict=False` stops the group. Evaluators outside the `ShortCircuit` always run.

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
session = EvalSession(
    model=ModelInfo(name="qwen-2.5"),
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

If an evaluator calls `ctx.judge()` and no judge was passed to `EvalSession`, a `RuntimeError` is raised. This is treated as an **infrastructure error** (not a test failure), same as a fixture crash.

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

@session.eval(evaluators=[my_scorer])
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

If two evaluators return dataclasses with the same field name (e.g. both have `accuracy`), the runner prefixes with the evaluator name when it detects a conflict: `llm_judge.accuracy`, `fact_check.accuracy`.

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
- **`eval_hash`** — hash of evaluators. Changes when the scoring criteria change.

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
