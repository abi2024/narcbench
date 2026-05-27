#!/usr/bin/env bash
# start_vllm.sh — launch vLLM for the CoT-collusion leakage screen.
# Lives on the network volume + committed to git. Survives pod termination.
set -euo pipefail

MODEL="Qwen/Qwen3-30B-A3B-Thinking-2507"
PORT=8020                       # matches config.py VLLM_PORT default
export HF_HOME=/workspace/.cache/huggingface
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

echo "== GPU =="
nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv
echo "== Model cache =="
ls -d "${HF_HOME}/hub/models--Qwen--Qwen3-30B-A3B-Thinking-2507" 2>/dev/null \
  && echo "model cached OK" \
  || echo "WARNING: model not in cache — vLLM will download ~57GB"

echo "== Launching vLLM: ${MODEL} on port ${PORT} =="
nohup vllm serve "${MODEL}" \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --served-model-name "${MODEL}" \
  --max-model-len 16384 \
  --gpu-memory-utilization 0.90 \
  > /workspace/narcbench/vllm.log 2>&1 &

echo "vLLM PID: $!"
echo "Tailing startup — wait for 'Application startup complete', then Ctrl-C to detach the tail (server keeps running):"
sleep 3
tail -f /workspace/narcbench/vllm.log