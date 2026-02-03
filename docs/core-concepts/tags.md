# Tags

Tags allow you to categorize and filter tests. ProTest's tag system has a killer feature: **automatic tag inheritance from fixtures**.

## Declaring Tags

### On Tests

```python
@session.test(tags=["slow", "integration"])
async def test_full_sync():
    ...
```

### On Fixtures

```python
@fixture(tags=["database"])
def db():
    return Database()

session.bind(db)
```

### On Suites

```python
api_suite = ProTestSuite("API", tags=["api"])
```

Suite tags are inherited by all tests in the suite (and child suites).

## Tag Inheritance (Killer Feature)

When a test uses a fixture, it **automatically inherits all tags from that fixture**. This works transitively through the entire dependency chain.

### Example

```python
# Fixture tagged "database"
@fixture(tags=["database"])
def db():
    return Database()

session.bind(db)


# Fixture that depends on db - inherits "database" tag
@fixture()
def user_repository(db: Annotated[Database, Use(db)]):
    return UserRepository(db)

session.bind(user_repository)


# Fixture that depends on user_repository - also inherits "database"
@fixture()
def user_service(repo: Annotated[UserRepository, Use(user_repository)]):
    return UserService(repo)

session.bind(user_service)


# This test is automatically tagged "database" (inherited through the chain)
@session.test()
async def test_create_user(svc: Annotated[UserService, Use(user_service)]):
    ...
```

The dependency chain is:
```
test_create_user → user_service → user_repository → db (tagged "database")
```

So `test_create_user` inherits the "database" tag without any explicit declaration.

### Why This Matters

**Without tag inheritance:**
```python
# You must manually tag EVERY test that touches the database
@session.test(tags=["database"])  # Easy to forget!
async def test_create_user(): ...

@session.test(tags=["database"])  # And this one...
async def test_delete_user(): ...

@session.test()  # Oops, forgot the tag!
async def test_update_user(): ...
```

**With tag inheritance:**
```python
# Tag the fixture ONCE
@fixture(tags=["database"])
def db(): ...

# All tests using db (directly or transitively) are automatically tagged
@session.test()
async def test_create_user(db: ...): ...  # Tagged "database"

@session.test()
async def test_delete_user(repo: ...): ...  # Tagged "database" (via repo → db)

@session.test()
async def test_update_user(svc: ...): ...  # Tagged "database" (via svc → repo → db)
```

**No forgotten tags. No manual tracking.**

## Effective Tags

A test's effective tags are the union of:

1. Tags declared on the test itself
2. Tags inherited from the suite (and parent suites)
3. Tags inherited from all fixtures (transitively)

```python
api_suite = ProTestSuite("API", tags=["api"])

@fixture(tags=["database"])
def db(): ...
session.bind(db)

@api_suite.test(tags=["slow"])
async def test_api_query(db: Annotated[Database, Use(db)]):
    ...

# Effective tags: {"api", "database", "slow"}
```

## Running with Tags

### Include Tags (-t, --tag)

Run only tests with specific tags:

```bash
# Run tests tagged "database"
protest run tests:session -t database

# Multiple tags use OR logic
protest run tests:session -t unit -t integration  # unit OR integration
```

### Exclude Tags (--no-tag)

Skip tests with specific tags:

```bash
# Skip all tests touching the database
protest run tests:session --no-tag database

# Skip slow and flaky tests
protest run tests:session --no-tag slow --no-tag flaky
```

### Combining Filters

```bash
# API tests that don't touch the database
protest run tests:session::API --no-tag database

# Integration tests excluding flaky ones
protest run tests:session -t integration --no-tag flaky
```

## Listing Tags

See all tags declared in a session:

```bash
protest tags list tests:session
```

Output:
```
api
database
integration
slow
```

Show effective tags per test (including inherited):

```bash
protest tags list tests:session -r
```

Output:
```
test_create_user: api, database
test_delete_user: api, database
test_list_users: api, database, slow
...
```

## Common Patterns

### Infrastructure Tags

Tag fixtures by the infrastructure they require:

```python
@fixture(tags=["database"])
def db(): ...

@fixture(tags=["redis"])
def cache(): ...

@fixture(tags=["s3"])
def storage(): ...
```

Run tests without external dependencies:
```bash
protest run tests:session --no-tag database --no-tag redis --no-tag s3
```

### Speed Tags

Tag slow tests:

```python
@session.test(tags=["slow"])
async def test_full_migration():
    ...
```

Quick feedback loop:
```bash
protest run tests:session --no-tag slow
```

### Environment Tags

Tag tests requiring specific environments:

```python
@fixture(tags=["requires-docker"])
def docker_client(): ...

@session.test(tags=["ci-only"])
async def test_deployment(): ...
```

Run locally (no Docker):
```bash
protest run tests:session --no-tag requires-docker
```
