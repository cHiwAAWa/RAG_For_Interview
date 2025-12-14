# interview_router.py (重構版)

import os
import shutil
from typing import Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from backend.models.pydantic_models import QuestionResponse
from backend.services.session_service import SessionService
from backend.services.agent_service import AgentService
from backend.services.speech_service import SpeechService
from backend.config import settings

router = APIRouter()

# 建議：在真實專案中，這些 Service 最好透過 FastAPI 的 Depends 注入，這裡先維持原樣
agent_service = AgentService()
speech_service = SpeechService()

# --- Helper Functions (獨立邏輯，方便測試) ---

def validate_session(session_id: str):
    """驗證 Session 是否存在"""
    session = SessionService.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session

def process_audio_file(session_id: str, audio_file: UploadFile) -> str:
    """處理音檔儲存與 STT 辨識，並確保暫存檔被刪除"""
    if not audio_file:
        return ""
    
    temp_filename = f"temp_{session_id}.wav"
    temp_path = os.path.join(settings.AUDIO_DIR, temp_filename)
    user_text = ""

    try:
        # 儲存檔案
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(audio_file.file, buffer)
        
        # 執行 STT
        user_text = speech_service.speech_to_text(temp_path)
    except Exception as e:
        print(f"STT Error: {e}")
        # 視需求，這裡可以選擇是否拋出錯誤或僅記錄
    finally:
        # 清理暫存檔
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
    return user_text

def update_session_history(session_id: str, user_answer: str, next_question: str):
    """更新對話歷史紀錄"""
    session = SessionService.get_session(session_id)
    if not session:
        return

    # 1. 更新上一題使用者的回答 (若有)
    if user_answer:
        last_history = session.get('history', [])
        if last_history:
             last_history[-1]['answer'] = user_answer
    
    # 2. 將新題目存入歷史 (等待下次回答)
    if next_question:
        SessionService.add_history(session_id, next_question, "")

# --- Main Endpoint ---

@router.post("/answer", response_model=QuestionResponse)
async def submit_answer(
    session_id: str = Form(...),    
    audio_file: UploadFile = File(None) 
):
    # 1. 驗證 Session
    validate_session(session_id)
    
    # 2. 處理音訊 (如果有的話)
    user_text = process_audio_file(session_id, audio_file)
    
    # 3. AI 生成下一題
    question_text = agent_service.generate_question(session_id)

    print(f"========================================")
    print(f" AI 生成的題目: {question_text}")
    print(f"========================================")
    
    if not question_text:
        return QuestionResponse(question_text="面試結束，感謝您的參與。", is_end=True)

    # 4. 更新歷史紀錄
    update_session_history(session_id, user_text, question_text)

    # 5. 回傳結果
    return QuestionResponse(
        question_text=question_text,
        is_end=False
    )