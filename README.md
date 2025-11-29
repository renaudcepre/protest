# ProTest - Cahier des Charges / Spécifications

Ce document décrit les objectifs, l'architecture, les fonctionnalités et les décisions
de conception du framework de test Python "ProTest". Il est destiné à évoluer de manière
itérative.

## Quick Start - Lancer les exemples

Chaque exemple est un projet indépendant avec son propre `pyproject.toml`.

```bash
cd examples/basic
uv sync
uv run protest run demo:session
```

## Légende

- 📋 Spécifié : Fonctionnalité dont les spécifications sont détaillées
- 🔍 À Explorer : Fonctionnalité à préciser ou dont les détails restent à définir
- 💡 Idée : Suggestion ou concept à considérer
- ℹ️ Note : Information contextuelle importante

## 1. Vision et Objectifs Généraux

L'objectif principal de ProTest n'est pas nécessairement de se différencier radicalement
de pytest en termes de fonctionnalités fondamentales, mais de proposer une alternative
moderne, conçue à partir de zéro ("from scratch"). La vision est de fournir un framework
de test :

- **Async Natif** : Construit autour d'asyncio pour tester facilement les applications
  asynchrones modernes (ex: FastAPI, Starlette). Gère nativement et automatiquement les
  interactions entre code de test/fixture synchrone et asynchrone.
- **Fortement Typé** : Utilisant pleinement les capacités de typage de Python moderne
  pour la clarté et la robustesse (ex: ). `typing.Annotated`
- **Explicite** : Évitant les mécanismes "magiques" ou implicites.
    - Les dépendances (fixtures) sont injectées explicitement via .
      `Annotated[..., Use(fixture)]`
    - Les tests sont enregistrés explicitement via des décorateurs (ex: ) sur des
      objets "Suite", plutôt que découverts par convention de nommage ().
      `@suite.test``test_*`
    - Les plugins sont enregistrés explicitement lors de l'instanciation de la session.
    - Le flux d'exécution doit être aussi clair que possible. (Voir Section 5 concernant
      le compromis sur `autouse`).

- **Sans Dette Technique** : En partant d'une base neuve, éviter de traîner l'héritage
  et la complexité accumulée par des outils plus anciens.

Le cas d'usage idéal est le test d'applications Python modernes, en particulier celles
utilisant asyncio. L'utilisateur cible est le développeur Python sensible aux avantages
du typage statique, de la programmation asynchrone et qui préfère des mécanismes
explicites à la convention implicite.

## 2. Architecture de Base

L'architecture s'inspire conceptuellement de frameworks web comme FastAPI :

