from datetime import datetime
import asyncio
import json
import os
import time
import pyaudio
import sys
import boto3
import sounddevice
from concurrent.futures import ThreadPoolExecutor
from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent, TranscriptResultStream
import streamlit as st
from io import BytesIO
import nest_asyncio
import threading

# 初始化 nest_asyncio
nest_asyncio.apply()

# Streamlit 頁面配置
st.set_page_config(page_title="Voice Chat with AI", layout="wide")
st.title("Voice Chat with AI Assistant")

# 初始化 AWS clients
bedrock = boto3.client(
    service_name='bedrock-runtime',
    region_name='us-west-2'
)

polly = boto3.client(
    service_name='polly',
    region_name='us-west-2'
)

# 創建自定義的 TranscriptResultStreamHandler
class MyTranscriptResultStreamHandler(TranscriptResultStreamHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.result = []
        
    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        results = transcript_event.transcript.results
        for result in results:
            if not result.is_partial:
                self.result.append(result.alternatives[0].transcript)

async def mic_stream():
    # 設置音頻參數
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    
    # 初始化 PyAudio
    p = pyaudio.PyAudio()
    
    # 打開音頻流
    stream = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK
    )
    
    # 生成音頻數據
    while True:
        data = stream.read(CHUNK)
        yield data

async def write_chunks(stream):
    async for chunk in stream:
        yield {
            "AudioEvent": {
                "AudioChunk": chunk
            }
        }

async def basic_transcribe():
    # 初始化轉錄客戶端
    client = TranscribeStreamingClient(region="us-west-2")
    
    # 創建流
    stream = await client.start_stream_transcription(
        language_code="zh-TW",
        media_sample_rate_hz=16000,
        media_encoding="pcm"
    )
    
    # 設置處理器
    handler = MyTranscriptResultStreamHandler(stream.output_stream)
    
    # 開始處理
    await asyncio.gather(
        write_chunks(mic_stream()),
        handler.handle_events()
    )
    
    return handler.result

def get_ai_response(input_text):
    try:
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": input_text
                        }
                    ]
                }
            ],
            "temperature": 0.7,
            "top_p": 0.9,
        })
        
        response = bedrock.invoke_model(
            modelId='anthropic.claude-3-haiku-20240307-v1:0',
            body=body
        )
        
        response_body = json.loads(response.get('body').read())
        return response_body['content'][0]['text']
    except Exception as e:
        st.error(f"獲取 AI 回應時發生錯誤: {str(e)}")
        return None

def text_to_speech(text):
    try:
        response = polly.synthesize_speech(
            Text=text,
            OutputFormat='mp3',
            VoiceId='Zhiyu',
            LanguageCode='cmn-CN'
        )
        
        if "AudioStream" in response:
            audio_stream = BytesIO(response['AudioStream'].read())
            return audio_stream
    except Exception as e:
        st.error(f"轉換語音時發生錯誤: {str(e)}")
        return None

def run_async_transcribe():
    # 在新線程中創建事件循環
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(basic_transcribe())
    finally:
        loop.close()

# 創建兩個列來顯示內容
col1, col2 = st.columns(2)

# 在左側列顯示錄音和轉錄部分
with col1:
    st.header("語音輸入")
    if st.button("開始錄音"):
        with st.spinner("正在聆聽..."):
            # 在新線程中運行異步代碼
            with ThreadPoolExecutor() as executor:
                future = executor.submit(run_async_transcribe)
                result = future.result()
                
                if result:
                    transcript = " ".join(result)
                    st.text_area("轉錄文字：", transcript, height=200)
                    
                    # 獲取 AI 回應
                    with st.spinner('獲取 AI 回應中...'):
                        ai_response = get_ai_response(transcript)
                        if ai_response:
                            with col2:
                                st.header("AI 回應")
                                st.text_area("", ai_response, height=400)
                                
                                # 轉換為語音並播放
                                audio_stream = text_to_speech(ai_response)
                                if audio_stream:
                                    st.audio(audio_stream, format='audio/mp3')

# 添加使用說明
st.markdown("""
### 使用說明:
1. 點擊「開始錄音」按鈕開始錄音
2. 說話（系統會自動轉錄）
3. 等待 AI 回應
4. 聆聽 AI 的語音回應
""")

