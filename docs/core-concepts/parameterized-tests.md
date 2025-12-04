# Parameterized Tests

Run the same test with multiple values using `ForEach` and `From`.

## Basic Usage

```python
from protest import ForEach, From

HTTP_CODES = ForEach([200, 201, 204])

@session.test()
def test_success_codes(code: Annotated[int, From(HTTP_CODES)]):
    assert code in range(200, 300)
```

This runs 3 tests: one for each code.

## Custom IDs

Provide readable names for test output:

```python
SCENARIOS = ForEach(
    [{"user": "alice", "expect": 200}, {"user": "bob", "expect": 403}],
    ids=lambda s: s["user"]
)

@session.test()
def test_permissions(scenario: Annotated[dict, From(SCENARIOS)]):
    # Output shows: test_permissions[alice], test_permissions[bob]
    pass
```

## Cartesian Product

Multiple `From` parameters create all combinations:

```python
USERS = ForEach(["alice", "bob"])
METHODS = ForEach(["GET", "POST"])

@session.test()
def test_api(
    user: Annotated[str, From(USERS)],
    method: Annotated[str, From(METHODS)]
):
    # Runs 4 times: alice+GET, alice+POST, bob+GET, bob+POST
    pass
```

## Combined with Factories

Factories and parameterization work together to replace pytest's indirect parametrization.

### The pytest way (implicit)

```python
# pytest - fixture reads param magically from request
@pytest.fixture
def api_user(request, user_factory):
    role = getattr(request, "param", UserRole.dev)
    return user_factory.create(role=role)

# indirect=True links the parametrize to the fixture
@pytest.mark.parametrize("api_user", [UserRole.creator], indirect=True)
def test_permissions(api_user):  # Where does the role come from? Magic.
    pass
```

### The ProTest way (explicit)

```python
ROLES = ForEach([UserRole.creator, UserRole.admin])

@session.factory()
def user(role: UserRole):
    return user_factory.create(role=role)

@session.test()
async def test_permissions(
    role: Annotated[UserRole, From(ROLES)],
    make_user: Annotated[FixtureFactory[User], Use(user)]
):
    api_user = await make_user(role=role)  # You see exactly what's happening
    assert api_user.role == role
```

Benefits:

- **Visible**: `From(ROLES)` shows the test runs multiple times
- **Explicit**: You see exactly how the user is configured
- **Flexible**: Other tests can use the same factory with a fixed role:

```python
@session.test()
async def test_creator_only(
    make_user: Annotated[FixtureFactory[User], Use(user)]
):
    api_user = await make_user(role=UserRole.creator)  # No loop, fixed role
```

## Restrictions

`From()` is only allowed in tests, not in fixtures. See [FAQ](../faq.md#why-cant-fixtures-use-from) for why.
