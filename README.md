# Gemma 4 × Expanso Edge — Multi-Modal Vision at the Edge

Turn any webcam into a structured data source. One frame, four analyses — object detection, OCR, scene description, and safety judgment — all running on a $200 Jetson at the edge.

```
┌─────────┐    ┌──────────────────────────────────────────┐    ┌─────────────┐
│  USB /   │    │          Expanso Edge Pipeline            │    │  Structured │
│  RTSP    │───▶│                                          │───▶│  Data Out   │
│  Camera  │    │  capture → Gemma 4 × 4 → schema → attest│    │             │
└─────────┘    │                                          │    │  • stdout   │
               │  1. DETECT  — object classification       │    │  • JSONL    │
               │  2. READ    — OCR / text extraction       │    │  • HTTP     │
               │  3. DESCRIBE — scene summary              │    │  • Kafka    │
               │  4. SAFETY  — hazard judgment             │    │  • S3       │
               │                                          │    │  • 69+      │
               └──────────────────────────────────────────┘    └─────────────┘
```

## Quick Start

### Prerequisites

- **[Expanso Edge](https://docs.expanso.io/getting-started/quickstart/)** — the pipeline runtime
- **Python 3.10+** with OpenCV (`pip install opencv-python`)
- **A Gemma 4 inference server** — either:
  - [llama.cpp](https://github.com/ggerganov/llama.cpp) with GGUF (recommended for Jetson)
  - [Ollama](https://ollama.ai) with `ollama pull gemma3`

### 1. Configure

```bash
cp .env.example .env
# Edit .env — set CAMERA_URL for IP cameras, or leave defaults for USB webcam
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

Structured JSON flows to your terminal — one envelope per frame with all four analyses:

```json
{
  "timestamp": "2026-04-07T14:23:01.482-04:00",
  "node_id": "edge-cam-001",
  "pipeline_version": "2.0.0",
  "model": "gemma4-e2b-q4",
  "frame_id": "a1b2c3d4-...",
  "mode": "multi",
  "detect": {
    "labels": ["person", "bottle"],
    "count": 2,
    "ms": 1847,
    "tokens": 42
  },
  "read_text": {
    "text": "Dasani, Purified Water",
    "ms": 1203,
    "tokens": 38
  },
  "describe": {
    "summary": "A person holds a water bottle at a desk",
    "ms": 982,
    "tokens": 35
  },
  "safety": {
    "safe": true,
    "risk": 1,
    "detail": "safe",
    "ms": 641,
    "tokens": 28
  },
  "total_ms": 4673,
  "total_tokens": 143,
  "integrity": { "frame_sha256": "a7ffc6f8..." },
  "attestation": { "_type": "https://in-toto.io/Statement/v1", "..." : "..." }
}
```

Every detection carries a **[Makoto](https://usemakoto.dev) data provenance attestation** — proving where the frame came from, what model processed it, and which edge node ran it.

### 4. Open the dashboard

```bash
uv run web/server.py
# → http://localhost:9090
```

The dashboard shows live camera feed, real-time Gemma 4 analysis, and detection history. It also supports **recording frames by label** for fine-tuning dataset creation.

## How It Works

The entire pipeline is **one YAML file** — [`pipeline.yaml`](pipeline.yaml):

| Stage | What Happens |
|-------|-------------|
| **Trigger** | `generate` fires every 5 seconds (configurable via `CAPTURE_INTERVAL`) |
| **Capture** | `subprocess` runs `capture_frame.py` — grabs a frame, outputs base64 JPEG |
| **4× Infer** | Four sequential `branch` processors send the same frame to Gemma 4 with different prompts: detect, read, describe, safety |
| **Schema** | Bloblang `mapping` assembles a structured envelope with derived analytics, per-mode fields, and timing |
| **Attest** | Bloblang `mutation` generates a [Makoto L1](https://usemakoto.dev/spec/) data provenance attestation |
| **Output** | `broker` fans out to stdout + JSONL file + dashboard HTTP endpoint |

### Why Expanso Edge?

**Without Expanso:** You write glue code for one model on one server with one output.

**With Expanso:** You get a declarative pipeline with structured output envelopes, SHA-256 integrity hashes, data provenance attestations, and fan-out to 69+ output destinations. Add Kafka in 3 lines. Deploy to a fleet from a dashboard.

## Project Structure

```
demo-gemma-4/
├── pipeline.yaml              # Expanso Edge pipeline (the star of the show)
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
│   ├── label_frames.py        #   Label recorded frames using Claude CLI
│   ├── prepare_training_data.py  # Convert labels → training JSONL
│   ├── labels/                #   Claude-generated labels (JSONL)
│   └── training_data/         #   Training dataset
│
├── prompts/                   # Prompt templates
├── systemd/                   # Jetson systemd services + OOM protection
├── docs/                      # Operational guides
└── tests/                     # Test suite (112 tests)
```

## Configuration

All settings via environment variables (see [`.env.example`](.env.example)):

| Variable | Default | Description |
|----------|---------|-------------|
| `CAPTURE_INTERVAL` | `5s` | Time between frame captures |
| `INFERENCE_URL` | `http://localhost:8081` | llama.cpp / Ollama server URL |
| `NODE_ID` | `edge-cam-001` | Edge node identifier (in output envelope) |
| `PIPELINE_VERSION` | `2.0.0` | Version tag (in output envelope) |
| `CAMERA_URL` | *(empty)* | RTSP/HTTP camera URL (overrides CAMERA_INDEX) |
| `CAMERA_INDEX` | `0` | USB webcam device index |
| `CAPTURE_WIDTH` | `320` | Frame width (pixels) |
| `CAPTURE_HEIGHT` | `240` | Frame height (pixels) |
| `JPEG_QUALITY` | `70` | JPEG compression quality (1-100) |
| `PORT` | `9090` | Dashboard web server port |

## Deployment

### Jetson Orin (production edge)

```bash
# One-time setup: downloads model, pulls container, starts server
./scripts/setup-jetson.sh

# Install systemd services for auto-start on boot
./scripts/demo-ctl install

# Daily operations
./scripts/demo-ctl start      # Start full stack (server → pipeline → dashboard → watchdog)
./scripts/demo-ctl stop       # Stop everything cleanly
./scripts/demo-ctl status     # Health check + memory + swap + disk
./scripts/demo-ctl doctor     # Full system diagnosis
./scripts/demo-ctl logs       # Tail all service logs
```

See [`docs/jetson-ops-guide.md`](docs/jetson-ops-guide.md) for memory management, OOM protection, and monitoring on the 7.4GB Orin.

### Mac (local development)

```bash
# Start inference server + dashboard
./scripts/mac-demo.sh start

# Deploy pipeline via Expanso Cloud
./scripts/deploy.sh

# Or run the edge agent locally
./scripts/run-edge.sh
```

### Expanso Cloud (fleet deployment)

```bash
./scripts/deploy.sh
```

The pipeline runs on any node with the `host=mac` label. Edit [`scripts/job.yaml`](scripts/job.yaml) to change constraints.

## Fine-Tuning

The repo includes a complete fine-tuning pipeline in [`finetune/`](finetune/) to train Gemma 4 on your own data:

### 1. Record training frames

Use the dashboard's recording UI at `http://localhost:9090/record` to capture frames organized by label (person, box, bottle, sign).

### 2. Label frames with Claude

```bash
cd finetune
python3 label_frames.py                    # Label all categories
python3 label_frames.py --category box     # One category
python3 label_frames.py --sample 30        # Sample N per category
python3 label_frames.py --dry-run          # Preview only
```

This sends each frame to Claude for structured labeling (bounding boxes, text, scene description, safety assessment).

### 3. Prepare training data

```bash
python3 prepare_training_data.py
# → training_data/train.jsonl (4 training pairs per frame)
```

### 4. Fine-tune on a GPU machine

```bash
# Script (recommended):
python3 finetune_gemma4.py --epochs 3 --lr 2e-4

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

## Adding Output Destinations

Expanso Edge supports 69+ output components. Add destinations in `pipeline.yaml`:

```yaml
output:
  broker:
    pattern: fan_out
    outputs:
      - stdout: {}
      - file:
          path: './detections/${! now().ts_format("2006-01-02") }.jsonl'
          codec: lines

      # Add a webhook:
      - http_client:
          url: https://your-api.com/detections
          verb: POST

      # Add Kafka:
      - kafka:
          addresses: ["localhost:9092"]
          topic: vision-detections

      # Add S3:
      - aws_s3:
          bucket: my-detections
          path: 'edge/${! count("s3") }.json'
```

## Tests

```bash
pip install pytest pyyaml
pytest tests/
```

## License

Apache 2.0 — see [LICENSE](LICENSE).
