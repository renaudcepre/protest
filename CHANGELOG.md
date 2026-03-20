# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1](https://github.com/renaudcepre/protest/compare/protest-v0.1.0...protest-v0.1.1) (2026-03-20)


### Features

* add `SuitePath` value object and integrate across codebase ([085b065](https://github.com/renaudcepre/protest/commit/085b065c49eadd83907363ca6885c02e820a95bf))
* add `tmp_path` fixture for temporary directory creation and cleanup ([35902ff](https://github.com/renaudcepre/protest/commit/35902ff7510698795511ce67197b5d792cd9ac1d))
* add `warns` context manager for testing warnings ([96e37b6](https://github.com/renaudcepre/protest/commit/96e37b6940eebe11fd0a9ddace7eeba57aec6914))
* add conditional test skipping with fixture support ([2d8d48f](https://github.com/renaudcepre/protest/commit/2d8d48fd6890df3d0a7c5971f2bebcb3bead2965))
* add CTRF JSON schema and subprocess output capture example ([0aaea22](https://github.com/renaudcepre/protest/commit/0aaea225bb385565d21af1f1981ca64d15651d95))
* add CustomFactory suite and custom factory implementation ([a66d715](https://github.com/renaudcepre/protest/commit/a66d7156b1a0e0263363d3ceaf398d9c679c609a))
* **cli, plugins:** add CTRF reporter and enhance help command ([7f63e87](https://github.com/renaudcepre/protest/commit/7f63e87f5217b013b98a7d3b16ea89915ed9989c))
* implement watchdog for clean exit on 3rd SIGINT and address deadlock scenarios ([18172ed](https://github.com/renaudcepre/protest/commit/18172ed21ed9786c0f63ec309d6678094d090f61))
* introduce `BarkPlugin` for vocal feedback on test failures ([f0eda38](https://github.com/renaudcepre/protest/commit/f0eda383a6c3b85b3de7d5a5a94e75ecc12a26ab))
* introduce Shell helper for async subprocess handling ([83e03e2](https://github.com/renaudcepre/protest/commit/83e03e2379640c0f27d8e260b3532bf24281ff05))
* introduce Shell helper for async subprocess handling ([227a2fd](https://github.com/renaudcepre/protest/commit/227a2fd4781c9b232af68757aff1bad636587f3e))
* **reporters:** add verbosity-based output control to ASCII and Rich reporters ([2df86b1](https://github.com/renaudcepre/protest/commit/2df86b1a295a0f7c96a740c1a7a553a458614843))
* **testing:** improve factory tracking and add intentional failure demo ([15abd20](https://github.com/renaudcepre/protest/commit/15abd20535bc9b775108fec5f08a2f3ed18d3ce6))
* **tests:** add comprehensive tests for unbound fixture tags and max_concurrency ([f2d5d79](https://github.com/renaudcepre/protest/commit/f2d5d79376eea291dc7574a24c1494e2b47a3c3a))


### Bug Fixes

* **di:** support `from __future__ import annotations` with From() params ([57624d8](https://github.com/renaudcepre/protest/commit/57624d8cf94ed81a7f28858b19e1e7211513b29e))
* **reporter:** remove Live mode from RichReporter ([7470cef](https://github.com/renaudcepre/protest/commit/7470cef343d0d5cfafe8f38a3bea7044525abc01))


### Documentation

* add async factory warning and side-effect import anti-pattern ([c759ebe](https://github.com/renaudcepre/protest/commit/c759ebeb168d199562c652d20d641c6de4218d70))
* add comprehensive guide for tags system ([f38db82](https://github.com/renaudcepre/protest/commit/f38db8260260919a4116115252c7330124f2fab4))
* add coverage section, project organization and FastAPI testing guides ([030ba36](https://github.com/renaudcepre/protest/commit/030ba3668ac792f8007e3332accdb6b045c09373))
* add documentation badge to README and adjust CLI help for quiet mode ([d2ae511](https://github.com/renaudcepre/protest/commit/d2ae5115c973369140e2cb2df06b5b3289e25e88))
* document architecture, decision journal, and filtering system ([54a0a09](https://github.com/renaudcepre/protest/commit/54a0a0988a3897a6f18f9d03d0e61eeb9560603d))
* improve clarity and consistency in README and core concept docs ([5e04e6e](https://github.com/renaudcepre/protest/commit/5e04e6e9cb87913252f645698406aab1e9985235))
* improve clarity in async testing and dependency injection guides ([643df01](https://github.com/renaudcepre/protest/commit/643df010af3525ad0b593c3dd0019dcfb7c92cbe))
* update documentation ([edb990b](https://github.com/renaudcepre/protest/commit/edb990b26d7516e4dc3b1ef0e78cc1eb65a731a1))
* update fixtures and factories documentation ([b4726d2](https://github.com/renaudcepre/protest/commit/b4726d2b5be4392864c887271e75d3926ba7ae1b))
* update installation instructions in README and installation guide ([83adb38](https://github.com/renaudcepre/protest/commit/83adb387a1d54ee380fbc3bd94fbc899751379c5))

## [0.1.0] - Unreleased

Initial public release.
