# resume_router.py

import os
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from backend.config import settings
from backend.services.resume_service import ResumeService
from backend.services.agent_service import AgentService
from backend.services.session_service import SessionService
from backend.models.pydantic_models import ResumeUploadResponse

router = APIRouter()
resume_service = ResumeService()
agent_service = AgentService()

@router.post("/upload", response_model=ResumeUploadResponse)
async def upload_resume(file: UploadFile = File(...)):
    # 1. 儲存上傳的檔案
    file_path = os.path.join(settings.UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    try:
        # 2. 解析履歷 (OCR + 結構化)
        processed_data = resume_service.process_resume(file_path)
        full_text = processed_data["full_text"]
        structured_data = processed_data["structured"]
        
        # 3. 推斷職位 (如果 OCR 沒抓到，就問 AI)
        job_title = structured_data.get("job_title")
        if not job_title:
            job_title = agent_service.infer_job(full_text)
            structured_data["job_title"] = job_title # 補回去
        
        # 4. 建立會話 (Session)
        session_id = SessionService.create_session(job_title, full_text)
        
        return ResumeUploadResponse(
            session_id=session_id,
            job_title=job_title,
            summary=full_text[:1000] + "...",
            structured_data=structured_data
        )
        
    except Exception as e:
        print(f"處理失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    