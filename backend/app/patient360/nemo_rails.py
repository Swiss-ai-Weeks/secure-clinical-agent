"""NeMo Guardrails runner for /chat. Checks only; it does not generate the answer."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from nemoguardrails import LLMRails, RailsConfig
from nemoguardrails.rails.llm.options import RailStatus, RailType

from .config import Settings
from .guardrails import NOT_ALLOWED, REFUSAL, RailResult, input_rails, output_rails

log = logging.getLogger(__name__)

_IMAGE_PACK = Path("/app/guardrails")
_INTERNAL_ERROR = "I'm sorry, an internal error has occurred."
# Identifier redaction already ran. A document blocked only for that is still published.
_PII_CATEGORIES = frozenset({"pii/privacy", "s9", "privacy"})
_rail_state: ContextVar[dict[str, Any]] = ContextVar("p360_nemo_rail_state")
_loaded: dict[tuple[str, str, str, str], NemoRails] = {}


def pack_path(settings: Settings) -> Path:
    if settings.guardrails_path is not None:
        return settings.guardrails_path
    if (_IMAGE_PACK / "config.yml").is_file():
        return _IMAGE_PACK
    return Path(__file__).resolve().parents[2] / "guardrails"


def _v1(url: str) -> str:
    base = url.rstrip("/")
    if base.endswith("/v1"):
        return base
    return f"{base}/v1"


async def check_identity_claim() -> bool:
    state = _rail_state.get()
    if state.get("mode") == "document":
        return True
    result = input_rails(state.get("question") or "")
    state["reason"] = result.reason
    state["input"] = result
    return result.ok


async def check_citation_leak() -> bool:
    state = _rail_state.get()
    result = output_rails(
        state.get("answer") or "",
        set(state.get("allowed_ids") or ()),
        patient_key=state.get("patient_key"),
    )
    state["reason"] = result.reason
    state["output"] = result
    return result.ok


class NemoRails:
    def __init__(self, rails: LLMRails, *, safety_enabled: bool) -> None:
        self._rails = rails
        self.safety_enabled = safety_enabled

    async def check_document(self, text: str) -> RailResult:
        """Content-safety only. The chat identity regex does not apply to a note."""
        if not self.safety_enabled:
            return RailResult(True, text=text or "")
        body = text or ""
        try:
            outcome, status = await self._rails.runtime.action_dispatcher.execute_action(
                "content_safety_check_input",
                {
                    "user_message": body,
                    "model_name": "content_safety",
                    "llm_task_manager": self._rails.runtime.llm_task_manager,
                    "llms": self._rails.runtime.registered_action_params.get("llms", {}),
                    "context": {"user_message": body},
                },
            )
        except Exception as exc:
            log.warning("NeMo document safety rail failed: %s", type(exc).__name__)
            return RailResult(False, "content_safety_unavailable", REFUSAL)
        return document_safety_result(outcome, status, body)

    async def check_input(self, question: str) -> RailResult:
        state: dict[str, Any] = {"question": question or "", "reason": ""}
        return await self._check(
            [{"role": "user", "content": question or ""}],
            [RailType.INPUT],
            state,
            kind="input",
        )

    async def check_output(
        self,
        answer: str,
        allowed_ids: set[str],
        *,
        patient_key: str | None = None,
        question: str = "",
    ) -> RailResult:
        state: dict[str, Any] = {
            "question": question or "",
            "answer": answer or "",
            "allowed_ids": set(allowed_ids),
            "patient_key": patient_key,
            "reason": "",
        }
        return await self._check(
            [
                {"role": "user", "content": question or ""},
                {"role": "assistant", "content": answer or ""},
            ],
            [RailType.OUTPUT],
            state,
            kind="output",
        )

    async def _check(
        self,
        messages: list[dict[str, str]],
        rail_types: list[RailType],
        state: dict[str, Any],
        *,
        kind: str,
    ) -> RailResult:
        token = _rail_state.set(state)
        try:
            result = await self._rails.check_async(messages, rail_types=rail_types)
        except Exception as exc:
            if self.safety_enabled:
                log.warning("NeMo content safety rail failed: %s", type(exc).__name__)
                return RailResult(False, "content_safety_unavailable", REFUSAL)
            raise
        finally:
            _rail_state.reset(token)
        return _from_check(result, state, kind=kind)


def document_safety_result(outcome: Any, status: str, text: str) -> RailResult:
    """Publish a note the safety model blocked only for privacy."""
    if status != "success" or outcome is None or getattr(outcome, "failed", False):
        return RailResult(False, "content_safety_unavailable", REFUSAL)
    if not getattr(outcome, "is_blocked", False):
        return RailResult(True, text=text)
    raw = (getattr(outcome, "metadata", None) or {}).get("policy_violations") or []
    categories = {str(item).strip().lower() for item in raw if str(item).strip()}
    if categories and categories <= _PII_CATEGORIES:
        return RailResult(True, text=text)
    return RailResult(False, "content_safety", NOT_ALLOWED)


def _from_check(result: Any, state: dict[str, Any], *, kind: str) -> RailResult:
    if result.status == RailStatus.BLOCKED:
        rail = result.rail or ""
        content = result.content or ""
        if "content safety" in rail or _INTERNAL_ERROR in content:
            if _INTERNAL_ERROR in content:
                return RailResult(False, "content_safety_unavailable", REFUSAL)
            return RailResult(False, "content_safety", NOT_ALLOWED)
        if rail == "check identity claim":
            return RailResult(False, "identity_claim", REFUSAL)
        return RailResult(False, state.get("reason") or "citation_leak", REFUSAL)
    if kind == "output":
        stored = state.get("output")
        if isinstance(stored, RailResult) and stored.ok:
            return stored
    return RailResult(True, text=result.content or "")


def _bind_endpoints(config: RailsConfig, settings: Settings) -> bool:
    safety = settings.safety_url.strip()
    nano = settings.nano_url.strip()
    kept = []
    for model in config.models:
        if model.type == "main":
            model.parameters["base_url"] = _v1(nano) if nano else "http://127.0.0.1:9/v1"
            if settings.nano_model.strip():
                model.model = settings.nano_model.strip()
            kept.append(model)
        elif model.type == "content_safety":
            if safety:
                model.parameters["base_url"] = _v1(safety)
                kept.append(model)
        else:
            kept.append(model)
    config.models = kept
    if not safety:
        config.rails.input.flows = [
            flow for flow in config.rails.input.flows if not flow.startswith("content safety")
        ]
        config.rails.output.flows = [
            flow for flow in config.rails.output.flows if not flow.startswith("content safety")
        ]
    return bool(safety)


def load_nemo_rails(settings: Settings) -> NemoRails:
    path = pack_path(settings)
    key = (str(path), settings.nano_url, settings.nano_model, settings.safety_url)
    cached = _loaded.get(key)
    if cached is not None:
        return cached
    config = RailsConfig.from_path(str(path))
    safety_enabled = _bind_endpoints(config, settings)
    rails = LLMRails(config)
    rails.register_action(check_identity_claim, name="check_identity_claim")
    rails.register_action(check_citation_leak, name="check_citation_leak")
    loaded = NemoRails(rails, safety_enabled=safety_enabled)
    _loaded[key] = loaded
    return loaded


def rails_for(deps: Any) -> NemoRails:
    """The rails loaded at startup, or a cached load when the lifespan did not run."""
    if deps.nemo is None:
        deps.nemo = load_nemo_rails(deps.settings)
    return deps.nemo
