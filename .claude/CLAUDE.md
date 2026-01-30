# ProTest - Architecture et Points d'Implémentation

## Vue d'ensemble

ProTest est un framework de test async-first avec injection de dépendances explicite (style FastAPI).

## Structure des Modules

```
protest/
├── core/           # Orchestration: Session, Suite, Runner, Collector
├── di/             # DI: Resolver, Markers (Use), Validation
├── entities/       # Dataclasses centralisées (core, events, execution)
├── events/         # Event bus découplé: Bus, Types
├── execution/      # Exécution: AsyncBridge, Capture, Context
├── fixtures/       # Built-ins: caplog, mocker
├── cache/          # Plugin --lf (last-failed)
├── tags/           # Tag system: TagFilterPlugin
├── filters/        # Suite et Keyword filter plugins
├── cli/            # Entry point CLI
└── reporting/      # Console output
```

## Règles d'Architecture - Imports

**IMPORTANT** : Éviter les solutions "quick fix" pour les imports circulaires.

### Code Smells à éviter

1. **Duck typing pour éviter un import** : `if hasattr(obj, "attr")` au lieu de `isinstance()`
2. **Import local dans une fonction** : `def foo(): from module import X`
3. **Import dans TYPE_CHECKING uniquement** pour contourner un cycle

Ces solutions masquent un problème d'architecture.

### Solution propre

Quand un cycle d'import apparaît, **extraire le code partagé** vers un module tiers :

```
AVANT (cycle):
collector.py ←→ decorators.py  # validate_no_from_params vs FixtureWrapper

APRÈS (pas de cycle):
validation.py ← decorators.py
      ↑              ↓
      └── collector.py
```

Exemple concret : `di/validation.py` a été créé pour casser le cycle entre `collector.py` et `decorators.py`.

## Organisation des Entities

Toutes les dataclasses sont centralisées dans `protest/entities/`:

```
entities/
├── __init__.py     # Ré-exports publics
├── core.py         # Fixture, FixtureRegistration, TestItem, TestOutcome, FixtureCallable
├── events.py       # TestCounts, TestResult, SessionResult, TestStartInfo, HandlerInfo, FixtureInfo
└── execution.py    # LogCapture
```

Import canonique: `from protest.entities import Fixture, TestResult, ...`

## Scope at Binding Architecture

Le scope des fixtures est déterminé par **où elles sont liées**, pas par le décorateur.
Les décorateurs définissent uniquement les **propriétés intrinsèques** (tags, cache, managed).

**IMPORTANT** : Toutes les fixtures doivent être décorées (pas de plain functions).

```python
from protest import fixture, factory

# Session scope - lié via session.bind()
@fixture(tags=["database"])
def database():
    yield connect()

session.bind(database)  # → SESSION scope

# Suite scope - lié via suite.bind()
@fixture()
def api_client(db: Annotated[DB, Use(database)]):
    return Client(db)

api_suite.bind(api_client)  # → SUITE scope

# Test scope (défaut) - pas de binding
@fixture()
def db_session():
    yield Session()
# Non lié → TEST scope automatique

@fixture()
def payload():
    return {"name": "test"}
# Non lié → TEST scope automatique
```

Les plain functions (sans décorateur) lèvent `PlainFunctionError` quand utilisées avec `Use()`.

### Caching et Scope

**Le caching est relatif au scope du binding :**

| Binding | Scope | Comportement cache |
|---------|-------|-------------------|
| `session.bind(fn)` | SESSION | Une instance pour toute la session |
| `suite.bind(fn)` | SUITE | Une instance par exécution de la suite |
| Pas de binding | TEST | **Nouvelle instance par test** |

**Conséquence importante** : Si une fixture ne doit PAS être partagée entre tests, ne pas la binder.

