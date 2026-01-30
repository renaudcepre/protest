# Filtering System

ProTest supports composable filters: suite, keyword, tag, and last-failed. All filters are plugins that hook into `COLLECTION_FINISH`.

## Filter Chain

Filters compose via **intersection** (AND logic). Each filter reduces the test list for the next:

```
Collector.collect()
    │
    ▼
SuiteFilterPlugin.on_collection_finish()
    │
    ▼
KeywordFilterPlugin.on_collection_finish()
    │
    ▼
TagFilterPlugin.on_collection_finish()
    │
    ▼
CachePlugin.on_collection_finish()
    │
    ▼
Filtered tests → Runner
```

Order matters. Selective filters (suite, keyword, tag) run before cache to ensure `--lf` only considers tests matching other filters.

## Suite Filter

Filters tests by suite path, specified in the target.

```bash
protest run demo:session::API           # Suite "API" and children
protest run demo:session::API::Users    # Suite "API::Users" only
```

**Implementation**: `protest/filters/suite.py`

```python
class SuiteFilterPlugin(PluginBase):
    def on_collection_finish(self, items: list[TestItem]) -> list[TestItem]:
        if not self.suite_path:
            return items

        return [
            item for item in items
            if item.suite_path and (
                item.suite_path == self.suite_path
                or item.suite_path.startswith(f"{self.suite_path}::")
            )
        ]
```

- Matches exact path or prefix with `::`
- Standalone tests (no suite) are excluded when filtering by suite

## Keyword Filter

Filters by substring in test name (including case_ids for parameterized tests).

```bash
protest run demo:session -k "login"           # Tests containing "login"
protest run demo:session -k "login" -k "auth" # OR logic: "login" OR "auth"
```

**Implementation**: `protest/filters/keyword.py`

```python
class KeywordFilterPlugin(PluginBase):
    def on_collection_finish(self, items: list[TestItem]) -> list[TestItem]:
        if not self.keywords:
            return items

        def matches(item: TestItem) -> bool:
            # Match against "test_name[case_id]"
            name = item.test_name
            if item.case_ids:
                name = f"{name}[{','.join(item.case_ids)}]"
            return any(kw.lower() in name.lower() for kw in self.keywords)

        return [item for item in items if matches(item)]
```

- Case-insensitive matching
- Multiple keywords = OR logic

## Tag Filter

Filters by test tags (including inherited tags from fixtures and suites).

```bash
protest run demo:session -t database         # Tests with "database" tag
protest run demo:session -t slow -t unit     # OR: "slow" OR "unit"
protest run demo:session --no-tag flaky      # Exclude "flaky"
```

**Implementation**: `protest/tags/plugin.py`

See [Tags](../core-concepts/tags.md) for tag inheritance rules.

## Cache Filter (--lf)

Re-runs only tests that failed in the previous run.

```bash
protest run demo:session --lf          # Last-failed tests only
protest run demo:session --cache-clear # Clear cache first
```

**Implementation**: `protest/cache/plugin.py`

Behavior:
- Empty cache or no failures → all tests run
- Failures in cache → only matching failed tests run
- No matching tests → 0 tests (no fallback)

## Combining Filters

All filters compose:

```bash
# Suite + keyword
protest run demo:session::API -k "login"

# Suite + keyword + tag
protest run demo:session::API -k "login" -t "slow"

# Suite + keyword + tag + last-failed
protest run demo:session::API -k "login" -t "slow" --lf
```

Example reduction:
```
100 tests collected
 │
 ├─ ::API filter    → 40 tests (60 excluded)
 ├─ -k "login"      → 12 tests (28 excluded)
 ├─ -t "slow"       → 5 tests (7 excluded)
 └─ --lf            → 2 tests (3 passed last time)
```

## Writing Custom Filters

Create a plugin implementing `on_collection_finish`:

```python
class PriorityFilter(PluginBase):
    """Run high-priority tests first."""
    name = "priority"

    def on_collection_finish(self, items: list[TestItem]) -> list[TestItem]:
        def priority(item: TestItem) -> int:
            if "critical" in item.tags:
                return 0
            if "high" in item.tags:
                return 1
            return 2
        return sorted(items, key=priority)
```

Return `None` to pass through unchanged. Return a modified list to filter or reorder.

## See Also

- [Plugins](plugins.md) - Plugin development guide
- [Tags](../core-concepts/tags.md) - Tag inheritance
- [CLI](../getting-started/running-tests.md) - CLI options
