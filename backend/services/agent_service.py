# agent_service.py

import ollama
from typing import List, Optional
from backend.services.rag_service import RagService
from backend.services.session_service import SessionService

# 設定使用的模型
MODEL = "llama3.1:8b"

class BaseAgent:
    """基礎 Agent 類別"""
    def __init__(self, model=MODEL):
        self.model = model

    def run_llm(self, prompt, temperature=0.5):
        """呼叫 LLM，強制使用繁體中文"""
        full_prompt = f"""你必須使用繁體中文（台灣用語）回答，不可使用簡體中文。

{prompt}

請務必使用繁體中文回答。"""
        
        try:
            response = ollama.chat(
                model=self.model,
                messages=[
                    {'role': 'system', 'content': '你是台灣的專業面試官，只使用繁體中文（台灣用語）進行溝通。'},
                    {'role': 'user', 'content': full_prompt}
                ],
                options={'temperature': temperature, 'num_predict': 512}
            )
            result = response['message']['content'].strip()
            return self._convert_to_traditional(result)
        except Exception as e:
            print(f"LLM 呼叫錯誤: {e}")
            return None
    
    def _convert_to_traditional(self, text: str) -> str:
        """簡轉繁（常見字詞補強）"""
        conversions = {
            '什么': '什麼', '怎么': '怎麼', '这': '這', '那个': '那個',
            '个': '個', '为': '為', '过': '過', '么': '麼',
            '不仅': '不僅', '网络': '網路', '程序': '程式', '项目': '專案'
        }
        for simp, trad in conversions.items():
            text = text.replace(simp, trad)
        return text

class JobInferenceAgent(BaseAgent):
    """職位推斷 Agent"""
    def infer_job_title(self, resume_text: str, structured_resume: dict = None):
        """根據履歷推斷職位"""
        if structured_resume and 'job_title' in structured_resume:
            job_title = structured_resume.get('job_title', '').strip()
            if job_title and len(job_title) > 2:
                return job_title
        
        prompt = f"""根據以下履歷內容推斷應徵職位，只需回答職位名稱：

{resume_text[:400]}

應徵職位："""
        
        output = self.run_llm(prompt, temperature=0.1)
        if output and len(output) < 50:
            return output.strip().replace('應徵職位', '').replace('：', '').replace(':', '').strip()
        return "未知職位"

class KnowledgeBasedQuestionAgent(BaseAgent):
    """基於知識庫的問題生成 Agent"""
    
    def __init__(self, rag_engine):
        super().__init__()
        self.rag_engine = rag_engine
        self.max_retry = 2
    
    def generate_question(self, job: str, resume: str, history: list):
        """基於知識庫動態生成問題"""
        attempts = 0
        while attempts < self.max_retry:
            focus = self._determine_focus(len(history))
            
            # 從 RAG 檢索知識
            try:
                knowledge = self.rag_engine.get_relevant_knowledge(
                    query=f"{job} {focus}",
                    job_title=job,
                    top_k=2
                )
            except Exception as e:
                print(f"RAG 檢索失敗: {e}")
                knowledge = []
            
            knowledge_context = self._build_knowledge_context(knowledge)
            
            # 組裝歷史對話
            history_context = ""
            if history:
                recent = history[-2:]
                history_context = "\n過去對話：\n"
                for turn in recent:
                    history_context += f"Q: {turn['question']}\nA: {turn['answer']}\n---\n"
            
            prompt = f"""你是台灣的專業面試官，請根據知識點生成原創面試問題。

應徵職位：{job}
本輪考核重點：{focus}

相關知識參考：
{knowledge_context}

履歷摘要：{resume[:800]}
{history_context}

要求：
1. 僅生成一個問題，請勿使用編號列表 (如 1., 2. 等)
2. 基於知識點設計問題，但不要直接複製
3. 問題要具體、可評估
4. 適合口頭回答
5. 使用繁體中文（台灣用語）
6. 直接輸出問題，無前言
7. 問題要與之前的問題不同
8. 如果你檢視到履歷中的經驗或先前的回答是模糊、空泛、或用戶承認是假設性的，請設計一個更深入的追問，或將問題從「你做過什麼」轉向「你會怎麼做」。
9. 不要在面試中提及這是第幾輪面試

請生成面試問題："""
            
            # 隨機性隨重試增加
            temperature = 0.7 + (attempts * 0.1)
            question = self.run_llm(prompt, temperature=temperature)
            
            if not question:
                return "請簡述您的相關經驗。"
            
            # 檢查重複
            if len(history) == 0 or not self._is_duplicate(question, history):
                return question
            
            print(f"(問題重複，重試第 {attempts + 1} 次)")
            attempts += 1
        
        return question

    def _is_duplicate(self, new_q: str, history: list) -> bool:
        """簡單字面相似度檢查"""
        if not history:
            return False
        
        def get_tokens(text):
            return set(text.replace(" ", "").replace("？", "").replace("，", ""))

        new_tokens = get_tokens(new_q)
        for h in history[-3:]: # 只檢查最近 3 題
            old_tokens = get_tokens(h['question'])
            if not new_tokens or not old_tokens:
                continue
            
            intersection = new_tokens.intersection(old_tokens)
            union = new_tokens.union(old_tokens)
            similarity = len(intersection) / len(union)
            
            if similarity > 0.6: # 超過 60% 字元重疊視為重複
                return True
        return False
    
    def _determine_focus(self, count):
        focuses = [
            "應徵動機與自我介紹",
            "核心專案經驗",
            "技術深度與實作細節",
            "問題解決能力",
            "團隊協作與溝通"
        ]
        return focuses[count] if count < len(focuses) else "綜合能力評估"
    
    def _build_knowledge_context(self, knowledge_items):
        if not knowledge_items:
            return "(無特定知識參考)"
        
        parts = []
        for item in knowledge_items:
            if item.get('type') == 'skill':
                concepts = ', '.join(item.get('concepts', [])[:3])
                parts.append(f"技能：{item.get('area')} (概念: {concepts})")
            else:
                parts.append(f"維度：{item.get('dimension')}")
        return "\n".join(parts)


# === 對外服務入口 ===
class AgentService:
    def __init__(self):
        self.rag_engine = RagService()
        self.question_agent = KnowledgeBasedQuestionAgent(self.rag_engine)
        self.job_agent = JobInferenceAgent()

    def generate_question(self, session_id: str) -> Optional[str]:
        """產生下一道面試題目"""
        session = SessionService.get_session(session_id)
        if not session:
            print(f"錯誤：Session {session_id} 不存在")
            return None

        job = session['job_title']
        history = session['history']
        resume = session['resume_text']
        
        return self.question_agent.generate_question(job, resume, history)

    def infer_job(self, resume_text: str) -> str:
        """推斷職位"""
        return self.job_agent.infer_job_title(resume_text)