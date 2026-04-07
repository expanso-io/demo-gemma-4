# Gemma 4 E2B Fine-Tuning Session — Hetzner

**Date:** 2026-04-07
**Machine:** hetzner.busted.dev
**GPU:** NVIDIA RTX 4000 SFF Ada Generation (20GB VRAM)
**Full log:** [hetzner-finetune.log](hetzner-finetune.log)

## Architecture Overview

Three machines, one pipeline:

```
┌─────────────────────┐     ┌──────────────────────┐     ┌──────────────────┐
│   Jetson Orin Nano   │     │  Hetzner GPU Server   │     │  Cloudflare R2   │
│  (edge inference)    │     │  hetzner.busted.dev   │     │  (backup)        │
├─────────────────────┤     ├──────────────────────┤     ├──────────────────┤
│ • Reolink camera     │     │ • RTX 4000 SFF Ada    │     │ Bucket:          │
│ • Frame capture      │────▶│ • Fine-tuning runs    │────▶│ demo-gemma-4/    │
│ • Label w/ Claude    │     │ • GGUF export         │     │  models/gguf/    │
│ • Inference (Ollama) │◀────│ • Merged safetensors  │     │  checkpoints/    │
│                      │     │                       │     │  recordings/     │
│ recordings/ (local)  │     │ ~/gemma4-finetune/    │     │  logs/           │
│ training_data/       │     │                       │     │                  │
│ labels/              │     │                       │     │                  │
└─────────────────────┘     └──────────────────────┘     └──────────────────┘
         │                                                         │
         │              ┌──────────────────┐                       │
         └─────────────▶│  GitHub           │◀──────(docs only)────┘
                        │  expanso-io/      │
                        │  demo-gemma-4     │
                        ├──────────────────┤
                        │ • Scripts         │
                        │ • Training JSONL  │
                        │ • Labels          │
                        │ • Docs + log      │
                        │ • Prompts         │
                        │ • Web dashboard   │
                        └──────────────────┘
```

### What lives where

| Artifact | GitHub | Jetson | Hetzner | R2 |
|---|:---:|:---:|:---:|:---:|
| Scripts (finetune, label, capture) | ✅ | ✅ | ✅ | — |
| Training JSONL (1,876 examples) | ✅ | ✅ | ✅ | — |
| Labels (469 Claude-labeled JSONL) | ✅ | ✅ | — | — |
| Recorded frames (469 JPGs, 19MB) | — | ✅ | ✅ | ✅ |
| Training log (62KB) | ✅ | ✅ | ✅ | ✅ |
| GGUF Q4_K_M (3.2GB) | — | — | ✅ | ✅ |
| Vision projector mmproj (942MB) | — | — | ✅ | ✅ |
| LoRA checkpoints (8×195MB) | — | — | ✅ | ✅ |
| Merged safetensors (9.6GB) | — | — | ✅ | — |
| Docs (this file) | ✅ | ✅ | — | — |

### Recovery scenarios

**Hetzner goes down:** GGUF, checkpoints, and recordings are in R2. Download and re-deploy.
```bash
rclone copy r2:demo-gemma-4/ ./restore/ --progress
```

**Jetson dies:** Clone repo from GitHub, pull GGUF from R2, deploy.
```bash
git clone git@github.com:expanso-io/demo-gemma-4.git
rclone copy r2:demo-gemma-4/models/gguf/ ~/models/gemma4-demo/
```

**R2 gone:** Everything still on Hetzner. Re-upload.
```bash
ssh hetzner.busted.dev
rclone copy ~/gemma4-finetune/gemma4-demo-tuned_gguf/ r2:demo-gemma-4/models/gguf/
```

**Need to retrain from scratch:** All scripts + labeled data are in GitHub. Just need a GPU.
```bash
git clone git@github.com:expanso-io/demo-gemma-4.git
rclone copy r2:demo-gemma-4/recordings/ ./recordings/
python3 prepare_training_data.py
python3 finetune_gemma4.py
```

## Configuration

