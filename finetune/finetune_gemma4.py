#!/usr/bin/env python3
"""
Fine-tune Gemma 4 E2B for the demo's 4 vision tasks.

Run on a machine with a GPU (Colab T4+, or any 16GB+ VRAM card).
Produces a GGUF file ready to deploy on the Jetson.

Prerequisites:
    pip install unsloth trl pillow

Usage:
    # Upload training_data/ and recordings/ to the GPU machine, then:
    python3 finetune_gemma4.py

    # Customize:
    python3 finetune_gemma4.py --epochs 3 --lr 2e-4 --output gemma4-demo
    python3 finetune_gemma4.py --quantize q4_k_m   # GGUF quantization level
"""

import argparse
import json
import os
import sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Fine-tune Gemma 4 E2B for demo tasks")
    parser.add_argument("--training-data", type=str, default="training_data/train.jsonl")
    parser.add_argument("--output", type=str, default="gemma4-demo-tuned")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=16)
    parser.add_argument("--max-seq-length", type=int, default=2048)
    parser.add_argument("--quantize", type=str, default="q4_k_m",
                        help="GGUF quantization: q2_k, q4_k_m, q8_0, f16")
    parser.add_argument("--skip-train", action="store_true",
                        help="Skip training, just export existing adapter")
    args = parser.parse_args()

    # ── Step 1: Load model ──────────────────────────────────
    print("=" * 60)
    print("  Gemma 4 E2B Fine-Tuning")
    print("=" * 60)

    try:
        from unsloth import FastVisionModel
    except ImportError:
        print("\nInstall unsloth first:")
        print("  pip install unsloth")
        print("\nOn Colab, run:")
        print("  !pip install unsloth trl pillow")
        sys.exit(1)

    print("\n[1/5] Loading Gemma 4 E2B...")
    model, tokenizer = FastVisionModel.from_pretrained(
        model_name="google/gemma-4-E2B-it",
        max_seq_length=args.max_seq_length,
        load_in_4bit=True,
    )

    # ── Step 2: Add LoRA adapters ───────────────────────────
    print("[2/5] Adding LoRA adapters...")
    model = FastVisionModel.get_peft_model(
        model,
        finetune_vision_layers=False,      # Freeze vision encoder (saves VRAM)
        finetune_language_layers=True,
        finetune_attention_modules=True,
        finetune_mlp_modules=True,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0,
        bias="none",
        target_modules="all-linear",
    )

    # ── Step 3: Prepare dataset ─────────────────────────────
    print("[3/5] Preparing dataset...")

    from PIL import Image

    training_data = args.training_data
    if not os.path.exists(training_data):
        print(f"  Training data not found: {training_data}")
        print("  Run: python3 prepare_training_data.py")
        sys.exit(1)

    # Load JSONL and build conversation format
    # Unsloth expects {"type": "image", "image": <PIL.Image>} in content
    records = []
    skipped = 0
    for line in open(training_data):
        rec = json.loads(line)
        img_path = rec["image_path"]
        if not os.path.exists(img_path):
            skipped += 1
            continue

        try:
            img = Image.open(img_path).convert("RGB")
        except Exception:
            skipped += 1
            continue

        records.append({
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": img},
                        {"type": "text", "text": rec["prompt"]},
                    ],
                },
                {
                    "role": "assistant",
                    "content": rec["response"],
                },
            ],
        })

    if skipped:
        print(f"  Skipped {skipped} records (missing images)")
    print(f"  Loaded {len(records)} training examples")

    # Convert to HF Dataset using the image path approach
    # (avoids PIL serialization issues with pyarrow)
    def make_dataset_from_records(records):
        """Create dataset that lazily loads images via the data collator."""
        # Store image paths, let the collator handle PIL loading
        rows = []
        for r in records:
            # Extract image from content
            img = None
            text = ""
            for item in r["messages"][0]["content"]:
                if item["type"] == "image":
                    img = item["image"]
                elif item["type"] == "text":
                    text = item["text"]
            response = r["messages"][1]["content"]
            rows.append({"image": img, "prompt": text, "response": response})

        # Use a simple wrapper dataset
        class VisionDataset:
            def __init__(self, data):
                self.data = data
            def __len__(self):
                return len(self.data)
            def __getitem__(self, idx):
                row = self.data[idx]
                return {
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "image", "image": row["image"]},
                                {"type": "text", "text": row["prompt"]},
                            ],
                        },
                        {
                            "role": "assistant",
                            "content": row["response"],
                        },
                    ],
                }
        return VisionDataset(rows)

    dataset = make_dataset_from_records(records)

    # ── Step 4: Train ───────────────────────────────────────
    if not args.skip_train:
        print(f"[4/5] Training ({args.epochs} epochs, lr={args.lr}, batch={args.batch_size}×{args.grad_accum})...")

        from trl import SFTTrainer, SFTConfig
        from unsloth import UnslothVisionDataCollator

        FastVisionModel.for_training(model)

        trainer = SFTTrainer(
            model=model,
            tokenizer=tokenizer,
            data_collator=UnslothVisionDataCollator(model, tokenizer),
            train_dataset=dataset,
            args=SFTConfig(
                output_dir=args.output + "-checkpoints",
                per_device_train_batch_size=args.batch_size,
                gradient_accumulation_steps=args.grad_accum,
                num_train_epochs=args.epochs,
                learning_rate=args.lr,
                warmup_steps=10,
                logging_steps=10,
                save_steps=100,
                fp16=False,
                bf16=True,
                optim="adamw_8bit",
                weight_decay=0.01,
                lr_scheduler_type="linear",
                seed=42,
                report_to="none",
                remove_unused_columns=False,
                dataset_text_field="",
                dataset_kwargs={"skip_prepare_dataset": True},
            ),
        )

        print("  Starting training...")
        stats = trainer.train()
        print(f"  Training loss: {stats.training_loss:.4f}")
        print(f"  Training time: {stats.metrics.get('train_runtime', 0):.0f}s")
    else:
        print("[4/5] Skipping training (--skip-train)")

    # ── Step 5: Export to GGUF ──────────────────────────────
    print(f"[5/5] Exporting to GGUF ({args.quantize})...")

    output_path = args.output
    os.makedirs(output_path, exist_ok=True)

    model.save_pretrained_gguf(
        output_path,
        tokenizer,
        quantization_method=args.quantize,
    )

    # List output files
    print(f"\n  Output directory: {output_path}/")
    for f in sorted(Path(output_path).glob("*")):
        size_mb = f.stat().st_size / 1024 / 1024
        print(f"    {f.name} ({size_mb:.1f} MB)")

    print("\n" + "=" * 60)
    print("  Fine-tuning complete!")
    print(f"  GGUF model: {output_path}/")
    print("")
    print("  To deploy on Jetson:")
    print(f"    scp {output_path}/*.gguf jetson:~/models/gemma4-demo/")
    print("    # Update start-server.sh to point to the new model")
    print("=" * 60)


if __name__ == "__main__":
    main()
