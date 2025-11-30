<p align="center">
  <img src="assets/logo-term.svg" alt="ProTest">
</p>
<p align="center">
  <em>Modern, async-first testing framework for Python 3.10+</em>
</p>
<p align="center">
  <strong>Explicit dependencies. Native async. Built-in parallelism.</strong>
</p>

---

## A Simple Example

```python
from protest import ProTestSession

session = ProTestSession()


def inc(x):
    return x + 1


@session.test()
def test_answer():
    assert inc(3) == 5
```

```bash
protest run test_sample:session
```

## Explicit Dependencies

No magic fixture names. You declare what you need:

```python
from typing import Annotated
from protest import Use, Scope, fixture


@fixture(scope=Scope.SESSION)
async def database():
    db = await Database.connect()
    yield db
    await db.close()


@session.test()
async def test_create_user(db: Annotated[Database, Use(database)]):
    user = await db.create_user("alice")
    assert user.name == "alice"
```

Functions without `@fixture` are treated as `FUNCTION` scope by default:

```python
def get_test_user():
    return User(name="alice")


@session.test()
def test_user(user: Annotated[User, Use(get_test_user)]):
    assert user.name == "alice"
```

## Features

- **Explicit DI** - No guessing which fixture you're using
- **Async native** - No plugin needed, just `async def`
- **Parallel execution** - Built-in with `-n 4`
- **Scoped fixtures** - `SESSION`, `SUITE`, `FUNCTION`
- **Mix sync/async** - They just work together

## Installation

```bash
git clone <repo-url>
cd protest
uv sync
```

## Usage

```bash
protest run module:session           # Run tests
protest run module:session -n 4      # Parallel
```

## Why not pytest?

|          | pytest             | ProTest                   |
|----------|--------------------|---------------------------|
| Fixtures | Implicit (by name) | Explicit (`Use(fixture)`) |
| Async    | Plugin required    | Native                    |
| Parallel | Plugin required    | Built-in                  |

pytest is battle-tested and has a huge ecosystem. Use ProTest if you want FastAPI-style
explicit dependencies in your tests.

## License

MIT
