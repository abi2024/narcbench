#!/usr/bin/env bash
# Health check — confirms vLLM is up and which model it serves.
curl -s http://127.0.0.1:8020/v1/models | python3 -m json.tool || echo "vLLM not responding on :8020"