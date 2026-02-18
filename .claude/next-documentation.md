# Documentation Rewrite - Nuxt Content

## Objectif

Repartir de zero sur la doc utilisateur dans un site Nuxt Content moderne, en profitant
pour faire une review complete du contenu. L'ancienne doc (mkdocs) sert de reference
mais on ne copie pas betement.

---

## Stack technique

Base identique a `jeveuxmonbrevet` (stack prouvee en prod).

| Composant       | Choix                              | Version   | Raison                                    |
|-----------------|------------------------------------|-----------|--------------------------------------------|
| Framework       | Nuxt                               | ^4.3.0    | Meme version que jeveuxmonbrevet           |
| UI              | @nuxt/ui                           | ^4.4.0    | Design pro, dark mode, composants          |
| Content         | @nuxt/content                      | ^3.11.2   | MDC, composants Vue dans le markdown       |
| MDC             | @nuxtjs/mdc                        | ^0.20.1   | Composants dans le markdown                |
| Styling         | Tailwind                           | ^4.1.18   | Tailwind v4, @theme static                 |
| Fonts           | @nuxt/fonts                        | ^0.13.0   | Gestion auto des fonts                     |
| Icons           | @iconify-json/lucide               | ^1.2.87   | Pack d'icones                              |
| Terminal output | Pipeline auto-gen (ANSI → HTML)    | custom    | Outputs toujours synces avec le vrai code  |
| Palette         | Noir + Violet (`#A855F7`)          | -         | Identite visuelle du logo                  |
| Linting         | @nuxt/eslint                       | ^1.13.0   | Meme config                                |
| TypeScript      | typescript                         | ^5.9.3    | Strict                                     |
| Package manager | pnpm                               | 10.28.2   | Meme que jeveuxmonbrevet                   |
| Deploy          | Vercel ou GitHub Pages             | -         | Gratuit, preview sur PR                    |
| Dossier         | `website/` a la racine du monorepo | -         | Separe du code Python                      |

### Differences avec jeveuxmonbrevet

| Element                | jeveuxmonbrevet       | protest website       | Raison                    |
|------------------------|-----------------------|-----------------------|---------------------------|
| Supabase               | oui                   | **non**               | Pas d'auth, site statique |
| Pinia                  | oui                   | **non**               | Pas de state management   |
| PWA                    | oui                   | **non**               | Pas besoin offline        |
| KaTeX (math)           | oui                   | **non**               | Pas de formules math      |
| Vitest                 | oui                   | **a voir**            | Optionnel                 |
| Sitemap                | oui                   | **oui**               | SEO                       |
| SSR                    | hybrid                | **full static**       | `nuxt generate`           |
| sharp                  | oui (images)          | **optionnel**         | Opti images si besoin     |

### Config static (nuxt.config.ts)

```ts
export default defineNuxtConfig({
  ssr: true,           // SSR pour le prerender
  nitro: {
    prerender: {
      crawlLinks: true,  // Crawl toutes les pages
      routes: ['/']
    }
  }
})
```

### CSS / Theme (assets/css/main.css)

Meme pattern que jeveuxmonbrevet mais avec la palette violet/noir :

```css
@import "tailwindcss";
@import "@nuxt/ui";

@theme static {
  --font-sans: 'Inter', sans-serif;
  --font-mono: 'JetBrains Mono', monospace;

  /* Purple palette (from logo #A855F7) */
  --color-brand-50: #faf5ff;
  --color-brand-100: #f3e8ff;
  --color-brand-200: #e9d5ff;
  --color-brand-300: #d8b4fe;
  --color-brand-400: #c084fc;
  --color-brand-500: #a855f7;   /* Primary - logo color */
  --color-brand-600: #9333ea;
  --color-brand-700: #7e22ce;
  --color-brand-800: #6b21a8;
  --color-brand-900: #581c87;
  --color-brand-950: #3b0764;

  /* Dark palette */
  --color-dark-50: #f8fafc;
  --color-dark-100: #f1f5f9;
  --color-dark-200: #e2e8f0;
  --color-dark-300: #cbd5e1;
  --color-dark-400: #94a3b8;
  --color-dark-500: #64748b;
  --color-dark-600: #475569;
  --color-dark-700: #334155;
  --color-dark-800: #1e293b;
  --color-dark-900: #0f172a;
  --color-dark-950: #020617;
}
```

### app.config.ts

```ts
export default defineAppConfig({
  ui: {
    colors: {
      primary: 'brand',
      neutral: 'dark'
    }
  }
})
```

---

## Terminal outputs auto-generes

### Probleme

Maintenir a la main les blocs "terminal output" dans la doc est invivable :
- Un changement d'indentation dans le reporter → toute la doc est fausse
- On oublie de mettre a jour → la doc ment
- C'est chiant

