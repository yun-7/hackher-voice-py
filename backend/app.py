# app.py
from flask import Flask, request, jsonify, send_file
import boto3
import json
import io
import time
from datetime import datetime
import requests
from flask import send_from_directory

app = Flask(__name__)


# AWS Clients
region = 'us-west-2'
bedrock = boto3.client('bedrock-runtime', region_name=region)
transcribe = boto3.client('transcribe', region_name=region)
s3 = boto3.client('s3', region_name=region)
polly = boto3.client('polly', region_name=region)

BUCKET_NAME = 'hackher'

def upload_to_s3(audio_file):
    file_name = f"audio_{datetime.now().strftime('%Y%m%d%H%M%S')}.wav"
    s3.upload_fileobj(audio_file, BUCKET_NAME, file_name)
    return f"s3://{BUCKET_NAME}/{file_name}", file_name

def transcribe_audio(s3_uri, job_name):
    transcribe.start_transcription_job(
        TranscriptionJobName=job_name,
        Media={'MediaFileUri': s3_uri},
        MediaFormat='wav',
        LanguageCode='zh-TW'
    )

    while True:
        status = transcribe.get_transcription_job(TranscriptionJobName=job_name)
        job_status = status['TranscriptionJob']['TranscriptionJobStatus']
        if job_status in ['COMPLETED', 'FAILED']:
            break
        time.sleep(2)

    if job_status == 'COMPLETED':
        transcript_url = status['TranscriptionJob']['Transcript']['TranscriptFileUri']
        response = requests.get(transcript_url)
        return response.json()['results']['transcripts'][0]['transcript']
    return None

def get_ai_response(text):
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": [{"type": "text", "text": text}]}],
        "temperature": 0.7,
        "top_p": 0.9
    })

    response = bedrock.invoke_model(
        modelId='anthropic.claude-3-haiku-20240307-v1:0',
        body=body
    )

    response_body = json.loads(response['body'].read())
    return response_body['content'][0]['text']

def synthesize_speech(text):
    response = polly.synthesize_speech(
        Text=text,
        OutputFormat='mp3',
        VoiceId='Zhiyu',
        LanguageCode='cmn-CN'
    )
    return io.BytesIO(response['AudioStream'].read())

@app.route('/upload', methods=['POST'])
def handle_upload():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    s3_uri, job_name = upload_to_s3(file)
    transcript = transcribe_audio(s3_uri, job_name)

    if not transcript:
        return jsonify({"error": "Transcription failed"}), 500

    ai_reply = get_ai_response(transcript)
    audio_stream = synthesize_speech(ai_reply)

    return jsonify({
        "transcript": transcript,
        "ai_response": ai_reply
    })

@app.route('/speak', methods=['POST'])
def speak():
    data = request.get_json()
    text = data.get("text")
    if not text:
        return jsonify({"error": "No text provided"}), 400

    audio_stream = synthesize_speech(text)
    return send_file(audio_stream, mimetype="audio/mp3", as_attachment=False)

@app.route('/')
def serve_frontend():
    return send_from_directory('.', '../frontend/index.html')

if __name__ == '__main__':
    app.run(debug=True, port=5050)