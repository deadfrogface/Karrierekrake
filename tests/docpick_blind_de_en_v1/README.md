# Docpick Blind DE/EN v1

Independent synthetic corpus (2 DE + 2 EN). Protocol:
1. Freeze parser/prompt/model
2. Run sealed extract (PDF only) → frozen_predictions + seal
3. Only then load phase_b_solutions and score V3.1
4. Label as BLIND — not Round2/3