### Solution : pipeline de generation

Les outputs terminal sont generes automatiquement en runnant les vrais exemples.

#### Architecture

```
examples/              # Les vrais scripts ProTest (existent deja)
  minimal/
  yorkshire/
  builtins/
  ...

scripts/
  generate-doc-outputs.py   # Script qui run les exemples et capture stdout

website/content/_outputs/   # Fichiers generes (gitignore-able ou commites)
  quickstart.ansi
  collect-only.ansi
  tags-filter.ansi
  parallel.ansi
  ...

doc-examples.yml            # Manifeste declaratif
```

#### Manifeste `doc-examples.yml`

```yaml
outputs:
  - id: quickstart
    command: "protest run session -q"
    working_dir: "examples/minimal"
    description: "Basic quickstart output"

  - id: quickstart-verbose
    command: "protest run session"
    working_dir: "examples/minimal"
    description: "Quickstart with full output"

  - id: collect-only
    command: "protest run session --collect-only"
    working_dir: "examples/minimal"
    description: "Collection mode output"

  - id: yorkshire-full
    command: "protest run tests:session"
    working_dir: "examples/yorkshire"
    description: "Full suite run with fixtures, tags"

  - id: tags-filter
    command: "protest run tests:session --no-tag database"
    working_dir: "examples/yorkshire"
    description: "Tag filtering example"

  - id: keyword-filter
    command: "protest run tests:session -k user"
    working_dir: "examples/yorkshire"
    description: "Keyword filtering"

  - id: parallel
    command: "protest run session -n 5"
    working_dir: "examples/stress_test"
    description: "Parallel execution"

  - id: builtins-caplog
    command: "protest run session"
    working_dir: "examples/builtins"
    description: "Built-in fixtures demo"

  - id: last-failed
    command: "protest run session --lf"
    working_dir: "examples/minimal"
    description: "Last-failed mode"
```

#### Script `scripts/generate-doc-outputs.py`

Lit le manifeste, run chaque commande, capture stdout/stderr, ecrit dans `website/content/_outputs/{id}.ansi`.

Options :
- `--check` : verifie que les outputs existants matchent (pour CI)
- `--update` : regenere tout
- `--only quickstart` : regenere un seul

#### Integration CI

```yaml
# Dans .github/workflows/ci.yml
- name: Check doc outputs are up to date
  run: python scripts/generate-doc-outputs.py --check
```

Si un reporter change et que les outputs divergent → CI fail → on sait qu'il faut regenerer.

#### Usage dans le markdown (Nuxt Content MDC)

```md
## Running your first test

::terminal-output{id="quickstart"}
::
```

Le composant `TerminalOutput.vue` :
1. Lit `_outputs/quickstart.ansi` au build time (via Nuxt Content query ou import)
2. Convertit ANSI → HTML colore (lib `ansi-to-html`)
3. Affiche dans un bloc terminal stylise

#### Avantages

- **Zero maintenance manuelle** des outputs dans la doc
- **Source of truth** = le vrai programme
- **CI verifie** la coherence doc ↔ code
- **Un seul endroit** pour ajouter un nouvel exemple (le manifeste)
- Les exemples dans `examples/` servent AUSSI de tests d'integration

---

## Snippets de code statiques

Pour les blocs de code source (pas les outputs), on garde du markdown classique avec syntax highlighting. Pas de Pyodide - ca n'apporte rien pour un framework de test.

### Composants Vue prevus

#### `CodeDiff.vue`
- Deux colonnes : pytest | ProTest
- Pour la page "Why ProTest?"
- Usage MDC : `::code-diff` avec slots `#pytest` et `#protest`

#### `TerminalOutput.vue`
- Lit les fichiers `.ansi` generes par le pipeline
- Convertit ANSI → HTML (lib `ansi-to-html`)
- Design terminal sombre avec titre de commande
- Bouton copy (copie le texte brut sans les codes ANSI)

---

## Plan du site

```
website/content/
├── index.md                        # Landing page hero + features
├── 1.getting-started/
│   ├── 1.installation.md
│   ├── 2.quickstart.md             # Premier test en 2 minutes
│   └── 3.your-first-suite.md       # Session + Suite + Fixtures
├── 2.core-concepts/
│   ├── 1.sessions-and-suites.md
│   ├── 2.tests.md
│   ├── 3.fixtures.md               # Tout sur les fixtures (scope, teardown, autouse)
│   ├── 4.dependency-injection.md   # Use(), Annotated, validation
│   ├── 5.factories.md
│   ├── 6.parameterized-tests.md    # ForEach, From, cartesian
│   └── 7.tags.md                   # Transitive tags, filtrage
├── 3.guides/
│   ├── 1.pytest-migration.md       # Guide migration complet
│   ├── 2.parallel-testing.md       # -n, max_concurrency, patterns
│   ├── 3.ci-integration.md         # GitHub Actions, CTRF, JUnit (quand dispo)
│   └── 4.plugins.md                # Ecrire un plugin
├── 4.reference/
│   ├── 1.cli.md                    # Toutes les commandes et flags
│   ├── 2.api.md                    # ProTestSession, ProTestSuite, fixture, factory, Use, etc.
│   ├── 3.builtins.md               # caplog, mocker, Shell, warns
│   └── 4.reporters.md              # Rich, ASCII, CTRF, Web
├── 5.faq.md
└── 6.why-protest.md                # Page de vente : comparaisons, argumentaire
```

