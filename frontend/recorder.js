let mediaRecorder;
    let socket;

    function startRecording() {
      socket = new WebSocket("ws://localhost:5050/ws");

      // WebSocket 打開後處理訊息
      socket.onopen = () => {
        console.log("✅ WebSocket connected!");
      };

      // 接收後端發送的轉錄結果
      socket.onmessage = (event) => {
        const transcription = event.data;
        console.log("🎤 Transcription result:", transcription);
        document.getElementById("transcriptionResult").textContent = transcription;  // 更新顯示的轉錄文本
      };

      // 開始錄音
      navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
        mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=pcm' });

        mediaRecorder.ondataavailable = (event) => {
          if (event.data.size > 0 && socket.readyState === WebSocket.OPEN) {
            socket.send(event.data);  // 將錄製的音訊數據傳送到 WebSocket
          }
        };

        mediaRecorder.start(250); // 每 250ms 傳一段音訊
      });
    }

    function stopRecording() {
      mediaRecorder.stop();
    
      // 等待錄音傳送完成後再關閉 WebSocket
      setTimeout(() => {
        if (socket && socket.readyState === WebSocket.OPEN) {
          socket.close();  // 確保連線正確關閉
        }
      }, 500);  // 暫時延遲 500ms 來確保所有音訊已經傳送完成
    }