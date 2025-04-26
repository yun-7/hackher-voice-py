fetch("http://localhost:5050/upload", {
  method: "POST",
  body: formData
})
async function uploadAudio() {
  const input = document.getElementById('audioInput');
  const file = input.files[0];
  if (!file) {
    alert("請選擇一個音訊檔案");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch("/upload", {
    method: "POST",
    body: formData,
  });

  const result = await response.json();

  if (response.ok) {
    document.getElementById("transcriptText").textContent = result.transcript;
    document.getElementById("aiResponseText").textContent = result.ai_response;

    // 播放 AI 回應語音
    const speechRes = await fetch("/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: result.ai_response }),
    });

    const blob = await speechRes.blob();
    const audioUrl = URL.createObjectURL(blob);
    const audioPlayer = document.getElementById("audioPlayer");
    audioPlayer.src = audioUrl;
    audioPlayer.play();
  } else {
    alert("處理失敗：" + result.error);
  }
}