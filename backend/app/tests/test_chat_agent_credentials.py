"""Exercise the credential handoff from chat to an agent's note tool call."""

from unittest.mock import AsyncMock, patch

import pytest

from patient360.auth import runtoken


@pytest.mark.parametrize("question", ["Summarize the latest note", "What changed?"])
async def test_chat_agent_can_read_notes_with_handed_off_token(harness, question):
    await harness.login("chen", auth_level=2)

    async def agent_turn(settings, token, question, *, sandbox, patient_key):
        # A sandbox sends only the run token, never the dashboard session cookie.
        async with harness.new_client() as agent:
            response = await agent.post(
                "/tools/notes",
                headers={"Authorization": f"Bearer {token}"},
                json={"patient_key": patient_key, "question": question},
            )
        assert response.status_code == 200, response.text
        assert response.json()["chunks"]
        claims = runtoken.verify(settings, token)
        assert claims.user_id == "u_chen"
        assert claims.act_sub == "agent:openshell"
        assert claims.sid in {session.sid for session in harness.sessions.rows.values()}
        return "Admission note reviewed [note_p101_admit]."

    with patch("patient360.chat.try_openshell_turn", new=AsyncMock(side_effect=agent_turn)) as turn:
        response = await harness.client.post("/chat", json={"question": question, "patient_key": "p_101"})

    turn.assert_awaited_once()
    assert response.status_code == 200, response.text
    assert response.json()["refused"] is False
    assert "[note_p101_admit]" in response.json()["answer"]
