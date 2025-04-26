import streamlit as st
from streamlit_lottie import st_lottie
import boto3
import json
import os
import io
from datetime import datetime
import time

# 載入 Lottie 動畫
def load_lottiefile(filepath):
    with open(filepath, "r", encoding='utf-8') as f:
        return json.load(f)

happy_animation = load_lottiefile("fire smile.json")
sad_animation = load_lottiefile("fire cry.json")
neutral_animation = load_lottiefile("fire wait.json")
talk_animation = load_lottiefile("fire talk.json")
think_animation = load_lottiefile("fire think.json")

animations = {
    "happy": happy_animation,
    "sad": sad_animation,
    "neutral": neutral_animation,
    "talk" : talk_animation,
    "think" : think_animation,
}

# Streamlit 頁面配置
st.set_page_config(page_title="Voice Chat with AI", layout="wide")
st.title("Voice Chat with AI Assistant")

col_animation, col_chat = st.columns([1, 2]) # 調整比例，左側動畫佔 1/3，右側聊天佔 2/3

with col_animation:
    st.subheader("AI 狀態")
    selected_animation = st.selectbox("選擇動畫", ["neutral", "happy", "sad", "talk", "think"])
    if selected_animation in animations:
        st_lottie(animations[selected_animation], key="status_animation", height=300) # 可以調整高度


# 初始化 AWS clients
bedrock = boto3.client(
    service_name='bedrock-runtime',
    region_name='us-west-2'
)

transcribe = boto3.client(
    service_name='transcribe',
    region_name='us-west-2'
)

s3 = boto3.client(
    service_name='s3',
    region_name='us-west-2'
)

polly = boto3.client(
    service_name='polly',
    region_name='us-west-2'
)


def upload_to_s3(audio_file, bucket_name='hackher'):
    """上傳文件到 S3"""
    try:
        file_name = f"audio_{datetime.now().strftime('%Y%m%d%H%M%S')}.wav"
        s3.upload_fileobj(audio_file, bucket_name, file_name)
        return f"s3://{bucket_name}/{file_name}"
    except Exception as e:
        st.error(f"上傳到 S3 時發生錯誤: {str(e)}")
        return None

def process_audio(audio_file):
    # 上傳到 S3
    s3_uri = upload_to_s3(audio_file)
    if not s3_uri:
        return None
    
    # 開始轉錄任務
    try:
        job_name = f"transcribe_job_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        response = transcribe.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={'MediaFileUri': s3_uri},
            MediaFormat='wav',
            LanguageCode='zh-TW'
        )
        
        # 等待轉錄完成
        with st.spinner('轉錄進行中...'):
            while True:
                status = transcribe.get_transcription_job(TranscriptionJobName=job_name)
                if status['TranscriptionJob']['TranscriptionJobStatus'] in ['COMPLETED', 'FAILED']:
                    break
                time.sleep(2)
        
        if status['TranscriptionJob']['TranscriptionJobStatus'] == 'COMPLETED':
            transcript_uri = status['TranscriptionJob']['Transcript']['TranscriptFileUri']
            # 從 JSON 中獲取實際的轉錄文本
            import requests
            response = requests.get(transcript_uri)
            transcript_text = response.json()['results']['transcripts'][0]['transcript']
            return transcript_text
        else:
            st.error("轉錄失敗")
            return None
    except Exception as e:
        st.error(f"處理音頻時發生錯誤: {str(e)}")
        return None

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
        return response_body['content'][0]['text'] if 'content' in response_body else response_body['messages'][0]['content'][0]['text']
    
    except Exception as e:
        st.error(f"獲取 AI 回應時發生錯誤: {str(e)}")
        if 'response_body' in locals():
            if 'content' in response_body:
                return response_body['content'][0]['text']
            elif 'messages' in response_body:
                return response_body['messages'][0]['content'][0]['text']
        return None
def text_to_speech(text):
    """將文字轉換為語音"""
    try:
        response = polly.synthesize_speech(
            Text=text,
            OutputFormat='mp3',
            VoiceId='Zhiyu',  # 使用中文女聲
            LanguageCode='cmn-CN'  # 設置為中文
        )
        
        if "AudioStream" in response:
            # 將音頻流轉換為 bytes
            audio_stream = io.BytesIO(response['AudioStream'].read())
            return audio_stream
    except Exception as e:
        st.error(f"轉換語音時發生錯誤: {str(e)}")
        return None
    
# Streamlit UI 組件
st.sidebar.header("Controls")
audio_file = st.sidebar.file_uploader("Upload Audio File", type=['wav'])

# 主要內容區域
col1, col2 = st.columns(2)

with col1:
    st.header("Your Voice Input")
    if audio_file:
        st.audio(audio_file)
        
        # 處理音頻文件
        transcript = process_audio(audio_file)
        if transcript:
                    st.success("音頻處理完成！")
                    st.subheader("轉錄文字：")
                    st.text_area("", transcript, height=200)
                    
                    # 獲取 AI 回應
                    with st.spinner('獲取 AI 回應中...'):
                        ai_response = get_ai_response(transcript)
                        if ai_response:
                            # 在右側列顯示 AI 回應
                            with col2:
                                st.header("AI 回應")
                                st.text_area("", ai_response, height=400)
                                                            
                                # 自動將 AI 回應轉換為語音並播放
                                audio_stream = text_to_speech(ai_response)
                                if audio_stream:
                                    # 使用 base64 編碼的方式來自動播放
                                    import base64
                                    audio_bytes = audio_stream.getvalue()
                                    b64 = base64.b64encode(audio_bytes).decode()
                                    
                                    # 創建自動播放的 HTML audio 元素
                                    md = f"""
                                        <audio id="myAudio" autoplay="true">
                                            <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
                                        </audio>
                                        <script>
                                            var audio = document.getElementById("myAudio");
                                            audio.play();
                                        </script>
                                        """
                                    st.markdown(md, unsafe_allow_html=True)
                                    
                                    # 同時也顯示一個可控的播放器
                                    st.audio(audio_bytes)
                            
                                
                        else:
                            st.error("無法獲取 AI 回應")
# 添加使用說明
st.markdown("""
### 使用說明:
1. 在側邊欄上傳語音檔案（WAV 格式）
2. 等待轉錄完成
3. 查看轉錄文字和 AI 回應
4. 聆聽 AI 的語音回應
""")