- **)`ProTestSession`**: L'équivalent de l'application principale (). Orchestrateur
  central pour l'exécution et le cycle de vie des fixtures globales (scope ). Contient
  le registre des fixtures et gère les plugins enregistrés. Gère la boucle d'événements
  asyncio principale et potentiellement un `ThreadPoolExecutor` pour le code synchrone.
  **Session (**`FastAPI()``SESSION`
- : L'équivalent d'un routeur (). Permet de regrouper logiquement des tests et
  potentiellement des fixtures de scope . Requiert un argument `name` unique lors de
  l'instanciation (ex: ). Les suites sont incluses dans la session. *
  *Suite (`ProTestSuite`)**`APIRouter()``SUITE``ProTestSuite(name="Ma Suite")`
- **Test**: Une fonction décorée explicitement (ex: ), équivalente à une route (). C'est
  l'unité de test exécutable. Le nom du test est par défaut le nom de la fonction
  décorée, mais peut être surchargé (). Peut être `def` ou `async def`.
  `@suite.test``@router.get``@suite.test(name="custom_name")`
- **Fixtures**: Fonctions fournissant des ressources (données, connexions, etc.) aux
  tests ou à d'autres fixtures. Définies via ou , ou fournies par des plugins. Elles
  sont l'équivalent des dépendances (). Peuvent être `def` ou `async def`.
    - Gestion des scopes (, , prévu, envisagé). `SESSION``FUNCTION``SUITE``CLASS`
    - Support des générateurs synchrones (`yield`) et asynchrones (`async yield`) pour
      setup/teardown.

`@session.fixture``@suite.fixture``Depends()`

- **Injection de Dépendances**: Mécanisme explicite via et .
  `typing.Annotated``src.use.Use`
- **Support Asynchrone**: Conçu nativement pour asyncio. Gère automatiquement les appels
  entre sync/async (voir section 3.2).
- **Logging**: Intégration avec le module standard. `logging`
- **Plugins**: Objets Python passés explicitement à lors de son instanciation. Ils
  permettent d'étendre le framework en fournissant des hooks, des fixtures, etc. Le
  plugin lui-même agit comme un conteneur/registre pour ses contributions.
  `ProTestSession(plugins=[...])`

## 3. Fonctionnalités Clés

### 3.1. Gestion des Fixtures

- 📋 Définition et enregistrement via . Le scope par défaut est .
  `@session.fixture``FUNCTION`
- 📋 Définition via . Permet de définir une fixture dans le contexte organisationnel
  d'une suite.
    - Important : ne restreint pas les scopes possibles. On peut toujours spécifier (ou
      autre) explicitement. `@suite.fixture``scope=Scope.SESSION`
    - 💡 Émettre un warning si `@suite.fixture(scope=Scope.SESSION)` est utilisé, pour
      alerter que le cycle de vie dépasse celui de la suite.

`@suite.fixture`

- 📋 Résolution récursive des dépendances (fixture dépendant d'autres fixtures via ).
  `Use`
- 📋 Dépendance aux Paramètres : Une fixture doit pouvoir dépendre des paramètres
  spécifiques à une invocation de test paramétré.
    - Mécanisme : La fixture déclare un argument typé avec la classe de l'objet
      paramètre (ex: `def my_fixture(case: MyParamClass): ...`). Le système DI injectera
      l'instance `case` correspondant à l'itération de test en cours.

- 📋 Mise en cache basée sur le scope.
- 📋 Nettoyage automatique (teardown) pour les générateurs.
- 📋 Support scopes , . `SESSION``FUNCTION`
- 📋 Support scope . `SUITE`
- 🔍 Support scope . `CLASS`
- 📋 Fixtures `autouse` : Fonctionnalité maintenue. Possibilité de marquer une fixture
  avec `autouse=True` (ex: `@session.fixture(autouse=True)`) pour qu'elle soit exécutée
  automatiquement pour tous les tests dans son scope, sans être demandée explicitement
  via . Voir Section 5 pour la justification. `Use`
- 📋 Fixtures fournies par des plugins (enregistrées sur l'objet plugin, collectées par
  la session).

### 3.2. Support Asynchrone et Synchrone

- 📋 Exécution de tests et fixtures `async def`.
- 📋 Gestion Automatique Sync/Async : Le framework gère automatiquement les dépendances
  entre fonctions synchrones (`def`) et asynchrones (`async def`).
    - Si un test/fixture `def` dépend d'une fixture `async def`, ProTest exécutera
      d'abord la fixture `async` dans la boucle d'événements principale, puis exécutera
      le code `def` dépendant dans un thread pool externe (similaire à
      FastAPI/Starlette), en lui injectant le résultat de la fixture `async`.
    - Si un test/fixture `async def` dépend d'une fixture `def`, ProTest exécutera la
      fixture `def` dans le thread pool externe pour ne pas bloquer la boucle
      principale.
    - Conséquence : L'adaptateur `Sync(...)` et `nest_asyncio` ne sont plus nécessaires.
      L'utilisateur utilise simplement `Use(ma_fixture)` quelle que soit la nature (
      sync/async) de la source et de la destination.

### 3.3. Exécution des Tests

- 📋 Exécution de tests individuels (), de suites (), de sessions ().
  `run_test``run_suite``run_session`
- 📋 Nettoyage automatique des scopes à la fin de , , .
  `run_test``run_suite``run_session`
- 📋 Les tests sont des fonctions enregistrées via un décorateur ( ou `@session.test`).
  Le nom du test est par défaut le nom de la fonction, surchargeable via
  `@*.test(name="...")`. `@suite.test`

### 3.4. Organisation des Tests

- 📋 Concept de `ProTestSuite(name="...")` pour regrouper des tests, enregistrement via .
  Nom de suite obligatoire et utilisé pour l'identification. `@suite.test`
- 📋 Inclusion des suites dans la session via `session.include_suite(suite)`.
- 📋 Possibilité d'enregistrer des tests directement sur la session (`@session.test`).

### 3.5. Système de Hooks et Plugins

- **Plugins** :
    - 📋 Enregistrement Explicite : Les plugins sont activés en passant une liste
      d'objets plugins à l'instanciation de la session:
      `ProTestSession(plugins=[plugin1, plugin2])`. Pas de découverte automatique.
    - 📋 Interaction Session/Plugin : L'objet plugin agit comme un conteneur. Il
      enregistre ses propres hooks et fixtures (via des décorateurs comme
      `@plugin.hook`, `@plugin.fixture` qui peuplent des attributs internes comme
      `plugin._hooks`, `plugin._fixtures`). La , lors de son initialisation, collecte
      ces contributions en accédant à ces attributs (ou via une méthode standard type
      `plugin.get_contributions()`) et les intègre à ses registres centraux.
      `ProTestSession`
    - 🔍 Capacités : Que peuvent faire les plugins ? (Implémenter des hooks, définir des
      fixtures, ajouter des options CLI ?, etc.)

- **Hooks** :
    - 📋 Mécanisme pour étendre le framework via `@protest.hook(Event.XYZ)` (pour
      l'utilisateur final) et/ou `@plugin.hook(Event.XYZ)` (pour les développeurs de
      plugins).
    - 📋 Définition d'un `Enum Event` (la liste se remplira au fur et à mesure).
    - 📋 Déclenchement des hooks aux points clés du cycle de vie par la .
      `ProTestSession`

### 3.6. Paramétrisation

- 📋 Approche retenue : Utilisation d'un décorateur `@suite.parametrize` (ou
  `@session.parametrize`) acceptant une liste d'objets (ex: dataclasses) ou de
  dictionnaires.
    - Si objets/dataclasses : L'instance de l'objet contenant le jeu de paramètres est
      injectée dans un argument unique de la fonction de test (ex:
      `def my_test(case: MyParamClass, ...)`). L'accès aux paramètres se fait via
      `case.param_name`.
        - _Avantages_ : Typage fort dès la définition, structuration, possibilité
          d'ajouter des métadonnées (`test_id`) ou méthodes.
        - _Inconvénients_ : Nécessite la définition d'une classe dédiée.

    - Si dictionnaires : Les valeurs du dictionnaire sont injectées dans les arguments
      de la fonction de test dont le nom correspond aux clés du dictionnaire (ex:
      `def my_test(param1: str, param2: int, ...)` pour un dictionnaire
      `{"param1": "a", "param2": 1}`).
        - _Avantages_ : Plus léger pour les cas simples, pas de classe à définir.
        - _Inconvénients_ : Pas de typage fort à la définition, signature du test
          potentiellement longue.

