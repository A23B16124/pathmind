#!/usr/bin/env bash
# Start two vLLM OpenAI-compat servers on the MI300X droplet.
# Usage: bash backend/vllm_config/start_vllm.sh
# Logs: /tmp/vllm_qwen72b.log, /tmp/vllm_meditron70b.log
# Stop: pkill -f vllm.entrypoints.openai.api_server

set -e

echo "[1/2] Starting Qwen2.5-72B on port 8001..."
nohup python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-72B-Instruct \
  --port 8001 \
  --dtype bfloat16 \
  --gpu-memory-utilization 0.55 \
  --max-model-len 8192 \
  --served-model-name qwen72b \
  > /tmp/vllm_qwen72b.log 2>&1 &

echo "[2/2] Starting Meditron-70B on port 8002..."
nohup python -m vllm.entrypoints.openai.api_server \
  --model epfl-llm/meditron-70b \
  --port 8002 \
  --dtype bfloat16 \
  --gpu-memory-utilization 0.40 \
  --max-model-len 4096 \
  --served-model-name meditron70b \
  > /tmp/vllm_meditron70b.log 2>&1 &

echo ""
echo "Both vLLM instances launching in background."
echo "Tail logs:"
echo "  tail -f /tmp/vllm_qwen72b.log"
echo "  tail -f /tmp/vllm_meditron70b.log"
echo ""
echo "When both report 'Application startup complete', set on the backend:"
echo "  export LLM_BACKEND=vllm"
echo "  export VLLM_BASE_URL_QWEN72B=http://localhost:8001/v1"
echo "  export VLLM_BASE_URL_MEDITRON70B=http://localhost:8002/v1"
echo "  pm2 restart pathmind-backend --update-env"