```python
# ❌ Mauvais : tracker partagé entre tous les tests de la suite
@fixture()
def call_tracker():
    reset_counts()
    return tracker

suite.bind(call_tracker)  # SUITE scope → même instance pour tous les tests

# ✓ Bon : tracker frais pour chaque test
@fixture()
def call_tracker():
    reset_counts()
    return tracker

# Pas de binding → TEST scope → nouvelle instance par test
```

### Autouse Fixtures

Fixtures auto-résolues au démarrage de leur scope, via `autouse=True` au binding :

```python
# Session autouse - résolu à SESSION_SETUP_START
@fixture()
def configure_logging():
    logging.basicConfig(level=logging.DEBUG)
    yield
    logging.shutdown()

session.bind(configure_logging, autouse=True)  # autouse au binding

# Suite autouse - résolu quand la suite démarre (avant son premier test)
@fixture()
def clean_environment():
    old = os.environ.copy()
    os.environ.clear()
    yield
    os.environ.update(old)

api_suite.bind(clean_environment, autouse=True)  # autouse au binding
```

Quand utiliser autouse :
- Side effects nécessaires pour tous les tests (logging, env setup)
- Les tests n'ont pas besoin de la valeur retournée, juste de l'effet
- Setup/teardown doit s'exécuter quel que soit les tests sélectionnés

### Suites Imbriquées

```python
parent_suite = ProTestSuite("Parent", description="Tests d'intégration API")
child_suite = ProTestSuite("Child")
parent_suite.add_suite(child_suite)  # Child's full_path = "Parent::Child"
```

### Règles de Scope

Une fixture ne peut dépendre que de fixtures dans un scope égal ou parent:
- Session peut dépendre de: session uniquement
- Suite "Parent::Child" peut dépendre de: session, "Parent", "Parent::Child"
- Test peut dépendre de: tout

## Points d'Implémentation Critiques

### 1. Résolution des Fixtures (di/resolver.py)

**Scope basé sur path:**
```python
self._scope_paths: dict[FixtureCallable, str | None]
# None = session, "SuiteName" = suite, "<test_scope>" = test
```

**Double-checked locking pour éviter les race conditions:**
```python
async with self._resolve_locks[target_fixture.func]:
    if target_fixture.is_cached:
        return target_fixture.cached_value
```

### 2. Wiring au Runtime

Les fixtures sont enregistrées dans `Session.__aenter__`:
```python
async def __aenter__(self):
    self._register_fixtures()  # Session + suites récursivement
    await self._resolver.__aenter__()
```

### 3. Gestion des Générateurs (setup/teardown)

Les fixtures avec `yield` sont wrappées en context managers:
```python
if is_generator_like(fixture.func):
    async_cm = asynccontextmanager(fixture.func)(**kwargs)
    result = await exit_stack.enter_async_context(async_cm)
```

L'`AsyncExitStack` garantit le teardown LIFO même en cas d'exception.

### 4. Isolation par Test (execution/context.py)

`TestExecutionContext` isole les fixtures TEST par test:
- TEST (`<test_scope>`) → cache local + exit stack local
- Suite/Session → délégué au Resolver parent

### 5. Factory Fixtures

Deux patterns disponibles :

**Managed (défaut)** - ProTest gère le cycle de vie via `FixtureFactory`:
```python
@factory()  # cache=False, managed=True par défaut
def user(name: str, role: str = "guest") -> User:
    user = User.create(name=name, role=role)
    yield user
    user.delete()  # Teardown automatique par instance

session.bind(user)  # → SESSION scope

# Usage - async obligatoire
alice = await user_factory(name="alice")
bob = await user_factory(name="bob")
```

**Non-managed** - Tu retournes ta propre classe factory:
```python
@factory(managed=False)
def user_factory(db: Annotated[Session, Use(db_session)]) -> UserFactory:
    return UserFactory(db=db)

session.bind(user_factory)  # → SESSION scope

# Usage - sync, méthodes custom
alice = factory.create(name="alice")
users = factory.create_many(count=5)
```

Les erreurs dans les factories sont distinguées des erreurs de test (ERROR vs FAIL).

### 6. Event Bus (events/bus.py)

