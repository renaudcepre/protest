# ProTest - Plan de Suivi & Architecture

## État Actuel (POC Fonctionnel ✅)

### Implémenté
- [x] **DI/Resolver** - Injection explicite via `Annotated[T, Use(fixture)]`
- [x] **Scopes** - SESSION > SUITE > FUNCTION avec caching
- [x] **Generator fixtures** - Setup/teardown via `yield` + ExitStack
- [x] **ProTestSession** - Container principal
- [x] **ProTestSuite** - Isolation des fixtures entre suites
- [x] **SuiteResolver** - Délégation au parent pour SESSION fixtures
- [x] **TestRunner** - Exécution basique avec injection
- [x] **CLI** - `protest run module:session` (style uvicorn)

### À Faire
- [ ] **Async support** - Fixtures et tests async
- [ ] **Plugins** - Architecture extensible (reporting, retry, etc.)
- [ ] **Hooks** - Événements du runner (on_test_end, etc.)

---

## Architecture Plugins - Design Validé

### Principe: Zéro Magic, Tout Explicite

```python
from protest import ProTestSession
from protest_rich import RichReporter
from protest_html import HtmlReport

session = ProTestSession()
session.use(RichReporter())
session.use(HtmlReport("report.html"))
```

### Interface Plugin

```python
from protest.plugin import Plugin, TestResult, TestContext

class Plugin:
    """Interface que tous les plugins implémentent."""

    # Setup - appelé lors de session.use(plugin)
    def setup(self, session: ProTestSession) -> None:
        """Permet au plugin d'enregistrer ses fixtures."""
        # Ex: session.resolver.register(self.docker_client, Scope.SESSION)
        pass

    # Lifecycle hooks (tous optionnels)
    def on_session_start(self, session: ProTestSession) -> None: ...
    def on_session_end(self, session: ProTestSession, passed: int, failed: int) -> None: ...

    def on_suite_start(self, suite: ProTestSuite) -> None: ...
    def on_suite_end(self, suite: ProTestSuite, results: list[TestResult]) -> None: ...

    def on_test_start(self, ctx: TestContext) -> None: ...
    def on_test_end(self, ctx: TestContext, result: TestResult) -> None: ...

    # Modifiers (peuvent changer le comportement)
    def should_skip(self, test: Callable) -> bool | str: ...  # str = skip reason
    def wrap_test(self, test: Callable) -> Callable: ...  # retry, timeout, etc.


@dataclass
class TestContext:
    """Contexte par test - évite les race conditions en parallèle."""
    test: Callable
    suite: ProTestSuite | None
    start_time: float  # set par le runner au début du test
    data: dict[str, Any]  # storage libre pour les plugins


@dataclass
class TestResult:
    ctx: TestContext
    passed: bool
    duration: float
    exception: Exception | None = None
```

### Implémentation dans ProTestSession

```python
class ProTestSession:
    def __init__(self) -> None:
        self._resolver = Resolver()
        self._suites: list[ProTestSuite] = []
        self._tests: list[Callable] = []
        self._plugins: list[Plugin] = []

    def use(self, plugin: Plugin) -> None:
        plugin.setup(self)  # ← Plugin peut enregistrer ses fixtures ici
        self._plugins.append(plugin)
```

### Implémentation dans TestRunner

```python
class TestRunner:
    def run(self) -> bool:
        # Notifier tous les plugins
        for plugin in self._session._plugins:
            plugin.on_session_start(self._session)

        # ... run tests ...

        for plugin in self._session._plugins:
            plugin.on_session_end(self._session, passed, failed)
```

### Exemple de Plugin: RichReporter

```python
from rich.console import Console
from protest.plugin import Plugin, TestResult

class RichReporter(Plugin):
    def __init__(self) -> None:
        self.console = Console()

    def on_test_end(self, test: Callable, result: TestResult) -> None:
        if result.passed:
            self.console.print(f"[green]✓[/] {test.__name__} ({result.duration:.2f}s)")
        else:
            self.console.print(f"[red]✗[/] {test.__name__}: {result.exception}")

    def on_session_end(self, session, passed: int, failed: int) -> None:
        color = "green" if failed == 0 else "red"
        self.console.print(f"\n[{color}]Results: {passed}/{passed+failed} passed[/]")
```

### Exemple de Plugin: Retry

