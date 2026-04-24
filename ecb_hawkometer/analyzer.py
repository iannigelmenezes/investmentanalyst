"""
ecb_hawkometer/analyzer.py
--------------------------
File-based handoff pattern for Claude inference.

Workflow:
  1. Build structured prompt files and write them to data/prompts/
  2. Write .pending marker files to data/results/
  3. Orchestrator (main.py) detects .pending files and delegates to OpenCode
  4. OpenCode reads the prompt, produces JSON, writes to data/results/<task>.json
  5. analyzer.py polls for the JSON result files and returns parsed dicts
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from ecb_hawkometer.weights import get_weight

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(_MODULE_DIR, "data")
_PROMPTS_DIR = os.path.join(_DATA_DIR, "prompts")
_RESULTS_DIR = os.path.join(_DATA_DIR, "results")


def _ensure_dirs() -> None:
    os.makedirs(_PROMPTS_DIR, exist_ok=True)
    os.makedirs(_RESULTS_DIR, exist_ok=True)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def build_speaker_prompts(
    db_speeches: list[dict],
    *,
    prompts_dir: Optional[str] = None,
    results_dir: Optional[str] = None,
) -> list[str]:
    """
    For each speaker with speeches in the last 8 weeks, build a prompt file.
    Returns list of result file paths that will be written by OpenCode.

    Prompt format (plain text written to file):
    ---
    TASK: ECB_SPEAKER_ANALYSIS
    SPEAKER: <name>
    SPEECH_COUNT: <n>

    SPEECHES:
    [Date: YYYY-MM-DD | Title: ...]
    <first 800 words of speech text>
    ---
    [repeat for each speech, up to 5 most recent]

    INSTRUCTIONS:
    Analyse the hawkishness of this ECB speaker based on their recent speeches.
    Return ONLY valid JSON matching this exact schema:
    {
      "speaker": "<name>",
      "hawkishness_score": <float 1.0-10.0>,
      "trend": "<increasing|decreasing|stable>",
      "key_themes": ["<theme1>", "<theme2>", "<theme3>"],
      "tone_summary": "<one paragraph plain English>",
      "representative_quote": "<short verbatim quote>"
    }
    Hawkishness scale: 1=extremely dovish, 5=neutral, 10=extremely hawkish.
    Base trend on comparing most recent speech to earlier speeches.
    """
    _ensure_dirs()
    p_dir = prompts_dir or _PROMPTS_DIR
    r_dir = results_dir or _RESULTS_DIR
    os.makedirs(p_dir, exist_ok=True)
    os.makedirs(r_dir, exist_ok=True)

    # Filter speeches from the last 8 weeks
    cutoff = datetime.now(tz=timezone.utc) - timedelta(weeks=8)
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    # Group speeches by speaker
    speakers: dict[str, list[dict]] = {}
    for speech in db_speeches:
        speech_date = speech.get("date", "")
        if speech_date >= cutoff_str:
            name = speech.get("speaker", "Unknown")
            speakers.setdefault(name, []).append(speech)

    result_paths: list[str] = []

    for speaker_name, speeches in speakers.items():
        # Sort by date descending, take up to 5 most recent
        speeches_sorted = sorted(speeches, key=lambda s: s.get("date", ""), reverse=True)
        recent = speeches_sorted[:5]

        ts = _timestamp()
        safe_name = speaker_name.replace(" ", "_").replace("/", "-")
        prompt_filename = f"speaker_{safe_name}_{ts}.txt"
        result_filename = f"speaker_{safe_name}_{ts}.json"
        pending_filename = f"speaker_{safe_name}_{ts}.pending"

        prompt_path = os.path.join(p_dir, prompt_filename)
        result_path = os.path.join(r_dir, result_filename)
        pending_path = os.path.join(r_dir, pending_filename)

        # Build prompt text
        lines: list[str] = []
        lines.append(f"TASK: ECB_SPEAKER_ANALYSIS")
        lines.append(f"SPEAKER: {speaker_name}")
        lines.append(f"SPEECH_COUNT: {len(recent)}")
        lines.append("")
        lines.append("SPEECHES:")

        for speech in recent:
            date_str = speech.get("date", "N/A")
            title = speech.get("title", "N/A")
            full_text = speech.get("full_text") or ""
            # Truncate to first 800 words
            words = full_text.split()
            truncated = " ".join(words[:800])
            lines.append(f"[Date: {date_str} | Title: {title}]")
            lines.append(truncated)
            lines.append("---")

        lines.append("")
        lines.append("INSTRUCTIONS:")
        lines.append(
            "Analyse the hawkishness of this ECB speaker based on their recent speeches."
        )
        lines.append(
            'Return ONLY valid JSON matching this exact schema:'
        )
        lines.append('{')
        lines.append('  "speaker": "<name>",')
        lines.append('  "hawkishness_score": <float 1.0-10.0>,')
        lines.append('  "trend": "<increasing|decreasing|stable>",')
        lines.append('  "key_themes": ["<theme1>", "<theme2>", "<theme3>"],')
        lines.append('  "tone_summary": "<one paragraph plain English>",')
        lines.append('  "representative_quote": "<short verbatim quote>"')
        lines.append('}')
        lines.append(
            "Hawkishness scale: 1=extremely dovish, 5=neutral, 10=extremely hawkish."
        )
        lines.append(
            "Base trend on comparing most recent speech to earlier speeches."
        )

        prompt_text = "\n".join(lines)

        # Write prompt file
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(prompt_text)

        # Write pending marker
        with open(pending_path, "w", encoding="utf-8") as f:
            f.write(f"PENDING: {result_path}\n")

        result_paths.append(result_path)

    return result_paths


def build_policy_prompt(
    speaker_scores: list[dict],
    last_rate: float = 4.25,
    *,
    prompts_dir: Optional[str] = None,
    results_dir: Optional[str] = None,
) -> str:
    """
    Build the policy prediction prompt file.
    Returns the result file path.

    Prompt includes: all speaker scores + weights + last known rate + today's date.

    INSTRUCTIONS section asks for JSON matching:
    {
      "prediction": "<hike|cut|hold>",
      "confidence": "<high|medium|low>",
      "next_meeting_date": "<YYYY-MM-DD>",
      "weighted_score": <float>,
      "rationale": "<paragraph>",
      "rubric": [{"factor": "...", "direction": "...", "weight_applied": <float>, "evidence": "..."}]
    }
    """
    _ensure_dirs()
    p_dir = prompts_dir or _PROMPTS_DIR
    r_dir = results_dir or _RESULTS_DIR
    os.makedirs(p_dir, exist_ok=True)
    os.makedirs(r_dir, exist_ok=True)

    ts = _timestamp()
    prompt_filename = f"policy_{ts}.txt"
    result_filename = f"policy_{ts}.json"
    pending_filename = f"policy_{ts}.pending"

    prompt_path = os.path.join(p_dir, prompt_filename)
    result_path = os.path.join(r_dir, result_filename)
    pending_path = os.path.join(r_dir, pending_filename)

    today_str = datetime.now().strftime("%Y-%m-%d")

    lines: list[str] = []
    lines.append("TASK: ECB_POLICY_PREDICTION")
    lines.append(f"DATE: {today_str}")
    lines.append(f"LAST_KNOWN_RATE: {last_rate}")
    lines.append(f"SPEAKER_COUNT: {len(speaker_scores)}")
    lines.append("")
    lines.append("SPEAKER_SCORES:")

    for score in speaker_scores:
        speaker = score.get("speaker", "Unknown")
        hawk_score = score.get("hawkishness_score", "N/A")
        trend = score.get("trend", "N/A")
        weight = get_weight(speaker)
        lines.append(
            f"  - {speaker} | hawkishness={hawk_score} | trend={trend} | weight={weight}"
        )

    lines.append("")
    lines.append("INSTRUCTIONS:")
    lines.append(
        "Based on the speaker hawkishness scores, weights, and the last known ECB policy rate, "
        "predict the most likely outcome at the next ECB Governing Council meeting."
    )
    lines.append("Return ONLY valid JSON matching this exact schema:")
    lines.append("{")
    lines.append('  "prediction": "<hike|cut|hold>",')
    lines.append('  "confidence": "<high|medium|low>",')
    lines.append('  "next_meeting_date": "<YYYY-MM-DD>",')
    lines.append('  "weighted_score": <float>,')
    lines.append('  "rationale": "<paragraph>",')
    lines.append(
        '  "rubric": [{"factor": "...", "direction": "...", "weight_applied": <float>, "evidence": "..."}]'
    )
    lines.append("}")
    lines.append(
        "Use the speaker weights to compute a weighted average hawkishness score. "
        "Score > 6 suggests hike, score < 4 suggests cut, 4-6 suggests hold."
    )

    prompt_text = "\n".join(lines)

    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(prompt_text)

    with open(pending_path, "w", encoding="utf-8") as f:
        f.write(f"PENDING: {result_path}\n")

    return result_path


# ---------------------------------------------------------------------------
# Polling helpers
# ---------------------------------------------------------------------------

def _poll_for_result(
    result_path: str,
    poll_interval: float = 2.0,
    timeout: float = 300.0,
) -> Optional[dict]:
    """
    Poll for a JSON result file. Returns parsed dict on success, None on timeout.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if os.path.exists(result_path):
            try:
                with open(result_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                # File may still be mid-write; retry
                pass
        time.sleep(poll_interval)
    return None


# ---------------------------------------------------------------------------
# High-level API
# ---------------------------------------------------------------------------

def get_speaker_scores(
    db_speeches: list[dict],
    *,
    poll_interval: float = 2.0,
    timeout: float = 300.0,
    prompts_dir: Optional[str] = None,
    results_dir: Optional[str] = None,
) -> list[dict]:
    """
    High-level function: build prompts, wait for results, return parsed scores.

    Steps:
    1. Call build_speaker_prompts() to write prompt files
    2. Print status messages
    3. Poll for result JSON files (every poll_interval seconds, timeout after timeout seconds)
    4. Parse and return list of score dicts

    If a result file is not found within timeout, prints a warning and skips that speaker.
    """
    result_paths = build_speaker_prompts(
        db_speeches,
        prompts_dir=prompts_dir,
        results_dir=results_dir,
    )
    n = len(result_paths)
    print(f"[Analyzer] Wrote {n} speaker prompt files to ecb_hawkometer/data/prompts/")
    print("[Analyzer] Waiting for OpenCode inference results...")

    scores: list[dict] = []
    for result_path in result_paths:
        result = _poll_for_result(result_path, poll_interval=poll_interval, timeout=timeout)
        if result is None:
            print(
                f"[Analyzer] WARNING: No result file found within timeout for {result_path}. Skipping."
            )
        else:
            scores.append(result)

    return scores


def get_policy_prediction(
    speaker_scores: list[dict],
    last_rate: float = 4.25,
    *,
    poll_interval: float = 2.0,
    timeout: float = 300.0,
    prompts_dir: Optional[str] = None,
    results_dir: Optional[str] = None,
) -> dict:
    """
    High-level function: build policy prompt, wait for result, return parsed prediction.
    Same polling pattern as get_speaker_scores().
    """
    result_path = build_policy_prompt(
        speaker_scores,
        last_rate=last_rate,
        prompts_dir=prompts_dir,
        results_dir=results_dir,
    )
    print("[Analyzer] Wrote policy prompt file to ecb_hawkometer/data/prompts/")
    print("[Analyzer] Waiting for OpenCode inference results...")

    result = _poll_for_result(result_path, poll_interval=poll_interval, timeout=timeout)
    if result is None:
        print(
            f"[Analyzer] WARNING: No policy result file found within timeout for {result_path}."
        )
        return {}

    return result
