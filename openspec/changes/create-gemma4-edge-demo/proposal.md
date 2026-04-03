# Proposal: Gemma 4 × Expanso Edge — "See, Think, Ship" Demo Video

**Change ID:** `create-gemma4-edge-demo`
**Status:** Draft
**Created:** 2026-04-03
**Author:** daaronch

---

## The Strategic Play

Gemma 4 dropped **yesterday** (April 2, 2026). Google's most capable open model, Apache 2.0, with native vision. The Google/Gemma team will be actively looking for compelling demos to amplify. If we build the **best edge deployment demo**, they share it — and in sharing it, they showcase Expanso's pipeline orchestration, fleet management, and structured data output to their entire audience.

**The frame we want Google to adopt when sharing:**
> "Look how easy it is to deploy Gemma 4 vision at the edge with Expanso — structured data out, zero cloud dependency, one YAML file, deploy to a thousand nodes."

## Why This Works for Google

Google wants to show Gemma 4 is:
- Easy to deploy anywhere (edge, on-device)
- Practically useful (not just benchmarks)
- Better than proprietary alternatives for real workloads

**We give them all three**, and the vehicle is Expanso.

---

## What Gemma 4 Can Do (Confirmed Day-1 Capabilities)

From the HuggingFace launch blog and DeepMind docs (April 2, 2026):

| Capability | Detail |
|---|---|
| **Object Detection** | Returns native JSON bounding boxes — no special prompting |
| **Pointing** | Locates specific elements with pixel coordinates |
| **OCR / Handwriting** | Reads printed and handwritten text from images |
| **Video Understanding** | Understands video content (E2B/E4B also handle audio) |
| **Multimodal Function Calling** | See image → decide which tool → call it |
| **GUI Detection** | Finds and locates UI elements in screenshots |

**Edge-ready sizes:**
- **E2B**: 2.3B effective (5.1B w/ embeddings) — phones, Raspberry Pi, IoT
- **E4B**: 4.5B effective (8B w/ embeddings) — Jetson, Mac Mini, laptops
- Both: 128K context, images + text + audio, Apache 2.0

---

## Demo Concept: "See, Think, Ship"

The title captures the three things happening: the camera **sees**, Gemma 4 **thinks**, and Expanso **ships** structured data to wherever it needs to go.

### The Core Narrative

> "AI models are getting incredible. But a model sitting on a server doesn't solve anything. What if you could turn any camera into an intelligent sensor — one that produces structured, schematized data — and deploy it to a hundred locations in minutes? That's Gemma 4 + Expanso."

### The Hook (First 20 seconds)

Split screen. Left: webcam showing you holding up a coffee mug. Right: terminal showing structured JSON flowing:

```json
{
  "timestamp": "2026-04-03T14:23:01Z",
  "node_id": "edge-cam-001",
  "objects": [
    {"label": "coffee mug", "confidence": 0.94, "bbox": [120, 45, 280, 310]}
  ],
  "scene_description": "Person holding white ceramic coffee mug at desk",
  "pipeline_version": "1.2.0",
  "model": "gemma-4-e4b-it"
}
```

Then you say: "That's not a demo script. That's a 15-line Expanso pipeline running Gemma 4 at the edge. Let me show you how."

---

### Full Demo Script (~4-5 min)

#### Act 1: "The Pipeline" (60s) — Expanso Is The Star

Show the complete pipeline YAML. Walk through it line by line:

```yaml
input:
  # Capture a frame from the webcam every 2 seconds
  command:
    name: python3
    args: ["capture_frame.py"]
    interval: 2s

pipeline:
  processors:
    # Send frame to local Gemma 4 inference server
    - http:
        url: http://localhost:8080/v1/chat/completions
        verb: POST
        headers:
          Content-Type: application/json

    # Transform raw model output into structured schema
    - mapping: |
        root.timestamp = now()
        root.node_id = env("NODE_ID").or("edge-cam-001")
        root.model = "gemma-4-e4b-it"
        root.pipeline_version = "1.2.0"
        root.objects = this.choices.0.message.content.parse_json()
        root.frame_id = uuid_v4()

output:
  broker:
    pattern: fan_out
    outputs:
      # Real-time display
      - stdout:
          codec: json_pretty
      # Structured archive
      - file:
          path: ./detections/${!now().format_timestamp("2006-01-02")}.jsonl
          codec: append_lines
```

**What to highlight:**
- "Input, process, output — that's it. This is the entire pipeline."
- "See that `mapping`? That's Bloblang. It takes the raw Gemma 4 response and turns it into a **schema** — timestamped, tagged with the node ID, versioned. This isn't just AI inference. This is **production data.**"
- "And that `fan_out` output? Same data goes to the terminal AND a structured JSONL archive. You could add Kafka, S3, PostgreSQL, Datadog — 69 output destinations, zero code changes."

