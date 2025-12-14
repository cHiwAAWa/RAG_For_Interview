# tests/test_interview_router.py
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from backend.main import app  # 假設你的 FastAPI app 在這裡初始化

client = TestClient(app)

# 模擬一個假的 session 資料
MOCK_SESSION_DATA = {
    "history": [{"question": "Q1", "answer": ""}],
    "job_title": "Engineer"
}

@pytest.fixture
def mock_dependencies():
    """
    使用 patch 來攔截並替換掉原本的 Service
    """
    with patch("backend.api.interview_router.SessionService") as mock_session, \
         patch("backend.api.interview_router.speech_service") as mock_speech, \
         patch("backend.api.interview_router.agent_service") as mock_agent:
        
        yield mock_session, mock_speech, mock_agent

def test_submit_answer_success(mock_dependencies):
    mock_session, mock_speech, mock_agent = mock_dependencies

    # 1. 設定 Mock 的行為 (Arrange)
    mock_session.get_session.return_value = MOCK_SESSION_DATA
    mock_speech.speech_to_text.return_value = "我會寫 Python"
    mock_agent.generate_question.return_value = "請解釋 GIL 是什麼？"

    # 2. 執行請求 (Act)
    # 模擬傳送 Session ID 和音檔
    response = client.post(
        "/api/v1/interview/answer", # 假設你的路由 prefix 是這個
        data={"session_id": "test-session-123"},
        files={"audio_file": ("test.wav", b"fake-audio-bytes", "audio/wav")}
    )

    # 3. 驗證結果 (Assert)
    assert response.status_code == 200
    data = response.json()
    assert data["question_text"] == "請解釋 GIL 是什麼？"
    assert data["is_end"] is False

    # 驗證是否有呼叫到對應的 Service
    mock_speech.speech_to_text.assert_called_once()
    mock_agent.generate_question.assert_called_once_with("test-session-123")
    
    # 驗證 Session 更新邏輯是否正確 (上一題的 answer 應該被填入)
    # 注意：這裡驗證的是我們是否有呼叫 add_history
    mock_session.add_history.assert_called_with("test-session-123", "請解釋 GIL 是什麼？", "")

def test_submit_answer_session_not_found(mock_dependencies):
    mock_session, _, _ = mock_dependencies

    # 設定 Mock 回傳 None，模擬找不到 Session
    mock_session.get_session.return_value = None

    response = client.post(
        "/api/v1/interview/answer",
        data={"session_id": "invalid-id"}
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"