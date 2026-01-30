
# Journal des Décisions Architecturales

Ce fichier documente les décisions de design, les tentatives abandonnées, et les questions ouvertes.

---

## 2025-01-30 : Capture des subprocesses - Abandon de FDCapture

**Contexte** : Besoin de capturer stdout/stderr des subprocesses dans les tests.

**Tentative** : Implémenter `FDCapture` avec `os.dup2()` pour rediriger les file descriptors OS vers des pipes, avec un thread de lecture en background.

**Problèmes rencontrés** :
- `select.select()` sur pipes ne fonctionne pas sur Windows
- Race conditions entre threads
- En mode concurrent (`-n 4`), impossible d'attribuer l'output d'un subprocess à un test spécifique (tous partagent fd 1/2)
- Complexité disproportionnée

**Décision** : Abandonner FDCapture. Fournir un helper `Shell` explicite à la place.

**Justification** :
- pytest-xdist fonctionne car multi-process (chaque worker a ses propres fd)
- ProTest est async in-process (fd partagés)
- Philosophie : forcer le dev à coder proprement plutôt que de la magie framework

**Alternative retenue** : `Shell.run()` avec pipes isolés par appel.

---

## 2025-01-30 : Plain functions vs @fixture() obligatoire

**Contexte** : Actuellement, `Use(plain_function)` lève `PlainFunctionError`. On force l'usage de `@fixture()`.

**Question ouverte** : Pourquoi ne pas autoriser les plain functions comme fixtures test-scoped sans tags ?

**Arguments POUR @fixture() obligatoire** :
- Explicite : on sait que c'est une fixture, pas un helper random
- Évite `Use(random_helper)` par accident
- Cohérence API
- Permet d'ajouter des comportements (tags, cache) plus tard sans breaking change

**Arguments POUR autoriser plain functions** :
- Moins de boilerplate pour les cas simples
- Une plain function = fixture test-scoped sans tags (sémantiquement équivalent)
- Plus "pythonic" (duck typing)

**Status** : À trancher. Actuellement on force `@fixture()`.

---

## 2025-01-30 : Scope at Binding vs Scope in Decorator

**Contexte** : Comment définir le scope d'une fixture ?

**Approche rejetée 1** : `@session.bind()` comme décorateur
- Problème : imports circulaires (fixtures.py doit importer session)
- Incompatible avec architecture modulaire

**Approche rejetée 2** : `@fixture(scope=FixtureScope.SESSION)`
- Problème : scope défini à la déclaration, pas au contexte d'utilisation
- Fixture "orpheline" si pas bindée

**Décision** : Scope at Binding
```python
@fixture()
def my_fixture(): ...

session.bind(my_fixture)  # SESSION scope
suite.bind(my_fixture)    # SUITE scope
# pas de bind = TEST scope
```

**Justification** :
- Pas de cycles d'import
- Le scope dépend du contexte d'utilisation
- Erreur explicite si double binding

**Inconvénient accepté** : On ne peut pas déterminer le scope en regardant uniquement le décorateur.

---

## Template pour nouvelles entrées

```
## YYYY-MM-DD : Titre

**Contexte** :

**Tentative/Options** :

**Décision** :

**Justification** :

**Status** : [Décidé / Question ouverte / Abandonné]
```