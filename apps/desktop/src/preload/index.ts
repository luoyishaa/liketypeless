import { contextBridge, ipcRenderer } from "electron";
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

export type LikeTypelessApi = {
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

const api: LikeTypelessApi = {
  health: () => ipcRenderer.invoke("api:health") as Promise<HealthResponse>,
  audioDevices: () => ipcRenderer.invoke("api:audio-devices") as Promise<AudioDevice[]>,
  recordingStatus: () => ipcRenderer.invoke("api:recording-status") as Promise<RecordingStatus>,
  startRecording: () => ipcRenderer.invoke("api:start-recording") as Promise<RecordingStatus>,
  stopRecording: () => ipcRenderer.invoke("api:stop-recording") as Promise<StopRecordingResponse>,
  transcribe: (filePath: string, provider?: string) =>
    ipcRenderer.invoke("api:transcribe", filePath, provider) as Promise<TranscribeResponse>,
  transcribeVoiceRecording: () =>
    ipcRenderer.invoke("api:transcribe-voice-recording") as Promise<VoiceTranscribeResponse>,
  previewVoiceRecording: () => ipcRenderer.invoke("api:preview-voice-recording") as Promise<VoicePreviewResponse>,
  finishVoiceRecording: () => ipcRenderer.invoke("api:finish-voice-recording") as Promise<VoiceFinishResponse>,
  structure: (text: string) => ipcRenderer.invoke("api:structure", text) as Promise<StructureResponse>
};

contextBridge.exposeInMainWorld("liketypeless", api);
