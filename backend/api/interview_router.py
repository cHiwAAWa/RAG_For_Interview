# interview_router.py

import os
import shutil
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from backend.models.pydantic_models import QuestionResponse
from backend.services.session_service import SessionService
from backend.services.agent_service import AgentService
from backend.services.speech_service import SpeechService
from backend.config import settings

router = APIRouter()
agent_service = AgentService()
speech_service = SpeechService()

@router.post("/answer", response_model=QuestionResponse)
async def submit_answer(
    session_id: str = Form(...),    
    audio_file: UploadFile = File(None) 
):
    # 1. 驗證 Session
    session = SessionService.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    user_text = ""
    
    # 2. 處理音檔 (STT)
    if audio_file:
        temp_filename = f"temp_{session_id}.wav"
        temp_path = os.path.join(settings.AUDIO_DIR, temp_filename)
        
        try:
            with open(temp_path, "wb") as buffer:
                shutil.copyfileobj(audio_file.file, buffer)
            
            # 呼叫 Azure STT
            user_text = speech_service.speech_to_text(temp_path)
            
        except Exception as e:
            print(f"STT Error: {e}")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # 3. 記錄歷史
    if user_text:
        last_history = session['history']
        if last_history:
             last_history[-1]['answer'] = user_text
    
    # 4. 生成下一題 (AI)
    question_text = agent_service.generate_question(session_id)

    print(f"========================================")
    print(f" AI 生成的題目: {question_test}")
    print(f"========================================")
    
    if not question_text:
        return QuestionResponse(question_text="面試結束，感謝您的參與。", is_end=True)

    # 存入新問題
    SessionService.add_history(session_id, question_text, "")

    # 5. 回傳結果 (不包含音檔 URL，只有文字)
    return QuestionResponse(
        question_text=question_text,
        is_end=False
    )
