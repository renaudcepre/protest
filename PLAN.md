# 🚀 ProTest MVP - Plan d'Action Détaillé

## 🎯 **Objectif MVP : Framework de test async-first, zero dependency, avec gestion automatique sync/async**

### **Critères de succès**
- [ ] Tests sync et async fonctionnent parfaitement
- [ ] Gestion automatique sync/async transparente (via `Sync()`)
- [ ] CLI fonctionnel avec `argparse` uniquement
- [ ] Zero dépendances externes
- [ ] Self-hosting (ProTest testé avec ProTest)
- [ ] Performance ≥ 80% de pytest sur même suite

---

## 📋 **Phase 1: Foundation & Examples-Driven Development (Semaine 1-2)**

### **1.1 Setup du projet "Zero Dependencies" (2 jours)**

#### **Structure finale**
```
protest/
├── src/protest/
│   ├── __init__.py
│   ├── session.py          # ✅ Déjà bien avancé
│   ├── suite.py            # ❌ À créer
│   ├── entities.py         # ✅ Existe
│   ├── use.py              # ✅ Existe
│   ├── concurrency.py      # ❌ À créer (volé de Starlette)
│   ├── dependencies.py     # ❌ À créer (inspiré FastAPI)
│   ├── cli.py              # ❌ À créer
│   └── reporting.py        # ❌ À créer
├── examples/               # ❌ TDD Examples
└── tests/                  # ✅ Existe
```

#### **pyproject.toml final**
```toml
[project]
name = "protest"
version = "0.1.0"
description = "Modern async-first testing framework"
requires-python = ">=3.9"
dependencies = []  # 🎯 ZERO DEPENDENCIES!

[project.scripts]
protest = "protest.cli:main"

[project.optional-dependencies]
dev = ["pytest>=8.0", "mypy", "ruff"]
```

### **1.2 Créer Examples Folder - TDD Approach (3 jours)**

#### **Examples à créer (par ordre de priorité)**
```
examples/
├── 01_basic_sync/
│   ├── usage.py              # Tests sync simples
│   ├── expected_output.txt   # Output CLI attendu
│   └── notes.md             # Questions/problèmes
├── 02_basic_async/
│   ├── usage.py              # Tests async purs
│   └── expected_output.txt
├── 03_mixed_sync_async/      # 🔥 CAS COMPLEXE
│   ├── usage.py              # Sync dépend d'async
│   └── notes.md             # Design questions
├── 04_fastapi_real_world/
│   ├── usage.py              # Vrai cas d'usage
│   └── app.py               # Mini FastAPI app
├── 05_error_scenarios/
│   ├── fixture_not_found.py
│   ├── circular_deps.py
│   └── expected_errors/
└── 06_parametrization/
    ├── usage.py
    └── notes.md
```

#### **Exemple concret - `examples/03_mixed_sync_async/usage.py`**
```python
"""
Le cas difficile que ProTest doit résoudre élégamment
"""
from protest import ProTestSession, Scope, Use, Sync
from typing import Annotated

session = ProTestSession()

@session.fixture(scope=Scope.SESSION)
async def async_db():
    """Fixture async - simulation connexion DB"""
    await asyncio.sleep(0.1)
    return "async_db_connection"

@session.fixture(scope=Scope.FUNCTION)  
def sync_processor(db: Annotated[str, Use(Sync(async_db))]):
    """Fixture sync qui dépend d'async - LE DÉFI"""
    return f"processor_with_{db}"

@session.test
def test_sync_using_async_dep(proc: Annotated[str, Use(sync_processor)]):
    """Test sync qui utilise une chaîne async→sync"""
    assert "async_db_connection" in proc

# CLI target: protest examples/03_mixed_sync_async/usage.py:session
```

### **1.3 "Vol de Code" Starlette/FastAPI (2 jours)**

#### **Sources à télécharger et étudier**
```bash
# Actions immédiates
git clone https://github.com/encode/starlette /tmp/starlette
git clone https://github.com/tiangolo/fastapi /tmp/fastapi

# Files à copier/adapter:
# - starlette/concurrency.py → protest/concurrency.py
# - fastapi/dependencies/utils.py → protest/dependencies.py  
# - fastapi/utils.py (type detection)
```