- 📋 Implémentation du décorateur `@*.parametrize` et de la logique d'injection
  correspondante.

### 3.7. Reporting

- 🔍 Affichage des résultats, erreurs, statistiques.
- 📋 Le reporting par défaut sera une sortie console textuelle (style pytest mais
  potentiellement modernisé : couleurs, emojis...).
- 📋 Les formats de reporting avancés (HTML, JUnit XML...) devront être implémentés via
  le système de plugins/hooks.

### 3.8. Optimisation (Idées)

- 💡 "Certificats de test" pour potentiellement skipper des tests sur la CI.

### 3.9. Exécution Parallèle (Fonctionnalité Future/Avancée)

- 🔍 Possibilité future d'exécuter les tests en parallèle (multi-processus) pour
  accélérer l'exécution.
- ℹ️ Complexité élevée liée à l'isolation des tests, la gestion des fixtures partagées
  et l'agrégation des résultats. Pas une priorité pour le MVP.

## 4. Points Techniques / Difficultés Connues ou Anticipées

- Implémentation de la gestion Sync/Async automatique : Logique d'orchestration pour
  résoudre les fixtures async puis exécuter le code sync dépendant dans un thread pool.
  Gestion du thread pool.
- Conception détaillée du système de hooks (signatures, gestion async, ordre d'appel).
- Conception du système de reporting console par défaut.
- Implémentation de la logique de paramétrisation (`@*.parametrize`).
- Implémentation de l'injection des paramètres dans les fixtures (le contexte de
  résolution doit connaître l'instance de paramètre active).
- Définition de l'API Plugin : Préciser la structure exacte de l'objet plugin et comment
  la session collecte ses contributions (accès direct aux attributs vs méthode
  standard).
- Gestion des options CLI ajoutées par les plugins : Comment permettre aux plugins
  d'ajouter des options CLI si l'enregistrement se fait lors de l'instanciation de la
  session (qui a lieu après le parsing CLI initial) ? Nécessite peut-être un mécanisme
  de pré-configuration ou un hook très précoce.
- Complexité de l'exécution parallèle : Isolation, gestion des fixtures, reporting
  distribué.
- Fiabilité du mécanisme de "certificat de test".

## 5. Philosophie / Non-Objectifs

- **Explicite avant tout** : Principe directeur. Privilégier les mécanismes clairs et
  explicites (DI via , enregistrement des tests via décorateurs, enregistrement des
  plugins via argument). `Use`
- **Compromis sur `autouse`** : La fonctionnalité `autouse=True` pour les fixtures est
  maintenue. Bien que l'utilisation de la fixture par le test soit implicite (non
  déclarée dans la signature), sa définition reste explicite. Ce compromis est accepté
  pour des raisons pragmatiques, notamment pour faciliter la gestion des
  setups/teardowns transversaux (logging, patching, transactions BDD, etc.) sans
  répétition excessive dans les signatures de tests.
