# ProTest Best Practices

This guide covers recommended patterns for organizing and writing tests with ProTest.

## Project Structure

### Recommended Layout

```
tests/
├── session.py              # Entry point: imports and assembles suites
├── fixtures.py             # Session-scoped shared fixtures (optional)
│
├── unit/
│   ├── __init__.py
│   ├── entities.py         # Suite + factories + tests for entities
│   ├── services.py         # Suite + factories + tests for services
│   └── repositories/       # Complex domain gets its own folder
│       ├── suite.py        # Parent suite that assembles children
│       ├── fixtures.py     # Shared fixtures for this domain
│       └── test_user_repo.py
│
└── integration/
    ├── suite.py
    └── test_api.py
```

### Key Principles

1. **Session entry point is thin** - only imports and `add_suite()` calls
2. **One suite per domain/feature** - reflects your application's structure
3. **Fixtures live near their tests** - in the same file or a sibling `fixtures.py`
4. **Nesting is meaningful** - `API::Users::Permissions` not arbitrary hierarchies

## Session Organization

### Good: Thin Entry Point

```python
# tests/session.py
from protest import ProTestSession

from tests.unit.entities import entities_suite
from tests.unit.services import services_suite
from tests.integration.suite import integration_suite
from tests.fixtures import database, cache  # Session fixtures

session = ProTestSession(concurrency=4)
session.bind(database)
session.bind(cache)
session.add_suite(entities_suite)
session.add_suite(services_suite)
session.add_suite(integration_suite)
```

### Bad: Everything in One File

```python
# DON'T DO THIS - 500 lines of mixed fixtures/suites/tests
session = ProTestSession()

@fixture()
def db(): ...

@fixture()
def cache(): ...

session.bind(db)
session.bind(cache)

suite1 = ProTestSuite("Suite1")
session.add_suite(suite1)

@suite1.test()
def test_something(): ...

# ... 500 more lines ...
```

## Suite Design

### Organize by Domain

```python
# tests/unit/notes.py
from protest import ProTestSuite, factory

notes_suite = ProTestSuite("Notes", tags=["domain", "notes"])

# Factories for this domain
@factory(cache=False)
def note(title: str = "Test Note") -> Note:
    return Note(id=uuid4(), title=title)

notes_suite.bind(note)

# Tests for this domain
@notes_suite.test()
async def test_note_can_be_archived(
    note_factory: Annotated[FixtureFactory[Note], Use(note)]
) -> None:
    n = await note_factory()
    archived = n.archive()
    assert archived.status == NoteStatus.ARCHIVED
```

### When to Nest Suites

Nest when there's a logical hierarchy:

```python
# Good: Logical grouping
api_suite = ProTestSuite("API")
users_suite = ProTestSuite("Users")
permissions_suite = ProTestSuite("Permissions")

users_suite.add_suite(permissions_suite)  # API::Users::Permissions
api_suite.add_suite(users_suite)
```

```python
# Bad: Arbitrary nesting
animals_suite = ProTestSuite("Animals")
puppies_suite = ProTestSuite("Puppies")
workers_suite = ProTestSuite("Workers")  # ?

animals_suite.add_suite(puppies_suite)
puppies_suite.add_suite(workers_suite)  # Confusing
```

### Use max_concurrency When Needed

```python
# Tests that share global state need sequential execution
di_suite = ProTestSuite(
    "DI",
    max_concurrency=1,
    tags=["di"]
)
# max_concurrency=1 because tests modify global provider_cache
```

## Fixture Placement & Scoping

### Scope Determines Placement

| Scope | Where to Define | Use Case |
|-------|-----------------|----------|
| Session | `session.py` or `fixtures.py` | Database, expensive resources |
| Suite | Suite file | Suite-specific setup |
| Test | Near test, `@fixture()` | Test isolation, cheap resources |

### Session Fixtures: Expensive Resources

