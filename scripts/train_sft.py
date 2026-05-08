#!/usr/bin/env python3
"""
SFT fine-tuning for Qwen2.5-7B-Instruct on PathMind text agents (histo_b + cross_slide).
Latency target: replace Meditron-70B with Qwen2.5-7B for 10x faster inference.

Uses TRL SFTTrainer + LoRA (r=16) — full FT not needed, dataset is small (~20 samples).

Usage:
  python3 train_sft.py [--epochs 3] [--dry-run]
"""
import argparse
import json
from pathlib import Path

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--batch", type=int, default=2)
    p.add_argument("--grad-accum", type=int, default=4)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--max-length", type=int, default=4096)
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--data", default="/root/pathmind/data/sft/sft_dataset.jsonl")
    p.add_argument("--output", default="/root/pathmind/models/qwen7b-pathmind-sft-v1")
    p.add_argument("--base-model", default="Qwen/Qwen2.5-7B-Instruct")
    return p.parse_args()

def load_dataset(path):
    from datasets import Dataset
    rows = []
    with open(path) as f:
        for line in f:
            r = json.loads(line)
            rows.append({"messages": r["messages"]})
    return Dataset.from_list(rows)

def main():
    args = parse_args()

    print(f"Loading dataset from {args.data}")
    dataset = load_dataset(args.data)
    print(f"  {len(dataset)} samples loaded")

    if args.dry_run:
        print("Dry run — dataset OK.")
        for i, row in enumerate(dataset.select(range(min(2, len(dataset))))):
            n = len(row["messages"])
            sizes = [len(m["content"]) for m in row["messages"]]
            print(f"  [{i}] msgs={n}, content sizes={sizes}")
        return

    print("Loading model + tokenizer (LoRA, no quant — 7B fits in bfloat16)…")
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import LoraConfig, get_peft_model, TaskType
    from trl import SFTTrainer, SFTConfig

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )

    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=args.lora_r,
        lora_alpha=args.lora_r * 2,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    sft_config = SFTConfig(
        output_dir=str(output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        max_seq_length=args.max_length,
        bf16=True,
        logging_steps=1,
        save_steps=10,
        save_total_limit=2,
        report_to="none",
        packing=False,
        dataset_text_field="messages",
    )

    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=dataset,
        tokenizer=tokenizer,
    )

    print(f"Starting SFT: {args.epochs} epochs, {len(dataset)} samples…")
    trainer.train()
    trainer.save_model()
    tokenizer.save_pretrained(str(output_dir))
    print(f"Done. LoRA adapter saved to {output_dir}")
    print()
    print("To deploy:")
    print(f"  python3 scripts/merge_lora.py --adapter {output_dir} --base {args.base_model}")
    print(f"  vllm serve {output_dir}-merged --port 8003")
    print("  # Update backend/llm.py VLLM_BASE_URL_MAP['meditron70b'] -> port 8003")

if __name__ == "__main__":
    main()
