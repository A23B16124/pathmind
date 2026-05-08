#!/usr/bin/env python3
"""Merge QLoRA adapter into base model for vLLM deployment."""
import argparse
from pathlib import Path

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--adapter", required=True)
    p.add_argument("--base", default="Qwen/Qwen2.5-VL-72B-Instruct")
    p.add_argument("--output", default=None)
    args = p.parse_args()

    output = args.output or args.adapter + "-merged"
    print(f"Merging {args.adapter} into {args.base} → {output}")

    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import PeftModel

    print("Loading base model…")
    model = AutoModelForCausalLM.from_pretrained(args.base, torch_dtype=torch.bfloat16, device_map="cpu")
    tokenizer = AutoTokenizer.from_pretrained(args.base)

    print("Loading LoRA adapter…")
    model = PeftModel.from_pretrained(model, args.adapter)

    print("Merging…")
    model = model.merge_and_unload()

    print(f"Saving merged model to {output}…")
    Path(output).mkdir(parents=True, exist_ok=True)
    model.save_pretrained(output)
    tokenizer.save_pretrained(output)
    print("Done.")

if __name__ == "__main__":
    main()
