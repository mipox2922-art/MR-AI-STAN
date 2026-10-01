import { useEffect, useRef, useState } from "react";

export default function VoiceControl({ onTranscript, disabled = false }) {
  const recognitionRef = useRef(null);
  const [state, setState] = useState("IDLE");
  const [supported, setSupported] = useState(true);

  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setSupported(false);
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "sw-TZ";
    recognition.interimResults = false;
    recognition.continuous = false;

    recognition.onstart = () => setState("LISTENING");
    recognition.onend = () => setState("IDLE");
    recognition.onerror = () => setState("ERROR");
    recognition.onresult = (event) => {
      const transcript = event.results?.[0]?.[0]?.transcript?.trim();
      if (transcript) onTranscript(transcript);
    };

    recognitionRef.current = recognition;
    return () => recognition.abort();
  }, [onTranscript]);

  const toggle = () => {
    if (disabled || !supported) return;
    try {
      if (state === "LISTENING") recognitionRef.current?.stop();
      else recognitionRef.current?.start();
    } catch {
      setState("ERROR");
    }
  };

  if (!supported) {
    return <div className="voice-disabled">VOICE API HAIPATIKANI KWENYE BROWSER HII</div>;
  }

  return (
    <button className={`voice-button voice-${state.toLowerCase()}`} onClick={toggle} disabled={disabled}>
      <span className="voice-orb">🎙</span>
      <span>{state === "LISTENING" ? "NASIKILIZA..." : "VOICE COMMAND"}</span>
    </button>
  );
}
