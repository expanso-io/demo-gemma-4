# Gemma 4 × Expanso Edge: Multi-Modal Vision at the Edge

Turn a USB or RTSP camera into structured records with four local analyses:
object detection, OCR, scene description, and a safety judgment. Expanso Edge
runs the pipeline beside the camera. Frames stay on the node.

```
┌─────────┐    ┌──────────────────────────────────────────┐    ┌─────────────┐
│  USB /   │    │          Expanso Edge Pipeline            │    │  Structured │
│  RTSP    │───▶│                                          │───▶│  Data Out   │
│  Camera  │    │  capture → Gemma 4 × 4 → schema → attest│    │             │
└─────────┘    │                                          │    │  • stdout   │
               │  1. DETECT  — object classification       │    │  • JSONL    │
               │  2. READ    — OCR / text extraction       │    │  • dashboard│
               │  3. DESCRIBE — scene summary              │    │    HTTP     │
               │  4. SAFETY  — hazard judgment             │    │             │
               └──────────────────────────────────────────┘    └─────────────┘
```

## Step explorer

Open `http://localhost:9090`, choose **Explorer**, and page through capture,
the four inference branches, schema assembly, attestation, and fan-out. Each
page renders the recorded JSON input and output from the bounded 2026-10-05
Expanso Edge run in [`web/static/explorer.json`](web/static/explorer.json).
Use the Left and Right arrow keys or the on-screen controls. Copy and download
results appear beside the control you used.

## Run locally

### Prerequisites

