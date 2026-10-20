# demo-gemma-4 — agent rules

Read [DEMO_INVARIANTS.md](DEMO_INVARIANTS.md) before acting. The vendored
file carries the rules that must hold in every checkout and worktree.
When this repository sits under `projects/demos`, `../AGENTS.md` applies
additionally. In that workspace, consult `../demo-guidance/README.md`
for recording, video review and publishing.

- Frame inference stays on the local Gemma server and is capped by
  `MAX_FRAMES`; text-only label review uses `model-gateway.toml` and fixture
  replay by default. Run `just provider-check` before committing.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
