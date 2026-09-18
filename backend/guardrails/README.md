# NeMo Guardrails (second wall)

Rails live in `patient360/guardrails.py` and run on every `/chat` turn.

- Input: identity-claim / jailbreak phrasing.
- Output: every `p_xxx` / `note_id` in the answer must appear in this run's tool results.
- Optional safety NIM: set `PATIENT360_SAFETY_URL` (compose service `safety` on 8002).

This directory is the config hook for a later Colang pack. The Python rails are the default so the in-proc demo does not depend on NeMo being installed.