- **Simplicité d'utilisation Sync/Async** : Le framework doit masquer la complexité de
  l'interaction sync/async à l'utilisateur final, en adoptant une approche similaire à
  FastAPI.
- _(À compléter)_

## 6. Interface Ligne de Commande (CLI)

L'exécution des tests se fera via une commande en ligne de commande.

### 6.1. Point d'Entrée

Le lanceur de tests identifie la session de test à exécuter via une syntaxe
`module:variable`, où `module` est le chemin vers le fichier Python (ou module) et
`variable` est le nom de l'instance dans ce fichier. `ProTestSession`
Exemple :

``` bash
protest path/to/my_tests.py:test_session
```

### 6.2. Exécution et Filtrage

- **Exécuter tous les tests** :

``` bash
  protest my_tests:test_session
```

- **Filtrer par suite de tests** : L'option permet de n'exécuter que les tests
  appartenant à une suite spécifique, identifiée par le nom fourni lors de sa création (
  `ProTestSuite(name=...)`). `--suite`

``` bash
  protest my_tests:test_session --suite "User Management"
```

- **Filtrer par test** : L'option permet de n'exécuter qu'un ou plusieurs tests
  spécifiques.
    - Le nom du test est par défaut le nom de la fonction Python, ou celui spécifié via
      `@*.test(name="...")`.
    - Si `nom_de_mon_test` correspond à plusieurs tests (dans différentes suites), tous
      les tests correspondants seront exécutés (similaire à `pytest -k`).
    - Pour cibler un test spécifique sans ambiguïté, utiliser la syntaxe
      `nom_de_la_suite::nom_du_test`.

`--test`

``` bash
  # Exécute tous les tests nommés 'test_creation'
  protest my_tests:test_session --test test_creation

  # Exécute uniquement le test 'test_creation' de la suite 'User Management'
  protest my_tests:test_session --test "User Management::test_creation"
```

- **Filtrer par tags** :
    - 📋 Une option (ex: `-t <tag>` ou `--tags <tag>`) permettra de sélectionner des
      tests basés sur les tags. Plusieurs options pourraient être combinées (logique
      AND/OR à définir). Une syntaxe d'expression complexe ("tag1 and not tag2") est
      différée. `-t`
