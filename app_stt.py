import streamlit as st
import boto3
import json
import os
import io
import base64
from datetime import datetime
import time
from botocore.exceptions import ClientError
import streamlit.components.v1 as components
import logging


# Streamlit 頁面配置
st.set_page_config(page_title="Voice Chat with AI", layout="wide")
st.title("Voice Chat with AI Assistant")

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

# 設定日誌
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

try:
    # 測試 S3 連接
    s3.list_buckets()
    logger.info("Successfully connected to S3")
except Exception as e:
    logger.error(f"Failed to initialize S3 client: {str(e)}")
    st.error("S3 連接失敗")


def upload_to_s3(audio_file, bucket_name='voice20250419'):
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
    
def save_audio_file(base64_audio):
    """將 base64 音頻數據保存為檔案"""
    try:
        # 創建保存錄音的目錄
        audio_dir = "recorded_audio"
        if not os.path.exists(audio_dir):
            os.makedirs(audio_dir)
        
        # 生成檔案名稱
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join(audio_dir, f"recording_{timestamp}.wav")
        
        # 解碼 base64 數據並保存檔案
        audio_bytes = base64.b64decode(base64_audio)
        st.audio(audio_bytes, format='audio/wav')
        with open(file_path, "wb") as f:
            f.write(audio_bytes)
        
        return file_path
    except Exception as e:
        st.error(f"保存音頻檔案時發生錯誤: {str(e)}")
        return None
def get_audio_recorder_html():
    return """
        <div>
            <button id="startRecord">開始錄音</button>
            <button id="stopRecord" disabled>停止錄音</button>
            <div id="recordingStatus"></div>
        </div>
        <script>
            let mediaRecorder;
            let audioChunks = [];
            
            const startButton = document.getElementById('startRecord');
            const stopButton = document.getElementById('stopRecord');
            const statusDiv = document.getElementById('recordingStatus');
            
            startButton.addEventListener('click', async () => {
                audioChunks = [];
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ 
                        audio: {
                            channelCount: 1,
                            sampleRate: 16000
                        } 
                    });
                    
                    mediaRecorder = new MediaRecorder(stream);
                    
                    mediaRecorder.ondataavailable = (event) => {
                        audioChunks.push(event.data);
                        console.log("Received audio chunk");
                    };
                    
                    mediaRecorder.onstop = async () => {
                        const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                        console.log("Audio blob created, size:", audioBlob.size);
                        
                        const reader = new FileReader();
                        reader.readAsDataURL(audioBlob);
                        reader.onloadend = () => {
                            const base64Audio = reader.result.split(',')[1];
                            console.log("Sending audio data, length:", base64Audio.length);
                            
                            // 發送到 Streamlit
                            window.parent.postMessage({
                                type: 'streamlit:set_component_value',
                                data: {
                                    audio_data: base64Audio
                                }
                            }, '*');
                            
                            statusDiv.textContent = '音頻數據已發送';
                        };
                    };
                    
                    mediaRecorder.start();
                    startButton.disabled = true;
                    stopButton.disabled = false;
                    statusDiv.textContent = '錄音中...';
                    
                } catch (err) {
                    console.error('錄音出錯:', err);
                    statusDiv.textContent = '無法啟動錄音: ' + err.message;
                }
            });
            
            stopButton.addEventListener('click', () => {
                mediaRecorder.stop();
                startButton.disabled = false;
                stopButton.disabled = true;
                statusDiv.textContent = '錄音已完成，處理中...';
            });
        </script>
    """


def save_audio_to_s3(base64_audio, bucket_name='voice20250419'):
    """將音頻數據保存到 S3"""
    try:
        # 檢查輸入數據
        if not base64_audio:
            st.error("沒有收到音頻數據")
            logger.error("base64_audio is empty or None")
            return None, None
            
        # 生成檔案名稱
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"recording_{timestamp}.wav"
        
        logger.info(f"Processing audio data, length: {len(base64_audio)}")
        
        # 解碼 base64 數據
        try:
            audio_bytes = base64.b64decode(base64_audio)
            logger.info(f"Successfully decoded audio data, size: {len(audio_bytes)} bytes")
        except Exception as e:
            st.error("Base64 解碼失敗")
            logger.error(f"Base64 decoding error: {str(e)}")
            return None, None
        
        # 檢查音頻數據大小
        if len(audio_bytes) == 0:
            st.error("音頻數據為空")
            logger.error("Audio bytes is empty")
            return None, None
            
        logger.info(f"Attempting to upload to bucket: {bucket_name}")
        logger.info(f"File name: recordings/{file_name}")
        
        # 上傳到 S3
        try:
            response = s3.put_object(
                Bucket=bucket_name,
                Key=f"recordings/{file_name}",
                Body=audio_bytes,
                ContentType='audio/wav'
            )
            logger.info(f"S3 upload response: {response}")
            
            s3_url = f"s3://{bucket_name}/recordings/{file_name}"
            st.success(f"檔案已成功上傳到 S3: {s3_url}")
            return s3_url, file_name
            
        except Exception as e:
            logger.error(f"S3 upload error: {str(e)}")
            st.error(f"S3 上傳失敗: {str(e)}")
            return None, None
            
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        st.error(f"發生未預期的錯誤: {str(e)}")
        return None, None

