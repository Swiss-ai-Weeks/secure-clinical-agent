"""POST /chat: mint a run token and answer in-proc. OpenShell is optional."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .audit import OUTCOME_SUCCESS, AuditEvent
from .auth import runtoken
from .auth.subject import Caller
from .deps import AppDeps
from .errors import Deny, NotFound
from .guardrails import REFUSAL, input_rails, output_rails
from .tools.notes import run_notes
from .tools.query import run_query
from .tools.schemas import NotesRequest, QueryFilters, QueryRequest


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(..., min_length=1, max_length=2000)
    patient_key: str | None = Field(None, pattern=r"^p_[0-9a-z]+$", max_length=64)


async def run_chat(deps: AppDeps, caller: Caller, req: ChatRequest, *, now: datetime) -> dict[str, Any]:
    rails = input_rails(req.question)
    if not rails.ok:
        return {
            "answer": REFUSAL,
            "citations": [],
            "retrievalSteps": ["Input rail blocked the question"],
            "audit_id": str(uuid4()),
            "policy_reason": rails.reason,
            "refused": True,
        }

    token, claims = runtoken.mint(
        deps.settings, user_id=caller.user.user_id, sid=caller.sid, agent_id="agent:inproc", now=now
    )
    del token
    agent = Caller(
        subject=caller.subject,
        channel="agent",
        session=caller.session,
        user=caller.user,
        jti=claims.jti,
        agent=claims.act_sub,
    )

    steps = ["Minted run token", "Searched authorized structured rows"]
    evidence: list[dict[str, Any]] = []
    allowed_ids = {req.patient_key} if req.patient_key else set()
    if req.patient_key:
        for dataset in ("labs", "conditions", "meds"):
            try:
                q = await run_query(
                    deps,
                    agent,
                    QueryRequest(patient_key=req.patient_key, dataset=dataset, filters=QueryFilters(limit=8)),
                    now=now,
                )
            except (NotFound, Deny):
                continue
            for row in q.rows:
                if row.get("redacted"):
                    continue
                cite = str(row.get("cite_id") or "")
                if cite:
                    allowed_ids.add(cite)
                evidence.append(
                    {
                        "id": cite or str(uuid4()),
                        "label": str(row.get("display") or row.get("code") or dataset),
                        "sourceId": cite,
                        "sourceType": (
                            "lab" if dataset == "labs" else "medication" if dataset == "meds" else "note"
                        ),
                        "text": str(row.get("display") or row.get("value_num") or ""),
                    }
                )
        try:
            notes = await run_notes(
                deps, agent, NotesRequest(patient_key=req.patient_key, question=req.question), now=now
            )
            steps.append("Searched authorized notes")
            for chunk in notes.chunks:
                nid = str(chunk.get("note_id") or chunk.get("cite_id") or "")
                if nid:
                    allowed_ids.add(nid)
                evidence.append(
                    {
                        "id": nid or str(uuid4()),
                        "label": str(chunk.get("note_id") or "note"),
                        "sourceId": str(chunk.get("cite_id") or nid),
                        "sourceType": "note",
                        "text": str(chunk.get("text") or ""),
                    }
                )
        except (NotFound, Deny):
            steps.append("Notes not authorized")

    if not evidence:
        answer = REFUSAL
        refused = True
        reason = "no_authorized_evidence"
    else:
        bits = [f"{e['label']}: {e['text']}" for e in evidence[:6] if e.get("text")]
        answer = "Based on authorized evidence: " + " ".join(bits)
        refused = False
        reason = None
    out = output_rails(answer, {i for i in allowed_ids if i})
    if not out.ok:
        answer, refused, reason = REFUSAL, True, out.reason
    else:
        answer = out.text

    audit_id = await deps.audit.write(
        AuditEvent(
            event_type="tool_call",
            agent_user=caller.user.user_id,
            agent_software="patient360-inproc",
            purpose_of_event="TREAT",
            entity_patient=req.patient_key,
            entity_resource="chat",
            outcome=OUTCOME_SUCCESS,
            outcome_desc="chat_answered",
            session_id=caller.sid,
            jti=claims.jti,
            detail={"refused": refused, "reason": reason, "runtime": deps.settings.agent_runtime},
        )
    )
    return {
        "answer": answer,
        "citations": [
            {"id": e["id"], "label": e["label"], "sourceId": e["sourceId"], "sourceType": e["sourceType"]}
            for e in evidence[:8]
        ],
        "retrievalSteps": steps,
        "audit_id": str(audit_id),
        "policy_reason": reason,
        "refused": refused,
    }
