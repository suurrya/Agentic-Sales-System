"""
model_wrapper.py
==================
Patches smolagents' JSON parsing to survive malformed LLM output, and
provides ResilientOpenAIModel — a drop-in replacement for OpenAIServerModel
that enforces temperature=0.0 on every call.

Three problems solved here:

1. Single-quote JSON  (most common)
   The model occasionally outputs Python-style dicts:
     {'type': 'function', 'name': 'check_inventory_tool', ...}
   smolagents' parse_json_blob calls json.loads which rejects single quotes.
   Fix: monkey-patch parse_json_blob to apply json-repair before raising.

2. Temperature drift
   Non-zero temperature lets the model "creatively" deviate from the strict
   JSON tool-call format.  Locking temperature=0.0 forces it to always pick
   the highest-probability (i.e., correct) token — double quotes for JSON keys.

   Note on empty-response detection: the retry loop checks result.content AND
   result.tool_calls.  ToolCallingAgent responses carry their payload in
   tool_calls; content is intentionally empty on those turns.  Checking only
   content caused every valid tool-call response to be retried unnecessarily,
   adding 13–220 s of wasted backoff per step.

3. Quoted numeric arguments — two separate code paths, two separate patches
   The model occasionally quotes numeric values: {"quantity": "300", "price": "80.00"}
   smolagents validates types BEFORE the function body runs, so "300" fails
   the int check even though int("300") would work.

   There are TWO parsing paths in smolagents that need patching:

   Path A — parse_json_blob (used by text/code agents):
     Called when the model embeds JSON in free text.  We patch this to run
     _coerce_parameters, which unwraps the {"parameters": {...}} envelope and
     coerces numeric strings inside it.

   Path B — parse_json_if_needed (used by ToolCallingAgent):
     Called when the model returns structured OpenAI tool_calls.  The arguments
     arrive as a flat dict {"item_name": ..., "price": "80.00"} — no "parameters"
     wrapper.  parse_json_blob is never called on this path, so Path A's patch
     has no effect here.  We patch parse_json_if_needed with _coerce_values,
     which coerces numeric strings in the flat arguments dict directly.

   Both patches must be applied in BOTH module namespaces (smolagents.models
   AND smolagents.agents) because agents.py imports the functions at the top
   level, creating its own reference that is unaffected by patching models alone.
"""

import json
import random
import re
import threading
import time

import smolagents.agents as _sm_agents
import smolagents.models as _sm_models
from json_repair import repair_json
from smolagents import OpenAIServerModel


# ── Shared numeric-string coercion logic ──────────────────────────────────────

def _coerce_values(args: dict) -> dict:
    """Coerce string-typed values to int or float where the string is purely numeric.

    Operates on a FLAT arguments dict — the kind returned by parse_json_if_needed
    after the OpenAI SDK deserialises a tool_call's arguments JSON string.

    Examples:
        {"quantity": "300", "price": "80.00"} → {"quantity": 300, "price": 80.0}
        {"item_name": "A4 paper", "date": "2026-01-10"} → unchanged
    """
    coerced = {}
    for key, value in args.items():
        if isinstance(value, str):
            stripped = value.strip()
            if re.fullmatch(r"-?\d+", stripped):
                try:
                    coerced[key] = int(stripped)
                    continue
                except ValueError:
                    pass
            if re.fullmatch(r"-?\d+\.\d+", stripped):
                try:
                    coerced[key] = float(stripped)
                    continue
                except ValueError:
                    pass
        coerced[key] = value
    return coerced


# ── Monkey-patch smolagents' parse_json_blob (Path A) ────────────────────────

_original_parse_json_blob = _sm_models.parse_json_blob