- Handlers sync: exécutés dans thread pool
- Handlers async: fire-and-forget avec tracking
- `wait_pending()`: attend tous les handlers async avant SESSION_COMPLETE

### 7. Collection des Tests (core/collector.py)

`Collector._collect_from_suite()` est récursif pour les suites imbriquées.
`chunk_by_suite()` groupe les tests par `suite_name` (full path).

## Exceptions

```
ProTestError (base)
├── FixtureError         # Erreur dans une fixture (wraps original)
├── ScopeMismatchError   # Fixture dépend d'un scope plus étroit
├── AlreadyRegisteredError
├── PlainFunctionError   # Plain function utilisée comme fixture sans @fixture()
├── UnregisteredDependencyError
└── FixtureNotFoundError
```

## Design Decisions

### Pourquoi Scope at Binding ?

- **Évite les scope mismatches** : le scope est déterminé au binding, pas à la définition
- **Séparation des préoccupations** : décorateur = propriétés intrinsèques, binding = contexte
- **Explicite** : `session.bind(fn)` rend visible où chaque fixture est liée
- **Flexible** : même fixture peut être liée avec différents scopes (pas recommandé mais possible)

### Pourquoi Use(ref) au lieu de Use("name")?

Rend les cycles **syntaxiquement impossibles**. Python lève NameError si on référence une fonction pas encore définie.

### Pourquoi AsyncExitStack partout?

Permet de mélanger fixtures sync et async avec teardown garanti.

## Points d'Attention pour Modifications

1. **Nested suites** → `suite.full_path` retourne "Parent::Child"
2. **Scope validation** → `_is_parent_or_same_path()` vérifie les préfixes
3. **Nouveau hook plugin** → Ajouter dans `Event` enum ET `PluginBase`
4. **Modifier la résolution** → Penser au double-checked locking

## Tests Importants

- `tests/core/test_runner.py` - Tests d'intégration du runner
- `tests/di/test_resolver.py` - Validation des scopes, caching, locks
- `tests/core/test_factory_errors.py` - Distinction erreur fixture vs test
- `tests/core/test_nested_suites.py` - Suites imbriquées

## Tag System

Le système de tags permet de filtrer les tests. Les tags sont **propagés transitivement** via les dépendances de fixtures.

### Déclarer des tags

```python
# Tags sur une suite (hérités par les tests ET suites enfants)
api_suite = ProTestSuite("API", tags=["api", "integration"])

# Tags sur une fixture (propagés aux tests qui l'utilisent)
@fixture(tags=["database"])
def db(): ...

session.bind(db)  # SESSION scope

# Tags sur un test
@api_suite.test(tags=["slow"])
async def test_api(): ...
```

### Calcul des tags effectifs d'un test

```
test.tags = tags_explicites_du_test
          ∪ suite.all_tags (inclut parents)
          ∪ tags_transitifs_des_fixtures
```

### CLI

```bash
protest run demo:session --tag database          # Tests avec tag "database" (OR)
protest run demo:session --tag slow --tag unit   # Tests avec "slow" OU "unit"
protest run demo:session --exclude-tag flaky     # Exclure les tests "flaky"
protest tags list demo:session                   # Lister tous les tags déclarés
protest tags list -r demo:session                # Tags effectifs par test
```

### Implémentation

- **`Fixture.tags`** : `set[str]` sur chaque fixture
- **`ProTestSuite.tags`** : tags déclarés, `.all_tags` inclut parents
- **`Collector`** : calcule les tags transitifs via `_get_transitive_fixture_tags()`
- **`TagFilterPlugin`** : filtre les `TestItem` dans `on_collection_finish()`
- **`TestItem.tags`** : tags effectifs calculés à la collection

### Points d'attention

- Toutes les fixtures doivent être décorées avec `@fixture()` ou `@factory()`
- Session/Suite fixtures doivent être liées via `session.bind()` ou `suite.bind()`
- Les tags de suites sont hérités par les suites enfants
- La propagation via fixtures est **transitive** : si A dépend de B qui dépend de C tagué "x", A hérite "x"

