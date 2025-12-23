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

    # 1. 新增關鍵字判斷函式
def check_voice_command(text: str):
    """檢查文字中是否包含下一題或退出的指令"""
    # 移除空格與標點符號方便比對
    clean_text = text.replace(" ", "").replace("。", "").replace("！", "").replace("？", "")
    
    # 定義關鍵字清單
    exit_keywords = ["退出", "結束面試", "停止面試", "不面試了", "離開"]
    next_keywords = ["下一題", "跳過", "換一題", "下一個問題", "下一天", "恰一聽", "摘婷", "車題"] # 加入可能聽錯的諧音
    
    for kw in exit_keywords:
        if kw in clean_text:
            return "EXIT"
    
    for kw in next_keywords:
        if kw in clean_text:
            return "NEXT"
    
    return None

# --- Main Endpoint ---

@router.post("/answer", response_model=QuestionResponse)
async def submit_answer(
    session_id: str = Form(...),    
    audio_file: UploadFile = File(None) 
):
    # 1. 驗證 Session
    validate_session(session_id)
    
    # 2. 執行 STT (音訊轉文字)
    user_text = process_audio_file(session_id, audio_file)
    print(f"🎤 使用者說: {user_text}")

    # 3. 🔥【新增】指令判斷邏輯
    command = check_voice_command(user_text)

    if command == "EXIT":
        print("🛑 偵測到退出指令")
        return QuestionResponse(
            question_text="好的，今天的面試到此結束，辛苦了。",
            is_end=True 
        )

    elif command == "NEXT":
        print("⏭️ 偵測到下一題指令，略過本次回答")
        # 覆蓋 user_text，讓 AI 知道使用者想換題
        user_text = "（使用者要求跳過此題，請直接提供下一個不同的面試問題）"
    
    # 4. AI 生成下一題
    question_text = agent_service.generate_question(session_id)

    print(f"========================================")
    print(f" AI 生成的題目: {question_text}")
    print(f"========================================")
    
    if not question_text:
        return QuestionResponse(question_text="面試結束，感謝您的參與。", is_end=True)

    # 5. 更新歷史紀錄
    update_session_history(session_id, user_text, question_text)

    # 6. 回傳結果
    return QuestionResponse(
        question_text=question_text,
        is_end=False
    )