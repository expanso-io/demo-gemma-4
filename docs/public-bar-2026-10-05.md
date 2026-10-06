# demo-gemma-4 public example proof, 2026-10-05

This report records the public-bar run completed on 2026-10-05 Pacific time
(2026-10-06T03:31:32Z). The code and configuration under test were commit
`4e87097b3507c514c3ebedbe5d5d6f45dea772cf`.

## Result

| Criterion | Result | Evidence |
|---|---|---|
| 1. Runs | PASS | Expanso Edge and CLI validation passed. One fixture record ran through the complete job and matched the output schema. |
| 2. Platform | PASS | The NVIDIA Jetson files, label selector, setup script, non-root systemd service, and authenticated operator deployment path passed their declared validators. |
| 3. Structure | PASS | The page contains the explanation, eight-stage explorer, run instructions, and deployment instructions. |
| 4. Usability | PASS | Light and dark modes passed overflow, computed contrast, and axe checks at 320, 400, 768, and 1440 pixels. Stage paging, JSON formatting, and local control feedback passed. |
| 5. Regressions | PASS | The retained-feature manifest passed. Detection-history replay and the `/record` route are retained. No removals are approved. |

The checker reported all five criteria as `PASS`, with no failed assertions.

## Fixture execution

The run used `fixtures/public-bar/input.jsonl`. The recorded frame envelope
contains four fixture-backed inference responses, so this proof made no model
calls and used no metered API keys. Expanso Edge processed one frame through
capture, detect, read, describe, safety, schema assembly, attestation, and
fan-out.

The output assertions were:

- one JSON record;
- detected labels `person` and `bottle`;
- extracted text `GEMMA 4`;
- description `A person holds a bottle beside an edge camera.`;
- safety result `safe`;
- a SHA-256 frame digest;
- an in-toto statement with Makoto transform provenance and record count `4`;
- identical JSONL and HTTP receipt content in `just fixture-run`.

The proof digests were:

| Artifact | SHA-256 |
|---|---|
| Input fixture | `7988fd2f245f21fd59c7ecc57e1f2676e81de0f80919f7dfba25a69a61d66f02` |
| Output schema | `ee6974e8dba3e05d74dd0ddf97ae461d20e89564a5bb38523d42ae983f2b0edc` |
| All-lane output | `436c142cd3703fd471fd662993437c0b4a62083f3f4136d91621d863aabd44d7` |

Both fixture services stopped after execution. Ports 18154, 18155, 19090,
and 4174 had no listeners after their respective checks.

## Explorer and browser proof

The explorer publishes real input and output for these stages:

1. capture
2. detect
3. read
4. describe
5. safety
6. schema
7. attest
8. fanout

The rendered lane checked each viewport in both palettes. Every combination
had zero horizontal overflow, passed computed WCAG AA text contrast, and had
no axe WCAG A or AA violations. Left and Right paged all eight stages while
the explorer scroll position stayed within two pixels. Both JSON panels were
valid and vertically formatted. Copy and download controls showed local
success and forced-failure feedback at the control.

## Regression proof

`public-features.json` records the public routes, controls, downloads, stage
features, and browser assertions. It explicitly retains detection-history
replay and `/record`. `tests/test_public_ui.py` checks that a new SSE client
receives the latest ten detections. `public-removals/none.json` contains no
approved removals.

## Tools and gates

| Tool | Version or result |
|---|---|
| Public bar | `1.1.3`, demo-kit commit `2b2fac927f2c8eb39d6e15cb00d06cc2ffb6cbfe` |
| Expanso Edge | `v2.1.21` |
| Expanso CLI | `v2.1.21` |
| Playwright | `1.55.0` |
| axe-core | `4.10.3` |
| Python | `3.14.7` |
| uv | `0.12.17` |
| actionlint | `1.7.12` |
| Repository tests | `142 passed` |
| UI lint | strict gate passed with one non-failing type-scale warning |

The local proof ran these gates:

- `just check`
- `just fixture-run`
- `uv run -s ../_demo-kit/lint-demo-ui.py . --video-strict`
- `actionlint .github/workflows/public-bar.yml`
- vendored-file sync check
- `uv run -s .demo-kit/public-bar.py --selftest`
- `uv run -s .demo-kit/public-bar.py --lane all`

The self-test accepted two known-good repositories, including a declared
fixture service, and proved that each criterion-isolated bad repository fails
only its intended criterion. `.github/workflows/public-bar.yml` runs the same
all-lane checker on pushes to `main`, pull requests, and manual dispatches,
then uploads the Markdown and JSON reports.

## Deployment boundary

No Expanso Cloud deployment was performed for this report. The proof covers
the generated job, local Expanso Edge execution, the Jetson deployment files,
and the authenticated operator instructions. It does not claim that a Cloud
job or Jetson node was deployed during this run.

Open captain calls: none.