def _coerce_parameters(json_data: dict) -> dict:
    """Coerce string-typed parameter values to int or float where appropriate.

    Path A wrapper: unwraps the {"parameters": {...}} or {"arguments": {...}}
    envelope produced by text/code agents, delegates value coercion to
    _coerce_values, then re-wraps under the original key.

    Guard: if the model returned a list instead of a dict, return it unchanged
    so smolagents can surface its own error rather than crashing here.
    """
    if not isinstance(json_data, dict):
        return json_data

    params = json_data.get("parameters") or json_data.get("arguments") or {}
    if not isinstance(params, dict):
        return json_data

    coerced = _coerce_values(params)

    if "parameters" in json_data:
        return {**json_data, "parameters": coerced}
    elif "arguments" in json_data:
        return {**json_data, "arguments": coerced}
    return json_data


def _resilient_parse_json_blob(json_blob: str) -> tuple[dict, str]:
    """Drop-in replacement for smolagents' parse_json_blob that applies
    json-repair when json.loads fails, then coerces numeric string parameters.

    json-repair handles:
    - Single-quoted keys/values  → double-quoted
    - Trailing commas
    - Missing closing braces
    - Unquoted keys

    _coerce_parameters handles:
    - Quoted integers: {"quantity": "300"} → {"quantity": 300}
    - Quoted floats:   {"price": "80.00"}  → {"price": 80.0}
    """
    # Fast path: try the original first (no overhead for well-formed JSON)
    try:
        json_data, before = _original_parse_json_blob(json_blob)
        return _coerce_parameters(json_data), before
    except ValueError:
        pass  # fall through to repair

    # Repair path: extract the JSON region, repair it, then retry
    try:
        first = json_blob.find("{")
        if first == -1:
            raise ValueError("The model output does not contain any JSON blob.")
        last_positions = [m.start() for m in re.finditer(r"\}", json_blob)]
        if not last_positions:
            raise ValueError("The model output does not contain any JSON blob.")
        last = last_positions[-1]

        raw_json = json_blob[first : last + 1]
        repaired = repair_json(raw_json, ensure_ascii=False, return_objects=False)
        json_data = json.loads(repaired)
        return _coerce_parameters(json_data), json_blob[:first]
    except (ValueError, json.JSONDecodeError) as repair_err:
        raise ValueError(
            f"Could not parse JSON from model output even after json-repair. "
            f"Raw excerpt: {json_blob[:300]!r}. Repair error: {repair_err}"
        )


# Install Path A patch — runs once when this module is first imported.
_sm_models.parse_json_blob = _resilient_parse_json_blob


# ── Monkey-patch smolagents' parse_json_if_needed (Path B) ───────────────────
# ToolCallingAgent calls parse_json_if_needed (NOT parse_json_blob) to deserialise
# the arguments JSON string from OpenAI structured tool_calls.  The result is a
# flat dict like {"item_name": "Table covers", "quantity": 50, "price": "80.00"}.
# Our Path A patch never runs on this code path, so "80.00" reaches smolagents'
# type-validator as a string and the call is rejected.
#
# Fix: wrap parse_json_if_needed to run _coerce_values on the parsed dict.
#
# Both module namespaces must be patched: agents.py imports parse_json_if_needed
# at the top level, creating its own reference that is unaffected by patching
# smolagents.models alone (confirmed via identity check at import time).

_original_parse_json_if_needed = _sm_models.parse_json_if_needed


def _resilient_parse_json_if_needed(arguments):
    """Drop-in replacement for parse_json_if_needed that coerces numeric strings.

    After the original function parses the JSON string into a dict, _coerce_values
    converts any purely-numeric string values (e.g. "80.00" → 80.0, "300" → 300)
    so smolagents' type-validator sees the correct Python type.
    """
    result = _original_parse_json_if_needed(arguments)
    if isinstance(result, dict):
        return _coerce_values(result)
    return result


# Patch both namespaces — agents.py holds its own imported reference.
_sm_models.parse_json_if_needed = _resilient_parse_json_if_needed
_sm_agents.parse_json_if_needed = _resilient_parse_json_if_needed


# ── ResilientOpenAIModel ──────────────────────────────────────────────────────

