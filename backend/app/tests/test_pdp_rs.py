"""The Rust PDP must match the Python matrix reason codes. FastAPI still calls Python."""

from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path

import pytest

from patient360.pdp import Resource, evaluate
from patient360.pdp.models import Context
from tests import test_pdp_matrix as matrix
from tests.fakes import FakeFga


def _load():
    release = Path(__file__).resolve().parents[2] / "pdp-rs" / "target" / "release"
    matches = sorted(release.glob("libpdp_rs.so"))
    if not matches:
        pytest.fail(f"build backend/pdp-rs first; missing {release}/libpdp_rs.so")
    spec = importlib.util.spec_from_file_location("pdp_rs", matches[0])
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PDP = _load()


def _subject(value) -> dict:
    return {
        "user_id": value.user_id,
        "role": value.role,
        "on_duty": value.on_duty,
        "auth_level": value.auth_level,
        "self_patient_id": value.self_patient_id,
    }


def _resource(value) -> dict:
    return {
        "type": value.type,
        "patient_key": value.patient_key,
        "dataset": value.dataset,
        "patient_age": value.patient_age,
    }


def _context(value) -> dict:
    target = None
    if value.target is not None:
        target = {
            "relation": value.target.relation,
            "grantee_user_id": value.target.grantee_user_id,
            "grantee_role": value.target.grantee_role,
            "granted_by": value.target.granted_by,
        }
    return {
        "now": value.now.isoformat(),
        "channel": value.channel,
        "action": value.action,
        "project_id": value.project_id,
        "group_by": list(value.group_by) if value.group_by is not None else None,
        "adolescent_age": value.adolescent_age,
        "majority_age": value.majority_age,
        "target": target,
        "appointment_created_by": value.appointment_created_by,
        "appointment_practitioner": value.appointment_practitioner,
    }


def _rust(fga: FakeFga, subj, resource, context, *, objects: bool = False):
    def check(user: str, relation: str, obj: str, now_iso: str) -> bool:
        now = datetime.fromisoformat(now_iso)
        fga.calls.append((user, relation, obj, now))
        return fga._holds(user, relation, obj, now)

    listed = None
    if objects:
        def listed(user: str, relation: str, type_: str, now_iso: str) -> list[str]:
            now = datetime.fromisoformat(now_iso)
            found = {t.object for t in fga.tuples if t.object.startswith(type_ + ":")}
            return sorted(o for o in found if fga._holds(user, relation, o, now))

    return PDP.evaluate(_subject(subj), _resource(resource), _context(context), check, listed)


async def _same(desc: str, subj, resource, context, *, objects: bool = False) -> None:
    py_fga = FakeFga()
    rs_fga = FakeFga()
    kwargs = {"list_objects": py_fga.list_objects} if objects else {}
    python = await evaluate(subj, resource, context, py_fga.check, **kwargs)
    rust = _rust(rs_fga, subj, resource, context, objects=objects)
    assert (rust["effect"], rust["reason_code"], rust["fga_consulted"]) == (
        python.effect,
        python.reason_code,
        python.fga_consulted,
    ), desc
    assert rust["policy_id"] == python.policy_id


@pytest.mark.asyncio
async def test_rust_matches_python_reason_codes():
    for desc, subj, patient, dataset, *_rest in matrix.MATRIX:
        await _same(desc, matrix.subject(**subj), matrix.resource(patient, dataset), matrix.ctx())
    for desc, subj, patient, *_rest in matrix.NOTES_MATRIX:
        await _same(desc, matrix.subject(**subj), Resource(type="notes", patient_key=patient), matrix.ctx())
    for desc, subj, rtype, patient, *_rest in matrix.IMAGING_MATRIX:
        await _same(desc, matrix.subject(**subj), Resource(type=rtype, patient_key=patient), matrix.ctx())
    for desc, subj, patient, context, *_rest in matrix.WRITE_MATRIX:
        await _same(desc, matrix.subject(**subj), Resource(type="consents", patient_key=patient), context)
    for desc, subj, *_rest in matrix.BREAK_GLASS_MATRIX:
        await _same(
            desc,
            matrix.subject(**subj),
            Resource(type="clinical_rows", patient_key="p_205"),
            matrix.bg(),
        )
    for desc, subj, patient, *_rest in matrix.IDENTITY_MATRIX:
        await _same(
            desc, matrix.subject(**subj), Resource(type="identity", patient_key=patient), matrix.ctx()
        )
    for desc, subj, patient, *_rest in matrix.CONSENTS_LIST_MATRIX:
        await _same(
            desc, matrix.subject(**subj), Resource(type="consents", patient_key=patient), matrix.ctx()
        )
    for desc, subj, dataset, project, *_rest in matrix.AGGREGATE_MATRIX:
        await _same(
            desc,
            matrix.subject(**subj),
            Resource(type="aggregate", dataset=dataset),
            Context(
                now=matrix.NOW,
                channel="dashboard",
                purpose="HRESCH",
                action="read",
                group_by=("code",) if dataset != "diet" else ("ward",),
                project_id=project,
                k_min=5,
            ),
            objects=True,
        )
    for desc, subj, patient, action, created_by, practitioner, *_rest in matrix.SCHEDULE_MATRIX:
        who = subj if isinstance(subj, dict) else subj
        await _same(
            desc,
            matrix.subject(**who),
            matrix.resource(patient, "encounters"),
            Context(
                now=matrix.NOW,
                channel="dashboard",
                purpose="TREAT",
                action=action,
                appointment_created_by=created_by,
                appointment_practitioner=practitioner,
            ),
        )
