import streamlit as st
import boto3
import json
import os
import io
from datetime import datetime
import time

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
    

#v2
js_code = """
<script>
let recognitionRef = { current: null };
let silenceTimer = null;
let isListening = false;
let restartTimer = null;
let finalTranscript = '';

// 等待 Streamlit 組件準備完成
function waitForStreamlit() {
    return new Promise((resolve) => {
        const checkStreamlit = () => {
            if (window.Streamlit) {
                resolve();
            } else {
                setTimeout(checkStreamlit, 100);
            }
        };
        checkStreamlit();
    });
}

function setListening(status) {
    isListening = status;
    document.getElementById('status').innerHTML = status ? '🎤 正在聆聽...' : '🛑 已暫停';
    document.getElementById('toggleBtn').textContent = status ? '停止錄音' : '開始錄音';
}

async function setTranscript(text) {
    document.getElementById('final').innerHTML = text;
    // 確保 Streamlit 已準備好
    if (text && text !== '空的') {
        try {
            await waitForStreamlit();
            window.Streamlit.setComponentValue(text);
        } catch (error) {
            console.error('Streamlit 通信錯誤:', error);
        }
    }
}

// 開始語音辨識
async function startListening() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        alert("此瀏覽器不支援語音辨識 😢");
        return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "zh-TW";
    recognition.interimResults = true;
    recognition.continuous = true;

    recognition.onstart = () => {
        setListening(true);
        console.log("🎤 語音辨識已啟動");
    };

    recognition.onend = () => {
      setListening(false);
      console.log("🛑 語音辨識已結束");

      // 等一段時間後自動重啟（例如：1 秒）
      restartTimer = setTimeout(() => {
        console.log("🔄 自動重啟語音辨識...");
        startListening();
      }, 1000);
    };

    recognition.onresult = (event) => {
        // 清除之前的靜音計時器
        if (silenceTimer) {
            clearTimeout(silenceTimer);
        }

        let interimTranscript = '';
        
        // 累積所有的識別結果
        for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
                finalTranscript += transcript + ' ';
            } else {
                interimTranscript += transcript;
            }
        }

        // 顯示結果
        const displayText = finalTranscript + interimTranscript;
        if (displayText.trim() === "") {
            setTranscript("空的");
        } else {
            setTranscript(displayText.trim());
        }

        // 設置 2 秒靜音檢測
        silenceTimer = setTimeout(() => {
            console.log("⏱️ 2 秒未說話，暫停語音辨識");
            if (finalTranscript.trim()) {
                setTranscript(finalTranscript.trim());
            }
            stopListening();
        }, 2000);
    };

    recognition.onerror = (event) => {
        console.error("語音辨識錯誤:", event.error);
        setListening(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
}

// 停止語音辨識
function stopListening() {
    if (recognitionRef.current) {
        recognitionRef.current.stop();
        clearTimeout(silenceTimer);
        setListening(false);
        finalTranscript = ''; // 重置最終文字
    }
}

// 切換語音辨識
function toggleRecording() {
    if (!isListening) {
        finalTranscript = ''; // 開始新的錄音時重置文字
        startListening();
    } else {
        stopListening();
    }
}

// 確保 Streamlit 已加載
waitForStreamlit().then(() => {
    console.log('Streamlit 已準備就緒');
}).catch(error => {
    console.error('Streamlit 加載失敗:', error);
});
</script>

<div>
    <button id="toggleBtn" onclick="toggleRecording()">開始錄音</button>
    <div id="status">🛑 已暫停</div>
    <div>
        <p>識別結果：<span id="final"></span></p>
    </div>
</div>
"""

def main():
    
    # 使用 components.html 來注入 JavaScript 代碼
    st.components.v1.html(js_code, height=200)
    
    # 接收從 JavaScript 傳來的識別結果
    result = st.empty()
    
    if st.session_state.get("speech_result"):
        result.write(f"識別結果: {st.session_state.speech_result}")
    # 獲取 AI 回應
        with st.spinner('獲取 AI 回應中...'):
            ai_response = get_ai_response(st.session_state.speech_result)
            if ai_response:
                # 在右側列顯示 AI 回應
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




if __name__ == "__main__":
    main()
