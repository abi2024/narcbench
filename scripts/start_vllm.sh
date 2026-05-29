#!/usr/bin/env bash
# start_vllm.sh — launch vLLM for the CoT-collusion leakage screen.
# Activates the venv itself so it works from any shell state.
set -euo pipefail

VENV=/workspace/narcbench/.venv-narcbench
MODEL="Qwen/Qwen3-30B-A3B-Thinking-2507"
PORT=8020                       # matches config.py VLLM_PORT default
export HF_HOME=/workspace/.cache/huggingface
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

if [ ! -f "${VENV}/bin/vllm" ]; then
  echo "ERROR: vllm not found at ${VENV}/bin/vllm" >&2
  echo "Is the venv intact? Try: source ${VENV}/bin/activate && which vllm" >&2
  exit 1
fi

echo "== GPU =="
nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv
echo "== Model cache =="
ls -d "${HF_HOME}/hub/models--Qwen--Qwen3-30B-A3B-Thinking-2507" 2>/dev/null \
  && echo "model cached OK" \
  || echo "WARNING: model not in cache — vLLM will download ~57GB"

echo "== Launching vLLM: ${MODEL} on port ${PORT} =="
nohup "${VENV}/bin/vllm" serve "${MODEL}" \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --served-model-name "${MODEL}" \
  --max-model-len 16384 \
  --gpu-memory-utilization 0.90 \
  > /workspace/narcbench/vllm.log 2>&1 &

echo "vLLM PID: $!"
echo "vLLM is starting in the background. Log: /workspace/narcbench/vllm.log"
echo "Watch startup separately:  tail -f /workspace/narcbench/vllm.log"
echo "Check readiness:           bash scripts/check_vllm.sh"
