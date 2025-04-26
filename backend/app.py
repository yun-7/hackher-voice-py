import boto3
from flask import Flask, send_from_directory
from flask_sock import Sock
import uuid
import io
from amazon_transcribe.client import TranscribeStreamingClient

app = Flask(__name__)
sock = Sock(app)

transcribe = boto3.client(
    service_name='transcribe',
    region_name='us-west-2'
)
transcribe_streaming = TranscribeStreamingClient(region='us-west-2')

@app.route("/")
def index():
    return send_from_directory('../frontend', 'index.html')

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory('../frontend', path)

def start_transcription_stream(ws):
    try:
        # 需要先建立一個生成器來傳送音訊流
        def audio_stream_generator():
            while True:
                data = ws.receive()  # 逐步從 WebSocket 接收音訊數據
                if data is None:
                    break
                yield {
                    'AudioEvent': {
                        'AudioChunk': data
                    }
                }
        # 開始一個實時語音轉錄流
        stream = transcribe_streaming.start_stream_transcription(
            language_code='zh-TW',
            media_sample_rate_hz=16000,  # 根據實際情況調整樣本率
            media_encoding='pcm',  # 使用 'pcm' 格式
            AudioStream=audio_stream_generator()
        )

        # 處理實時返回的轉錄結果
        for event in stream['TranscriptResultStream']:
            if 'Transcript' in event:
                transcript = event['Transcript']['Results'][0]['Alternatives'][0]['Transcript']
                print(f"🎤 Transcription: {transcript}")
                ws.send(transcript)  # 發送轉錄結果給前端
    except Exception as e:
        print("Error with transcription:", e)


@sock.route('/ws')
def websocket_connection(ws):
    print("✅ WebSocket connected!")
    try:
        start_transcription_stream(ws)
    except Exception as e:
        print("Error processing WebSocket:", e)
    finally:
        print("Closing WebSocket")

if __name__ == "__main__":
    app.run(debug=True, port=5050)
