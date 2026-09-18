"""Clinical row reader for /tools/query. Postgres implementation plus the protocol tests fake."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from ..db import Database
from ..errors import Transient
from ..pdp.models import Obligations
from .datasets import DATASETS, build_aggregate_query, build_query
from .schemas import QueryFilters

log = logging.getLogger(__name__)


class ClinicalReader(Protocol):
    async def fetch(
        self, dataset: str, patient_key: str, filters: QueryFilters, obligations: Obligations
    ) -> list[dict[str, Any]]: ...

    async def patient_birth_year(self, patient_key: str) -> int | None:
        """Year of birth from clinical.patients (the only age the store holds), or None when unknown."""
        ...

    async def aggregate(
        self,
        dataset: str,
        group_by: list[str],
        filters: QueryFilters,
        obligations: Obligations,
        scoped_keys: tuple[str, ...] | None,
    ) -> list[dict[str, Any]]:
        """COUNT(*) cells. scoped_keys=None is the researcher path (every row)."""
        ...

    async def get_appointment(self, appointment_id: UUID) -> dict[str, Any] | None: ...

    async def insert_appointment(self, row: dict[str, Any]) -> dict[str, Any]: ...

    async def update_appointment(
        self, appointment_id: UUID, fields: dict[str, Any]
    ) -> dict[str, Any] | None: ...

    async def booked_windows(
        self, *, practitioner_user_id: str | None, start: datetime, end: datetime
    ) -> list[dict[str, Any]]: ...

    async def list_notes(self, patient_key: str) -> list[dict[str, Any]]: ...

    async def list_imaging(self, patient_key: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]: ...


class PgClinicalReader:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def patient_birth_year(self, patient_key: str) -> int | None:
        try:
            async with self.db.pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT birth_year FROM clinical.patients WHERE patient_key = %s", (patient_key,)
                )
                row = await cur.fetchone()
        except Exception as exc:
            log.error("patient read failed: %s", exc.__class__.__name__)
            raise Transient("clinical store unavailable") from exc
        return row["birth_year"] if row else None

    async def fetch(
        self, dataset: str, patient_key: str, filters: QueryFilters, obligations: Obligations
    ) -> list[dict[str, Any]]:
        spec = DATASETS[dataset]
        sql, params = build_query(spec, patient_key, filters, obligations)
        try:
            async with self.db.pool.connection() as conn:
                cur = await conn.execute(sql, params)
                rows = await cur.fetchall()
        except Exception as exc:
            log.error("clinical read failed: %s", exc.__class__.__name__)
            raise Transient("clinical store unavailable") from exc
        out = [dict(r) for r in rows]
        if dataset == "encounters":
            out.extend(await self._appointment_as_encounters(patient_key))
        return out

    async def aggregate(
        self,
        dataset: str,
        group_by: list[str],
        filters: QueryFilters,
        obligations: Obligations,
        scoped_keys: tuple[str, ...] | None,
    ) -> list[dict[str, Any]]:
        spec = DATASETS[dataset]
        sql, params = build_aggregate_query(spec, group_by, filters, obligations, scoped_keys)
        try:
            async with self.db.pool.connection() as conn:
                cur = await conn.execute(sql, params)
                rows = await cur.fetchall()
        except Exception as exc:
            log.error("aggregate read failed: %s", exc.__class__.__name__)
            raise Transient("clinical store unavailable") from exc
        return [dict(r) for r in rows]

    async def _appointment_as_encounters(self, patient_key: str) -> list[dict[str, Any]]:
        sql = (
            "SELECT cite_id, status, 'AMB' AS class, service_type AS type_code, "
            "service_type_system AS type_system, service_type_display AS type_display, "
            "start_at AS started_at, end_at AS ended_at, NULL AS reason_code, "
            "NULL AS reason_system, NULL AS reason_display, dept, "
            "confidentiality, sensitivity "
            "FROM clinical.appointments "
            "WHERE patient_key = %s AND status IN ('booked', 'pending')"
        )
        try:
            async with self.db.pool.connection() as conn:
                cur = await conn.execute(sql, (patient_key,))
                return [dict(r) for r in await cur.fetchall()]
        except Exception as exc:
            log.error("appointment read failed: %s", exc.__class__.__name__)
            raise Transient("clinical store unavailable") from exc

    async def get_appointment(self, appointment_id: UUID) -> dict[str, Any] | None:
        try:
            async with self.db.pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT * FROM clinical.appointments WHERE id = %s", (appointment_id,)
                )
                row = await cur.fetchone()
        except Exception as exc:
            log.error("appointment get failed: %s", exc.__class__.__name__)
            raise Transient("clinical store unavailable") from exc
        return dict(row) if row else None

    async def insert_appointment(self, row: dict[str, Any]) -> dict[str, Any]:
        cols = [
            "source_id",
            "patient_key",
            "practitioner_user_id",
            "status",
            "start_at",
            "end_at",
            "dept",
            "service_type",
            "service_type_system",
            "service_type_display",
            "created_by",
        ]
        names = ", ".join(cols)
        placeholders = ", ".join(f"%({c})s" for c in cols)
        sql = f"INSERT INTO clinical.appointments ({names}) VALUES ({placeholders}) RETURNING *"
        try:
            async with self.db.pool.connection() as conn:
                cur = await conn.execute(sql, row)
                inserted = await cur.fetchone()
        except Exception as exc:
            log.error("appointment insert failed: %s", exc.__class__.__name__)
            raise Transient("clinical store unavailable") from exc
        assert inserted is not None
        return dict(inserted)

    async def update_appointment(self, appointment_id: UUID, fields: dict[str, Any]) -> dict[str, Any] | None:
        if not fields:
            return await self.get_appointment(appointment_id)
        sets = ", ".join(f"{k} = %({k})s" for k in fields)
        params = {**fields, "id": appointment_id}
        sql = f"UPDATE clinical.appointments SET {sets} WHERE id = %(id)s RETURNING *"
        try:
            async with self.db.pool.connection() as conn:
                cur = await conn.execute(sql, params)
                row = await cur.fetchone()
        except Exception as exc:
            log.error("appointment update failed: %s", exc.__class__.__name__)
            raise Transient("clinical store unavailable") from exc
        return dict(row) if row else None

    async def list_notes(self, patient_key: str) -> list[dict[str, Any]]:
        sql = (
            "SELECT cite_id, source_id, patient_key, type_code, type_display, authored_at, "
            "internal, provenance, published, confidentiality, sensitivity, sanitized_ref, "
            "deid_version, chunk_count "
            "FROM clinical.notes WHERE patient_key = %s AND published = true "
            "ORDER BY authored_at DESC"
        )
        try:
            async with self.db.pool.connection() as conn:
                cur = await conn.execute(sql, (patient_key,))
                return [dict(r) for r in await cur.fetchall()]
        except Exception as exc:
            log.error("notes list failed: %s", exc.__class__.__name__)
            raise Transient("clinical store unavailable") from exc

    async def list_imaging(self, patient_key: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        studies_sql = (
            "SELECT cite_id, source_id, patient_key, status, study_at, modality, "
            "series_count, instance_count, procedure_code, procedure_display, "
            "body_site_display, orthanc_id, confidentiality, sensitivity "
            "FROM clinical.studies WHERE patient_key = %s ORDER BY study_at DESC"
        )
        reports_sql = (
            "SELECT cite_id, source_id, patient_key, status, category, code, display, "
            "effective_at, issued_at, conclusion_text, report_ref, study_id, "
            "confidentiality, sensitivity "
            "FROM clinical.imaging_reports WHERE patient_key = %s ORDER BY issued_at DESC"
        )
        try:
            async with self.db.pool.connection() as conn:
                cur = await conn.execute(studies_sql, (patient_key,))
                studies = [dict(r) for r in await cur.fetchall()]
                cur = await conn.execute(reports_sql, (patient_key,))
                reports = [dict(r) for r in await cur.fetchall()]
        except Exception as exc:
            log.error("imaging list failed: %s", exc.__class__.__name__)
            raise Transient("clinical store unavailable") from exc
        return studies, reports

    async def booked_windows(
        self, *, practitioner_user_id: str | None, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        where = ["status IN ('booked', 'pending')", "start_at < %(end)s", "start_at >= %(start)s"]
        params: dict[str, Any] = {"start": start, "end": end}
        if practitioner_user_id:
            where.append("practitioner_user_id = %(practitioner)s")
            params["practitioner"] = practitioner_user_id
        sql = (
            "SELECT practitioner_user_id, start_at, end_at FROM clinical.appointments "
            f"WHERE {' AND '.join(where)}"
        )
        try:
            async with self.db.pool.connection() as conn:
                cur = await conn.execute(sql, params)
                return [dict(r) for r in await cur.fetchall()]
        except Exception as exc:
            log.error("appointment windows failed: %s", exc.__class__.__name__)
            raise Transient("clinical store unavailable") from exc