class ResilientOpenAIModel(OpenAIServerModel):
    """OpenAIServerModel with temperature=0.0 and a concurrency cap on API calls.

    Two problems solved:

    1. Temperature drift
       Locked at 0.0 so the model always picks the highest-probability token —
       correct JSON syntax — reducing formatting errors.

    2. API overload → empty responses
       NVIDIA's free-tier API returns empty strings (not 429s) when too many
       requests arrive simultaneously.  A class-level threading.Semaphore caps
       the number of in-flight generate() calls across ALL agent instances so
       the API is never flooded, even when many agents run in parallel threads.
       If a call returns empty, it is retried up to 3 times with exponential
       backoff before the empty result is handed back to smolagents.

    Usage — identical to OpenAIServerModel:
        model = ResilientOpenAIModel(
            model_id="meta/llama-3.3-70b-instruct",
            api_base="https://integrate.api.nvidia.com/v1",
            api_key=os.getenv("NVIDIA_API_KEY"),
        )
    """

    # Shared across every instance — caps total concurrent NVIDIA API calls.
    # Set to 2: NVIDIA's free tier throttles at 3+ concurrent calls; 2 is the
    # empirically safe ceiling while still allowing some parallelism.
    _api_semaphore = threading.Semaphore(2)

    def generate(
        self,
        messages,
        stop_sequences=None,
        response_format=None,
        tools_to_call_from=None,
        **kwargs,
    ):
        # Inject temperature unless the caller explicitly overrides it.
        kwargs.setdefault("temperature", 0.0)

        # Retry up to 3 times with exponential backoff if the API returns empty
        # or raises a timeout/connection error.
        #
        # The semaphore is acquired PER CALL and released before sleeping so other
        # agents can make API calls during the backoff window. Holding the semaphore
        # across a sleep would block every other agent for 3–9 seconds per retry.
        #
        # Timeout handling: when client_kwargs={"timeout": 30} is set, the OpenAI
        # SDK raises APITimeoutError after 30 s instead of hanging indefinitely.
        # We catch that here and treat it identically to an empty response so the
        # retry loop fires.  Without this catch, the exception escapes the loop
        # and bypasses all retry logic.
        result = None
        for attempt in range(3):
            with self._api_semaphore:
                try:
                    result = super().generate(
                        messages,
                        stop_sequences=stop_sequences,
                        response_format=response_format,
                        tools_to_call_from=tools_to_call_from,
                        **kwargs,
                    )
                    content = getattr(result, "content", "") or ""
                    tool_calls = getattr(result, "tool_calls", None) or []
                    # A response is valid if it has text content OR tool calls.
                    # ToolCallingAgent responses carry their payload in tool_calls;
                    # content is intentionally empty on those turns. Checking only
                    # content caused every valid tool-call response to be retried.
                    if content.strip() or tool_calls:
                        return result
                    failure_reason = "empty response (no content and no tool calls)"
                except Exception as api_err:
                    # Covers APITimeoutError, APIConnectionError, and any other
                    # transient network failure from the OpenAI SDK.
                    failure_reason = f"{type(api_err).__name__}: {api_err}"
                    result = None

            # Semaphore released — sleep outside it so other agents aren't blocked.
            # Jitter (±1s on first retry, ±2s on second) staggers concurrent agents
            # so their retries don't all hit the NVIDIA API at the same instant
            # (thundering herd). Without jitter, two agents that fail together sleep
            # the same duration and collide again on every subsequent attempt.
            if attempt < 2:
                base_delay = 3 * (3 ** attempt)  # 3s, then 9s
                jitter = random.uniform(0, attempt + 1)  # 0–1s, then 0–2s
                delay = base_delay + jitter
                print(f"[MODEL] {failure_reason} (attempt {attempt + 1}/3) — retrying in {delay:.1f}s...")
                time.sleep(delay)
            else:
                print(f"[MODEL] {failure_reason} (attempt 3/3) — all retries exhausted, returning empty.")

        # Return the last result even if still empty — smolagents handles fallback.
        return result
