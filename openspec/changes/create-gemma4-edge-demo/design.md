# Design: Gemma 4 × Expanso Edge — "See, Think, Ship"

## Architecture

```
                          Expanso Edge Node
┌─────────┐    ┌──────────────────────────────────────────┐    ┌─────────────────┐
│  USB     │    │                                          │    │  Structured     │
│  Webcam  │───▶│  capture_frame.py ──▶ http processor    │───▶│  Data Out       │
│          │    │    (OpenCV)        (Gemma 4 server)      │    │                 │
└─────────┘    │                         │                 │    │  • stdout       │
               │                  ┌──────▼──────┐          │    │  • JSONL file   │
               │                  │  Bloblang    │          │    │  • HTTP API     │
               │                  │  Schema Map  │          │    │  • Kafka        │
               │                  └──────┬──────┘          │    │  • S3 / GCS     │
               │                         │                 │    │  • PostgreSQL   │
               │                  ┌──────▼──────┐          │    │  • Datadog      │
               │                  │  Fan-Out    │──────────│───▶│  • ...69+ more  │
               │                  │  Broker     │          │    └─────────────────┘
               │                  └─────────────┘          │
               └──────────────────────────────────────────┘
                              │
                    Expanso Cloud Dashboard
                    ┌─────────────────────┐
                    │  • Fleet monitoring  │
                    │  • Deploy to N nodes │
                    │  • Label selectors   │
                    │  • Config updates    │
                    └─────────────────────┘
```

## Key Design Decisions

### 1. Gemma 4 as an OpenAI-Compatible Server (not embedded)

Run Gemma 4 via Ollama (or llama.cpp `--server`) exposing `/v1/chat/completions`. The Expanso pipeline calls it via the standard `http` processor.

**Why this matters for the demo:**
- Uses Expanso's existing `http` processor — no custom code, no plugins
- Any viewer can swap in a different model (Llama, Mistral, Phi) by changing one URL
- Shows Expanso as model-agnostic infrastructure
- The inference server can be containerized and deployed alongside the edge agent

### 2. Bloblang Schema Transform = The Expanso Value Prop

The single most important thing to show: raw model output goes IN, structured, schematized data comes OUT.

**Raw Gemma 4 response:**
```json
{
  "choices": [{
    "message": {
      "content": "[{\"label\": \"coffee mug\", \"box_2d\": [120, 45, 280, 310]}]"
    }
  }]
}
```

**After Bloblang mapping:**
```json
{
  "timestamp": "2026-04-03T14:23:01.482Z",
  "node_id": "edge-cam-001",
  "pipeline_version": "1.2.0",
  "model": "gemma-4-e4b-it",
  "frame_id": "a1b2c3d4-...",
  "objects": [
    {
      "label": "coffee mug",
      "confidence": 0.94,
      "bbox": {"x1": 120, "y1": 45, "x2": 280, "y2": 310}
    }
  ],
  "object_count": 1,
  "processing_ms": 1847
}
```

**What to say in the video:** "This is the difference between an AI demo and a production system. Expanso's Bloblang takes raw model output and gives you timestamped, versioned, node-tagged structured data. Your downstream systems don't need to know about Gemma 4. They just consume clean JSON."

### 3. Fan-Out Output Pattern = "Deploy Once, Send Everywhere"

The `broker` with `fan_out` is critical. In the demo:

```yaml
output:
  broker:
    pattern: fan_out
    outputs:
      # 1. Real-time terminal display
      - stdout:
          codec: json_pretty

      # 2. Local structured archive
      - file:
          path: ./detections/${!now().format_timestamp("2006-01-02")}.jsonl
          codec: append_lines

      # 3. (Demo 5: add live) Forward to any API
      - http_client:
          url: https://your-api.com/detections
          verb: POST
```

**What to say:** "One detection, three destinations. Add a fourth in one line. Kafka? Three lines. S3? Three lines. Expanso ships 69 output components. This is why it's called a pipeline, not a script."

### 4. Hot-Swap = Pipeline Config Update (Not Just Prompt Change)

The "hot-swap" demo should show TWO things changing, not just the prompt:
1. **The prompt** (what Gemma 4 looks for)
2. **The Bloblang schema** (what fields the output contains)