#### **Code à voler/adapter**

##### **`protest/concurrency.py` (from Starlette)**
```python
# Copie quasi-directe de starlette/concurrency.py
import asyncio
import contextvars
import functools
import typing
from concurrent.futures import ThreadPoolExecutor

async def run_in_threadpool(func, *args, **kwargs):
    """Volé de Starlette - battle tested!"""
    # [Implementation exacte de Starlette]
```

##### **`protest/dependencies.py` (inspired by FastAPI)**
```python
# Adaptation de fastapi/dependencies/utils.py
async def solve_fixture_dependencies(
    fixture_info: FixtureInfo,
    resolved_cache: dict[str, Any],
    session: 'ProTestSession'
) -> Any:
    """Résolution récursive comme FastAPI mais pour fixtures"""
    # [Logique adaptée de FastAPI]
```

---

## 📋 **Phase 2: Core Implementation (Semaine 3-4)**

### **2.1 ProTestSuite Implementation (3 jours)**

#### **`src/protest/suite.py`**
```python
from typing import Callable, Any
from .entities import Scope, FixtureInfo
from .use import Use

class ProTestSuite:
    def __init__(self, name: str):
        self.name = name
        self.tests: dict[str, Callable] = {}
        self.fixtures: dict[str, FixtureInfo] = {}
    
    def test(self, name: str | None = None):
        """Décorateur pour enregistrer un test"""
        def decorator(func: Callable) -> Callable:
            test_name = name or func.__name__
            self.tests[test_name] = func
            return func
        return decorator
    
    def fixture(self, scope: Scope = Scope.FUNCTION):
        """Décorateur pour enregistrer une fixture"""
        # [Implementation similaire à session.fixture]
```

#### **Intégration dans `ProTestSession`**
```python
# Ajouter à src/protest/session.py
class ProTestSession:
    def __init__(self):
        # ... existing code
        self.suites: dict[str, ProTestSuite] = {}
    
    def include_suite(self, suite: ProTestSuite):
        """Inclure une suite dans la session"""
        if suite.name in self.suites:
            raise ValueError(f"Suite '{suite.name}' already included")
        self.suites[suite.name] = suite
        
        # Merge fixtures from suite
        for name, fixture_info in suite.fixtures.items():
            if name in self.fixtures:
                # TODO: Handle conflicts
                pass
            self.fixtures[name] = fixture_info
```

### **2.2 Système Sync/Async Magic (4 jours)**

#### **Détection automatique sync/async**
```python
# src/protest/dependencies.py
import inspect
from .concurrency import run_in_threadpool

async def resolve_fixture_with_sync_async_magic(
    fixture_info: FixtureInfo,
    resolved_deps: dict[str, Any],
    session: 'ProTestSession'
) -> Any:
    """
    Résout une fixture en gérant automatiquement sync/async
    """
    func = fixture_info.func
    is_async_func = inspect.iscoroutinefunction(func)
    is_async_gen = inspect.isasyncgenfunction(func)
    
    # Détection des dépendances sync/async
    sync_deps = {}
    async_deps = {}
    
    for param_name, dep in fixture_info.dependencies.items():
        if isinstance(dep, Sync):
            # Sync() wrapper détecté
            async_dep_value = resolved_deps[param_name]
            sync_deps[param_name] = async_dep_value
        else:
            # Dépendance normale
            if param_name in resolved_deps:
                if is_async_func:
                    async_deps[param_name] = resolved_deps[param_name]
                else:
                    sync_deps[param_name] = resolved_deps[param_name]
    
    # Exécution selon le type
    if is_async_func or is_async_gen:
        # Fixture async - exécution directe
        if is_async_gen:
            async_gen = func(**async_deps)
            value = await async_gen.__anext__()
            # Store generator for cleanup
            return value, async_gen
        else:
            return await func(**async_deps)
    else:
        # Fixture sync - utiliser threadpool si deps async
        if any(isinstance(dep, Sync) for dep in fixture_info.dependencies.values()):
            # On a des dépendances async → threadpool
            return await run_in_threadpool(func, **sync_deps)
        else:
            # Tout sync → exécution directe
            return func(**sync_deps)
```

