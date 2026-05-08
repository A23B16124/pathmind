#!/usr/bin/env python3
"""
QLoRA DPO fine-tuning for Qwen2.5-VL-72B on AMD MI300X.
Uses TRL DPOTrainer + bitsandbytes 4-bit (QLoRA).

Data: /root/pathmind/data/dpo/dpo_pairs.jsonl
Model: Qwen/Qwen2.5-VL-72B-Instruct (already local at /root/models/ or HF cache)
Output: /root/pathmind/models/qwen72b-pathmind-dpo-v1/

Usage:
  python3 train_dpo_qlora.py [--epochs 1] [--batch 1] [--dry-run]
"""
import argparse
import json
import os
from pathlib import Path

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--epochs", type=int, default=2)
    p.add_argument("--batch", type=int, default=1)
    p.add_argument("--grad-accum", type=int, default=8)
    p.add_argument("--lr", type=float, default=5e-5)
    p.add_argument("--beta", type=float, default=0.1, help="DPO beta (KL penalty)")
    p.add_argument("--max-length", type=int, default=2048)
    p.add_argument("--dry-run", action="store_true", help="Validate setup without training")
    p.add_argument("--data", default="/root/pathmind/data/dpo/dpo_pairs.jsonl")
    p.add_argument("--output", default="/root/pathmind/models/qwen72b-pathmind-dpo-v1")
    p.add_argument("--base-model", default="Qwen/Qwen2.5-VL-72B-Instruct")
    return p.parse_args()

def load_dataset(path: str):
    """Load DPO pairs and format for TRL DPOTrainer."""
    from datasets import Dataset
    records = []
    with open(path) as f:
        for line in f:
            r = json.loads(line)
            # TRL DPOTrainer expects: prompt (list of messages), chosen (str), rejected (str)
            records.append({
                "prompt":   r["prompt"],
                "chosen":   [{"role": "assistant", "content": r["chosen"]}],
                "rejected": [{"role": "assistant", "content": r["rejected"]}],
            })
    return Dataset.from_list(records)

def main():
    args = parse_args()

    print(f"Loading dataset from {args.data}")
    dataset = load_dataset(args.data)
    print(f"  {len(dataset)} pairs loaded")

    if args.dry_run:
        print("Dry run — dataset OK. Exiting without training.")
        print("Pairs sample:")
        for i, row in enumerate(dataset.select(range(min(2, len(dataset))))):
            print(f"  [{i}] prompt_msgs={len(row['prompt'])} chosen_len={len(row['chosen'][0]['content'])} rejected_len={len(row['rejected'][0]['content'])}")
        return

    print("Loading model + tokenizer (QLoRA 4-bit)…")
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
    from peft import LoraConfig, get_peft_model, TaskType
    from trl import DPOTrainer, DPOConfig

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    tokenizer.padding_side = "left"

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )

    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    dpo_config = DPOConfig(
        output_dir=str(output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        beta=args.beta,
        max_length=args.max_length,
        max_prompt_length=args.max_length // 2,
        bf16=True,
        logging_steps=1,
        save_steps=10,
        save_total_limit=2,
        report_to="none",
        remove_unused_columns=False,
        dataloader_num_workers=0,
    )

    trainer = DPOTrainer(
        model=model,
        ref_model=None,  # uses implicit reference (frozen copy)
        args=dpo_config,
        train_dataset=dataset,
        tokenizer=tokenizer,
    )

    print(f"Starting DPO training: {args.epochs} epochs, {len(dataset)} pairs…")
    trainer.train()

    print(f"Saving LoRA adapter to {output_dir}…")
    trainer.save_model()
    tokenizer.save_pretrained(str(output_dir))
    print("Done.")
    print()
    print("To load for inference:")
    print(f"  from peft import PeftModel")
    print(f"  model = PeftModel.from_pretrained(base_model, '{output_dir}')")
    print()
    print("To hot-swap in vLLM:")
    print(f"  # Merge LoRA: python3 scripts/merge_lora.py --adapter {output_dir}")
    print(f"  # Then: vllm serve merged_model --enable-lora")

if __name__ == "__main__":
    main()
