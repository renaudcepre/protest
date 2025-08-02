# 📋 ProTest Implementation Plan

## 🎯 Overview

ProTest is a modern Python testing framework designed from scratch with native async
support, strong typing, and explicit dependency injection. This document outlines the
implementation strategy, identifies major pain points, and provides a phased approach to
building the framework.

## 📊 Implementation Phases

### Phase 1: Core Foundation (MVP)

**Duration**: ~2 weeks  
**Goal**: Minimal functional structure

#### 1.1 Base Models (2-3 days)

- [ ] Implement `ProTestSession` class
- [ ] Implement `ProTestSuite` class
- [ ] Create `Scope` enum (SESSION, SUITE, FUNCTION)
- [ ] Implement `Use` marker for injection
- [ ] Define data structures for tests/fixtures storage

#### 1.2 Dependency Injection System (3-4 days)

- [ ] Dependency resolution with `Annotated` support
- [ ] Build dependency graph
- [ ] Implement caching by scope
- [ ] Cycle detection and error handling

#### 1.3 Fixture System (4-5 days)

- [ ] `@session.fixture` decorator
- [ ] `@suite.fixture` decorator
- [ ] Generator support (setup/teardown)
- [ ] SESSION and FUNCTION scope implementation
- [ ] Resolution and caching logic

#### 1.4 Test Registration (2 days)

- [ ] `@suite.test` decorator
- [ ] `@session.test` decorator
- [ ] Test collection mechanism
- [ ] Metadata support (name, tags)

#### 1.5 Basic Execution (3 days)

- [ ] `run_test()` implementation
- [ ] `run_suite()` implementation
- [ ] `run_session()` implementation
- [ ] Error handling and reporting
- [ ] Scope cleanup

### Phase 2: Async Support

**Duration**: ~1.5 weeks  
**Goal**: Transparent sync/async handling using Starlette's proven approach

#### 2.1 Async Foundation (5-6 days)

- [ ] Study Starlette's concurrency implementation (1 day)
- [ ] Copy and adapt `starlette/concurrency.py` core functions
- [ ] Implement `is_async_callable()` detection
- [ ] Implement `run_in_threadpool()` for sync code
- [ ] Setup main event loop with shared ThreadPoolExecutor
- [ ] Add contextvars support for proper context propagation
- [ ] Create universal `run_callable()` method

#### 2.2 Async Fixtures (3 days)

- [ ] `async def` fixture support
- [ ] Async generators (`async yield`)
- [ ] Mixed sync/async dependencies
- [ ] Generator handling (both sync and async)
- [ ] Proper teardown sequencing

### Phase 3: Essential Features

**Duration**: ~2 weeks  
**Goal**: Feature parity with basic pytest usage

#### 3.1 Parametrization (3-4 days)

- [ ] `@*.parametrize` decorator
- [ ] Object/dataclass support
- [ ] Dictionary support
- [ ] Parameter injection in fixtures

#### 3.2 CLI Basic (3 days)

- [ ] Argument parser
- [ ] Session discovery (`module:variable`)
- [ ] Filtering (--suite, --test)
- [ ] Console reporting

#### 3.3 Plugin System (4-5 days)

- [ ] Plugin interface/protocol
- [ ] Fixture/hook collection from plugins
- [ ] Hook system (Event enum)
- [ ] Lifecycle hooks implementation

### Phase 4: Polish & Advanced Features

**Duration**: ~1 week  
**Goal**: Production-ready framework

#### 4.1 Additional Scopes (2 days)

- [ ] SUITE scope implementation
- [ ] Lifecycle management

#### 4.2 Autouse Fixtures (1 day)

- [ ] `autouse=True` flag
- [ ] Automatic execution logic

#### 4.3 Enhanced Reporting (2-3 days)

- [ ] Colors and progress bars
- [ ] Error formatting
- [ ] Statistics summary

## 🔥 Major Pain Points

### 1. Automatic Sync/Async Management ⚡

**Challenge**: Orchestrating calls between sync and async code without blocking

**Technical difficulties**:

- Runtime detection of function types
- Efficient ThreadPoolExecutor management
- Deadlock prevention
- Proper exception propagation

**Strategy**: Adapt Starlette's proven implementation

**Starlette's approach** (simplified from `starlette/concurrency.py`):