```python
class RetryOnFail(Plugin):
    def __init__(self, max_retries: int = 3) -> None:
        self.max_retries = max_retries

    def wrap_test(self, test: Callable) -> Callable:
        def wrapped(*args, **kwargs):
            last_exception = None
            for attempt in range(self.max_retries):
                try:
                    return test(*args, **kwargs)
                except Exception as e:
                    last_exception = e
            raise last_exception
        return wrapped
```

### Exemple de Plugin: Docker (avec fixtures)

```python
from protest.plugin import Plugin
from protest.core.scope import Scope

class DockerPlugin(Plugin):
    def __init__(self, image: str = "python:3.12") -> None:
        self.image = image

    def setup(self, session: ProTestSession) -> None:
        # Enregistre les BOUND METHODS (self.xxx, pas self._xxx)
        session.resolver.register(self.docker_client, Scope.SESSION)
        session.resolver.register(self.container, Scope.SUITE)

    def docker_client(self) -> Generator[DockerClient, None, None]:
        import docker
        client = docker.from_env()
        yield client
        client.close()

    def container(self, client: Annotated[DockerClient, Use(...)]) -> Generator[Container, None, None]:
        # Note: la dépendance sera résolue via self.docker_client de cette instance
        container = client.containers.run(self.image, detach=True)
        yield container
        container.stop()
        container.remove()
```

Usage - référencer l'INSTANCE du plugin:
```python
session = ProTestSession()

# Garder une référence à l'instance !
postgres = DockerPlugin(image="postgres:15")
redis = DockerPlugin(image="redis:7")

session.use(postgres)
session.use(redis)

# Utiliser les bound methods de chaque instance
@session.test
def test_with_both_containers(
    pg: Annotated[Container, Use(postgres.container)],
    cache: Annotated[Container, Use(redis.container)],
):
    assert pg.status == "running"
    assert cache.status == "running"
```

**Pourquoi ça marche:** `postgres.container` et `redis.container` sont deux objets différents (bound methods), donc deux fixtures distinctes. C'est une feature: on peut utiliser le même plugin plusieurs fois avec des configs différentes.

---

## Pourquoi Cette Architecture Est Safe

### 1. Pas de modification du Resolver/DI
Les plugins peuvent **ajouter** des fixtures via `setup()`, mais n'interfèrent pas avec la résolution. Ils opèrent **autour** des tests, pas **dans** le DI.

### 2. Compatible Async
```python
class Plugin:
    async def on_test_end(self, ctx, result) -> None: ...
    # OU
    def on_test_end(self, ctx, result) -> None: ...
```
Le runner peut détecter si c'est async et await si nécessaire.

### 3. Ordre d'exécution clair
- `setup()`: appelé immédiatement lors de `session.use()`
- `on_*_start`: appelés dans l'ordre d'enregistrement
- `on_*_end`: appelés dans l'ordre inverse (comme ExitStack)
- `wrap_test`: composés (plugin1.wrap(plugin2.wrap(test)))

### 4. Opt-in total
- Pas de plugin = comportement actuel (print basique)
- Un plugin peut implémenter seulement les hooks qu'il veut

### 5. Thread-safe via TestContext
Chaque test reçoit son propre `TestContext` avec:
- `start_time` set par le runner
- `data: dict` pour que les plugins stockent leur état par-test
- Pas de state partagé = pas de race condition en parallèle

---

## Points de Vigilance pour l'Async

Quand tu implémenteras l'async, assure-toi que:

1. **TestRunner.run()** devient `async def run()`
2. **Les hooks** peuvent être async ou sync (duck typing)
3. **wrap_test** retourne `Callable | Coroutine`

```python
# Le runner doit gérer les deux
async def _call_hook(self, plugin, method_name, *args):
    method = getattr(plugin, method_name, None)
    if method:
        result = method(*args)
        if inspect.iscoroutine(result):
            await result
```

---

## Séquence d'Implémentation Recommandée

1. **Async Support** - Sans plugins d'abord
2. **Plugin base class** - Juste l'interface + `session.use()`
3. **Hooks dans runner** - Appeler les plugins aux bons moments
4. **Premier plugin** - RichReporter pour valider l'archi
5. **wrap_test** - Pour retry/timeout

---

## Fichiers à Créer/Modifier

| Fichier | Action |
|---------|--------|
| `protest/plugin.py` | NEW - Plugin base class + TestResult |
| `protest/core/session.py` | ADD - `_plugins` list + `use()` method |
| `protest/core/runner.py` | MODIFY - Appeler les hooks |
