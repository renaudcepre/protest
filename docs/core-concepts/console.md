# Console Output

Print progress and debug messages that bypass test capture.

## The Problem

`print()` inside tests and fixtures is captured by ProTest. During long-running fixtures (pipeline imports, graph seeding), there's no visible feedback.

## `console.print`

```python
from protest import console

@fixture()
async def pipeline():
    for i, scene in enumerate(scenes):
        console.print(f"[cyan]pipeline:[/] importing {scene.name} ({i+1}/{len(scenes)})")
        await import_scene(scene)
    return driver
```

Messages appear inline in the reporter output, between test results.

## Rich Markup

`console.print` supports Rich markup. The Rich reporter renders colors; the ASCII reporter strips tags.

```python
console.print(f"[bold green]done[/] in {duration:.1f}s")
console.print(f"[yellow]warning:[/] slow query ({elapsed:.2f}s)")
```

## Raw Mode

Skip markup processing with `raw=True`:

```python
console.print("debug: raw bytes here", raw=True)
```

The message is passed as-is to both reporters.

## How It Works

`console.print` sends a `USER_PRINT` event through the event bus. The reporter receives it and writes to the real stdout (bypassing test capture). This means:

- Messages appear immediately, not buffered until test end
- Works with `-n 4` (concurrent tests) — the event bus serializes per plugin
- No interference with test capture or `result.output`
