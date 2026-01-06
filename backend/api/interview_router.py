# interview_router.py

import os
import shutil
import time
import uuid
from typing import Optional, Dict
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from backend.models.pydantic_models import QuestionResponse
from backend.services.session_service import SessionService
from backend.services.agent_service import AgentService
from backend.services.speech_service import SpeechService
from backend.config import settings

router = APIRouter()
agent_service = AgentService()
speech_service = SpeechService()

# --- Helper Functions (輔助函式) ---

def process_audio_file(session_id: str, audio_file: UploadFile) -> str:
    """
    處理音檔：儲存並執行 STT，【現在會保留檔案】
    回傳: {"text": "辨識文字", "file_path": "儲存路徑"}
    """
    if not audio_file:
        return {"text": "", "file_path": None}
    
    # 1. 建立永久儲存目錄 (例如 saved_audio)
    save_dir = os.path.join(settings.BASE_DIR, "saved_audio")
    os.makedirs(save_dir, exist_ok=True)

    # 2. 產生唯一檔名 (避免覆蓋)
    # 格式範例: session123_1701234567_abcde.wav
    unique_name = f"{session_id}_{int(time.time())}_{uuid.uuid4().hex[:5]}.wav"
    file_path = os.path.join(save_dir, unique_name)
    
    user_text = ""

    try:
        # 3. 儲存檔案 (永久保留)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(audio_file.file, buffer)
        
        # 4. 執行 STT
        user_text = speech_service.speech_to_text(file_path)
        
    except Exception as e:
        print(f"STT Error: {e}")
        # 因為要保留檔案供除錯或紀錄，這裡不刪除檔案
    
    # 注意：這裡移除了 finally { os.remove(...) } 區塊
            
    return {"text": user_text, "file_path": file_path}

def check_voice_command(text: str) -> Optional[str]:
    """
    檢查文字中是否包含下一題或退出的指令
    """
    if not text:
        return None

    # 移除空格與標點符號方便比對
    clean_text = text.replace(" ", "").replace("。", "").replace("！", "").replace("？", "")
    
    # 定義關鍵字清單
    exit_keywords = ["退出", "結束面試", "停止面試", "不面試了", "離開"]
    # 加入可能聽錯的諧音
    next_keywords = ["下一題", "跳過", "換一題", "下一個問題", "下一天", "恰一聽", "摘婷", "車題"] 
    
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
    session = SessionService.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # 2. 處理音檔 (STT) - 只呼叫一次！
    result = process_audio_file(session_id, audio_file)
    user_text = result["text"]
    saved_path = result["file_path"] # 這裡拿到了檔案路徑
    
    print(f"🎤 使用者說: {user_text}")
    if saved_path:
        print(f"💾 音檔已儲存: {saved_path}")

    # 3. 🔥 指令判斷邏輯
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

    # 4. 更新歷史紀錄 (儲存使用者的回答)
    if user_text:
        last_history = session.get('history', [])
        if last_history:
             last_history[-1]['answer'] = user_text
             # 如果你的 SessionService 支援存音檔路徑，可以在這裡加入
             # last_history[-1]['audio_path'] = saved_path

    # 5. 生成下一題 (AI)
    question_text = agent_service.generate_question(session_id)

    print(f"========================================")
    print(f" AI 生成的題目: {question_text}")
    print(f"========================================")
    
    if not question_text:
        return QuestionResponse(question_text="面試結束，感謝您的參與。", is_end=True)

    # 6. 存入新問題
    SessionService.add_history(session_id, question_text, "")

    # 7. 回傳結果
    return QuestionResponse(
        question_text=question_text,
        is_end=False
    )