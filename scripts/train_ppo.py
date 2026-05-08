#!/usr/bin/env python3
"""
PPO reward modeling for the Chief agent on Qwen2.5-VL-72B.

Setup:
  - Policy = Chief agent (Qwen2.5-VL-72B with LoRA from DPO step)
  - Reward = compute_reward(pred, ground_truth) from backend.reward_function
  - Training data: cases with ground truth (TCGA-COAD, ~10 initially)

Key principle: PPO requires the policy to GENERATE outputs and get rewards.
So we wrap the Chief inference loop and feed (prompt, generation, reward) tuples
to PPOTrainer.

NOTE: This is a research-grade setup. For production-scale PPO on 72B you'd want
multi-GPU + DeepSpeed ZeRO-3. On a single MI300X 192GB this works for small batches.

Usage:
  python3 train_ppo.py [--steps 100] [--dry-run]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, "/root/pathmind")
from backend.reward_function import compute_reward

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--steps", type=int, default=200)
    p.add_argument("--batch", type=int, default=1)
    p.add_argument("--lr", type=float, default=1e-5)
    p.add_argument("--mini-batch", type=int, default=1)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--ground-truth", default="/root/pathmind/data/benchmark/ground_truth.json")
    p.add_argument("--demo-reports", default="/root/pathmind/data/demo_reports")
    p.add_argument("--base-model", default="Qwen/Qwen2.5-VL-72B-Instruct")
    p.add_argument("--dpo-adapter", default="/root/pathmind/models/qwen72b-pathmind-dpo-v1",
                   help="Optional: start PPO from DPO-trained adapter")
    p.add_argument("--output", default="/root/pathmind/models/qwen72b-pathmind-ppo-v1")
    return p.parse_args()

def build_query_dataset(gt_path: str, demo_dir: str):
    """Build query prompts from ground truth + cross-slide context for Chief."""
    gt = json.loads(open(gt_path).read())
    demos = Path(demo_dir)
    queries = []
    for sub, gt_entry in gt.items():
        enriched = demos / f"bench-enriched-{sub.lower()}.json"
        if not enriched.exists(): continue
        rep = json.loads(enriched.read_text()).get("report", {})
        # Use the cross_slide synthesis as the input context (Chief sees this)
        prompt = (
            f"Case: {sub}\n"
            f"Cross-slide synthesis: {str(rep.get('cross_slide', ''))[:1500]}\n"
            f"Differential diagnostician confidence: {rep.get('confidence', 0.85)}\n"
            f"Clinical context: {gt_entry.get('clinical_context', '')}\n"
            f"Task: Produce final consensus diagnosis with pT/pN/grade/biomarkers. "
            f"Output JSON: {{\"diagnosis\":\"...\", \"pt\":\"pTX\", \"pn\":\"pNX\", \"grade\":\"GX\", \"biomarkers\":[...]}}"
        )
        queries.append({
            "case_id": sub,
            "prompt": prompt,
            "truth": gt_entry["structured"],
            "clinical_context": gt_entry.get("clinical_context", ""),
        })
    return queries

def parse_chief_output(text: str) -> dict:
    """Extract JSON dict from model output."""
    import re
    # Try to find a JSON block
    m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if not m: return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}

def main():
    args = parse_args()

    print(f"Loading queries from {args.ground_truth}")
    queries = build_query_dataset(args.ground_truth, args.demo_reports)
    print(f"  {len(queries)} cases with ground truth + enriched reports")

    if args.dry_run:
        print("Dry run — testing reward function on cached predictions.")
        for q in queries[:2]:
            print(f"\n--- {q['case_id']} ---")
            print(f"Truth dx: {q['truth'].get('primary_diagnosis', '?')}")
            # Mock a hallucinated prediction
            mock = {"diagnosis": "Invasive ductal carcinoma", "pt": "pT2", "pn": "pN0", "grade": "G3", "biomarkers": []}
            r = compute_reward(mock, q["truth"], q["clinical_context"])
            print(f"Mock breast prediction reward: {r['reward']:.3f} (organ_hallucination={r['organ_hallucination']})")
            mock2 = {"diagnosis": q["truth"].get("primary_diagnosis", ""), "pt": q["truth"].get("pt_stage",""),
                     "pn": q["truth"].get("pn_stage",""), "grade": q["truth"].get("tumor_grade",""), "biomarkers": []}
            r2 = compute_reward(mock2, q["truth"], q["clinical_context"])
            print(f"Mock perfect prediction reward: {r2['reward']:.3f}")
        return

    print("Loading policy + tokenizer (PPO from DPO-tuned adapter)…")
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from trl import PPOTrainer, PPOConfig, AutoModelForCausalLMWithValueHead
    from peft import PeftModel

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    base = AutoModelForCausalLM.from_pretrained(args.base_model, torch_dtype=torch.bfloat16,
                                                 device_map="auto", trust_remote_code=True)
    if Path(args.dpo_adapter).exists():
        print(f"  Loading DPO adapter from {args.dpo_adapter}")
        base = PeftModel.from_pretrained(base, args.dpo_adapter)
        base = base.merge_and_unload()

    model = AutoModelForCausalLMWithValueHead.from_pretrained(base)

    ppo_config = PPOConfig(
        learning_rate=args.lr,
        batch_size=args.batch,
        mini_batch_size=args.mini_batch,
        log_with=None,
    )
    trainer = PPOTrainer(config=ppo_config, model=model, tokenizer=tokenizer)

    print(f"Starting PPO: {args.steps} steps over {len(queries)} cases (looped)…")
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    for step in range(args.steps):
        q = queries[step % len(queries)]
        prompt_ids = tokenizer(q["prompt"], return_tensors="pt").input_ids.to(model.pretrained_model.device)

        # Generate
        gen_kwargs = {"max_new_tokens": 256, "do_sample": True, "temperature": 0.7,
                      "top_p": 0.9, "pad_token_id": tokenizer.eos_token_id}
        response_ids = trainer.generate(prompt_ids[0], **gen_kwargs)
        response_text = tokenizer.decode(response_ids[0], skip_special_tokens=True)

        # Compute reward
        pred = parse_chief_output(response_text)
        r = compute_reward(pred, q["truth"], q["clinical_context"])
        reward_tensor = torch.tensor([r["reward"]], dtype=torch.float32, device=prompt_ids.device)

        # PPO step
        stats = trainer.step([prompt_ids[0]], [response_ids[0]], [reward_tensor])
        print(f"[{step+1}/{args.steps}] {q['case_id']:18s} reward={r['reward']:.3f} "
              f"dx={r['components']['dx_score']:.2f} hall={r['organ_hallucination']}")

        if (step + 1) % 20 == 0:
            trainer.save_pretrained(str(output_dir))

    trainer.save_pretrained(str(output_dir))
    print(f"Done. PPO model saved to {output_dir}")

if __name__ == "__main__":
    main()
