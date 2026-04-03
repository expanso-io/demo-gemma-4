# Tasks: create-gemma4-edge-demo

## Phase 1: Model & Inference Setup
- [ ] Install Ollama and pull Gemma 4 E4B-it (or build llama.cpp with GGUF)
- [ ] Verify Gemma 4 E4B serves on OpenAI-compatible endpoint (`/v1/chat/completions`)
- [ ] Test vision: send a base64 image + "detect objects" prompt, confirm JSON bounding box response
- [ ] Test OCR: send handwritten text image, confirm accurate reading
- [ ] Benchmark: measure tokens/sec and end-to-end latency per frame on target hardware
- [ ] Test on Jetson Orin Nano if available (or document Mac Mini M-series performance)

## Phase 2: Expanso Edge Pipeline (THE Star)
- [ ] Build `capture_frame.py` — OpenCV webcam grabber, outputs base64 JSON to stdout
- [ ] Build `pipeline.yaml` — Complete Expanso Edge pipeline:
  - Input: command/generate source calling capture script
  - Processor: `http` to local Gemma 4 inference server
  - Processor: `mapping` (Bloblang) to transform raw response → structured schema
  - Output: `broker` with `fan_out` → stdout + JSONL file
- [ ] Test: `expanso-edge run --config pipeline.yaml` produces structured detections
- [ ] Build `prompts/` directory with swappable prompt templates:
  - `detect_objects.txt` — General object detection with bounding boxes
  - `detect_shapes.txt` — Geometric shape detection
  - `read_text.txt` — OCR mode
  - `safety_check.txt` — Safety/risk analysis mode
  - `describe_scene.txt` — Scene mood/description mode
- [ ] Build `schemas/` directory with example output for each mode
- [ ] Test hot-swap: edit pipeline YAML prompt reference, confirm behavior changes without restart
- [ ] Add optional `http_client` output destination to demonstrate fan-out extensibility

## Phase 3: Fleet & Cloud Deployment
- [ ] Create `job.yaml` — Expanso Cloud job format wrapping the pipeline config
- [ ] Add node labels: `role: camera-inference`, `model: gemma-4-e4b`
- [ ] Create `docker-compose.yaml` — Gemma 4 server + Expanso Edge agent in one stack
- [ ] Test cloud deployment flow: push job → node picks it up → pipeline runs
- [ ] Capture Expanso Cloud dashboard screenshots/recordings for fleet segment
- [ ] Document the "deploy to N nodes" workflow

## Phase 4: Demo Polish & Props
- [ ] Create physical props: paper shapes (triangle, square, circle), handwritten notes
- [ ] Find/prepare objects for "What Am I Holding?" segment (mug, apple, keys, phone)
- [ ] Dry-run full demo script end-to-end, time each segment
- [ ] Test the "viral moment": hot-swap from object detection → safety mode on camera
- [ ] Ensure terminal output is readable on video (font size, color scheme)
- [ ] Prepare split-screen recording setup (webcam feed + terminal)

## Phase 5: Content & Publish
- [ ] Write `README.md`:
  - Pipeline YAML walkthrough (line-by-line)
  - Quick start: 3 commands to run the full demo
  - Architecture diagram
  - "Add your own output destination" guide
  - Hardware requirements
- [ ] Film demo video following Act 1-4 script from proposal
- [ ] Edit video with captions, architecture diagrams, YAML highlights
- [ ] Cut 3× 60s social clips: (1) Pipeline YAML walkthrough, (2) Hot-swap moment, (3) Fleet deploy
- [ ] Write companion blog post for blog.expanso.io
- [ ] Push repo to GitHub with clean README
- [ ] Publish video to YouTube
- [ ] Share on: Twitter/X, LinkedIn, HuggingFace community, Reddit r/LocalLLaMA
- [ ] Reach out to Google DevRel / Gemma team with link