---

## Inventaire de l'ancienne doc vs nouvelle structure

| Ancienne doc                                    | Statut                          | Destination nouvelle doc                    | Action                                                |
|-------------------------------------------------|---------------------------------|---------------------------------------------|-------------------------------------------------------|
| `getting-started/installation.md` (22 lignes)   | Trop court                      | `1.getting-started/1.installation.md`       | Rewrite: ajouter pip install, optionals, verification |
| `getting-started/quickstart.md` (90 lignes)     | OK mais a verifier              | `1.getting-started/2.quickstart.md`         | Review + verifier exemples                            |
| `getting-started/running-tests.md` (168 lignes) | En cours de modif (uncommitted) | `4.reference/1.cli.md`                      | Fusionner avec cli.md                                 |
| `core-concepts/sessions-and-suites.md`          | A verifier                      | `2.core-concepts/1.sessions-and-suites.md`  | Review                                                |
| `core-concepts/tests.md`                        | Manque warns, skip conditionnel | `2.core-concepts/2.tests.md`                | Completer                                             |
| `core-concepts/fixtures.md`                     | A verifier                      | `2.core-concepts/3.fixtures.md`             | Review                                                |
| `core-concepts/dependency-injection.md`         | Doublon potentiel avec fixtures | `2.core-concepts/4.dependency-injection.md` | Clarifier scope                                       |
| `core-concepts/factories.md`                    | A verifier                      | `2.core-concepts/5.factories.md`            | Review                                                |
| `core-concepts/parameterized-tests.md`          | A verifier                      | `2.core-concepts/6.parameterized-tests.md`  | Review                                                |
| `core-concepts/tags.md`                         | OK                              | `2.core-concepts/7.tags.md`                 | Review                                                |
| `core-concepts/builtins.md` (458 lignes)        | Le plus gros, warns recent      | `4.reference/3.builtins.md`                 | Review + verifier warns                               |
| `core-concepts/reporters.md`                    | A verifier                      | `4.reference/4.reporters.md`                | Review                                                |
| `cli.md` (389 lignes)                           | Doublon avec running-tests.md   | `4.reference/1.cli.md`                      | Fusionner les deux                                    |
| `faq.md` (168 lignes)                           | A enrichir                      | `5.faq.md`                                  | Ajouter questions reelles                             |
| `best-practices.md` (493 lignes)                | A verifier                      | Repartir dans les guides                    | Eclater                                               |
| `guides/pytest-to-protest.md` (484 lignes)      | Critique pour adoption          | `3.guides/1.pytest-migration.md`            | Review approfondie                                    |
| `internals/*` (6 fichiers)                      | Dev docs                        | Hors scope site public (garder dans repo)   | Ne pas migrer                                         |
| `architecture/fixture-scoping-design.md`        | Decision doc                    | Garder en interne                           | Ne pas migrer                                         |

### Contenu nouveau (n'existe pas encore)

| Page                  | Contenu                                                          |
|-----------------------|------------------------------------------------------------------|
| `your-first-suite.md` | Tuto progressif : session seule → ajout suite → ajout fixtures   |
| `parallel-testing.md` | Guide dedie au parallelisme (patterns, gotchas, max_concurrency) |
| `ci-integration.md`   | GitHub Actions, GitLab CI, CTRF output                           |
| `plugins.md` (guide)  | Ecrire son premier plugin (tuto complet)                         |
| `api.md` (reference)  | Reference API exhaustive                                         |
| `why-protest.md`      | Page de vente / argumentaire (expand du README)                  |

---

## Workflow de validation

Chaque section suit ce flow :

```
1. Draft par Claude → fichier .md dans website/content/
2. Review par Renaud → commentaires / corrections
3. Validation → on passe a la section suivante
4. Repeat
```

Ordre de redaction propose :

### Phase 1 - Fondations (bloquant release)

- [ ] Init projet Nuxt Content + layout de base
- [ ] Landing page (index.md)
- [ ] Installation
- [ ] Quickstart
- [ ] Why ProTest? (page de vente)

### Phase 2 - Core (bloquant release)

