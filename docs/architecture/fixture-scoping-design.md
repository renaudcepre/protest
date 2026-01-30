# Fixture Scoping Design Decision

## Contexte

ProTest est un framework de test async-first avec injection de dépendances explicite. Les fixtures peuvent avoir trois scopes :

- **SESSION** : Une instance pour toute la session de tests
- **SUITE** : Une instance par suite de tests
- **TEST** : Une instance fraîche par test (défaut)

Le défi architectural est de permettre l'organisation des fixtures en modules séparés tout en gardant une API explicite et sans ambiguïté.

---

## Approche 1 : Tree-Based (rejetée)

### Principe

Le scope est déterminé par **où** on décore la fixture :

```python
# fixtures.py
from myproject.session import session  # Import nécessaire

@session.bind()
def database():
    yield connect()

@api_suite.bind()
def client():
    return Client()
```

### Avantages

- API explicite : une action = scope + binding
- Impossible d'avoir une fixture "orpheline"
- Mental model simple

### Problème bloquant : Imports circulaires

```
fixtures.py  ←──imports──  session.py
     │                          │
     └────imports───────────────┘
```

Pour décorer avec `@session.bind()`, le fichier fixtures.py doit importer `session`. Mais session.py doit importer les fixtures pour les utiliser dans les tests.

**Verdict** : Incompatible avec une architecture modulaire (fichiers > 400 lignes sinon).

---

## Approche 2 : Mark & Collect (rejetée)

### Principe

Séparer la déclaration du scope et le binding :

```python
# fixtures.py (pas d'import de session)
from protest import fixture, FixtureScope

@fixture(scope=FixtureScope.SESSION)
def database():
    yield connect()

@fixture(scope=FixtureScope.SUITE)
def client():
    return Client()
```

```python
# session.py
from .fixtures import database, client

session = ProTestSession()
api_suite = ProTestSuite("API")

session.use_fixtures([database])
api_suite.use_fixtures([client])
```

### Avantages

- Pas de cycle d'import
- Fixtures dans des modules séparés

### Problèmes identifiés

| Problème | Description |
|----------|-------------|
| **Deux étapes requises** | Décorateur (`scope=X`) + binding (`use_fixtures`). Redondant et source d'erreurs. |
| **Incohérence possible** | `@fixture(scope=SUITE)` + `session.use_fixtures()` = mismatch silencieux ou erreur ? |
| **Fixtures orphelines** | Une fixture `scope=SUITE` sans binding a un comportement implicite surprenant (scope "flottant" = une instance par suite appelante). |
| **Double source de vérité** | Le scope est déclaré au décorateur ET vérifié au binding. Lequel fait foi ? |

**Verdict** : Résout les imports mais introduit de l'ambiguïté et des états incohérents.

---

## Approche 3 : Scope au Binding (retenue)

### Principe

Le décorateur marque une fonction comme fixture, **sans déclarer de scope**. Le scope est déterminé uniquement par le binding.

```python
# fixtures.py (pas d'import de session, pas de scope)
from protest import fixture

@fixture()
def database():
    yield connect()

@fixture()
def client():
    return Client()

@fixture()
def temp_file():
    yield "/tmp/test"
```

```python
# session.py
from protest import ProTestSession, ProTestSuite
from .fixtures import database, client

session = ProTestSession()
api_suite = ProTestSuite("API")

session.bind(database)      # database → SESSION scope
api_suite.bind(client)      # client → SUITE scope
# temp_file non bindée         # temp_file → TEST scope (défaut)

session.add_suite(api_suite)
```

### Utilisation dans les tests

```python
@api_suite.test()
def test_example(
    db: Annotated[Connection, Use(database)],    # SESSION (bindé à session)
    c: Annotated[Client, Use(client)],           # SUITE (bindé à api_suite)
    tmp: Annotated[str, Use(temp_file)],         # TEST (pas bindé = défaut)
):
    pass
```

### Règles de résolution

1. **Fixture bindée** → utilise le scope du binding
2. **Fixture non bindée** → TEST scope par défaut
3. **Double binding** → Erreur explicite (`AlreadyRegisteredError`)

### Avantages

| Aspect | Bénéfice |
|--------|----------|
| **Pas de cycle d'import** | fixtures.py n'importe pas session.py |
| **Source de vérité unique** | Le scope est défini au binding, pas au décorateur |
| **Pas d'orphelins ambigus** | Non bindé = TEST scope (comportement sain et prévisible) |
| **API familière** | `session.bind(fn)` ressemble à `@session.bind()` |
| **Simplicité du décorateur** | `@fixture()` fait une seule chose : marquer comme fixture |
| **Erreurs explicites** | Double binding = erreur, pas de comportement implicite |

### Inconvénient accepté

On ne peut pas déterminer le scope d'une fixture en regardant uniquement son décorateur. Il faut regarder où elle est bindée.

**Justification** : Le scope d'une fixture dépend de son contexte d'utilisation, pas de sa définition. Une même fixture pourrait théoriquement être SESSION dans un projet et SUITE dans un autre. Le binding rend cette dépendance explicite.

---

## Migration depuis Mark & Collect

### Avant (Mark & Collect)

```python
@fixture(scope=FixtureScope.SESSION, tags=["database"])
def database():
    yield connect()

session.use_fixtures([database])
```

### Après (Scope au Binding)

```python
@fixture(tags=["database"])
def database():
    yield connect()

session.bind(database)
```

### Changements

1. Retirer `scope=` du décorateur `@fixture()`
2. Remplacer `session.use_fixtures([fn])` par `session.bind(fn)`
3. Remplacer `suite.use_fixtures([fn])` par `suite.bind(fn)`

---

## Diagramme de décision

```
                    @fixture()
                        │
                        ▼
            ┌─────────────────────┐
            │  Fixture marquée    │
            │  (pas de scope)     │
            └─────────────────────┘
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
   session.bind() suite.bind()  (rien)
          │             │             │
          ▼             ▼             ▼
      SESSION         SUITE         TEST
       scope          scope         scope
```

---

## Validation du scope des dépendances

Les règles de scope restent inchangées :

- SESSION peut dépendre de : SESSION uniquement
- SUITE peut dépendre de : SESSION, SUITE (même suite ou parent)
- TEST peut dépendre de : tout

```python
@fixture()
def config():
    return {}

@fixture()
def database(cfg: Annotated[dict, Use(config)]):
    yield connect(cfg)

session.bind(config)    # SESSION
session.bind(database)  # SESSION - OK (dépend de SESSION)
```

```python
session.bind(config)    # SESSION
api_suite.bind(database)  # SUITE dépend de SESSION → OK
```

```python
api_suite.bind(config)  # SUITE
session.bind(database)  # SESSION dépend de SUITE → ERREUR
```

---

## Conclusion

L'approche "Scope au Binding" combine les avantages des deux approches précédentes :

- **De Tree-Based** : une seule action pour définir le scope (`session.bind(fn)`)
- **De Mark & Collect** : pas de cycles d'import

Elle élimine les inconvénients :

- **Pas de redondance** : le scope n'est déclaré qu'une fois
- **Pas d'ambiguïté** : le binding EST le scope
- **Pas d'orphelins** : non bindé = TEST scope explicite