#### **Classe Sync() wrapper**
```python
# src/protest/use.py
class Sync:
    """Wrapper pour utiliser une fixture async dans un contexte sync"""
    def __init__(self, async_fixture):
        self.async_fixture = async_fixture
        self.name = getattr(async_fixture, "__name__", None)
    
    def __repr__(self):
        return f"Sync({self.name})"
```

### **2.3 CLI basique avec argparse (2 jours)**

#### **`src/protest/cli.py`**
```python
import argparse
import sys
import importlib
import asyncio
from pathlib import Path

def parse_target(target: str) -> tuple[str, str]:
    """Parse 'module:variable' format"""
    if ":" not in target:
        raise ValueError("Target must be in format 'module:variable'")
    
    module_path, variable_name = target.split(":", 1)
    return module_path, variable_name

def import_session(module_path: str, variable_name: str):
    """Import session from module"""
    try:
        # Add current directory to Python path
        sys.path.insert(0, str(Path.cwd()))
        
        # Convert file path to module name
        if module_path.endswith('.py'):
            module_path = module_path[:-3]
        module_name = module_path.replace('/', '.')
        
        module = importlib.import_module(module_name)
        session = getattr(module, variable_name)
        return session
    except Exception as e:
        print(f"Error importing {module_path}:{variable_name}: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        prog="protest",
        description="Modern async-first testing framework"
    )
    parser.add_argument(
        "target", 
        help="Target session in format 'module:variable' (e.g., tests:session)"
    )
    parser.add_argument(
        "--suite", 
        help="Run specific suite by name"
    )
    parser.add_argument(
        "--test",
        help="Run specific test (format: 'test_name' or 'suite_name::test_name')"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    # Import session
    module_path, variable_name = parse_target(args.target)
    session = import_session(module_path, variable_name)
    
    # Execute tests
    try:
        result = asyncio.run(run_session_with_filters(
            session, 
            suite_filter=args.suite,
            test_filter=args.test,
            verbose=args.verbose
        ))
        sys.exit(0 if result.success else 1)
    except Exception as e:
        print(f"Error running tests: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

### **2.4 Reporting simple mais efficace (1 jour)**

#### **`src/protest/reporting.py`**
```python
import time
from dataclasses import dataclass
from typing import Any

# ANSI colors - zero dependencies!
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"

@dataclass
class TestResult:
    name: str
    suite: str | None
    success: bool
    duration: float
    error: Exception | None = None

class SimpleReporter:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results: list[TestResult] = []
        self.start_time: float | None = None
    
    def start_session(self):
        self.start_time = time.time()
        print("Running tests...")
    
    def test_started(self, name: str, suite: str | None = None):
        if self.verbose:
            suite_prefix = f"{suite}::" if suite else ""
            print(f"  {suite_prefix}{name} ... ", end="")
    
    def test_passed(self, name: str, suite: str | None, duration: float):
        result = TestResult(name, suite, True, duration)
        self.results.append(result)
        
        if self.verbose:
            print(f"{Colors.GREEN}✓{Colors.RESET} ({duration:.3f}s)")
        else:
            print(f"{Colors.GREEN}✓{Colors.RESET} {name} ({duration:.3f}s)")
    
    def test_failed(self, name: str, suite: str | None, duration: float, error: Exception):
        result = TestResult(name, suite, False, duration, error)
        self.results.append(result)
        
        if self.verbose:
            print(f"{Colors.RED}✗{Colors.RESET} ({duration:.3f}s)")
        else:
            print(f"{Colors.RED}✗{Colors.RESET} {name} ({duration:.3f}s)")
        
        # Print error details
        print(f"  {Colors.RED}{type(error).__name__}: {error}{Colors.RESET}")
    
    def finish_session(self):
        total_time = time.time() - self.start_time if self.start_time else 0
        
        passed = sum(1 for r in self.results if r.success)
        failed = len(self.results) - passed
        
        print(f"\n{passed} passed, {failed} failed in {total_time:.2f}s")
        
        return TestSessionResult(
            total=len(self.results),
            passed=passed,
            failed=failed,
            duration=total_time,
            success=failed == 0
        )

