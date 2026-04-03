# Gemma 4 × Expanso Edge — "See, Think, Ship"

Turn any webcam into a structured data source at the edge. Gemma 4 **sees**, Expanso Edge **ships** — timestamped, versioned, schematized JSON to any destination.

```
┌─────────┐    ┌──────────────────────────────────────────┐    ┌─────────────┐
│  USB     │    │          Expanso Edge Pipeline            │    │  Structured │
│  Webcam  │───▶│                                          │───▶│  Data Out   │
└─────────┘    │  capture_frame.py ──▶ Gemma 4 server     │    │             │
               │       (OpenCV)       (Ollama/llama.cpp)   │    │  • stdout   │
               │                           │               │    │  • JSONL    │
               │                    ┌──────▼──────┐        │    │  • HTTP     │
               │                    │  Bloblang    │        │    │  • Kafka    │
               │                    │  Schema Map  │        │    │  • S3      │
               │                    └──────┬──────┘        │    │  • 69+     │
               │                    ┌──────▼──────┐        │    └─────────────┘
               │                    │  Fan-Out    │        │
               │                    │  Broker     │        │
               │                    └─────────────┘        │
               └──────────────────────────────────────────┘
```

## Quick Start

### 1. Prerequisites

```bash
# Install Expanso Edge
# https://docs.expanso.io/getting-started/quickstart/

# Install Python dependencies
pip install -r requirements.txt

# Install and start Ollama
# https://ollama.ai
ollama serve
```

### 2. Pull Gemma 4

```bash
ollama pull gemma4-e4b-it
```

### 3. Run

```bash
chmod +x run.sh
./run.sh                    # default: object detection
```

You should see structured JSON flowing in your terminal:

```json
{
  "timestamp": "2026-04-03T14:23:01.482-04:00",
  "node_id": "edge-cam-001",
  "pipeline_version": "1.0.0",
  "model": "gemma4-e4b-it",
  "frame_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "mode": "detect_objects",
  "processing_ms": 1847,
  "payload": [
    {"label": "coffee mug", "confidence": 0.94, "box_2d": [120, 45, 280, 310]},
    {"label": "keyboard", "confidence": 0.91, "box_2d": [50, 200, 400, 500]}
  ],
  "object_count": 2,
  "has_detections": true,
  "labels": ["coffee mug", "keyboard"],
  "integrity": {
    "payload_sha256": "e3b0c44298fc1c14...",
    "frame_sha256": "a7ffc6f8bf1ed766..."
  },
  "attestation": {
    "_type": "https://in-toto.io/Statement/v1",
    "subject": [{"name": "detection:a1b2c3d4-...", "digest": {"sha256": "e3b0c44..."}}],
    "predicateType": "https://makoto.dev/transform/v1",
    "predicate": {
      "inputs": [{"name": "webcam-frame:a1b2c3d4-...", "digest": {"sha256": "a7ffc6f..."}}],
      "transform": {"type": "vision-inference", "name": "detect_objects", "version": "1.0.0"},
      "executor": {"id": "expanso-edge://edge-cam-001", "platform": "expanso-edge"}
    }
  }
}
```