```python
# tests/fixtures.py
from protest import fixture

@fixture(tags=["database"])
async def database() -> AsyncGenerator[Database, None]:
    db = await Database.connect()
    yield db
    await db.close()

# In session.py: session.bind(database)
```

### Suite Fixtures: Domain-Specific Setup

```python
# tests/unit/api.py
from protest import ProTestSuite, fixture

api_suite = ProTestSuite("API")

@fixture()
async def authenticated_client(
    db: Annotated[Database, Use(database)]
) -> AsyncGenerator[APIClient, None]:
    client = APIClient(db)
    await client.login("test@example.com")
    yield client
    await client.logout()

api_suite.bind(authenticated_client)
```

### Test Fixtures: Fresh Per Test

```python
# Use @fixture() (not scoped) for per-test isolation
@fixture()
def request_payload() -> dict:
    return {"name": "test", "value": 42}
```

## Factory Patterns

### Managed Factories (Default)

ProTest manages lifecycle - use `yield` for teardown:

```python
@factory(cache=False)
async def user(
    db: Annotated[Database, Use(database)],
    email: str = "test@example.com",
    role: str = "user",
) -> User:
    user = await User.create(db, email=email, role=role)
    yield user
    await user.delete()  # Automatic cleanup

suite.bind(user)
```

Usage:
```python
@suite.test()
async def test_user_permissions(
    user_factory: Annotated[FixtureFactory[User], Use(user)]
) -> None:
    admin = await user_factory(role="admin")
    reader = await user_factory(role="reader")
    # Both users automatically cleaned up after test
```

### cache=False for Mutable Entities

```python
# Each call creates a fresh instance
@factory(cache=False)
def note(title: str = "Test") -> Note:
    return Note(id=uuid4(), title=title)

suite.bind(note)

# Usage: creates two distinct notes
n1 = await note_factory(title="First")
n2 = await note_factory(title="Second")
assert n1.id != n2.id
```

## Naming Conventions

### Tests

```python
# Pattern: test_<subject>_<behavior>_<condition>
def test_user_can_be_archived_when_inactive(): ...
def test_note_validation_fails_without_title(): ...
def test_api_returns_401_for_unauthenticated_request(): ...
```

### Suites

```python
# Use domain/feature names
ProTestSuite("Users")           # Good
ProTestSuite("API")             # Good
ProTestSuite("Authentication")  # Good

ProTestSuite("TestGroup1")      # Bad
ProTestSuite("Misc")            # Bad
```

### Fixtures and Factories

```python
# Name after what they provide
@fixture()
def database(): ...      # Provides a database

@factory()
def user(): ...          # Provides a user (becomes user_factory in tests)

@fixture()
def api_client(): ...    # Provides an API client
```

## Tags Usage

### Semantic Tags

```python
# Domain tags
ProTestSuite("API", tags=["api"])
@fixture(tags=["database"])

# Behavior tags
@suite.test(tags=["slow"])
@suite.test(tags=["flaky"])

# Environment tags
@suite.test(tags=["requires-redis"])
```

### Running with Tags

```bash
# Run only API tests
protest run tests:session -t api

# Exclude slow tests
protest run tests:session --exclude-tag slow

# Combine filters
protest run tests:session -t api --exclude-tag flaky
```

## Common Anti-Patterns

### 1. Global State for Retries

```python
# BAD
retry_count = 0

@session.test(retry=3)
def test_flaky_thing():
    global retry_count
    retry_count += 1
    if retry_count < 3:
        raise ValueError("Not yet")
```

```python
# GOOD: Design test to be idempotent
@session.test(retry=3)
async def test_external_api_call():
    response = await api.call()
    assert response.status == 200
```

### 2. Kitchen Sink Tests

```python
# BAD: Too many features at once
@session.test(
    timeout=5.0,
    retry=Retry(times=3, delay=0.5, on=ConnectionError),
    xfail="Sometimes fails in CI",
    tags=["slow", "flaky", "integration", "database"],
)
async def test_everything_at_once(): ...
```

