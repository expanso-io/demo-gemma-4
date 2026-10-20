<!-- generated from _demo-kit/DEMO_INVARIANTS.md, edit there -->
# Demo invariants

Distilled from David's repeated corrections across demo sessions, 2026-09-16
to 2026-10-20. Every demo worker loads this before touching UI, lifecycle, or
recording. It is short on purpose: `_demo-kit/` remains the full reference.
A rule here outranks a rule in a single demo's docs.

Demos are visual and high-level. They show the story; they are not proof
points. No evidence panels, proof strips, claim substantiation or
citations. Things on screen still run for real (real Cloud, real model).

## Lifecycle

- `just up` is the only start command. It deploys or updates the Cloud
  pipelines itself (never `just up cloud`), reuses a pipeline that already
  exists, starts from zero data, and leaves pipelines off unless the opening
  beat says otherwise. It prints every URL the presenter needs.
- `just down` stops everything this demo started: local Expanso Edge,
  containers, tunnels, remote GPU machines. It deletes this demo's Cloud
  pipelines and its state and log files. Zero orphans; verify with `ps`/`lsof`.
- Pipelines are toggled by David in Expanso Cloud, never from the web page.
  The board shows observed Cloud and Edge state.
- Credentials: the shared `expanso-demos` workspace from the demos `.env`,
  through a project-local profile. Never the global Expanso profile. Never
  the macOS Keychain.
- Latest `expanso-edge` and `expanso-cli` from PATH. Never pin, never install
  a copy per demo.
- Python runs through `uv run`, never bare `python`.
- A demo that adds more than about 1 GB of data needs a gate; `just down`
  deletes what it created.

## State truth on screen

- Sources and devices are always on and emitting, before Expanso exists.
  Without Expanso, data goes nowhere, piles up, or flows the expensive way.
- Expanso nodes and the orchestrator are grayed out, or absent, until the
  pipeline is actually live. Live means a dark-gray light turns green with a
  subtle pulse.
- When a pipeline is live, particles flow constantly. Counters move in step
  with particles, and numbers add up across stages.
- A page refresh shows the true current state: no phantom particles or jobs.
- Never show "mock", "replay", "recorded", or "live demo". Say "topology".
  Run against the real service (real Jev, real Cloud), not a stub.
- If David cannot explain an element in one sentence, cut it or rename it.
  Pipelines are named for what they do.

## Layout

- One 16:9 frame at 1920x1080. No internal scrollbars, no horizontal scroll;
  size boxes to their content. Depth goes on extra browser tabs (data,
  slides), not scroll.
- Flow left to right: sources converge on one entry point into the Expanso
  node, the pipeline is drawn inside it, and one exit fans out to the
  destinations.
- Nothing moves on hover or on alert. Labels and numbers align across
  columns; an empty value keeps its slot.
- No click is ever lost. Click inspects (a modal with the full data point,
  JSON laid out vertically and syntax colored); ctrl-click triggers the
  fault or alarm where the demo has one.
- Few words, large elements, progressive disclosure across pages. Objects
  stay in place from page to page.
- Palette, theme and iconography come from the subject. Take interaction and
  composition from Space Force (`demo-space-force-edge-routing`), NICU
  (`demo-intel-nicu-edge`) and oil-gas (`demo-oil-gas-motherduck`); never
  their palettes. Draw real subject graphics (Paper, icon libraries,
  source-system logos).
- Arrows at least 2px with larger endpoints; links never clipped.

## Story and recording

- Default arc: data collected and going nowhere (Expanso gray); the pipeline
  shown and switched on in Expanso Cloud; data flowing in volume, hover to
  inspect; the destination visibly filling (Power BI, bucket, lakehouse);
  then a fault, recovery, or pipeline swap.
- The recording script is scannable bullets in David's voice, told from the
  customer's pain.
- Comparisons run in seconds (about 10s), not minutes.
- Never name customers.
- Publishing a take: Descript Studio Sound plus filler removal, trim dead air
  and degraded waits, standard bumpers from the bumper tool ("Office Hours"
  header only for office hours), YouTube unlisted with the demo profile,
  dub.co `exso.cloud` links for video, repo and site. Not done until live.

## Agent behavior

- Work in the permanent checkout under `projects/demos/<demo>` and land on
  `main`. (Decision pending: see the analysis report.)
- Merge your own green PRs without asking. Escalate only destructive or
  security-sensitive changes.
- Before showing David anything, screenshot every state (zero, off, on,
  fault, recovery) at 1920x1080 and check it against this list.
- Close tabs, workspaces and sessions when the work is done.
