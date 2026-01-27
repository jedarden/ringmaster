/**
 * Custom hook for browser-based speech recognition using Web Speech API.
 * Provides a simple interface for voice-to-text transcription.
 */
import { useState, useCallback, useRef, useEffect } from "react";

// Type definitions for Web Speech API (not in standard lib)
interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}

interface SpeechRecognitionResultList {
  length: number;
  item(index: number): SpeechRecognitionResult;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionResult {
  length: number;
  item(index: number): SpeechRecognitionAlternative;
  [index: number]: SpeechRecognitionAlternative;
  isFinal: boolean;
}

interface SpeechRecognitionAlternative {
  transcript: string;
  confidence: number;
}

interface SpeechRecognitionErrorEvent extends Event {
  error: string;
  message: string;
}

interface SpeechRecognitionInterface extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
}

// Global types for webkit prefix
declare global {
  interface Window {
    SpeechRecognition?: new () => SpeechRecognitionInterface;
    webkitSpeechRecognition?: new () => SpeechRecognitionInterface;
  }
}

export interface UseSpeechRecognitionOptions {
  /** Language for recognition (default: "en-US") */
  lang?: string;
  /** Whether to return interim results (default: true) */
  interimResults?: boolean;
  /** Callback when transcription is received */
  onTranscript?: (transcript: string, isFinal: boolean) => void;
  /** Callback when an error occurs */
  onError?: (error: string) => void;
}

export interface UseSpeechRecognitionResult {
  /** Whether the browser supports speech recognition */
  isSupported: boolean;
  /** Whether currently listening */
  isListening: boolean;
  /** Current transcript (interim or final) */
  transcript: string;
  /** Error message if any */
  error: string | null;
  /** Start listening */
  startListening: () => void;
  /** Stop listening */
  stopListening: () => void;
  /** Clear transcript and error */
  reset: () => void;
}

export function useSpeechRecognition(
  options: UseSpeechRecognitionOptions = {}
): UseSpeechRecognitionResult {
  const {
    lang = "en-US",
    interimResults = true,
    onTranscript,
    onError,
  } = options;

  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);

  const recognitionRef = useRef<SpeechRecognitionInterface | null>(null);
  const isSupported = typeof window !== "undefined" &&
    (!!window.SpeechRecognition || !!window.webkitSpeechRecognition);

  // Initialize recognition on mount
  useEffect(() => {
    if (!isSupported) return;

    const SpeechRecognitionClass =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognitionClass) return;

    const recognition = new SpeechRecognitionClass();
    recognition.continuous = false;
    recognition.interimResults = interimResults;
    recognition.lang = lang;

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let finalTranscript = "";
      let interimTranscript = "";

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const text = result[0].transcript;
        if (result.isFinal) {
          finalTranscript += text;
        } else {
          interimTranscript += text;
        }
      }

      const fullTranscript = finalTranscript || interimTranscript;
      setTranscript(fullTranscript);
      onTranscript?.(fullTranscript, !!finalTranscript);
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      const errorMessage = getErrorMessage(event.error);
      setError(errorMessage);
      setIsListening(false);
      onError?.(errorMessage);
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognition.onstart = () => {
      setIsListening(true);
      setError(null);
    };

    recognitionRef.current = recognition;

    return () => {
      recognition.abort();
      recognitionRef.current = null;
    };
  }, [isSupported, lang, interimResults, onTranscript, onError]);

  const startListening = useCallback(() => {
    if (!recognitionRef.current || isListening) return;
    setTranscript("");
    setError(null);
    try {
      recognitionRef.current.start();
    } catch {
      // Already started, ignore
    }
  }, [isListening]);

  const stopListening = useCallback(() => {
    if (!recognitionRef.current || !isListening) return;
    recognitionRef.current.stop();
  }, [isListening]);

  const reset = useCallback(() => {
    setTranscript("");
    setError(null);
    if (isListening) {
      stopListening();
    }
  }, [isListening, stopListening]);

  return {
    isSupported,
    isListening,
    transcript,
    error,
    startListening,
    stopListening,
    reset,
  };
}

function getErrorMessage(error: string): string {
  switch (error) {
    case "no-speech":
      return "No speech detected. Please try again.";
    case "audio-capture":
      return "No microphone found. Please check your audio settings.";
    case "not-allowed":
      return "Microphone access denied. Please allow microphone access.";
    case "network":
      return "Network error occurred. Please check your connection.";
    case "aborted":
      return "Speech recognition was aborted.";
    case "language-not-supported":
      return "Language not supported.";
    case "service-not-allowed":
      return "Speech recognition service not allowed.";
    default:
      return `Speech recognition error: ${error}`;
  }
}
