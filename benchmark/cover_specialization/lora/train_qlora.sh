#!/usr/bin/env bash
set -euo pipefail
# Cover-only QLoRA on microsoft/Phi-4-mini-instruct (NOT on GGUF).
# Requires NVIDIA GPU. Example using TRL SFTTrainer + PEFT — adjust paths.
echo "Prepare HF env, then run TRL SFT with training_config.json"
echo "Base: microsoft/Phi-4-mini-instruct"
echo "Data: train.jsonl / validation.jsonl"
exit 1
