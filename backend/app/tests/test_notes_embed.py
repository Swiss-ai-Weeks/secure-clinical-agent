from __future__ import annotations

from unittest.mock import patch

import pytest

from patient360.tools.stores import HttpNotes


class _Resp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _Client:
    def __init__(self, posted: dict) -> None:
        self.posted = posted

    async def __aenter__(self) -> _Client:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, url: str, json: dict | None = None) -> _Resp:
        self.posted["url"] = url
        self.posted["json"] = json
        return _Resp({"data": [{"embedding": [0.1, 0.2]}]})

    async def put(
        self,
        url: str,
        params: dict | None = None,
        headers: dict | None = None,
        json: dict | None = None,
    ) -> _Resp:
        self.posted["put_url"] = url
        self.posted["put"] = json
        return _Resp({})


@pytest.mark.asyncio
async def test_embed_sends_required_model_field() -> None:
    posted: dict = {}
    notes = HttpNotes("http://qdrant", "key", embed_url="http://embed:8000")
    with patch("patient360.tools.stores.httpx.AsyncClient", lambda **kwargs: _Client(posted)):
        vector = await notes._embed("The library opens at nine.", input_type="query")
    assert posted["url"] == "http://embed:8000/v1/embeddings"
    assert posted["json"]["model"] == "nvidia/llama-nemotron-embed-vl-1b-v2"
    assert posted["json"]["input"] == ["The library opens at nine."]
    assert posted["json"]["input_type"] == "query"
    assert vector == [0.1, 0.2]


@pytest.mark.asyncio
async def test_upsert_embeds_note_text_for_retrieval() -> None:
    posted: dict = {}
    notes = HttpNotes("http://qdrant", "key", embed_url="http://embed:8000")
    with patch("patient360.tools.stores.httpx.AsyncClient", lambda **kwargs: _Client(posted)):
        await notes.upsert(
            [{"id": "c1", "payload": {"text": "Blood pressure log from the scan.", "patient_key": "p_103"}}]
        )
    assert posted["json"]["input_type"] == "passage"
    assert posted["put"]["points"][0]["vector"] == [0.1, 0.2]