Every detection carries its own **[Makoto](https://usemakoto.dev) data provenance attestation** — SLSA for data. The attestation proves where the frame came from, what model processed it, which edge node executed it, and includes SHA-256 integrity hashes for verification.

## Switch Modes — Hot-Swap the Brain

The same pipeline, same camera, same model — different behavior:

```bash
./run.sh detect_objects     # What's in the frame?
./run.sh detect_shapes      # Geometric shape detection
./run.sh read_text          # OCR / handwriting recognition
./run.sh safety_check       # Safety hazard monitoring
./run.sh describe_scene     # Mood and atmosphere analysis
```

Each mode loads a different prompt from `prompts/` and produces a different output schema — all through the same Expanso pipeline.

**Create your own mode** — just add a prompt file:

```bash
echo 'Count the people in this image. Return ONLY JSON:
{"count": 0, "positions": ["left", "center"]}' > prompts/count_people.txt

./run.sh count_people
```

## How It Works

The entire pipeline is **one YAML file** — [`pipeline.yaml`](pipeline.yaml):

| Stage | Component | What It Does |
|-------|-----------|-------------|
| **Input** | `generate` | Fires a trigger every 3 seconds |
| **Capture** | `subprocess` → `capture_frame.py` | Grabs a webcam frame, outputs base64 JPEG |
| **Infer** | `branch` → `http` | Sends frame + prompt to Gemma 4 (OpenAI-compatible API) |
| **Schema** | `mapping` (Bloblang) | Transforms raw output into structured envelope with derived analytics, mode-specific fields, integrity hashes, and data minimization (strips raw image) |
| **Attest** | `mutation` (Bloblang) | Generates a [Makoto L1](https://usemakoto.dev/spec/) data provenance attestation (in-toto format) |
| **Output** | `broker` (fan_out) | Same data → terminal + JSONL file (+ Kafka, S3, HTTP...) |

### The Expanso Difference

**Without Expanso:** You get raw model text. You write glue code. You manage one server.

**With Expanso:** You get timestamped, versioned, node-tagged structured data — with derived analytics, conditional fields per mode, SHA-256 integrity hashes, and Makoto provenance attestations. You add destinations in 3 lines. You deploy to a fleet from a dashboard.

```yaml
# This Bloblang mapping is the difference between a demo and production:
root.timestamp = now().ts_format("2006-01-02T15:04:05.000Z07:00")
root.node_id = env("NODE_ID").or("edge-cam-001")
root.pipeline_version = env("PIPELINE_VERSION").or("1.0.0")
root.model = env("GEMMA_MODEL").or("gemma4-e4b-it")
root.frame_id = uuid_v4()
root.mode = $mode
root.processing_ms = timestamp_unix_milli() - metadata("inference_start")
root.payload = if $parsed != null { $parsed } else { {"raw": $raw} }

# Derived analytics — computed by the pipeline, not the model:
root.object_count = $raw.parse_json().length().catch(0)
root.has_detections = root.object_count > 0
root.labels = if $mode == "detect_objects" { $parsed.map_each(i -> i.label) } else { deleted() }
root.alert = if $mode == "safety_check" { $parsed.risk_level.or(0) > 3 } else { deleted() }

# Data integrity — SHA-256 hashes for both input and output:
root.integrity.payload_sha256 = $raw.hash("sha256").encode("hex")
root.integrity.frame_sha256 = this.image_base64.hash("sha256").encode("hex")
# NOTE: image_base64 is deliberately NOT copied — data minimization.
```

Then a Makoto L1 attestation is added to every record — proving provenance, transform lineage, and executor identity per the [usemakoto.dev](https://usemakoto.dev) spec.

## Project Structure

```
demo-gemma-4/
├── pipeline.yaml          # ← THE STAR: Expanso Edge pipeline
├── capture_frame.py       # Webcam → base64 JSON (subprocess)
├── run.sh                 # Launcher with mode selection
├── requirements.txt       # Python: opencv-python
├── prompts/               # Swappable prompt templates
│   ├── detect_objects.txt
│   ├── detect_shapes.txt
│   ├── read_text.txt
│   ├── safety_check.txt
│   └── describe_scene.txt
└── detections/            # Auto-created: daily JSONL archives
    └── 2026-04-03.jsonl
```

## Configuration

All settings via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `CAPTURE_INTERVAL` | `3s` | Time between frame captures |
| `INFERENCE_URL` | `http://localhost:11434` | Ollama / llama.cpp server URL |
| `GEMMA_MODEL` | `gemma4-e4b-it` | Model name |
| `NODE_ID` | `edge-cam-001` | Edge node identifier (in output) |
| `PIPELINE_VERSION` | `1.0.0` | Version tag (in output) |
| `CAMERA_INDEX` | `0` | OpenCV camera device index |
| `CAPTURE_WIDTH` | `640` | Frame width (pixels) |
| `CAPTURE_HEIGHT` | `480` | Frame height (pixels) |
| `JPEG_QUALITY` | `80` | JPEG compression quality (1-100) |

## Adding Output Destinations

Uncomment or add outputs in `pipeline.yaml`:

```yaml
output:
  broker:
    pattern: fan_out
    outputs:
      - stdout: {}
      - file:
          path: './detections/${! now().ts_format("2006-01-02") }.jsonl'
          codec: lines

      # Add a webhook (3 lines):
      - http_client:
          url: https://your-api.com/detections
          verb: POST

      # Add Kafka (3 lines):
      - kafka:
          addresses: ["localhost:9092"]
          topic: vision-detections

      # Add S3 (3 lines):
      - aws_s3:
          bucket: my-detections
          path: 'edge/${! count("s3") }.json'
```

One detection. As many destinations as you need. **69+ output components available.**

## License

Apache 2.0 — same as Gemma 4.
