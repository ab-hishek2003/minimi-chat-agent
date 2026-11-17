"""Automated tests. The AI model is replaced by a fake, so no API keys or internet are needed."""
import importlib
import io
import pathlib
import sys
import types

import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parents[1]
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0f01f0005000201a5f645400000000049454e44ae426082")


def fake_model(content="Hello! This is a test answer."):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        msg = types.SimpleNamespace(content=content, tool_calls=None)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    create.calls = calls
    return create


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # each test gets its own empty database
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setenv("TAVILY_API_KEY", "test")
    (tmp_path / "index.html").write_text((ROOT / "index.html").read_text(encoding="utf-8"), encoding="utf-8")
    sys.path.insert(0, str(ROOT))
    sys.modules.pop("app", None)
    module = importlib.import_module("app")
    module.client.chat.completions.create = fake_model()
    yield module
    sys.path.remove(str(ROOT))
    sys.modules.pop("app", None)


@pytest.fixture
def client(app_module):
    return TestClient(app_module.app)


def test_health_and_homepage(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert "minimi" in client.get("/").text


def test_chat_saves_a_conversation(client):
    r = client.post("/chat", data={"message": "hi"})
    assert r.status_code == 200 and r.json()["reply"].startswith("Hello")
    chats = client.get("/conversations").json()
    assert len(chats) == 1 and chats[0]["title"] == "hi"
    assert len(client.get(f"/conversations/{chats[0]['id']}").json()) == 2


def test_empty_and_oversized_messages_are_rejected(client):
    assert client.post("/chat", data={"message": "   "}).status_code == 400
    assert client.post("/chat", data={"message": "x" * 9000}).status_code == 400


def test_visitors_cannot_see_each_others_chats(app_module):
    alice, bob = TestClient(app_module.app), TestClient(app_module.app)
    cid = alice.post("/chat", data={"message": "secret"}).json()["conversation_id"]
    assert bob.get("/conversations").json() == []
    assert bob.get(f"/conversations/{cid}").status_code == 404
    assert bob.post("/chat", data={"message": "x", "conversation_id": cid}).status_code == 404
    assert bob.delete(f"/conversations/{cid}").status_code == 404
    assert alice.delete(f"/conversations/{cid}").status_code == 200


def test_rate_limit(client, app_module):
    app_module.CHAT_PER_HOUR = 2
    codes = [client.post("/chat", data={"message": "m"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_picture_goes_to_a_vision_model(client, app_module):
    r = client.post("/chat", data={"message": "what is this?"}, files=[("files", ("a.png", PNG, "image/png"))])
    assert r.status_code == 200
    sent = app_module.client.chat.completions.create.calls[-1]
    assert sent["model"] in app_module.VISION_MODELS
    assert sent["messages"][-1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_text_file_is_read_and_remembered(client, app_module):
    cid = client.post("/chat", data={"message": "read"},
                      files=[("files", ("n.txt", b"The launch date is 14 March.", "text/plain"))]).json()["conversation_id"]
    client.post("/chat", data={"message": "when is it?", "conversation_id": cid})
    sent = app_module.client.chat.completions.create.calls[-1]["messages"]
    assert any("launch date is 14 March" in m["content"] for m in sent if isinstance(m["content"], str))


def test_word_document_is_read(client, app_module):
    from docx import Document
    doc, buf = Document(), io.BytesIO()
    doc.add_paragraph("Budget is 5000 rupees.")
    doc.save(buf)
    client.post("/chat", data={"message": "read"}, files=[("files", ("b.docx", buf.getvalue(), "application/octet-stream"))])
    assert "Budget is 5000 rupees." in app_module.client.chat.completions.create.calls[-1]["messages"][-1]["content"]


def test_file_limits(client, app_module):
    many = [("files", (f"f{i}.txt", b"a", "text/plain")) for i in range(6)]
    assert client.post("/chat", data={"message": "x"}, files=many).status_code == 400
    app_module.MAX_FILE_BYTES = 10
    assert client.post("/chat", data={"message": "x"}, files=[("files", ("big.txt", b"a" * 50, "text/plain"))]).status_code == 400


def test_broken_reply_is_replaced(client, app_module):
    app_module.client.chat.completions.create = fake_model("[2026-11-15 ...] ... ... ... ... ... ... ... ... ... ...")
    reply = client.post("/chat", data={"message": "hi"}).json()["reply"]
    assert "could not produce a clear answer" in reply


def test_hidden_thinking_is_removed(client, app_module):
    app_module.client.chat.completions.create = fake_model("<think>private</think>Visible answer.")
    assert client.post("/chat", data={"message": "hi"}).json()["reply"] == "Visible answer."


def test_failed_ai_call_leaves_no_trace(client, app_module):
    def boom(**kwargs):
        raise RuntimeError("service down")

    app_module.client.chat.completions.create = boom
    assert client.post("/chat", data={"message": "hi"}).status_code == 502
    assert client.get("/conversations").json() == []