```python
# GOOD: Focused tests
@session.test(timeout=5.0)
async def test_api_responds_within_sla(): ...

@session.test(retry=3)
async def test_flaky_external_service(): ...
```

### 3. Arbitrary Suite Hierarchies

```python
# BAD
main_suite = ProTestSuite("Main")
sub1 = ProTestSuite("Group1")
sub2 = ProTestSuite("Things")
main_suite.add_suite(sub1)
sub1.add_suite(sub2)
```

```python
# GOOD: Domain-driven
api_suite = ProTestSuite("API")
users_suite = ProTestSuite("Users")
api_suite.add_suite(users_suite)  # Clear: API::Users
```

### 4. Uncaptured Subprocess Output

**Case 1: Testing a CLI/executable directly**

Use the `Shell` helper:

```python
from protest import Shell

@session.test()
async def test_my_cli():
    result = await Shell.run("my-cli --version")
    assert result.success
    assert "1.0.0" in result.stdout
    # Output automatically captured and shown on failure
```

**Case 2: Testing production code that calls subprocesses**

If your production code calls subprocesses without capturing output, that's already a code smell:

```python
# BAD PRODUCTION CODE: No output capture = no logs, no debug, no error handling
def convert_video(input_path: str, output_path: str) -> None:
    subprocess.run(["ffmpeg", "-i", input_path, output_path])  # Where do errors go?
```

```python
# GOOD PRODUCTION CODE: Capture output for logging and error handling
def convert_video(input_path: str, output_path: str) -> ConversionResult:
    result = subprocess.run(
        ["ffmpeg", "-i", input_path, output_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error(f"FFmpeg failed: {result.stderr}")
        raise ConversionError(result.stderr)
    return ConversionResult(stdout=result.stdout)
```

**Bottom line**: If you're fighting to capture subprocess output in tests, either use `Shell` for CLI tests, or your production code probably needs improvement.

### 5. Overusing Session Scope

```python
# BAD: Should be test-scoped but bound to session
@fixture()
def request_id(): ...
session.bind(request_id)  # Fresh value needed per test!

# GOOD: Test-scoped (not bound)
@fixture()
def request_id() -> str:
    return str(uuid4())
```

## Example: Real-World Test File

```python
# tests/unit/notes.py
"""Tests for Note domain entity."""
from typing import Annotated
from uuid import uuid4

from protest import FixtureFactory, ProTestSuite, Use, raises, factory

from myapp.domain import Note, NoteStatus, InvalidTransitionError

notes_suite = ProTestSuite("Notes", tags=["domain"])


# === Factories ===

@factory(cache=False)
def note(
    title: str = "Test Note",
    status: NoteStatus = NoteStatus.DRAFT,
) -> Note:
    return Note(id=uuid4(), title=title, status=status)

notes_suite.bind(note)


# === Tests ===

@notes_suite.test()
async def test_draft_note_can_be_published(
    note_factory: Annotated[FixtureFactory[Note], Use(note)]
) -> None:
    draft = await note_factory(status=NoteStatus.DRAFT)
    published = draft.publish()
    assert published.status == NoteStatus.PUBLISHED


@notes_suite.test()
async def test_published_note_can_be_archived(
    note_factory: Annotated[FixtureFactory[Note], Use(note)]
) -> None:
    published = await note_factory(status=NoteStatus.PUBLISHED)
    archived = published.archive()
    assert archived.status == NoteStatus.ARCHIVED


@notes_suite.test()
async def test_draft_cannot_be_archived_directly(
    note_factory: Annotated[FixtureFactory[Note], Use(note)]
) -> None:
    draft = await note_factory(status=NoteStatus.DRAFT)
    with raises(InvalidTransitionError):
        draft.archive()
```

## See Also

- [Fixtures](core-concepts/fixtures.md)
- [Factories](core-concepts/factories.md)
- [Tags](core-concepts/tags.md) - Tag inheritance and filtering
- [CLI Reference](cli.md)