This demonstrates that Expanso manages the ENTIRE pipeline behavior, not just the model input.

**Before (object detection):**
```yaml
# In the http processor body:
prompt: "Detect all objects. Return JSON array: [{label, confidence, bbox}]"

# In the mapping:
root.objects = this.choices.0.message.content.parse_json()
root.object_count = root.objects.length()
```

**After (safety monitoring):**
```yaml
# In the http processor body:
prompt: "Analyze for safety concerns. Return JSON: {safe: bool, risk_level: 1-5, concerns: [strings]}"

# In the mapping:
root.safe = this.choices.0.message.content.parse_json().safe
root.risk_level = this.choices.0.message.content.parse_json().risk_level
root.concerns = this.choices.0.message.content.parse_json().concerns
root.alert = root.risk_level > 3
```

**What to say:** "I didn't just change the prompt. I changed the output schema. The downstream system now gets `risk_level` and `alert` fields instead of `objects` and `bbox`. Same camera. Same model. Different pipeline. Different data. That's the power of pipeline-as-code."

### 5. Fleet Deployment via Expanso Cloud

The fleet segment should be SHORT (30s) but impactful:

```yaml
# job.yaml — Cloud deployment format
name: gemma4-vision-detector
type: pipeline
selector:
  role: camera-inference
  model: gemma-4
config:
  # ... same pipeline YAML from local demo ...
```

**What to say:** "This is the same pipeline YAML, wrapped in a job manifest with a label selector. Deploy it to Expanso Cloud, and every node tagged `camera-inference` picks it up automatically. Update the config centrally, all nodes get the new version. No SSH. No Ansible. No drift."

## Prompt Templates

### `prompts/detect_objects.txt`
```
Analyze this image. Detect all visible objects.
Return ONLY a JSON array: [{"label": "name", "confidence": 0.0-1.0, "box_2d": [y1, x1, y2, x2]}]
```

### `prompts/detect_shapes.txt`
```
Analyze this image. Identify all geometric shapes drawn on paper.
Return ONLY a JSON array: [{"shape": "name", "color": "color", "position": "left|center|right"}]
```

### `prompts/read_text.txt`
```
Read all text visible in this image. Return exactly what is written.
Return ONLY JSON: {"text": "the text", "type": "handwritten|printed|mixed", "language": "en"}
```

### `prompts/safety_check.txt`
```
Analyze this image for potential safety concerns in a workplace context.
Return ONLY JSON: {"safe": true/false, "risk_level": 1-5, "concerns": ["list"], "description": "brief scene summary"}
```

### `prompts/describe_scene.txt`
```
Describe the mood, atmosphere, and content of this scene.
Return ONLY JSON: {"mood": "description", "dominant_colors": ["colors"], "objects": ["items"], "summary": "one sentence"}
```

## Output Schema (Shared Envelope)

Every detection mode produces data in a consistent envelope — this is key for downstream consumers:

```json
{
  "timestamp": "ISO-8601",
  "node_id": "string",
  "pipeline_version": "semver",
  "model": "string",
  "frame_id": "uuid",
  "mode": "detect_objects|detect_shapes|read_text|safety_check|describe_scene",
  "processing_ms": 0,
  "payload": { }
}
```

The `payload` field contains mode-specific data. Downstream systems can route on `mode` while the envelope stays stable across all pipeline configurations.

## Risk Mitigation

| Risk | Mitigation |
|---|---|
| Inference too slow for engaging demo | Ollama/llama.cpp is fast on Apple Silicon. Show "processing..." animation. 1-3s per frame is fine for the narrative. |
| Gemma 4 not yet in Ollama | Fall back to llama.cpp server with GGUF. Or use transformers + API wrapper. |
| Model gives wrong detections | Pre-test all demo objects. Acknowledge "this is live" if something's off — authenticity helps. |
| Expanso Edge setup looks complex | Viewer sees ONE YAML file. Docker-compose handles the rest. README has 3-command quickstart. |
| Fleet segment needs Expanso Cloud access | Pre-record the dashboard segment if live access is unreliable. |
| Google doesn't share it | The demo still stands on its own as excellent Expanso content. Google sharing is upside, not a requirement. |
