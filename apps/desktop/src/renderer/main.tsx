import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import type {
  AudioDevice,
  HealthResponse,
  RecordingStatus,
  StopRecordingResponse,
  StructureResponse,
  TranscribeResponse,
  VoiceFinishResponse,
  VoicePreviewResponse,
  VoiceTranscribeResponse
} from "@liketypeless/shared";
import "./styles.css";

declare global {
  interface Window {
    liketypeless: {
      health: () => Promise<HealthResponse>;
      audioDevices: () => Promise<AudioDevice[]>;
      recordingStatus: () => Promise<RecordingStatus>;
      startRecording: () => Promise<RecordingStatus>;
      stopRecording: () => Promise<StopRecordingResponse>;
      transcribe: (filePath: string, provider?: string) => Promise<TranscribeResponse>;
      transcribeVoiceRecording: () => Promise<VoiceTranscribeResponse>;
      previewVoiceRecording: () => Promise<VoicePreviewResponse>;
      finishVoiceRecording: () => Promise<VoiceFinishResponse>;
      structure: (text: string) => Promise<StructureResponse>;
    };
  }
}

const sampleText =
  "\u55ef\u6211\u89c9\u5f97\u6211\u4eec\u4e0b\u4e00\u6b65\u5c31\u662f\u5148\u628a\u8fd9\u4e2a\u8bed\u97f3\u8f93\u5165\u7684\u6d41\u7a0b\u8dd1\u901a\uff0c\u7136\u540e\u7136\u540e\u518d\u53bb\u505a\u5212\u7ebf\u7ffb\u8bd1\uff0c\u554a\u4e2d\u95f4\u8981\u6ce8\u610f\u4e00\u4e0b\u5feb\u6377\u952e\u4e0d\u8981\u548c\u7cfb\u7edf\u51b2\u7a81\u3002";

function formatAudioLevel(value: number): string {
  return value.toFixed(4);
}

