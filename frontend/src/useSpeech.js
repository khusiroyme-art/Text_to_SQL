import { useCallback, useEffect, useRef, useState } from "react";

// The Web Speech API is prefixed in Chrome/Edge and absent in Firefox, so
// `supported` is exported and the button is hidden rather than shown broken.
// Everything here is browser-side: no audio is ever sent to our backend.
const Recognition =
  typeof window !== "undefined"
    ? window.SpeechRecognition || window.webkitSpeechRecognition
    : null;

export function useSpeech(onTranscript) {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState(null);
  const recognitionRef = useRef(null);
  // Kept in a ref so restarting recognition never rebinds a stale callback.
  const callbackRef = useRef(onTranscript);
  callbackRef.current = onTranscript;

  useEffect(() => {
    if (!Recognition) return undefined;
    const recognition = new Recognition();
    recognition.lang = "en-US";
    recognition.interimResults = true;
    recognition.continuous = false;

    recognition.onresult = (event) => {
      // Concatenate every chunk: the API delivers a growing result list, and
      // reading only the last one drops the start of a longer question.
      const transcript = Array.from(event.results)
        .map((r) => r[0].transcript)
        .join("")
        .trim();
      if (transcript) callbackRef.current(transcript);
    };
    recognition.onerror = (event) => {
      setError(
        event.error === "not-allowed"
          ? "Microphone permission was denied."
          : `Speech recognition failed (${event.error}).`
      );
      setListening(false);
    };
    // Fires on silence as well as on stop(), so this is the only place that
    // clears the listening flag on the happy path.
    recognition.onend = () => setListening(false);

    recognitionRef.current = recognition;
    return () => {
      recognition.onresult = null;
      recognition.onerror = null;
      recognition.onend = null;
      recognition.abort();
    };
  }, []);

  const toggle = useCallback(() => {
    const recognition = recognitionRef.current;
    if (!recognition) return;
    if (listening) {
      recognition.stop();
      return;
    }
    setError(null);
    try {
      recognition.start();
      setListening(true);
    } catch {
      // start() throws if it is already running - harmless, and recovering is
      // better than surfacing it.
      setListening(false);
    }
  }, [listening]);

  return { supported: Boolean(Recognition), listening, error, toggle };
}