@dataclass
class TestSessionResult:
    total: int
    passed: int
    failed: int
    duration: float
    success: bool
```

---

## 📋 **Phase 3: Integration & Testing (Semaine 5)**

### **3.1 Self-Testing - ProTest testé avec ProTest (3 jours)**

#### **Migrer les tests existants**
```python
# tests/test_protest_with_protest.py
from protest import ProTestSession, ProTestSuite, Scope, Use
from typing import Annotated

# Créer session ProTest pour tester ProTest
test_session = ProTestSession()
core_suite = ProTestSuite(name="Core Tests")

@core_suite.fixture
def sample_session():
    """Fixture qui crée une session ProTest à tester"""
    return ProTestSession()

@core_suite.test
def test_fixture_registration(session: Annotated[ProTestSession, Use(sample_session)]):
    """Test que l'enregistrement des fixtures fonctionne"""
    
    @session.fixture
    def dummy_fixture():
        return "test_value"
    
    assert "dummy_fixture" in session.fixtures
    assert session.fixtures["dummy_fixture"].scope == Scope.FUNCTION

@core_suite.test  
async def test_async_fixture_resolution(session: Annotated[ProTestSession, Use(sample_session)]):
    """Test de résolution de fixture async"""
    
    @session.fixture
    async def async_fixture():
        return "async_value"
    
    result = await session._resolve_fixture(Use(async_fixture))
    assert result == "async_value"

test_session.include_suite(core_suite)
```

### **3.2 Tests d'exemples automatisés (2 jours)**

#### **Test runner pour examples/**
```python
# tests/test_examples.py  
import subprocess
import sys
from pathlib import Path

examples_suite = ProTestSuite(name="Examples Tests")

@examples_suite.test
def test_basic_sync_example():
    """Vérifie que l'exemple basic sync fonctionne"""
    result = subprocess.run([
        sys.executable, "-m", "protest",
        "examples/01_basic_sync/usage.py:session"
    ], capture_output=True, text=True)
    
    assert result.returncode == 0
    assert "✓" in result.stdout
    assert "passed" in result.stdout

@examples_suite.test
def test_mixed_sync_async_example():
    """Le test ultime - sync/async mixing"""
    result = subprocess.run([
        sys.executable, "-m", "protest", 
        "examples/03_mixed_sync_async/usage.py:session"
    ], capture_output=True, text=True)
    
    assert result.returncode == 0
    # Vérifier que le test sync avec dep async fonctionne
    assert "test_sync_using_async_dep" in result.stdout
    assert "✓" in result.stdout

test_session.include_suite(examples_suite)
```

---

## 📋 **Phase 4: Polish & Documentation (Semaine 6)**

### **4.1 Error Messages excellents (2 jours)**

#### **Fixtures not found avec suggestions**
```python
# src/protest/errors.py
import difflib

class FixtureNotFoundError(Exception):
    def __init__(self, fixture_name: str, available_fixtures: list[str]):
        # Suggestion avec difflib
        suggestions = difflib.get_close_matches(
            fixture_name, available_fixtures, n=3, cutoff=0.6
        )
        
        message = f"Fixture '{fixture_name}' not found."
        
        if suggestions:
            if len(suggestions) == 1:
                message += f" Did you mean '{suggestions[0]}'?"
            else:
                message += f" Did you mean one of: {', '.join(suggestions)}?"
        
        message += f"\nAvailable fixtures: {', '.join(sorted(available_fixtures))}"
        
        super().__init__(message)
```

### **4.2 Performance benchmarks (2 jours)**

#### **Benchmark vs pytest**
```python
# benchmarks/compare_pytest.py
import time
import asyncio
import pytest
from protest import ProTestSession

