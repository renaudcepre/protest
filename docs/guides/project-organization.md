# Project Organization

How to structure a real ProTest project with multiple files, suites, and fixtures.

## The Recommended Pattern

The key idea: **one session file assembles everything explicitly**. Each test module exports its suite, and the session imports and registers it. No side-effect imports, no `# noqa`.

### Layout

```
tests/
├── session.py              # Entry point: imports and assembles suites
├── fixtures/
│   ├── database.py         # Session-scoped fixtures
│   └── users.py            # Factories
│
├── domain/
│   ├── test_users.py       # Defines + exports users_suite
│   └── test_orders.py      # Defines + exports orders_suite
│
└── api/
    ├── suite.py             # Parent suite, assembles children
    ├── fixtures.py          # API-specific fixtures (client, auth)
    ├── test_users_api.py    # Defines + exports users_api_suite
    └── test_orders_api.py   # Defines + exports orders_api_suite
```

### Step 1: Test Modules Export Their Suite

Each test file creates a suite, registers its tests, and **exports** the suite object:

```python
# tests/domain/test_users.py
from typing import Annotated

from protest import FixtureFactory, ProTestSuite, Use, factory

from myapp.domain import User

users_suite = ProTestSuite("Users", tags=["domain"])

@factory(cache=False)
def user(name: str = "Alice", role: str = "member") -> User:
    return User(name=name, role=role)

users_suite.bind(user)


@users_suite.test()
async def test_user_can_change_role(
    user_factory: Annotated[FixtureFactory[User], Use(user)],
) -> None:
    u = await user_factory()
    u.change_role("admin")
    assert u.role == "admin"


@users_suite.test()
def test_user_display_name() -> None:
    u = User(name="Alice", role="member")
    assert u.display_name == "Alice (member)"
```

The `@suite.test()` decorators register tests at import time. The key is that `users_suite` is exported — another module will import and consume it.

### Step 2: Intermediate Suites Assemble Children

For nested hierarchies, a parent suite imports its children:

```python
# tests/api/suite.py
from protest import ProTestSuite

from tests.api.test_users_api import users_api_suite
from tests.api.test_orders_api import orders_api_suite

api_suite = ProTestSuite("API", tags=["api"])
api_suite.add_suite(users_api_suite)
api_suite.add_suite(orders_api_suite)
```

Every import is immediately consumed by `.add_suite()` — no dead imports.

### Step 3: Session Assembles Everything

The session file is thin — just imports and registration:

```python
# tests/session.py
from protest import ProTestSession

from tests.fixtures.database import database
from tests.fixtures.users import user
from tests.domain.test_users import users_suite
from tests.domain.test_orders import orders_suite
from tests.api.suite import api_suite

session = ProTestSession(concurrency=4)

# Bind session-scoped fixtures
session.bind(database)
session.bind(user)

# Assemble suites
session.add_suite(users_suite)
session.add_suite(orders_suite)
session.add_suite(api_suite)
```

Every import is **consumed** by `.bind()` or `.add_suite()`. No unused imports, no `# noqa`.

### Running

```bash
# All tests
protest run tests.session:session

# Just the API suite
protest run tests.session:session::API

# Nested suite
protest run tests.session:session::API::Users

# By tag
protest run tests.session:session -t domain

# By keyword
protest run tests.session:session -k "change_role"
```

## Why This Pattern Works

1. **Every import is consumed** — `suite.add_suite()`, `session.bind()`, or `session.add_suite()` uses the imported object. No linter warnings, no `# noqa`.

2. **Clear ownership** — each test file owns its suite. You can read one file and understand what it tests.

3. **Composable** — suites nest naturally. `API::Users::Permissions` is just three files, each adding its suite to the parent.

4. **IDE-friendly** — "Go to Definition" on any suite import takes you to the file that defines it. Rename refactoring works.

## Anti-Pattern: Side-Effect Imports

When a test module doesn't export its suite but instead reaches into the session file to get it, you end up with side-effect imports:

```python
# DON'T DO THIS — tests/session.py
from protest import ProTestSession, ProTestSuite

session = ProTestSession()
domain_suite = ProTestSuite("Domain")
session.add_suite(domain_suite)

# Side-effect imports: importing for registration, not for the value
import tests.domain.test_users   # noqa: F401, E402
import tests.domain.test_orders  # noqa: F401, E402
```

```python
# tests/domain/test_users.py — reaches back into session
from tests.session import domain_suite  # circular risk!

@domain_suite.test()
def test_something(): ...
```

Problems:
- **`# noqa` everywhere** — linters correctly warn about unused imports
- **Circular import risk** — test modules import from session, session imports test modules
- **Invisible dependencies** — removing an import silently drops tests with no error
- **Import order matters** — suites must be defined before test modules are imported

## Anti-Pattern: One Session Per Test File

```python
# DON'T DO THIS
# tests/test_users.py
session = ProTestSession()
suite = ProTestSuite("Users")
session.add_suite(suite)
# ...

# tests/test_orders.py
session = ProTestSession()  # Another session!
suite = ProTestSuite("Orders")
session.add_suite(suite)
```

Problems:
- No shared fixtures between sessions
- Can't run all tests at once
- No suite hierarchy
- Multiple `protest run` commands needed

## Real-World Example

The [Yorkshire example](https://github.com/renaudcepre/protest/tree/main/examples/yorkshire) demonstrates this pattern at scale:

```
yorkshire/tests/
├── session.py           # Imports + assembles all suites
├── fixtures.py          # Session fixtures (kennel, yorkshire factory)
└── suites/
    ├── puppies/suite.py    # Exports puppies_suite
    ├── adults/             # Parent suite with children
    │   ├── workers/        # Nested child
    │   └── unemployed/
    ├── seniors/suite.py
    ├── showcase/suite.py
    └── ...
```

The session file imports each suite and registers it — every import consumed, zero `# noqa`.

## Tips

- **Start simple.** One file with session + suite + tests is fine for small projects. Split when a file gets too long or when you need suite nesting.

- **Fixtures near their tests.** Put domain-specific factories in the same file as the suite, or in a sibling `fixtures.py` if shared across multiple suites.

- **One file = one leaf suite.** Each test file defines exactly one suite. Intermediate suites (parents) live in `suite.py` files that assemble children.

- **Name suites after your domain**, not after the file structure. `ProTestSuite("Users")`, not `ProTestSuite("TestUsers")`.

## See Also

- [Best Practices](../best-practices.md) — fixture placement, naming conventions, tags
- [Fixtures](../core-concepts/fixtures.md) — scope at binding, teardown
- [Running Tests](../getting-started/running-tests.md) — CLI filters, tags, `--lf`