```python
import asyncio
import functools
from contextvars import ContextVar
from typing import Any, Callable


async def run_in_threadpool(func: Callable, *args: Any, **kwargs: Any) -> Any:
    """Run sync function in threadpool from async context."""
    loop = asyncio.get_event_loop()
    func_call = functools.partial(func, *args, **kwargs)
    return await loop.run_in_executor(None, func_call)


def is_async_callable(obj: Any) -> bool:
    """Check if callable is async."""
    while isinstance(obj, functools.partial):
        obj = obj.func
    return asyncio.iscoroutinefunction(obj) or (
            callable(obj) and asyncio.iscoroutinefunction(obj.__call__)
    )
```

**ProTest adaptation**:

```python
class TestRunner:
    def __init__(self):
        # Single shared executor like Starlette
        self._executor = None

    async def run_callable(self, func: Callable, *args, **kwargs):
        """Universal runner for sync/async callables."""
        if is_async_callable(func):
            return await func(*args, **kwargs)
        else:
            # Run sync in threadpool
            return await run_in_threadpool(func, *args, **kwargs)

    async def resolve_fixture(self, fixture_def, context):
        """Resolve any fixture (sync or async)."""
        # Dependencies already resolved
        deps = await self.resolve_dependencies(fixture_def.dependencies)

        # Run fixture function (sync or async)
        result = await self.run_callable(fixture_def.func, **deps)

        # Handle generators
        if inspect.isgenerator(result):
            # Sync generator
            value = await run_in_threadpool(next, result)
            yield value
            # Teardown
            await run_in_threadpool(next, result, None)
        elif inspect.isasyncgen(result):
            # Async generator
            value = await result.__anext__()
            yield value
            # Teardown
            await result.aclose()
        else:
            yield result
```

**Key benefits of copying Starlette**:

- Battle-tested in production
- Handles edge cases (generators, partial functions, classes)
- Efficient thread pool management
- Proper context propagation with contextvars
- Clean exception handling

**Implementation steps**:

1. Copy relevant parts from `starlette/concurrency.py`
2. Adapt for ProTest's fixture/test context
3. Add our specific needs (fixture caching, scope management)
4. Keep Starlette's contextvars approach for proper context propagation

### 2. Context-Aware Dependency Injection 🎯

**Challenge**: Resolving fixtures with proper context (parameters, scope)

**Technical difficulties**:

- Passing parametrization context to fixtures
- Cache management per (scope, params) tuple
- Recursive resolution without losing context
- Type safety throughout the chain

**Key considerations**:

- Each test execution needs its own resolution context
- Fixtures must access current parameter values
- Cache invalidation strategy

### 3. Plugin Architecture 🔌

**Challenge**: Flexible design without magic

**Technical difficulties**:

- CLI options from plugins vs initial parsing
- Collecting contributions (fixtures, hooks)
- Hook execution order
- Plugin isolation

**Proposed interface**:

```python
class PluginProtocol:
    def get_fixtures(self) -> list[FixtureDefinition]: ...

    def get_hooks(self) -> list[HookDefinition]: ...

    def get_cli_options(self) -> list[CLIOption]: ...
```

### 4. Complex Lifecycle Management 🔄

**Challenge**: Managing setup/teardown at multiple levels

**Technical difficulties**:

- Correct teardown order (LIFO)
- Error handling during cleanup
- Autouse fixtures and their dependencies
- Scope mixing (SUITE fixture in SESSION)

**Critical scenarios**:

- Fixture failure during setup
- Test failure with pending teardowns
- Keyboard interruption handling
- Partial suite execution

### 5. Performance & Scalability 📈

**Challenge**: Stay performant with many tests

**Technical difficulties**:

- Efficient fixture caching
- Minimize DI overhead
- Prepare for future parallelization
- Memory management for large test suites

## 📁 Recommended Project Structure