def get_audio_recorder_html():
    return """
        <div>
            <button id="startRecord">開始錄音</button>
            <button id="stopRecord" disabled>停止錄音</button>
            <div id="recordingStatus"></div>
        </div>
        <script>
            let mediaRecorder;
            let audioChunks = [];
            
            const startButton = document.getElementById('startRecord');
            const stopButton = document.getElementById('stopRecord');
            const statusDiv = document.getElementById('recordingStatus');
            
            startButton.addEventListener('click', async () => {
                audioChunks = [];
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ 
                        audio: {
                            channelCount: 1,
                            sampleRate: 16000
                        } 
                    });
                    
                    mediaRecorder = new MediaRecorder(stream);
                    
                    mediaRecorder.ondataavailable = (event) => {
                        audioChunks.push(event.data);
                        console.log("Received audio chunk");
                    };
                    
                    mediaRecorder.onstop = async () => {
                        const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                        console.log("Audio blob created, size:", audioBlob.size);
                        
                        const reader = new FileReader();
                        reader.readAsDataURL(audioBlob);
                        reader.onloadend = () => {
                            const base64Audio = reader.result.split(',')[1];
                            console.log("Sending audio data, length:", base64Audio.length);
                            
                            // 發送到 Streamlit
                            window.parent.postMessage({
                                type: 'streamlit:set_component_value',
                                data: {
                                    audio_data: base64Audio
                                }
                            }, '*');
                            
                            statusDiv.textContent = '音頻數據已發送';
                            console.log("Audio data sent to Streamlit");
                        };
                    };
                    
                    mediaRecorder.start();
                    startButton.disabled = true;
                    stopButton.disabled = false;
                    statusDiv.textContent = '錄音中...';
                    
                } catch (err) {
                    console.error('錄音出錯:', err);
                    statusDiv.textContent = '無法啟動錄音: ' + err.message;
                }
            });
            
            stopButton.addEventListener('click', () => {
                mediaRecorder.stop();
                startButton.disabled = false;
                stopButton.disabled = true;
                statusDiv.textContent = '錄音已完成，處理中...';
            });
        </script>
    """

# Streamlit 主程式
def main():
    st.title("語音錄製")
    
    # 添加錄音組件
    components.html(get_audio_recorder_html(), height=150)
    
    # 使用 session_state 來存儲音頻數據
    if 'audio_data' not in st.session_state:
        st.session_state.audio_data = None
    
    # 當收到音頻數據時
    if st.session_state.audio_data:
        logger.info("Received audio data in session state")
        logger.info(f"Audio data length: {len(st.session_state.audio_data)}")
        
        # 顯示接收到的數據大小
        st.write(f"接收到的音頻數據大小: {len(st.session_state.audio_data)} bytes")
        
        s3_url, file_name = save_audio_to_s3(st.session_state.audio_data)
        
        if s3_url and file_name:
            st.success(f"錄音已上傳至: {s3_url}")
            
            # 顯示音頻播放器
            try:
                audio_bytes = base64.b64decode(st.session_state.audio_data)
                st.audio(audio_bytes, format='audio/wav')
            except Exception as e:
                logger.error(f"Error playing audio: {str(e)}")
                st.error("音頻播放失敗")
        else:
            st.error("音頻上傳失敗")

if __name__ == "__main__":
    main()

# 添加回調來接收音頻數據
components.html(
    """
    <script>
    window.addEventListener('message', function(e) {
        if (e.data.type === 'streamlit:set_component_value') {
            console.log('Received data in callback:', e.data);
        }
    });
    </script>
    """,
    height=0
)


