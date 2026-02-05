# ProTest - Instructions pour Claude

## Vue d'ensemble

ProTest est un framework de test async-first avec injection de dépendances explicite (style FastAPI).

---

## Instructions pour l'IA

### Règles de Documentation

**Après chaque modification significative :**

1. Mettre à jour la doc utilisateur (`docs/`) si l'API change
2. Vérifier que la doc existante ne contredit pas les changements
3. Vérifier que les exemples dans `examples/` fonctionnent

Checklist :
- [ ] `docs/*.md` - doc utilisateur à jour ?
- [ ] `examples/` - exemples fonctionnels ?
- [ ] `README.md` - cohérent ?
- [ ] Pas de doc obsolète qui contredit le nouveau comportement ?

### Règles de Tests

**Après chaque implémentation :**

1. Écrire les tests correspondants
2. Lancer les tests avec coverage : `uv run pytest tests/test_xxx.py --cov=protest.module --cov-report=term-missing`
3. Viser 100% de coverage sur le nouveau code

### Journal des Décisions

Documenter les décisions architecturales dans `.claude/DECISIONS.md` :
- Pourquoi on fait X et pas Y
- Les tentatives abandonnées
- Les questions ouvertes

### Où trouver la documentation

| Sujet | Fichier |
|-------|---------|
| Fixtures & Scope | `docs/core-concepts/fixtures.md` |
| Factories | `docs/core-concepts/factories.md` |
| Tags (héritage transitif) | `docs/core-concepts/tags.md` |
| Built-ins (caplog, mocker, Shell) | `docs/core-concepts/builtins.md` |
| Suites & Sessions | `docs/core-concepts/sessions-and-suites.md` |
| Tests paramétrés | `docs/core-concepts/parameterized-tests.md` |
| CLI & Filtres | `docs/getting-started/running-tests.md` |
| Best practices | `docs/best-practices.md` |
| Architecture (design doc) | `docs/architecture/fixture-scoping-design.md` |

---

## Structure du Code

```
protest/
├── core/           # Session, Suite, Runner, Collector
├── di/             # FixtureContainer, Markers (Use), Validation
├── entities/       # Dataclasses centralisées
├── events/         # Event bus
├── execution/      # AsyncBridge, Capture, Context
├── fixtures/       # Built-ins: caplog, mocker
├── cache/          # Plugin --lf
├── tags/           # TagFilterPlugin
├── filters/        # Suite et Keyword filters
├── cli/            # Entry point CLI
└── reporting/      # Rich/Ascii reporters
```

### Organisation des Entities

```
entities/
├── __init__.py     # Ré-exports publics
├── core.py         # Fixture, TestItem, TestOutcome
├── events.py       # TestResult, SessionResult, etc.
└── execution.py    # LogCapture
```

Import canonique: `from protest.entities import ...`

---

## Règles d'Architecture

### Imports circulaires

**Éviter les quick fixes :**
- ❌ `if hasattr(obj, "attr")` au lieu de `isinstance()`
- ❌ Import local dans une fonction
- ❌ Import dans `TYPE_CHECKING` uniquement

**Solution :** Extraire le code partagé vers un module tiers.

Exemple : `di/validation.py` créé pour casser le cycle `collector.py ↔ decorators.py`.

### Exceptions

```
ProTestError (base)
├── FixtureError
├── ScopeMismatchError
├── AlreadyRegisteredError
├── PlainFunctionError
├── UnregisteredDependencyError
└── FixtureNotFoundError
```

### Convention `# noqa`

Chaque `# noqa` DOIT avoir une explication :

```python
# Format: # noqa: CODE - explication courte
from module import func  # noqa: PLC0415 - lazy import for startup perf
```

Codes courants :
- `PLR0913` - Too many arguments (acceptable pour API publiques)
- `PLC0415` - Import outside top-level (lazy imports pour perf)
- `PLR2004` - Magic value in comparison (acceptable dans tests/exemples)
- `T201` - print() usage (acceptable pour CLI output intentionnel)
- `S604/S607` - Shell/subprocess (expliquer pourquoi c'est safe)
- `N806` - Variable in function should be lowercase (acceptable pour constantes de test)
- `SIM117` - Nested with statements (parfois requis pour testing)
- `PLW0603` - Global statement (acceptable pour compteurs de retry dans démos)
- `PLR0912` - Too many branches (acceptable si refactoring réduirait la lisibilité)

---

## Points d'Implémentation Internes

*Ces détails sont pour le développement du framework, pas documentés pour les users.*

### Résolution des Fixtures (`di/resolver.py`)

**Double-checked locking :**
```python
async with self._resolve_locks[target_fixture.func]:
    if target_fixture.is_cached:
        return target_fixture.cached_value
```

**Scope paths :**
- `None` = session
- `"SuiteName"` = suite
- `"<test_scope>"` = test

### Wiring au Runtime

Les fixtures sont enregistrées dans `Session.__aenter__` via `_register_fixtures()`.

### Générateurs (teardown)

Fixtures avec `yield` wrappées en context managers via `asynccontextmanager`.
`AsyncExitStack` garantit teardown LIFO.

### Isolation par Test (`execution/context.py`)

`TestExecutionContext` isole les fixtures TEST :
- Cache local + exit stack local pour TEST scope
- Délègue au FixtureContainer parent pour Suite/Session

### Event Bus (`events/bus.py`)

- Handlers sync → thread pool
- Handlers async → fire-and-forget avec tracking
- `wait_pending()` avant `SESSION_COMPLETE`

### Collection (`core/collector.py`)

- `_collect_from_suite()` récursif pour suites imbriquées
- `chunk_by_suite()` groupe par `suite_name`

### Ordre des filtres

```
Collector.collect()
    → SuiteFilterPlugin
    → KeywordFilterPlugin
    → TagFilterPlugin
    → CachePlugin
    → Tests filtrés
```

---

## Points d'Attention

1. **Nested suites** → `suite.full_path` = `"Parent::Child"`
2. **Scope validation** → `_is_parent_or_same_path()`
3. **Nouveau hook** → Ajouter dans `Event` enum ET `PluginBase`
4. **Double-checked locking** → Penser aux race conditions

---

## Tests Importants

- `tests/core/test_runner.py` - Intégration runner
- `tests/di/test_resolver.py` - Scopes, caching, locks
- `tests/core/test_factory_errors.py` - ERROR vs FAIL
- `tests/core/test_nested_suites.py` - Suites imbriquées