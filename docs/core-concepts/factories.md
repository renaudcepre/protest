# Factories

Factories create configurable fixture instances with automatic caching and teardown.

## Basic Usage

A factory is a fixture that accepts arguments and can be called multiple times:

```python
from protest import factory, FixtureFactory, Use
from typing import Annotated

@factory()
def user(name: str, role: str = "guest"):
    print(f"Creating user {name}")
    yield {"name": name, "role": role}
    print(f"Deleting user {name}")

session.bind(user)  # → SESSION scope

@session.test()
async def test_users(
    user_factory: Annotated[FixtureFactory[dict], Use(user)]
):
    alice = await user_factory(name="alice", role="admin")
    bob = await user_factory(name="bob")

    assert alice["role"] == "admin"
    assert bob["role"] == "guest"
```

Key points:

- Use `@factory()` decorator (no scope parameter)
- Scope is determined by binding: `session.bind()` or `suite.bind()`
- No binding = TEST scope (fresh factory per test)
- The test receives a `FixtureFactory[T]`, not the value directly
- Call the factory with `await` - it's always async
- Each call can pass different arguments

## Scope at Binding

Like regular fixtures, factory scope is determined by WHERE you bind:

```python
@factory()
def user(name: str):
    yield User(name)
    # cleanup

# SESSION scope - one factory shared across all tests
session.bind(user)

# SUITE scope - one factory per suite
api_suite.bind(user)

# TEST scope (no binding) - fresh factory per test
```

## Caching

By default, factories do **not** cache instances (`cache=False`). Each call creates a new instance:

```python
@factory()  # cache=False by default
def user(name: str):
    yield User(name)

@session.test()
async def test_no_cache(user_factory: Annotated[FixtureFactory, Use(user)]):
    alice1 = await user_factory(name="alice")
    alice2 = await user_factory(name="alice")
    assert alice1 is not alice2  # Different instances!
```

To enable caching (same arguments return same instance), use `cache=True`:

```python
@factory(cache=True)
def user(name: str):
    yield User(name)

@session.test()
async def test_with_cache(user_factory: Annotated[FixtureFactory, Use(user)]):
    alice1 = await user_factory(name="alice")
    alice2 = await user_factory(name="alice")
    bob = await user_factory(name="bob")

    assert alice1 is alice2  # Same instance (cached by args)
    assert alice1 is not bob  # Different args = different instance
```

## Automatic Teardown

Factories with `yield` get automatic cleanup in LIFO order:

```python
@factory()
def user(name: str, role: str = "guest"):
    user = db.create_user(name, role)
    yield user
    db.delete_user(user.id)  # Cleanup runs for each created instance

session.bind(user)
```

If a test creates `alice` then `bob`, teardown runs `bob` first, then `alice`.

## Dependencies

Factories can depend on other fixtures:

```python
@fixture()
def database():
    return Database()

session.bind(database)

@factory()
def user(
    db: Annotated[Database, Use(database)],
    name: str,
    role: str = "guest"
):
    user = db.insert_user(name, role)
    yield user
    db.delete_user(user.id)

session.bind(user)
```

## Error Handling

Factory errors are reported as **SETUP ERROR**, not test failures:

```
⚠ test_create_user: [FIXTURE] ConnectionError: Database unavailable
```

This distinguishes infrastructure problems from test bugs.

## Managed vs Non-Managed Factories

### Managed (Default)

ProTest manages the lifecycle - use `yield` for teardown:

```python
@factory()  # managed=True by default
def user(name: str):
    user = User.create(name)
    yield user
    user.delete()  # Automatic cleanup

session.bind(user)

# Usage - async, ProTest manages lifecycle
alice = await user_factory(name="alice")
```

### Non-Managed

Return your own factory class when you need custom methods:

```python
@factory(managed=False)
def user_factory(db: Annotated[Database, Use(database)]):
    return UserFactory(db=db)

session.bind(user_factory)

# Usage - sync, you manage lifecycle
alice = factory.create(name="alice")
users = factory.create_many(count=5)
```
