# Capability: Gemma 4 Edge Vision Demo

A demo application and video showcasing Gemma 4 multimodal vision orchestrated by Expanso Edge pipelines, producing structured schematized data from camera input at the edge.

## ADDED Requirements

### Requirement: Expanso Edge Vision Pipeline
The system MUST define an Expanso Edge pipeline YAML with input (webcam frame capture), processor (HTTP call to local Gemma 4 inference server + Bloblang schema transform), and fan-out output (stdout + JSONL file) that produces timestamped, node-tagged, versioned structured JSON for every frame.

#### Scenario: End-to-end structured detection
Given a configured pipeline.yaml running via expanso-edge
When a webcam frame containing a coffee mug is captured
Then the output is structured JSON containing timestamp, node_id, pipeline_version, model, frame_id, and an objects array with the detected label

#### Scenario: Fan-out to multiple destinations
Given a pipeline with broker fan_out configured for stdout and file output
When a detection is produced
Then the same structured JSON appears in both the terminal and the JSONL archive file

### Requirement: Gemma 4 Inference Server
The system MUST run Gemma 4 E4B-it as an OpenAI-compatible inference server accepting base64 image input with a text prompt and returning JSON detection results.

#### Scenario: Object detection via API
Given a running Gemma 4 server on localhost:8080
When a base64 image of a triangle on paper is sent with a detect-shapes prompt
Then the response contains a JSON array with an entry for triangle

#### Scenario: OCR via API
Given a running Gemma 4 server
When a base64 image of handwritten text saying Hello from the Edge is sent with a read-text prompt
Then the response contains the transcribed text

### Requirement: Bloblang Schema Transform
The pipeline MUST use Bloblang mapping to transform raw model responses into a consistent output envelope with timestamp, node_id, pipeline_version, model, frame_id, mode, processing_ms, and a mode-specific payload field.

#### Scenario: Raw response to structured schema
Given a raw Gemma 4 response with choices.0.message.content containing JSON
When the Bloblang mapping processor runs
Then the output contains all envelope fields plus the parsed payload

### Requirement: Prompt Hot-Swap with Schema Change
The system MUST support changing both the detection prompt AND the output schema by editing the pipeline YAML, without restarting the inference server, so the pipeline produces differently-shaped structured data for different use cases.

#### Scenario: Switch from object detection to safety monitoring
Given a running pipeline using detect_objects prompt with objects array output
When the operator edits the pipeline YAML to use safety_check prompt and risk_level schema
Then the next detection cycle produces output with safe, risk_level, and concerns fields instead of objects

### Requirement: Fleet Deployment Job Manifest
The project MUST include a job.yaml in Expanso Cloud format with label selectors so the pipeline can be deployed to multiple edge nodes from a central dashboard.

#### Scenario: Targeted fleet deployment
Given a job.yaml with selector role camera-inference and model gemma-4
When the job is deployed to Expanso Cloud
Then only nodes matching those labels receive and run the pipeline

### Requirement: Documentation and Reproducibility
The project MUST include a README with a 3-command quickstart, line-by-line pipeline YAML walkthrough, architecture diagram, and instructions for adding custom output destinations.

#### Scenario: New user reproduces the demo
Given a user with Docker, a webcam, and internet access
When they follow the README quickstart commands
Then Gemma 4 server starts, the Expanso pipeline runs, and structured detection JSON appears in their terminal