| Parameter | Value |
|---|---|
| Base model | `google/gemma-4-E2B-it` |
| Quantization (loading) | 4-bit (via Unsloth) |
| LoRA rank (r) | 16 |
| LoRA alpha | 16 |
| Target modules | all-linear (language only, vision frozen) |
| Training examples | 1,876 (469 frames × 4 tasks) |
| Tasks | detect, read_text, describe, safety |
| Epochs | 3 |
| Batch size | 2 per device × 4 gradient accumulation = 8 effective |
| Learning rate | 2e-4 (linear decay) |
| Warmup steps | 10 |
| Optimizer | adamw_8bit |
| Precision | bf16 |
| Max seq length | 2048 |

## Training Data

469 frames captured from a Reolink security camera across 4 categories:
- **bottle**: 92 frames
- **box**: 187 frames
- **person**: 98 frames
- **sign**: 92 frames

Labels generated using Claude Opus (`claude-opus-4-6`) via `label_frames.py`, then converted to training JSONL via `prepare_training_data.py`. Each frame produces 4 training examples (one per task).

## Results

| Metric | Value |
|---|---|
| Total steps | 705 |
| Training time | 1,461s (~24 min) |
| Initial loss | 11.58 |
| Final loss | ~0.10 |
| Average loss | 0.389 |
| Samples/sec | 3.85 |

### Loss progression (sampled)

| Step | Loss | Epoch |
|---|---|---|
| 10 | 11.58 | 0.04 |
| 20 | 3.886 | 0.09 |
| 30 | 1.082 | 0.13 |
| 50 | 0.450 | 0.21 |
| 100 | 0.208 | 0.43 |
| 200 | 0.159 | 0.85 |
| 300 | 0.138 | 1.28 |
| 400 | 0.142 | 1.70 |
| 500 | 0.134 | 2.13 |
| 600 | 0.116 | 2.56 |
| 700 | 0.110 | 2.94 |
| 705 | 0.102 | 3.00 |

## Output Artifacts

All stored on Hetzner at `~/gemma4-finetune/`:

| Path | Size | Description |
|---|---|---|
| `gemma4-demo-tuned_gguf/gemma-4-E2B-it.Q4_K_M.gguf` | 3.2 GB | Quantized model for deployment |
| `gemma4-demo-tuned_gguf/gemma-4-E2B-it.BF16-mmproj.gguf` | 942 MB | Vision projector |
| `gemma4-demo-tuned/model.safetensors` | 9.6 GB | Full merged model (bf16) |
| `gemma4-demo-tuned-checkpoints/` | 1.6 GB | 8 checkpoints (every 100 steps + final) |

## Software Versions

- Unsloth: 2026.4.4
- TRL: 0.24.0
- Transformers: 5.5.0
- PyTorch: 2.10.0+cu128
- CUDA: 8.9 / Toolkit 12.8

## Backup (Cloudflare R2)

All artifacts are backed up to the `demo-gemma-4` R2 bucket:

| R2 Path | Contents |
|---|---|
| `models/gguf/` | Q4_K_M GGUF (3.2GB) + mmproj (942MB) |
| `checkpoints/` | 8 LoRA checkpoints (checkpoint-100 through checkpoint-705) |
| `recordings/` | 469 captured frames (bottle/box/person/sign) |
| `logs/` | Full training log |

```bash
# Download GGUF from R2 (requires rclone with r2 remote configured)
rclone copy r2:demo-gemma-4/models/gguf/ ./models/

# Download everything
rclone copy r2:demo-gemma-4/ ./backup/ --progress
```

## Deployment

```bash
# Copy GGUF to Jetson (from R2)
rclone copy r2:demo-gemma-4/models/gguf/ jetson:~/models/gemma4-demo/

# Or from Hetzner directly
scp hetzner.busted.dev:~/gemma4-finetune/gemma4-demo-tuned_gguf/*.gguf jetson:~/models/gemma4-demo/
```

## Reproducing

```bash
# On a GPU machine with 16GB+ VRAM:
ssh hetzner.busted.dev
cd ~/gemma4-finetune
./run_finetune.sh
```

Or from scratch using the repo scripts:
```bash
# 1. Capture frames (on Jetson with camera)
python3 capture_frame.py

# 2. Label with Claude
python3 label_frames.py

# 3. Prepare training JSONL
python3 prepare_training_data.py

# 4. Upload to GPU machine and run
scp -r training_data/ recordings/ hetzner.busted.dev:~/gemma4-finetune/
ssh hetzner.busted.dev "cd ~/gemma4-finetune && ./run_finetune.sh"
```