```
protest/
├── src/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── session.py      # ProTestSession implementation
│   │   ├── suite.py        # ProTestSuite implementation
│   │   ├── fixture.py      # Fixture definitions and decorators
│   │   ├── test.py         # Test definitions and decorators
│   │   └── scope.py        # Scope enum and management
│   ├── di/
│   │   ├── __init__.py
│   │   ├── resolver.py     # Dependency resolution logic
│   │   ├── markers.py      # Use marker implementation
│   │   └── cache.py        # Fixture caching
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── runner.py       # Test execution engine
│   │   ├── async_bridge.py # Sync/async orchestration (Starlette-inspired)
│   │   └── context.py      # Execution context
│   ├── plugins/
│   │   ├── __init__.py
│   │   ├── base.py         # Plugin protocol
│   │   └── hooks.py        # Hook system
│   └── cli/
│       ├── __init__.py
│       └── main.py         # CLI entry point
└── tests/
    ├── __init__.py
    ├── conftest.py         # Pytest configuration and fixtures
    ├── di/
    │   ├── __init__.py
    │   └── test_resolver.py  # Dedicated tests for DI using pytest
    ├── core/
    │   ├── __init__.py
    │   └── test_fixtures.py  # Dedicated tests for core features
    └── dogfooding/
        ├── __init__.py
        └── test_simple.py    # Early dogfooding tests with ProTest itself
```

## 🚀 Quick Start Implementation

### Step 1: Minimal Working Example

Create the simplest possible test that can run:

```python
# src/core/session.py
class ProTestSession:
    def __init__(self):
        self.tests = []

    def test(self, func):
        self.tests.append(func)
        return func

    def run_session(self):
        for test in self.tests:
            try:
                test()
                print(f"✓ {test.__name__}")
            except AssertionError as e:
                print(f"✗ {test.__name__}: {e}")


# example.py
from protest import ProTestSession

session = ProTestSession()


@session.test
def test_basic():
    assert 1 + 1 == 2


if __name__ == "__main__":
    session.run_session()
```

### Step 2: Add Fixtures

```python
# src/core/fixture.py
class Fixture:
    def __init__(self, func, scope=Scope.FUNCTION):
        self.func = func
        self.scope = scope
        self.cache = {}


# src/di/resolver.py
def resolve_dependencies(func, fixture_registry):
    # Analyze function signature
    # Build dependency graph
    # Resolve and inject
    pass
```

### Step 3: Implement Async Support

Build on the sync foundation by adding async detection and handling inspired by
Starlette's battle-tested approach.

```python
# src/execution/async_bridge.py
# Adapted from starlette/concurrency.py
import asyncio
import functools


async def run_in_threadpool(func, *args, **kwargs):
    loop = asyncio.get_event_loop()
    func_call = functools.partial(func, *args, **kwargs)
    return await loop.run_in_executor(None, func_call)
```

## 💡 Key Recommendations

1. **Start Simple**: Complete Phase 1 without async first
2. **Study Starlette**: Deep dive into `starlette/concurrency.py` before implementing
   Phase 2
3. **Bootstrap with Pytest, then Dogfood**: Use a stable framework like `pytest` to build and validate the core dependency injection and execution logic (Phase 1-2). Once the foundation is reliable, start writing tests using ProTest itself to accelerate development and ensure its quality.
4. **Type Safety**: Enable mypy strict mode from the beginning
5. **Modular Architecture**: Keep DI, execution, and reporting separate
6. **Performance Benchmarks**: Regularly measure against pytest
7. **Documentation**: Write docs alongside code
8. **Error Messages**: Invest in clear, helpful error messages early

## 📈 Success Metrics

- [ ] Can run basic tests with fixtures
- [ ] Async/sync interoperability works seamlessly
- [ ] Plugin system allows extending functionality
- [ ] Performance within 20% of pytest for common cases
- [ ] Type checking catches common errors
- [ ] Clear error messages guide users

## 🔮 Future Considerations

- Parallel test execution (multiprocess)
- Test result caching ("certificates")
- Watch mode for development
- Integration with IDEs
- Advanced reporting formats
- Performance profiling tools

## 📦 Dependencies & References

### Core Dependencies

- Python 3.10+ (for modern typing features)
- No runtime dependencies for core functionality

### Implementation References

- **Starlette**: Study [
  `concurrency.py`](https://github.com/encode/starlette/blob/master/starlette/concurrency.py)
  for async/sync handling
- **FastAPI**: Inspiration for DI system and API design
- **pytest**: Study plugin architecture (but avoid complexity)

### Optional Dependencies

- `rich` or `click` for enhanced CLI
- `anyio` if we want to support trio in addition to asyncio