- **[Expanso Edge](https://docs.expanso.io/getting-started/quickstart/)** and `expanso-cli`
- **Python 3.11+** with [`uv`](https://docs.astral.sh/uv/)
- **A Gemma 4 inference server** — either:
  - [llama.cpp](https://github.com/ggerganov/llama.cpp) with GGUF (recommended for Jetson)
  - [Ollama](https://ollama.ai) with `ollama pull gemma3`

### 1. Configure

```bash
cp .env.example .env
# Set CAMERA_URL for an IP camera, or leave it empty for a USB camera.
```

### 2. Start the inference server

```bash
# Option A: llama.cpp (Jetson / dedicated GPU)
./scripts/start-server.sh

# Option B: Ollama (Mac / desktop)
ollama serve
```

### 3. Run the pipeline

```bash
./run.sh
```

`run.sh` starts a local Expanso Edge agent, submits the committed job, and
writes one JSON envelope per frame to stdout and `detections/gemma4.jsonl`.
Every envelope includes the frame digest, four analysis records, and a
[Makoto](https://usemakoto.dev) provenance attestation.

### 4. Open the dashboard

```bash
uv run web/server.py
# → http://localhost:9090
```

The dashboard shows the live feed, the current Gemma 4 result, and detection
history. A new browser connection receives the last ten detections before live
updates begin. The `/record` page captures frames by label for fine-tuning.

### Reproduce the checked-in verification

```bash
just fixture-run
```

This bounded path runs the committed job with Expanso Edge against one frame
from `Gemma-Short.gif`. A local fixture endpoint returns the four recorded
responses. The assertion compares the JSONL record with the dashboard HTTP
receipt and makes no model call. See
[`docs/public-bar-2026-10-05.md`](docs/public-bar-2026-10-05.md) for the run
record.

## Deploy with Expanso Cloud

On the Jetson, install the model server and the `hardware=nvidia-jetson` node
label, then install the systemd units:

```bash
./scripts/setup-jetson.sh
./scripts/demo-ctl install
./scripts/demo-ctl start
```

From an authenticated operator machine, validate and deploy the generated job:

```bash
uv run -s scripts/render-job.py --check
expanso-cli job validate scripts/job.yaml --offline
./scripts/deploy.sh
```

[`scripts/job.yaml`](scripts/job.yaml) embeds the same validated pipeline and
selects nodes with `hardware=nvidia-jetson`. The model endpoint and camera stay
on that node. See [`docs/jetson-ops-guide.md`](docs/jetson-ops-guide.md) for
daily service and memory operations.

### Model call boundaries

Frame analysis stays on the local Gemma server. The four requests for a frame
run sequentially, do not retry, and stop after three frames by default. Set
`MAX_FRAMES` for a deliberate longer hardware run.

The fine-tuning labeler also uses the local vision server, processes frames
sequentially, and caps a run at 12 frames by default. It never invokes a model
provider CLI. A separate text-only dataset review goes through the demo-kit
model gateway. That review replays a committed fixture unless an operator
starts the gateway in capped live mode with a subscription backend.

## How It Works

The entire pipeline is **one YAML file** — [`pipeline.yaml`](pipeline.yaml):

| Stage | What Happens |
|-------|-------------|
| **Trigger** | `generate` fires every 5 seconds and stops emitting after `MAX_FRAMES` |
| **Capture** | `subprocess` runs `capture_frame.py` — grabs a frame, outputs base64 JPEG |
| **4× Infer** | Four sequential `branch` processors send the same frame to Gemma 4 with different prompts: detect, read, describe, safety |
| **Schema** | Bloblang `mapping` assembles a structured envelope with derived analytics, per-mode fields, and timing |
| **Attest** | Bloblang `mutation` generates a [Makoto L1](https://usemakoto.dev/spec/) data provenance attestation |
| **Output** | `broker` fans out to stdout + JSONL file + dashboard HTTP endpoint |

### Why Expanso Edge?

**Without Expanso:** You write glue code for one model on one server with one output.

**With Expanso:** The declarative pipeline produces a structured envelope,
computes a SHA-256 frame digest, adds provenance, and sends the same record to
stdout, JSONL, and the local dashboard endpoint. Expanso Cloud schedules that
job on labeled edge nodes.

## Project Structure

```
demo-gemma-4/
├── pipeline.yaml              # Expanso Edge pipeline (the star of the show)
├── model-gateway.toml         # Fixture-first text review gateway
├── fixtures/model/            # Recorded review for zero-call rehearsal
├── capture_frame.py           # Webcam → base64 JSON (subprocess)
├── run.sh                     # Pipeline launcher
├── .env.example               # All configurable environment variables
├── requirements.txt           # Python dependencies
│
├── web/                       # Live dashboard
│   ├── server.py              #   Dashboard + recording server
│   └── static/
│       ├── index.html         #   Dashboard UI
│       └── record.html        #   Training data capture UI
│
├── scripts/                   # Operational helpers
│   ├── start-server.sh        #   llama.cpp server management (start/stop/test)
│   ├── demo-ctl               #   Stack management CLI (start/stop/status/doctor)
│   ├── watchdog.sh            #   Health + swap monitoring daemon
│   ├── deploy.sh              #   Deploy pipeline to Expanso Cloud
│   ├── mac-demo.sh            #   Mac local development launcher
│   ├── run-edge.sh            #   Run Expanso Edge agent with local config
│   ├── setup-jetson.sh        #   One-command Jetson setup (model download + server)
│   ├── setup-dhcp-mac.sh      #   Camera network setup for IP cameras (Mac)
│   ├── dhcp-server.py         #   Minimal DHCP server for IP cameras
│   ├── job.yaml               #   Expanso Cloud job spec
│   └── Modelfile.fast         #   Ollama model definition
│
├── finetune/                  # Fine-tuning pipeline
│   ├── finetune_gemma4.py     #   Fine-tuning script (GPU machine)
│   ├── finetune_gemma4.ipynb  #   Fine-tuning notebook (Colab/Jupyter)
│   ├── label_frames.py        #   Capped local Gemma vision labeling
│   ├── review_labels.py       #   One gateway review of label counts
│   ├── prepare_training_data.py  # Convert labels → training JSONL
│   ├── labels/                #   Structured frame labels (JSONL)
│   └── training_data/         #   Training dataset
│
├── prompts/                   # Prompt templates
├── systemd/                   # Jetson systemd services + OOM protection
├── docs/                      # Operational guides
└── tests/                     # Test suite
```

## Configuration

All settings via environment variables (see [`.env.example`](.env.example)):

| Variable | Default | Description |
|----------|---------|-------------|
| `CAPTURE_INTERVAL` | `5s` | Time between frame captures |
| `MAX_FRAMES` | `3` | Local vision frames processed per run |
| `INFERENCE_URL` | `http://localhost:8081` | llama.cpp / Ollama server URL |
| `NODE_ID` | `edge-cam-001` | Edge node identifier (in output envelope) |
| `PIPELINE_VERSION` | `2.0.0` | Version tag (in output envelope) |
| `CAMERA_URL` | *(empty)* | RTSP/HTTP camera URL (overrides CAMERA_INDEX) |
| `CAMERA_INDEX` | `0` | USB webcam device index |
| `CAPTURE_WIDTH` | `320` | Frame width (pixels) |
| `CAPTURE_HEIGHT` | `240` | Frame height (pixels) |
| `JPEG_QUALITY` | `70` | JPEG compression quality (1-100) |
| `DETECTIONS_FILE` | `./detections/gemma4.jsonl` | JSONL output path |
| `PORT` | `9090` | Dashboard web server port |

## Fine-Tuning

The repo includes a complete fine-tuning pipeline in [`finetune/`](finetune/) to train Gemma 4 on your own data:

### 1. Record training frames

Use the dashboard's recording UI at `http://localhost:9090/record` to capture frames organized by label (person, box, bottle, sign).

### 2. Label frames with local Gemma

```bash
uv run finetune/label_frames.py
uv run finetune/label_frames.py \
--category box \
--max-frames 12
uv run finetune/label_frames.py --dry-run
```

The labeler sends each frame to `INFERENCE_URL` one at a time. It stops at the
run cap and writes bounding boxes, text, scene description, and safety labels.

Review the checked-in label inventory through the fixture-first gateway:

```bash
just gateway-up
just review-labels
just gateway-status
just gateway-down
```

Fixture mode makes zero live calls. To refresh the fixture, start the gateway
once with `GATEWAY_MODE=live`, `GATEWAY_BACKEND=gemini`, and
`GATEWAY_RECORD=1`, then run `just review-labels` from a terminal.

### 3. Prepare training data

```bash
uv run finetune/prepare_training_data.py
# → training_data/train.jsonl (4 training pairs per frame)
```

### 4. Fine-tune on a GPU machine

```bash
# Script (recommended):
uv run finetune/finetune_gemma4.py \
--epochs 3 \
--lr 2e-4

# Or use the Jupyter notebook:
# Upload finetune_gemma4.ipynb to Colab with training_data/ and recordings/
```

Requires a GPU with 16GB+ VRAM (Colab T4 works). Uses [Unsloth](https://github.com/unslothai/unsloth) + LoRA for efficient training.

### 5. Deploy the fine-tuned model

```bash
scp gemma4-demo-tuned/*.gguf jetson:~/models/gemma4-demo/
./scripts/demo-ctl restart
```

See [`docs/hetzner-finetune-session.md`](docs/hetzner-finetune-session.md) for a complete fine-tuning session log with architecture, hyperparameters, and results.

## Configured outputs

The published pipeline fans each completed envelope to these three outputs:

```yaml
output:
  broker:
    pattern: fan_out
    outputs:
      - stdout: {}
      - file:
          path: "${DETECTIONS_FILE:./detections/gemma4.jsonl}"
          codec: lines
      - drop_on:
          error: true
          output:
            http_client:
              url: "${DASHBOARD_URL:http://localhost:9090}/api/detection"
              verb: POST
              retries: 12
              retry_period: 500ms
```

## Tests

```bash
just check
gitleaks git --no-banner
```

## License

Apache 2.0. See [LICENSE](LICENSE).
