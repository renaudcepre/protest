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
user_suite = ProTestSuite("User")

@user_suite.fixture()
def user():
    return User("alice")

@user_suite.test()
def test_create(user: Annotated[User, Use(user)]):
    assert user.name == "alice"

@user_suite.test()
def test_delete(user: Annotated[User, Use(user)]):
    user.delete()
    assert user.deleted
```

### What classes provide vs suites

| Feature | pytest classes | ProTest suites |
|---------|---------------|----------------|
| Group related tests | ✓ | ✓ |
| Shared fixtures | `self` or class-scoped fixtures | `@suite.fixture()` |
| Setup/teardown | `setup_method`/`teardown_method` | `yield` in fixtures |
| Named groups in output | ✓ | ✓ |
| Inheritance | ✓ | ✗ |

### Why not inheritance?

Test inheritance creates implicit behavior that's hard to trace. When a test fails in a subclass, you need to check the parent class, grandparent class, and any mixins to understand what's happening.

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
# Hypothetical - NOT SUPPORTED
@session.fixture()
def db(engine: Annotated[str, From(ENGINES)]):  # 3 engines
    ...

@session.fixture()
def user(role: Annotated[str, From(ROLES)], db: ...):  # 2 roles
    ...

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