# Même suite de tests en pytest et ProTest
# Mesurer:
# - Startup time
# - Execution time  
# - Memory usage
# - Async test performance

def benchmark_startup():
    """Compare session creation time"""
    
def benchmark_async_tests():
    """Compare async test execution"""
    
def benchmark_fixture_resolution():
    """Compare fixture resolution performance"""
```

### **4.3 Documentation & Examples (3 jours)**

#### **README.md complet**
```markdown
# ProTest 🚀

Modern async-first testing framework for Python.

## Why ProTest?

- **Zero Dependencies** - No bloat, no conflicts
- **Async Native** - Built for modern Python applications  
- **Explicit** - No magic, clear dependency injection
- **Fast** - Lightweight and performant

## Quick Start

```python
from protest import ProTestSession, Use
from typing import Annotated

session = ProTestSession()

@session.fixture
async def api_client():
    async with httpx.AsyncClient() as client:
        yield client

@session.test
async def test_api(client: Annotated[httpx.AsyncClient, Use(api_client)]):
    response = await client.get("/health")
    assert response.status_code == 200
```

Run with: `protest my_tests.py:session`
```

#### **Migration guide depuis pytest**
```markdown
# Migrating from pytest

## Fixtures
```python
# pytest
@pytest.fixture
def my_fixture():
    return "value"

# ProTest
@session.fixture  
def my_fixture():
    return "value"
```

## Tests
```python
# pytest  
def test_something(my_fixture):
    assert my_fixture == "value"

# ProTest
@session.test
def test_something(fixture: Annotated[str, Use(my_fixture)]):
    assert fixture == "value"
```
```

---

## 🎯 **Critères d'acceptation MVP**

### **Fonctionnalités obligatoires**
- [ ] ✅ Session/Suite/Test avec fixtures
- [ ] ✅ Injection via `Annotated[T, Use(fixture)]`
- [ ] ✅ Scopes `SESSION`, `SUITE`, `FUNCTION`
- [ ] ✅ Gestion automatique sync/async via `Sync()`
- [ ] ✅ CLI fonctionnel: `protest module:session`
- [ ] ✅ Reporting console avec couleurs
- [ ] ✅ Zero dependencies
- [ ] ✅ Self-hosting (ProTest testé avec ProTest)

### **Métriques de succès**
- [ ] Performance ≥ 80% de pytest (async tests)
- [ ] Startup time < 100ms
- [ ] Memory usage < pytest
- [ ] Examples folder complet avec 6+ cas d'usage
- [ ] Error messages clairs avec suggestions
- [ ] Documentation complète

### **Tests de validation**
- [ ] FastAPI app complète testée avec ProTest
- [ ] Migration d'une vraie test suite depuis pytest
- [ ] Benchmark performance documenté
- [ ] Zero external dependencies confirmed

---

## 🚀 **Timeline & Resources**

### **Planning global : 6 semaines**
- **Semaines 1-2** : Foundation + Examples-driven design
- **Semaines 3-4** : Core implementation (sync/async magic)
- **Semaine 5** : Integration & self-testing  
- **Semaine 6** : Polish & documentation

### **Ressources clés**
- **Starlette source code** - Thread pool implementation
- **FastAPI source code** - Dependency resolution patterns
- **Examples folder** - Design validation continue

### **Risques identifiés**
- **Complexité sync/async** - Mitigé par vol de code Starlette/FastAPI
- **Performance vs pytest** - À monitorer dès Phase 2
- **Error handling** - Beaucoup de edge cases à gérer

---

## 💎 **Différenciateurs clés**

1. **Zero Dependencies** - Installation propre, pas de conflits
2. **Async Native** - Conçu pour FastAPI/async apps modernes  
3. **Explicit DI** - `Use()` syntax claire et typée
4. **Modern Python** - Utilise `Annotated`, async/await, etc.
5. **Battle-tested patterns** - Code volé de Starlette/FastAPI

**ProTest = pytest moderne pour l'ère async** 🎯