## Architecture (Ports & Adapters)

L'architecture sépare clairement:
- **Domain** : `ProTestSession`, `TestRunner`, `Collector`, `Resolver`
- **Ports (API)** : `protest/api.py` - `run_session()`, `collect_tests()`, `list_tags()`
- **Adapters** :
  - CLI (`protest/cli/`) - argparse, potentiellement Typer
  - Loader (`protest/loader.py`) - chargement de modules Python
  - Reporters - plugins Rich/Ascii

### API publique (`protest/api.py`)

```python
from protest import ProTestSession, run_session, collect_tests, list_tags

session = ProTestSession()
# ... définir tests/fixtures ...

# Exécuter
success = run_session(session, concurrency=4, exitfirst=True)

# Collecter sans exécuter
items = collect_tests(session, include_tags={"unit"})

# Lister les tags
tags = list_tags(session)
```

### Loader (`protest/loader.py`)

```python
from protest import load_session, LoadError

try:
    session = load_session("module:session_name", app_dir=".")
except LoadError as e:
    print(e)
```

## CLI (cli/main.py)

Entry point: `protest <command> [options]`

Commands:
- `protest run module:session [options]` - Run tests
- `protest tags list module:session` - List tags

Exit codes: 0 = success, 1 = failure/error.

La CLI est un simple adapter qui utilise `api.py` et `loader.py`.

## Filtering System

ProTest supporte plusieurs filtres composables : suite, keyword, tag, et last-failed.

### Suite Filter (::SuiteName)

Filtre via le target pour lancer uniquement une suite (et ses enfants).

```bash
protest run demo:session::API           # Tests dans suite "API" et enfants
protest run demo:session::API::Users    # Tests dans suite "API::Users" uniquement
```

**Implémentation** : `SuiteFilterPlugin` dans `protest/filters/suite.py`
- Filtre sur `item.suite_path` (exact ou préfixe avec `::`)
- Les tests standalone (sans suite) sont exclus

### Keyword Filter (-k)

Filtre par substring sur le nom du test (+ case_ids pour les paramétrés).

```bash
protest run demo:session -k "login"           # Tests contenant "login"
protest run demo:session -k "login" -k "auth" # OR logic
```

**Implémentation** : `KeywordFilterPlugin` dans `protest/filters/keyword.py`
- Match sur `item.test_name` + case_ids (ex: `test_user[admin]`)
- Multiple patterns = OR logic

### Combinaison de filtres

Tous les filtres se composent (intersection) :

```bash
# Suite + keyword
protest run demo:session::API -k "login"

# Suite + keyword + tag
protest run demo:session::API -k "login" -t "slow"

# Suite + keyword + tag + last-failed
protest run demo:session::API -k "login" -t "slow" --lf
```

### Architecture des filtres

Les filtres sont des plugins qui s'enregistrent sur `Event.COLLECTION_FINISH`.
L'ordre est important : les filtres "sélectifs" (suite, keyword, tag) s'appliquent AVANT le cache.

```
Collector.collect()
    → SuiteFilterPlugin.on_collection_finish()
    → KeywordFilterPlugin.on_collection_finish()
    → TagFilterPlugin.on_collection_finish()
    → CachePlugin.on_collection_finish()
    → Tests filtrés
```

Chaque plugin reçoit la liste et retourne une liste filtrée (chaînage).

### Comportement du CachePlugin avec --lf

- Si le cache est vide ou ne contient aucun test échoué → tous les tests sont exécutés
- Si le cache contient des tests échoués → seuls les tests échoués présents dans la collection filtrée sont exécutés
- Si aucun test de la collection filtrée n'est dans les tests échoués → 0 tests exécutés (pas de fallback)

## Shared Cache Storage

Le cache est accessible via `session.cache` (instance de `CacheStorage`). Cette API permet le partage de données entre plugins sans couplage direct.

