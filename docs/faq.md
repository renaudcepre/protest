# FAQ

## Why no test classes?

ProTest doesn't support test classes. Use suites instead.

**pytest:**

```python
class TestUser:
    @pytest.fixture
    def user(self):
        return User("alice")

    def test_create(self, user):
        assert user.name == "alice"

    def test_delete(self, user):
        user.delete()
        assert user.deleted
```

**ProTest:**

```python
from protest import ProTestSuite, fixture, Use
from typing import Annotated

user_suite = ProTestSuite("User")


@fixture()
def user():
    return User("alice")

user_suite.bind(user)  # SUITE scope


@user_suite.test()
def test_create(u: Annotated[User, Use(user)]):
    assert u.name == "alice"


@user_suite.test()
def test_delete(u: Annotated[User, Use(user)]):
    u.delete()
    assert u.deleted
```

### What classes provide vs suites

| Feature                | pytest classes                   | ProTest suites      |
|------------------------|----------------------------------|---------------------|
| Group related tests    | ✓                                | ✓                   |
| Shared fixtures        | `self` or class-scoped fixtures  | `suite.bind(fn)`    |
| Setup/teardown         | `setup_method`/`teardown_method` | `yield` in fixtures |
| Named groups in output | ✓                                | ✓                   |
| Inheritance            | ✓                                | ✗                   |

### Why not inheritance?

Test inheritance creates implicit behavior that's hard to trace. When a test fails in a subclass, you need to check the
parent class, grandparent class, and any mixins to understand what's happening.

ProTest favors explicit composition: if two suites need the same fixtures, import and use them explicitly.

```python
from myapp.fixtures import database, user


@api_suite.test()
def test_api(
        db: Annotated[Database, Use(database)],
        user: Annotated[User, Use(user)],
):
    ...


@admin_suite.test()
def test_admin(
        db: Annotated[Database, Use(database)],
        user: Annotated[User, Use(user)],
):
    ...
```

You can see exactly what each test uses. No hunting through class hierarchies.

## Why can't fixtures use `From()`?

`From()` is only allowed in tests, not fixtures. This is intentional.

If fixtures could use `From()`, you'd get hidden cartesian products:

```python
# Hypothetical - NOT SUPPORTED (decorator syntax doesn't exist either)
# If this were possible:
@fixture()
def db(engine: Annotated[str, From(ENGINES)]):  # 3 engines
    ...
session.bind(db)

@fixture()
def user(role: Annotated[str, From(ROLES)], db: ...):  # 2 roles
    ...
session.bind(user)

@session.test()
def test_perms(method: Annotated[str, From(METHODS)], user: ...):  # 4 methods
    ...
# Would run 3 × 2 × 4 = 24 times with no visibility in the test!
```

Instead, use factories and keep parameterization visible in the test:

```python
@session.test()
def test_perms(
        engine: Annotated[str, From(ENGINES)],
        role: Annotated[str, From(ROLES)],
        method: Annotated[str, From(METHODS)],
        db_factory: Annotated[FixtureFactory[DB], Use(database)],
        user_factory: Annotated[FixtureFactory[User], Use(user)],
):
    db = await db_factory(engine_type=engine)
    user = await user_factory(role=role, db=db)
    # You SEE it's 3×2×4 = 24 tests
```

## Why doesn't ProTest capture subprocess output automatically?

ProTest captures `print()` and `logging` automatically, but subprocess output goes directly to OS file descriptors (fd
1/2), bypassing Python's `sys.stdout`.

In ProTest's async-concurrent architecture, all tests run in the same process sharing the same file descriptors. There's
no way to attribute subprocess output to a specific test when multiple tests run concurrently.

**Solution: use the `Shell` helper**

```python
from protest import Shell


@suite.test()
async def test_ffmpeg_conversion() -> None:
    result = await Shell.run(["ffmpeg", "-i", "input.mp4", "output.webm"])

    assert result.success
    # stdout/stderr automatically captured and shown on failure
```

The `Shell` helper:
- Runs subprocesses with isolated pipes (no fd sharing issues)
- Automatically prints output for ProTest to capture
- Works safely with concurrent tests (`-n 4`)
- Supports timeout, working directory, environment variables

**With shell features (pipes, &&, etc.):**

```python
@suite.test()
async def test_pipeline() -> None:
    result = await Shell.run("cat file.txt | grep pattern", shell=True)
    assert result.success
```

See `examples/subprocess_capture/session.py` for complete examples and [Built-ins](core-concepts/builtins.md#shell) for full API.

