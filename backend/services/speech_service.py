# speech_service.py

import azure.cognitiveservices.speech as speechsdk
from backend.config import settings
import time

class SpeechService:
    def __init__(self):
        # 設定 Azure 語音組態 (STT 需要)
        self.speech_config = speechsdk.SpeechConfig(
            subscription=settings.AZURE_SPEECH_KEY, 
            region=settings.AZURE_SPEECH_REGION
        )
        self.speech_config.speech_recognition_language = "zh-TW" # 設定辨識語言

    def speech_to_text(self, audio_file_path: str) -> str:
        """
        將 wav 音檔轉為文字 (STT)
        """
        # 設定音訊輸入來自檔案
        audio_config = speechsdk.audio.AudioConfig(filename=audio_file_path)
        
        # 建立辨識器
        speech_recognizer = speechsdk.SpeechRecognizer(
            speech_config=self.speech_config, 
            audio_config=audio_config
        )

        done = False
        all_results = []

        def stop_cb(evt):
            """回呼函式：當辨識結束時觸發"""
            print(f'CLOSING on {evt}')
            nonlocal done
            done = True

        def recognized_cb(evt):
            """回呼函式：每辨識出一句就觸發"""
            if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
                print(f'RECOGNIZED: {evt.result.text}')
                all_results.append(evt.result.text)

        # 連接事件
        speech_recognizer.recognized.connect(recognized_cb)
        speech_recognizer.session_stopped.connect(stop_cb)
        speech_recognizer.canceled.connect(stop_cb)

        print(f"正在辨識音檔 (連續模式): {audio_file_path}")
        speech_recognizer.start_continuous_recognition()

        # 等待辨識完成 (因為是讀檔案，Azure 會快速讀完)
        # 這裡用簡單的迴圈等待，配合超時機制避免卡死
        timeout_sec = 30  
        start_time = time.time()
        while not done:
            time.sleep(0.1)
            if time.time() - start_time > timeout_sec:
                print("STT Timeout: 強制停止")
                break
        
        # 停止辨識
        speech_recognizer.stop_continuous_recognition()
        
        # 組合所有句子
        final_text = "".join(all_results)
        return final_text
    
    