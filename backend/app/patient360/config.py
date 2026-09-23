"""Settings. Every variable is prefixed PATIENT360_ and comes from the environment."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PATIENT360_", extra="ignore")

    # Postgres `fhir`, connecting as the least-privilege role p360_app.
    db_dsn: SecretStr = Field(description="postgres://p360_app:...@postgres:5432/fhir")

    # OpenFGA grant store. The store is resolved by name at startup; the newest
    # authorization model is pinned and stamped into audit rows as policy_version.
    openfga_url: str = "http://openfga:8080"
    openfga_key: SecretStr
    openfga_store_name: str = "patient360-grants"

    # OpenBao linkage vault: the only place login -> pseudonym persists.
    linkage_url: str = "http://openbao:8200"
    linkage_token: SecretStr
    linkage_mount: str = "secret"

    # Run tokens (RFC 9068 at+JWT with RFC 8693 act). HS256: the backend is the
    # sole issuer and the sole verifier.
    run_token_secret: SecretStr
    run_token_issuer: str = "patient360-backend"
    run_token_audience: str = "patient360-tools"
    run_token_ttl_seconds: int = 600

    # Sessions (NIST SP 800-63-4 / ASVS 5.0 V7).
    cookie_name: str = "p360_session"
    cookie_secure: bool = True
    session_inactivity_seconds: int = 3600
    session_absolute_seconds: int = 86400

    # Human writes (Build Plan §4.2). Consent windows are bounded; break-glass is a fixed
    # short window with a per-user activation limit (in-memory, one process).
    consent_max_days: int = 365
    break_glass_minutes: int = 60
    break_glass_per_hour: int = 3

    # Minors. Between the two ages, caregiver-role readers (guardians, named caregivers) see
    # R/V rows redacted (adolescent_confidential). Majority also bounds guardian windows at
    # registration. Ages are approximate: the store holds the birth year only.
    adolescent_age: int = 14
    majority_age: int = 18

    # Researcher aggregates (Build Plan §2). CMS-grade 11 when k_min_cms is set.
    k_min: int = 5
    k_min_cms: bool = False

    @property
    def effective_k_min(self) -> int:
        return 11 if self.k_min_cms else self.k_min

    # Notes / media / chat. Empty URLs keep the in-memory stores (tests, offline demo).
    qdrant_url: str = ""
    qdrant_api_key: SecretStr = SecretStr("")
    embed_url: str = ""
    embed_model: str = "nvidia/llama-nemotron-embed-vl-1b-v2"
    minio_url: str = ""
    minio_access_key: str = ""
    minio_secret_key: SecretStr = SecretStr("")
    orthanc_url: str = ""
    orthanc_user: str = ""
    orthanc_password: SecretStr = SecretStr("")
    nano_url: str = ""
    nano_model: str = ""
    safety_url: str = ""
    guardrails_path: Path | None = None
    agent_runtime: str = "openshell"
    openshell_url: str = ""
    openshell_sandbox: str = "patient360"
    openshell_agent: str = "main"
    media_ttl_seconds: int = 300
    vista_url: str = ""
    vista_work_dir: Path = Path("/data/patient360")
    vista_timeout_seconds: float = 300

    # Dev-only surface: /dev/run-token, /docs, and the dev-login map.
    dev: bool = False
    devlogin_path: Path = Path(__file__).with_name("devlogin.demo.json")

    agent_software: str = "patient360-backend"
