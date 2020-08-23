$(function() {
  // Convert text-to-speech
  $("#text-to-speech").on("click", function(e) {
    e.preventDefault();
    var ttsInput = document.getElementById("translation-result").value;
    var ttsVoice = document.getElementById("select-voice").value;
    var ttsRequest = { 'text': ttsInput, 'voice': ttsVoice }

    var xhr = new XMLHttpRequest();
    xhr.open('post', '/text-to-speech', true);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.responseType = "blob";
    xhr.onload = function(evt){
      if (xhr.status === 200) {
        audioBlob = new Blob([xhr.response], {type: "audio/mpeg"});
        audioURL = URL.createObjectURL(audioBlob);
        if (audioURL.length > 5){
          var audio = document.getElementById('audio');
          var source = document.getElementById('audio-source');
          source.src = audioURL;
          audio.load();
          audio.play();
        }else{
          console.log("An error occurred getting and playing the audio.")
        }
      }
    }
    xhr.send(JSON.stringify(ttsRequest));
  });
});