function App(): React.ReactElement {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [devices, setDevices] = useState<AudioDevice[]>([]);
  const [recordingStatus, setRecordingStatus] = useState<RecordingStatus | null>(null);
  const [lastRecording, setLastRecording] = useState<StopRecordingResponse | null>(null);
  const [lastTranscription, setLastTranscription] = useState<TranscribeResponse | null>(null);
  const [lastVoiceFinish, setLastVoiceFinish] = useState<VoiceFinishResponse | null>(null);
  const [lastVoiceTranscription, setLastVoiceTranscription] = useState<VoiceTranscribeResponse | null>(null);
  const [livePreview, setLivePreview] = useState<VoicePreviewResponse | null>(null);
  const [input, setInput] = useState(sampleText);
  const [result, setResult] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isRecordingActionRunning, setIsRecordingActionRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void Promise.all([
      window.liketypeless.health().then(setHealth),
      window.liketypeless.audioDevices().then(setDevices),
      window.liketypeless.recordingStatus().then(setRecordingStatus)
    ]).catch((unknownError: unknown) => {
      setError(unknownError instanceof Error ? unknownError.message : String(unknownError));
    });
  }, []);

  useEffect(() => {
    if (!recordingStatus?.isRecording || isLoading || isRecordingActionRunning) {
      setLivePreview(null);
      return;
    }

    let cancelled = false;
    let nextPreviewTimer: ReturnType<typeof setTimeout> | null = null;

    const refreshPreview = async (): Promise<void> => {
      try {
        const response = await window.liketypeless.previewVoiceRecording();
        if (!cancelled) {
          setLivePreview(response);
        }
      } catch (unknownError) {
        const message = unknownError instanceof Error ? unknownError.message : String(unknownError);
        if (!cancelled && !message.includes("Recording has not captured audio yet")) {
          setError(message);
        }
      } finally {
        if (!cancelled) {
          nextPreviewTimer = setTimeout(() => void refreshPreview(), 3000);
        }
      }
    };

    void refreshPreview();
    return () => {
      cancelled = true;
      if (nextPreviewTimer) {
        clearTimeout(nextPreviewTimer);
      }
    };
  }, [isLoading, isRecordingActionRunning, recordingStatus?.isRecording]);

  async function handleStructure(): Promise<void> {
    setIsLoading(true);
    setError(null);
    setResult("");

    try {
      const response = await window.liketypeless.structure(input);
      setResult(response.structuredText);
    } catch (unknownError) {
      setError(unknownError instanceof Error ? unknownError.message : String(unknownError));
    } finally {
      setIsLoading(false);
    }
  }

  async function handleStartRecording(): Promise<void> {
    setIsRecordingActionRunning(true);
    setError(null);
    setLastRecording(null);
    setLastTranscription(null);
    setLastVoiceFinish(null);
    setLastVoiceTranscription(null);

    try {
      setRecordingStatus(await window.liketypeless.startRecording());
    } catch (unknownError) {
      setError(unknownError instanceof Error ? unknownError.message : String(unknownError));
    } finally {
      setIsRecordingActionRunning(false);
    }
  }

  async function handleStopRecording(): Promise<void> {
    setIsRecordingActionRunning(true);
    setError(null);

    try {
      const response = await window.liketypeless.stopRecording();
      setLastRecording(response);
      setRecordingStatus(await window.liketypeless.recordingStatus());
    } catch (unknownError) {
      setError(unknownError instanceof Error ? unknownError.message : String(unknownError));
    } finally {
      setIsRecordingActionRunning(false);
    }
  }

  async function handleTranscribeLastRecording(provider?: string): Promise<void> {
    if (!lastRecording) {
      return;
    }

    setIsLoading(true);
    setError(null);
    setLastTranscription(null);

    try {
      const response = await window.liketypeless.transcribe(lastRecording.filePath, provider);
      setLastTranscription(response);
      setInput(response.text);
    } catch (unknownError) {
      setError(unknownError instanceof Error ? unknownError.message : String(unknownError));
    } finally {
      setIsLoading(false);
    }
  }

  async function handleFinishVoiceRecording(): Promise<void> {
    setIsLoading(true);
    setError(null);
    setLastTranscription(null);
    setResult("");

    try {
      const response = await window.liketypeless.finishVoiceRecording();
      setLastVoiceFinish(response);
      setInput(response.transcript);
      setResult(response.structuredText);
      setRecordingStatus(await window.liketypeless.recordingStatus());
      setLastRecording({
        filePath: response.audioFilePath,
        durationSeconds: response.durationSeconds,
        sampleRate: recordingStatus?.sampleRate ?? 16000,
        channels: recordingStatus?.channels ?? 1,
        audioRms: response.audioRms,
        audioPeak: response.audioPeak
      });
    } catch (unknownError) {
      setError(unknownError instanceof Error ? unknownError.message : String(unknownError));
    } finally {
      setIsLoading(false);
    }
  }

  async function handleTranscribeVoiceRecording(): Promise<void> {
    setIsLoading(true);
    setError(null);
    setLastTranscription(null);
    setLastVoiceFinish(null);
    setLastVoiceTranscription(null);
    setResult("");

    try {
      const response = await window.liketypeless.transcribeVoiceRecording();
      setLastVoiceTranscription(response);
      setInput(response.transcript);
      setRecordingStatus(await window.liketypeless.recordingStatus());
      setLastRecording({
        filePath: response.audioFilePath,
        durationSeconds: response.durationSeconds,
        sampleRate: recordingStatus?.sampleRate ?? 16000,
        channels: recordingStatus?.channels ?? 1,
        audioRms: response.audioRms,
        audioPeak: response.audioPeak
      });
    } catch (unknownError) {
      setError(unknownError instanceof Error ? unknownError.message : String(unknownError));
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <section className="intro">
        <div>
          <p className="eyebrow">MVP local loop</p>
          <h1>liketypeless</h1>
        </div>
        <div className="status-panel">
          <span className={health?.ollamaReachable ? "status-dot ok" : "status-dot"} />
          <span>{health ? `Ollama ${health.ollamaReachable ? "ready" : "offline"}` : "Checking API"}</span>
          <strong>{health?.defaultModel ?? "qwen3:8b"}</strong>
        </div>
      </section>

      <section className="workspace">
        <div className="section-heading">
          <label>Audio recording</label>
          <span>{devices.length} input device(s)</span>
        </div>
        <div className="button-row">
          <button
            type="button"
            onClick={handleStartRecording}
            disabled={isRecordingActionRunning || recordingStatus?.isRecording === true}
          >
            Start recording
          </button>
          <button
            className="secondary"
            type="button"
            onClick={handleStopRecording}
            disabled={isRecordingActionRunning || recordingStatus?.isRecording !== true}
          >
            Stop recording
          </button>
          <button
            className="secondary"
            type="button"
            onClick={handleFinishVoiceRecording}
            disabled={isLoading || recordingStatus?.isRecording !== true}
          >
            Stop + transcribe + structure
          </button>
          <button
            className="secondary"
            type="button"
            onClick={handleTranscribeVoiceRecording}
            disabled={isLoading || recordingStatus?.isRecording !== true}
          >
            Stop + fast transcribe
          </button>
          <button
            className="secondary"
            type="button"
            onClick={() => void handleTranscribeLastRecording()}
            disabled={isLoading || lastRecording === null}
          >
            Transcribe last with Whisper
          </button>
          <button
            className="secondary"
            type="button"
            onClick={() => void handleTranscribeLastRecording("local-sensevoice")}
            disabled={isLoading || lastRecording === null}
          >
            Transcribe last with SenseVoice
          </button>
        </div>
        <div className="recording-meta">
          <span>Status: {recordingStatus?.isRecording ? "recording" : "idle"}</span>
          <span>Sample rate: {recordingStatus?.sampleRate ?? 16000} Hz</span>
          <span>Channels: {recordingStatus?.channels ?? 1}</span>
        </div>
        {livePreview ? (
          <div className="live-preview" aria-live="polite">
            <div>
              <strong>Live preview</strong>
              <span>
                {livePreview.sttProvider} · {livePreview.sttElapsedMs} ms · {livePreview.durationSeconds.toFixed(1)} s
              </span>
            </div>
            <p>{livePreview.transcript || "Listening..."}</p>
          </div>
        ) : null}
        {devices.length > 0 ? (
          <ul className="device-list">
            {devices.map((device) => (
              <li key={device.id}>
                <strong>{device.name}</strong>
                <span>
                  {device.maxInputChannels} channel(s), {Math.round(device.defaultSampleRate)} Hz default
                </span>
              </li>
            ))}
          </ul>
        ) : null}
        {lastRecording ? (
          <pre className="file-output">
            {lastRecording.filePath}
            {"\n"}
            {lastRecording.durationSeconds.toFixed(2)} seconds
            {"\n"}
            RMS {formatAudioLevel(lastRecording.audioRms)} / Peak {formatAudioLevel(lastRecording.audioPeak)}
          </pre>
        ) : null}
        {lastTranscription ? (
          <pre className="file-output">
            {lastTranscription.provider} / {lastTranscription.model}
            {"\n"}
            STT {lastTranscription.sttElapsedMs} ms
            {"\n"}
            {lastTranscription.text}
          </pre>
        ) : null}
        {lastVoiceTranscription ? (
          <pre className="file-output">
            {lastVoiceTranscription.sttProvider} / {lastVoiceTranscription.sttModel}
            {"\n"}
            STT {lastVoiceTranscription.sttElapsedMs} ms / Total {lastVoiceTranscription.totalElapsedMs} ms
            {"\n"}
            RMS {formatAudioLevel(lastVoiceTranscription.audioRms)} / Peak{" "}
            {formatAudioLevel(lastVoiceTranscription.audioPeak)}
            {"\n"}
            {lastVoiceTranscription.transcript || "(empty transcript)"}
          </pre>
        ) : null}
        {lastVoiceFinish ? (
          <pre className="file-output">
            {lastVoiceFinish.sttProvider} / {lastVoiceFinish.sttModel}
            {"\n"}
            STT {lastVoiceFinish.sttElapsedMs} ms / Structure {lastVoiceFinish.llmElapsedMs} ms / Total{" "}
            {lastVoiceFinish.totalElapsedMs} ms
            {"\n"}
            RMS {formatAudioLevel(lastVoiceFinish.audioRms)} / Peak {formatAudioLevel(lastVoiceFinish.audioPeak)}
            {"\n"}
            {lastVoiceFinish.transcript || "(empty transcript)"}
          </pre>
        ) : null}
      </section>

      <section className="workspace">
        <label htmlFor="raw-text">Raw voice transcript</label>
        <textarea
          id="raw-text"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          spellCheck={false}
        />
        <button type="button" onClick={handleStructure} disabled={isLoading || input.trim().length === 0}>
          {isLoading ? "Structuring..." : "Structure locally"}
        </button>
      </section>

      <section className="workspace output">
        <label htmlFor="structured-text">Structured text</label>
        <textarea id="structured-text" value={result} readOnly placeholder="The structured result will appear here." />
      </section>

      {error ? <pre className="error">{error}</pre> : null}
    </main>
  );
}

createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
