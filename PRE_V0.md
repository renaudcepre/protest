
### 🛠️ 1. Code : Gestion des "Factory Errors"
C'est la dernière fonctionnalité manquante pour la robustesse.

* [ ] **Exceptions** : Ajouter la classe `FixtureError` dans `protest/exceptions.py`.
* [ ] **Modèle** : Ajouter le champ `is_factory: bool` à la classe `Fixture` (`core/fixture.py`).
* [ ] **Décorateur** : Ajouter le paramètre `factory=False` au décorateur `@fixture` (`di/decorators.py`).
* [ ] **Resolver** : Implémenter le wrapping automatique des résultats si `is_factory=True` pour lever `FixtureError` en cas de pépin (`di/resolver.py`).
* [ ] **Runner** : Ajouter un bloc `except FixtureError` dans `_run_test` pour classer ces erreurs en "Infra/Setup" et non "Test Fail" (`core/runner.py`).

### 🧹 2. Nettoyage & Projet
Pour faire propre avant la photo officielle.

* [ ] **Git Reboot** : Créer la branche orpheline `main`, faire le commit unique "Initial Release".
* [ ] **Licence** : Ajouter le fichier `LICENSE` (MIT).
* [ ] **Ignore** : Vérifier que le `.gitignore` est bien configuré (exclure `.venv`, `__pycache__`, etc.).

### 🚀 3. Release
Le moment de vérité.

* [ ] **Tag** : Créer le tag `v0.1.0`.
* [ ] **Champagne** : Obligatoire. 🍾

C'est tout. Tu as le feu vert !