### Usage dans un plugin

```python
class MyPlugin(PluginBase):
    def setup(self, session: ProTestSession) -> None:
        # Lire les données cachées
        durations = session.cache.get_durations()
        failed = session.cache.get_failed_node_ids()

    def on_test_pass(self, result: TestResult) -> None:
        # Écrire dans le cache
        session.cache.set_result(result.node_id, "passed", result.duration)

    def on_session_end(self, result: SessionResult) -> None:
        session.cache.save()
```

### API de CacheStorage

- `load()` / `save()` / `clear()` - Opérations fichier
- `get_result(node_id)` → `TestCacheEntry | None`
- `set_result(node_id, status, duration)`
- `get_results()` → `dict[str, TestCacheEntry]`
- `get_durations()` → `dict[str, float]`
- `get_failed_node_ids()` → `set[str]`
- `get_passed_node_ids()` → `set[str]`

Le `CachePlugin` utilise cette API pour `--lf` et `--cache-clear`.

## API de Test : Smart Shortcuts

L'API de test utilise des **objets de configuration explicites** avec des raccourcis ergonomiques pour les cas simples.

**Philosophie : 100% explicite, zéro magie** - pas de `setattr`/`getattr` sur les fonctions.

### Signature de @test()

```python
@session.test(
    tags: list[str] | None = None,        # Tags pour filtrage
    timeout: float | None = None,          # Timeout en secondes
    skip: bool | str | Skip | None = None, # Skip avec raison
    xfail: bool | str | Xfail | None = None, # Expected failure
    retry: int | Retry | None = None,      # Retry configuration
)
```

### Cas simples (80%) - Raccourcis

```python
@session.test(retry=3, timeout=5.0)
async def test_flaky(): ...

@session.test(skip="WIP: auth refactor")
def test_not_ready(): ...

@session.test(xfail="Bug #123")
def test_known_issue(): ...
```

### Cas avancés (20%) - Objets explicites

```python
from protest import Retry, Skip, Xfail

@session.test(
    retry=Retry(times=3, delay=1.0, on=ConnectionError),
    xfail=Xfail(reason="Flaky in CI", strict=False),
)
async def test_advanced(): ...

# Multiple exceptions
@session.test(retry=Retry(times=2, on=(ConnectionError, TimeoutError)))
async def test_network(): ...
```

### Dataclasses de configuration

```python
@dataclass(frozen=True, slots=True)
class Retry:
    times: int
    delay: float = 0.0
    on: type[Exception] | tuple[type[Exception], ...] = (Exception,)
    # on=ConnectionError → normalisé en (ConnectionError,)

@dataclass(frozen=True, slots=True)
class Skip:
    reason: str = "Skipped"

@dataclass(frozen=True, slots=True)
class Xfail:
    reason: str = "Expected failure"
    strict: bool = True
```

### Normalisation des raccourcis

| Argument | Type Raccourci | Normalisé en interne |
|----------|----------------|----------------------|
| `retry=3` | `int` | `Retry(times=3)` |
| `retry=True` | - | Non supporté |
| `Retry(on=Exc)` | `type` | `Retry(on=(Exc,))` |
| `skip=True` | `bool` | `Skip()` |
| `skip="WIP"` | `str` | `Skip(reason="WIP")` |
| `xfail=True` | `bool` | `Xfail()` |
| `xfail="Bug"` | `str` | `Xfail(reason="Bug")` |
| `timeout=5.0` | `float` | reste `float` |

### Validation