#### Act 2: "See It Work" — Progressive Visual Demos (90s)

**Demo 1: Shape Detective 🔺🟥⭕**
- Hold up paper with a triangle → structured JSON with `"shape": "triangle"`
- Add a square next to it → JSON now shows both shapes
- "No retraining. No new model. Gemma 4 understands shapes zero-shot."

**Demo 2: "What Am I Holding?" 🍎🔑📱**
- Hold up random objects one at a time
- Each produces clean, structured JSON with labels, confidence scores, positions
- Hold up TWO objects → model describes both with spatial relationships
- "Every detection is structured data. Every field is typed. This is what your downstream systems actually need."

**Demo 3: Live OCR at the Edge 📝**
- Hold up a handwritten note: "Hello from the Edge!"
- Gemma 4 reads it → JSON: `{"text": "Hello from the Edge!", "type": "handwritten"}`
- Hold up a printed business card → extracts name, email, phone into structured fields
- "No Tesseract. No OCR library. Just a language model that reads."

#### Act 3: "The Pipeline Power Move" — Expanso Differentiators (90s)

This is the segment that makes Expanso impossible to ignore.

**Demo 4: Hot-Swap the Brain 🧠** *(The Viral Moment)*
- Pipeline is running, detecting objects
- **Live-edit the pipeline YAML** on camera:
  - Change the prompt from "detect objects" to "is anything potentially dangerous in this scene?"
  - Change the output schema in the Bloblang mapping to include `risk_level` and `concerns` fields
- Hold up a kitchen scene with a knife → model flags it with structured risk data
- "Same camera. Same model. Same edge device. I changed **two lines of YAML** and now it's a safety monitoring system. No redeployment. No retraining. That's what Expanso gives you."

**Demo 5: Add a Destination in One Line 📡**
- Add an `http_client` output to the fan_out:
  ```yaml
  - http_client:
      url: https://your-api.com/detections
      verb: POST
  ```
- "Now every detection goes to the terminal, the archive, AND your API. Three lines. Imagine this is a webhook to Slack, or PagerDuty, or your data lake."

**Demo 6: Fleet Vision — "Now Do It 1000 Times" 🌐** *(Expanso Cloud Moment)*
- Switch to the Expanso Cloud dashboard
- Show the pipeline deployed to one node
- Show labels: `role: camera-inference`, `model: gemma-4`
- "See this button? Deploy. Now this pipeline runs on every camera node in your network. Same config, same schema, same structured output. One YAML file, a hundred locations, zero configuration drift."
- Show the monitoring view: nodes reporting, pipelines healthy, data flowing

#### Act 4: "The Full Picture" (30s)

Architecture diagram:

```
┌─────────┐    ┌─────────────────────────────────┐    ┌──────────────┐
│  Camera  │───▶│  Expanso Edge Node              │───▶│  Structured  │
│  (any)   │    │                                   │    │  Data Out    │
└─────────┘    │  ┌─────────┐  ┌──────────────┐   │    │              │
               │  │ Capture │─▶│ Gemma 4 E4B  │   │    │  • JSONL     │
               │  └─────────┘  └──────┬───────┘   │    │  • Kafka     │
               │                      │            │    │  • S3        │
               │              ┌───────▼────────┐   │    │  • API       │
               │              │ Bloblang Schema│   │    │  • Datadog   │
               │              │ Transformation │   │    │  • Postgres  │
               │              └───────┬────────┘   │    │  • ...69+    │
               │                      │            │    └──────────────┘
               │              ┌───────▼────────┐   │
               │              │  Fan-Out to    │   │    ┌──────────────┐
               │              │  N Destinations│───────▶│ Expanso Cloud│
               │              └────────────────┘   │    │  Dashboard   │
               └─────────────────────────────────┘    └──────────────┘

No cloud inference. No data leaving your network.
Deploy to any edge device. Manage from one dashboard.
```

Closing: "Gemma 4 is the brain. Expanso is the nervous system. Together, they turn any camera into a structured data source — at the edge, at scale, under your control. Link in the description."

---

## Why Google Shares This

1. **It makes Gemma 4 look amazing** — real-world vision, zero-shot, at the edge
2. **It's not a competitor** — Expanso is infrastructure, not a model. Showcasing Expanso showcases the Gemma ecosystem
3. **Production-ready framing** — This isn't a Jupyter notebook demo. It's a deployable pipeline. That's the story Google needs: "Gemma 4 is ready for production"
4. **Timing** — First edge deployment demo with structured output. Day-2 content for a Day-1 launch

## Why This Goes Viral Beyond Google

