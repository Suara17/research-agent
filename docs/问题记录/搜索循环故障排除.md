# Troubleshooting: Search Loop & Information Deviation

## Issue Description
**Symptom**: During the batch processing of Question ID 0, the Agent performed multiple search rounds (10+ attempts) without finding the correct answer, eventually leading to a timeout.
**Root Cause Analysis**:
1.  **Search Deviation (Information Loop)**: The Agent initially identified correct keywords (`Adrian Bowyer`, `RepRapPro`), but was subsequently misled by irrelevant search results (`A. E. Eiben`, `Robot Baby Project`), causing it to deviate further from the correct path.
2.  **Lack of Self-Correction**: The Agent failed to realize that consecutive searches were yielding diminishing returns and did not revert to the initial hypothesis.

## Resolution
**1. Enhanced System Prompt with Self-Correction Protocols**
Updated `agent.py` to include a specific "Self-Correction" section in the System Prompt:
*   **Search Deviation Detection**: Explicitly instructs the Agent to stop the current line of thought if two consecutive searches yield no relevant info.
*   **Keyword Optimization**: Advises simplifying keywords if results are empty.
*   **Evidence Verification**: Mandates cross-checking conclusions against search evidence.

**2. Timeout Extension**
Increased `TIMEOUT_SECONDS` in `run_batch.py` from 60s to 120s to accommodate the "Deep Research" pattern (Search -> Read -> Think -> Answer).

**3. Resume Capability**
Implemented a resume logic in `run_batch.py` to skip already processed questions, preventing data loss and saving API costs.

## Monitoring
Check `batch_run.log` for:
*   `start qid=X attempt=Y`: Indicates a new attempt.
*   `ok qid=X`: Success.
*   `giveup qid=X`: Final failure after retries.
