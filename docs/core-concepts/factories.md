# Factories

Factories create configurable fixture instances with automatic caching and teardown.

## Basic Usage

A factory is a fixture that accepts arguments and can be called multiple times:

```python
from protest import factory, FixtureFactory, FixtureScope, Use

@factory(scope=FixtureScope.SESSION)
def user(name: str, role: str = "guest"):
    print(f"Creating user {name}")
    yield {"name": name, "role": role}
    print(f"Deleting user {name}")

session.use_fixtures([user])

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

- Use `@factory(scope=FixtureScope.SESSION)` or `@factory(scope=FixtureScope.SUITE)` for scoped factories
- Use `@factory()` for test-scoped factories
- Bind to session/suite with `use_fixtures([...])`
- The test receives a `FixtureFactory[T]`, not the value directly
- Call the factory with `await` - it's always async
- Each call can pass different arguments

## Automatic Caching

Same arguments return the same instance:

```python
@session.test()
async def test_caching(user_factory: Annotated[FixtureFactory[dict], Use(user)]):
    alice1 = await user_factory(name="alice")
    alice2 = await user_factory(name="alice")
    bob = await user_factory(name="bob")

    assert alice1 is alice2  # Same instance (cached)
    assert alice1 is not bob  # Different args = different instance
```

## Automatic Teardown

Factories with `yield` get automatic cleanup in LIFO order:

```python
@factory(scope=FixtureScope.SESSION)
def user(name: str, role: str = "guest"):
    user = db.create_user(name, role)
    yield user
    db.delete_user(user.id)  # Cleanup runs for each created instance

session.use_fixtures([user])
```

If a test creates `alice` then `bob`, teardown runs `bob` first, then `alice`.

## Dependencies

Factories can depend on other fixtures:

```python
@fixture(scope=FixtureScope.SESSION)
def database():
    return Database()

session.use_fixtures([database])

@factory(scope=FixtureScope.SESSION)
def user(
    db: Annotated[Database, Use(database)],
    name: str,
    role: str = "guest"
):
    user = db.insert_user(name, role)
    yield user
    db.delete_user(user.id)

session.use_fixtures([user])
```

## Error Handling

Factory errors are reported as **SETUP ERROR**, not test failures:

```
⚠ test_create_user: [FIXTURE] ConnectionError: Database unavailable
```

This distinguishes infrastructure problems from test bugs.