1. **The hot-swap moment** — Editing YAML and changing AI behavior live is genuinely surprising
2. **Visual + tactile** — Holding up objects to a camera is inherently shareable
3. **"I could do this"** — Viewers can picture their own use case immediately
4. **The fleet moment** — Going from 1 camera to 1000 with a button click is a power fantasy

---

## Technical Approach

### Architecture

Gemma 4 runs as an OpenAI-compatible inference server (via llama.cpp `--server` or vLLM or Ollama). Expanso Edge pipeline sends frames to it via the `http` processor. This is the cleanest pattern because:

1. It uses Expanso's existing `http` processor — no custom plugins
2. OpenAI-compatible API means any model can be swapped in later
3. The inference server can be containerized alongside the Expanso Edge agent

### Stack
- **Model**: Gemma 4 E4B-it, quantized (Q4_K_M via llama.cpp or Ollama)
- **Inference Server**: Ollama or llama.cpp server (OpenAI-compatible endpoint)
- **Pipeline**: Expanso Edge (`expanso-edge run --config pipeline.yaml`)
- **Frame Capture**: Python script using OpenCV (simple `capture_frame.py`)
- **Schema Transform**: Bloblang mappings inside the pipeline
- **Outputs**: stdout + JSONL file + optional HTTP/Kafka/S3
- **Fleet Deploy**: Expanso Cloud dashboard (for the fleet segment)
- **Hardware**: NVIDIA Jetson Orin Nano (for "edge cred") and/or Mac Mini M-series

### Key Files
1. `pipeline.yaml` — The Expanso Edge pipeline (THE star of the show)
2. `capture_frame.py` — OpenCV webcam grabber, outputs base64 JSON to stdout
3. `prompts/` — Swappable prompt templates for different detection modes
4. `schemas/` — Example output schemas showing what structured data looks like
5. `docker-compose.yaml` — Gemma 4 server + Expanso Edge agent
6. `job.yaml` — Expanso Cloud job format for fleet deployment
7. `README.md` — Full setup guide, pipeline walkthrough, demo script

### Expanso Features Showcased

| Feature | How It Appears in Demo |
|---|---|
| **Pipeline-as-Code (YAML)** | The entire demo is one YAML file. We walk through every line. |
| **Bloblang Transforms** | Raw model output → structured schema with timestamps, node IDs, versions |
| **Fan-Out Outputs** | Same data → terminal + file + API. "Add Kafka in one line." |
| **200+ Components** | Mention the breadth: "69 outputs, 73 processors, 61 inputs" |
| **Edge Processing** | "No cloud round-trip. Data never leaves the network." |
| **Fleet Management** | Expanso Cloud dashboard: deploy to all nodes, monitor health |
| **Label Selectors** | `role: camera-inference, model: gemma-4` — targeted deployment |
| **Hot Config Updates** | Edit pipeline, behavior changes — no restart, no redeployment |
| **Offline Resilience** | "If the network drops, the pipeline keeps running locally" |

---

## Open Questions

1. **Ollama vs llama.cpp server vs vLLM**: Ollama is easiest for demo setup and most accessible for viewers. llama.cpp server is lighter. vLLM is fastest but heaviest. Recommend **Ollama** for the demo (viewers can `ollama pull gemma4-e4b` and follow along).
2. **Hardware**: Film on Jetson Orin Nano for maximum "edge cred"? Or Mac Mini for accessibility? **Recommendation**: Film on both, lead with Jetson.
3. **Expanso Cloud segment**: Do we have a demo/sandbox account to show the fleet view? Need to confirm access.
4. **Video format**: Recommend 4-5 min YouTube primary + three 60s clips for social (pipeline YAML walkthrough, hot-swap moment, fleet deployment).
5. **Companion blog post?**: Could publish on blog.expanso.io with the video embedded and full pipeline walkthrough.

## Success Metrics

- Google/Gemma team shares or reposts the demo
- First Expanso + Gemma 4 edge demo published (day-2 of launch)
- Demo repo gets 100+ GitHub stars in first week
- Video gets 10K+ views across platforms
- The "hot-swap" clip gets independently shared
- At least 5 inbound inquiries mentioning "the Gemma demo"

## Timeline

| Day | Milestone |
|---|---|
| Day 1 (Today) | Approve proposal. Get Gemma 4 E4B running via Ollama. Benchmark inference speed. |
| Day 2 | Build pipeline YAML + capture script. Test end-to-end with Expanso Edge. Iterate on Bloblang schemas. |
| Day 3 | Build all prompt templates. Test hot-swap flow. Prepare physical props. Dry-run full demo. |
| Day 4 | Film demo video. Prepare Expanso Cloud fleet segment. |
| Day 5 | Edit video, write README + blog post, push repo. |
| Day 6 | Publish everywhere. Reach out to Google DevRel / Gemma team. |
