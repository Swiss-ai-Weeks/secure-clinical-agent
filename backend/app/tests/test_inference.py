from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from patient360.inference import chat_payload, complete_chat


def test_chat_payload_disables_thinking():
    payload = chat_payload("nvidia/nemotron-3-nano", [{"role": "user", "content": "Summarize."}])
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}
    assert payload["max_tokens"] == 800


class _FakeClient:
    def __init__(self, response: httpx.Response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, url: str, json: dict):
        self.payload = json
        self.url = url
        return self._response


def _response(body: dict) -> httpx.Response:
    return httpx.Response(
        200, json=body, request=httpx.Request("POST", "http://nano.test/v1/chat/completions")
    )


async def test_complete_chat_returns_content():
    client = _FakeClient(_response({"choices": [{"message": {"content": "HbA1c is 6.35% [obs_a1]."}}]}))
    with patch("patient360.inference.httpx.AsyncClient", return_value=client):
        text = await complete_chat(
            "http://nano.test",
            "nvidia/nemotron-3-nano",
            [{"role": "user", "content": "q"}],
        )
    assert text == "HbA1c is 6.35% [obs_a1]."
    assert client.payload["chat_template_kwargs"] == {"enable_thinking": False}


async def test_complete_chat_rejects_empty_reasoning_only_content():
    client = _FakeClient(
        _response(
            {
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": "", "reasoning_content": "The user wants a summary."},
                    }
                ]
            }
        )
    )
    with (
        patch("patient360.inference.httpx.AsyncClient", return_value=client),
        pytest.raises(RuntimeError, match="empty completion"),
    ):
        await complete_chat(
            "http://nano.test",
            "nvidia/nemotron-3-nano",
            [{"role": "user", "content": "q"}],
        )