- [ ] Sessions & Suites
- [ ] Tests
- [ ] Fixtures
- [ ] Dependency Injection
- [ ] Factories
- [ ] Parameterized Tests
- [ ] Tags

### Phase 3 - Guides

- [ ] Pytest Migration
- [ ] Parallel Testing
- [ ] CI Integration
- [ ] Ecrire un Plugin

### Phase 4 - Reference

- [ ] CLI Reference
- [ ] API Reference
- [ ] Builtins
- [ ] Reporters

### Phase 5 - Polish

- [ ] FAQ
- [ ] Pipeline generate-doc-outputs (script + manifeste + CI check)
- [ ] Composant TerminalOutput.vue (ANSI → HTML)
- [ ] Composant CodeDiff.vue (pytest vs protest)
- [ ] Exemples manquants (factories, parameterized, plugins, skip/xfail)
- [ ] SEO, OpenGraph, meta
- [ ] Deploy

---

## Exemples existants (base pour le pipeline)

| Dossier | Contenu | Utilisable pour |
|---|---|---|
| `examples/minimal/` | Session basique, un test | Quickstart, first steps |
| `examples/yorkshire/` | App complete, suites, fixtures, tags | Core concepts, tags, filtering |
| `examples/builtins/` | caplog, mocker, shell | Builtins reference |
| `examples/stress_test/` | Tests paralleles | Parallel guide |
| `examples/subprocess_capture/` | Shell fixture | Builtins (Shell) |
| `examples/dogfood/` | httpx, pydantic, starlette | Real-world guides, CI |

### Exemples a creer

| Exemple manquant | Pour documenter |
|---|---|
| `examples/factories/` | Factories, FixtureFactory |
| `examples/parameterized/` | ForEach, From, cartesian |
| `examples/plugins/` | Ecrire un plugin custom |
| `examples/skip_xfail/` | skip conditionnel, xfail, retry |

---

## Points d'attention

1. **README.md** - Devra pointer vers le site de doc au lieu de contenir toute l'API
   reference
2. **Installation** - Passer de `git clone` a `pip install protest` (necessite
   publication PyPI d'abord)
3. **Exemples** - Chaque snippet de la doc doit etre testable (extraire dans `examples/`
   si possible)
4. **Langue** - Doc en **anglais** (audience internationale)
5. **Doublons** - L'ancienne doc a `cli.md` ET `running-tests.md` qui se chevauchent →
   fusionner
6. **best-practices.md** - 493 lignes d'un seul bloc → eclater dans les guides
   pertinents
7. **internals/** - Ne PAS migrer vers le site public, garder dans le repo pour les
   contributeurs

---

## Issues GitHub liees

- **#78** - docs: full review + migration Nuxt Content (issue principale)
- **#54** - install release-please (pour changelog automatique sur le site)
- **#44** - `protest docs` command (living documentation)

---

## Branding / Theme

Tire du logo SVG (`assets/logo-term.svg`) :

| Element | Valeur | Note |
|---|---|---|
| Couleur primaire | `#A855F7` (purple-500) | Cercles du logo |
| Texte sur sombre | `#f8fafc` (slate-50) | Texte "protest" dans le logo |
| Font logo | JetBrains Mono 600 | Monospace, bold |
| Style | Fond noir, accents violet | Terminal-inspired |

Nuxt UI permet de configurer la couleur primaire dans `app.config.ts` :

```ts
export default defineAppConfig({
  ui: {
    primary: 'purple',
    gray: 'neutral',
  }
})
```

Dark mode par defaut (theme "terminal"), light mode dispo.

---

## Decisions

| Question                               | Options                                        | Decision                                 |
|----------------------------------------|------------------------------------------------|------------------------------------------|
| Stack                                  | Nuxt UI Pro / custom / autre                   | **Nuxt UI 4.4 (meme stack que jvmb)**   |
| Package manager                        | npm / pnpm / yarn                              | **pnpm** (meme que jvmb)                |
| Tailwind                               | v3 / v4                                        | **v4** (@theme static, meme que jvmb)   |
| Monorepo ou repo separe pour le site ? | `website/` dans le repo vs repo `protest-docs` | **`website/` dans le repo**              |
| Versioning de la doc ?                 | Une seule version (latest) vs multi-version    | **latest uniquement pour v0.x**          |
| Rendu                                  | SSR / SPA / Static                             | **Full static** (`nuxt generate`)        |

### Encore ouvertes

| Question                               | Options                                        |
|----------------------------------------|------------------------------------------------|
| Domaine                                | protest.dev ? protest-py.dev ? GitHub Pages ?  |
| Deploy                                 | Vercel ? Netlify ? GitHub Pages ?              |
| Doc API auto-generee ?                 | Sphinx-like extraction vs manuelle             |