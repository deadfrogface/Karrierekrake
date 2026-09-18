# Cover LoRA prep

Status: `BLOCKED_NO_SUITABLE_GPU_AND_INSUFFICIENT_DATA`

Train rows: 64 (need ≥300)
Val rows: 16 (need ≥50)

Train from HF `microsoft/Phi-4-mini-instruct`, then convert merged weights to GGUF Q4_K_M and route only CoverLetterWriter to `karrierekrake-phi4-mini-cover-v1`.
