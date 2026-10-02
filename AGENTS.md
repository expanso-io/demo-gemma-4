# demo-gemma-4 — agent rules

> **Directory-wide rules apply.** Read [`../AGENTS.md`](../AGENTS.md) first —
> it governs every demo in `projects/demos/`. For anything involving a screen
> recording, a finished video, publishing copy, or a launch, read
> [`../demo-guidance/README.md`](../demo-guidance/README.md) before acting.
> `_demo-kit` runs before you record; `demo-guidance` runs after.

- Frame inference stays on the local Gemma server and is capped by
  `MAX_FRAMES`; text-only label review uses `model-gateway.toml` and fixture
  replay by default. Run `just provider-check` before committing.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
