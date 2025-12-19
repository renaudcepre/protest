# Dependency Injection Internals

ProTest uses explicit, tree-based dependency injection. The scope of a fixture is
determined by **where** you decorate it, not by an enum parameter.

## Scope Hierarchy

```
ProTestSession
    │
    ├── Session fixtures (@session.fixture)
    │       └── Cached once, shared across all tests
    │
    ├── ProTestSuite "API"
    │       │
    │       ├── Suite fixtures (@api_suite.fixture)
    │       │       └── Cached per suite, shared within suite
    │       │
    │       └── ProTestSuite "API::Users"
    │               │
    │               └── Suite fixtures (@users_suite.fixture)
    │                       └── Cached for this nested suite
    │
    └── Tests
            └── Test fixtures (@fixture)
                    └── Fresh per test
```

## Scope Rules

### Decorator → Scope Mapping

| Decorator            | Scope   | Internal `scope_path`                    |
|----------------------|---------|------------------------------------------|
| `@session.fixture()` | Session | `None`                                   |
| `@suite.fixture()`   | Suite   | `suite.full_path` (e.g., `"API::Users"`) |
| `@fixture()`         | Test    | `"<test_scope>"`                         |

### Nested Suite Paths

Suites can be nested, and the `full_path` reflects the hierarchy:

```python
api_suite = ProTestSuite("API")
users_suite = ProTestSuite("Users")
api_suite.add_suite(users_suite)

# users_suite.full_path == "API::Users"
```

### Scope Validation

A fixture can only depend on fixtures with **equal or wider** scope:

| Requester Scope | Can Depend On            |
|-----------------|--------------------------|
| Session         | Session only             |
| Suite `"A"`     | Session, `"A"`           |
| Suite `"A::B"`  | Session, `"A"`, `"A::B"` |
| Test            | Anything                 |

Violating this raises `ScopeMismatchError`:

```python
@fixture()  # Test scope
def per_test():
    return "fresh"


@session.fixture()
def shared(x: Annotated[str, Use(per_test)]):
    # ERROR: Session can't depend on test-scoped fixture
    pass
```

## Resolution Flow

When a test requests a fixture, the resolver follows this flow:

```
resolve(fixture_func)
    │
    ├── Check cache (scope-appropriate)
    │       └── Hit? Return cached value
    │
    ├── Acquire lock (prevents duplicate resolution)
    │
    ├── Resolve dependencies (recursive)
    │
    ├── Execute fixture function
    │       ├── Regular function → call and get result
    │       └── Generator (yield) → wrap in context manager
    │
    ├── Cache result
    │
    └── Return value
```

### Three Cache Levels

| Scope   | Where Cached                            | Lifetime         |
|---------|-----------------------------------------|------------------|
| Session | `Resolver._registry[func].cached_value` | Entire session   |
| Suite   | `Resolver._path_caches[path][func]`     | While suite runs |
| Test    | `TestExecutionContext._cache[func]`     | Single test      |

Resolution is thread-safe. Concurrent tests requesting the same session fixture will
wait for the first resolution to complete, then share the cached value.

## Fixture Lifecycle

Generator fixtures use `yield` to separate setup from teardown:

```python
@session.fixture()
async def database():
    db = await connect()  # Setup
    yield db  # Value used by tests
    await db.close()  # Teardown
```

### Event Sequence

```
FIXTURE_SETUP_START
       │
       ▼
[Execute until yield]
       │
       ▼
FIXTURE_SETUP_DONE
       │
       ▼
[Fixture value used by tests]
       │
       ▼
FIXTURE_TEARDOWN_START
       │
       ▼
[Resume after yield]
       │
       ▼
FIXTURE_TEARDOWN_DONE
```

### LIFO Teardown

Fixtures are torn down in reverse order of setup using `AsyncExitStack`:

```
Setup order:    database → api_client → user_factory
Teardown order: user_factory → api_client → database
```

This guarantees dependencies outlive their dependents.

## Test Isolation

Each test runs in its own `TestExecutionContext`, which provides:

- **Own cache**: Test-scoped fixtures are stored here, not shared
- **Own exit stack**: Manages teardown for that test's fixtures

```python
class TestExecutionContext:
    def __init__(self, parent: Resolver, suite_path: str | None):
        self._parent = parent
        self._cache: dict[FixtureCallable, Any] = {}
        self._exit_stack = AsyncExitStack()

    async def resolve(self, target_func: FixtureCallable) -> Any:
        return await self._parent.resolve(
            target_func,
            current_path=self._suite_path,
            context_cache=self._cache,  # Injected
            context_exit_stack=self._exit_stack,
        )
```

When a test requests a fixture:

- **Test-scoped**: Uses the context's local cache and exit stack
- **Suite/Session-scoped**: Delegated to the parent Resolver's global caches

This allows parallel tests to have independent test-scoped fixtures while sharing
session/suite fixtures.

## For Plugin Developers

Plugins can hook into fixture lifecycle via four events: `FIXTURE_SETUP_START`,
`FIXTURE_SETUP_DONE`, `FIXTURE_TEARDOWN_START`, and `FIXTURE_TEARDOWN_DONE`.
See [Events](events.md#fixture-lifecycle) for the complete reference.

### FixtureInfo Payload

All fixture events emit `FixtureInfo`:

```python
@dataclass(frozen=True, slots=True)
class FixtureInfo:
    name: str  # Fixture function name
    scope: FixtureScope  # SESSION, SUITE, or TEST
    scope_path: str | None = None  # Suite path or None
    duration: float = 0  # Setup/teardown time
    autouse: bool = False  # Auto-resolved fixture
```

### Example: Tracking Fixture Durations

```python
from protest.plugin import PluginBase
from protest.entities import FixtureInfo


class FixtureDurationPlugin(PluginBase):
    name = "fixture-durations"

    def __init__(self):
        self.durations: dict[str, float] = {}

    def on_fixture_setup_done(self, info: FixtureInfo) -> None:
        key = f"{info.scope.value}:{info.name}"
        self.durations[key] = info.duration

    def on_session_complete(self, result) -> None:
        print("Fixture setup times:")
        for name, duration in sorted(
                self.durations.items(),
                key=lambda x: -x[1]
        ):
            print(f"  {name}: {duration:.3f}s")
```

## See Also

- [Fixtures](../core-concepts/fixtures.md) - User guide for fixtures
- [Factories](../core-concepts/factories.md) - Factory fixtures
- [Events](events.md) - Complete event reference
- [Plugins](plugins.md) - Plugin development guide