- `timeout < 0` → `ValueError` (à la décoration)
- `Retry(times < 0)` → `ValueError` (à la création de l'objet)
- `Retry(delay < 0)` → `ValueError` (à la création de l'objet)

### Interaction entre comportements

| Combinaison | Résultat |
|-------------|----------|
| `skip + xfail` | Skip prioritaire (test non exécuté) |
| `skip + retry` | Skip prioritaire |
| `xfail + retry` | Retry puis xfail/xpass |
| `timeout + retry` | Timeout déclenche retry |

## Built-in Fixtures

### caplog

Capture les logs pendant un test. Voir `protest/fixtures/builtins.py`.

### mocker

Fixture de mocking avec cleanup automatique. Alternative à `with patch(...)`.

**Fichiers** : `protest/fixtures/mocker.py`, `protest/fixtures/builtins.py`

### Usage

```python
from protest import Mocker, Use, mocker

@session.test()
def test_payment(m: Annotated[Mocker, Use(mocker)]):
    mock_stripe = m.patch("services.stripe.charge")
    mock_stripe.return_value = {"status": "success"}

    process_payment()

    mock_stripe.assert_called_once()
```

### API Mocker

| Méthode | Description |
|---------|-------------|
| `patch(target)` | Patch un chemin string (`module.function`) |
| `patch.object(obj, attr)` | Patch un attribut sur un objet |
| `patch.dict(d, values, clear=False)` | Patch un dict (ex: `os.environ`) |
| `spy(obj, method)` | Appelle le vrai code mais track les appels |
| `stub(name)` | Crée un mock callable (pour callbacks) |
| `async_stub(name)` | Stub async |
| `create_autospec(spec)` | Mock qui respecte la signature |
| `stop(mock)` | Stop un patch spécifique |
| `stopall()` | Stop tous les patchs (appelé auto au teardown) |
| `resetall()` | Reset les mocks (call_count = 0) |

### spy() - Surveiller sans mocker

```python
# Modern style (recommended) - IDE-friendly, Ctrl+Click works
spy = m.spy(email_service.send)

# Classic style - still supported
spy = m.spy(email_service, "send")

email_service.send("to@test.com", "Subject", "Body")  # Vraie méthode appelée

spy.assert_called_once()
assert spy.spy_return == {"status": "sent"}  # Valeur retournée par la vraie méthode
```

### Types exportés

```python
from protest import Mocker, MockType, AsyncMockType
```

### Implémentation

- `Mocker._patchers` : liste des patchers actifs
- `Mocker._mocks` : liste des mocks créés
- `Mocker._mock_to_patcher` : mapping mock → patcher pour `stop()`
- Teardown LIFO garanti via `reversed(self._patchers)`

## Limitations Connues

### Capture de Subprocess

**Limitation** : ProTest capture automatiquement `print()` et `logging`, mais PAS la sortie directe des subprocesses.

**Pourquoi** : Les subprocesses écrivent directement sur les file descriptors OS (fd 1/2), pas via `sys.stdout`. Dans une architecture async-concurrent où tous les tests partagent le même process, il est impossible d'attribuer la sortie d'un subprocess à un test spécifique.

**Différence avec pytest-xdist** : xdist lance des workers dans des processes séparés (chacun avec ses propres fd). ProTest utilise async dans un seul process.

**Solution : capturer explicitement**

```python
import subprocess

@suite.test()
def test_with_subprocess() -> None:
    # ✓ capture_output=True route stdout/stderr vers result
    result = subprocess.run(
        ["echo", "Hello"],
        capture_output=True,
        text=True,
    )

    # Re-print pour que ProTest le capture
    if result.stdout:
        print(result.stdout, end="")

    assert "Hello" in result.stdout
```

**Patterns recommandés** :
- `subprocess.run(..., capture_output=True)` - le plus simple
- `subprocess.check_output(...)` - pour les commandes qui doivent réussir
- Helper function `run_and_capture()` - pour usage répété

**Voir** : `examples/subprocess_capture/session.py` pour des exemples complets.

**Tentatives abandonnées** : Une implémentation FDCapture (capture au niveau OS avec `os.dup2`, threads, pipes) a été évaluée mais abandonnée car :
- Non portable Windows (`select.select()` ne supporte pas les pipes)
- Race conditions entre threads
- Complexité disproportionnée pour le bénéfice
- En mode concurrent, impossible d'attribuer l'output au bon test
