export const DEFAULT_API_BASE_URL = "http://127.0.0.1:8716";
export const DEFAULT_OLLAMA_MODEL = "qwen3:8b";

export type StructureRequest = {
  text: string;
  model?: string;
};

export type StructureResponse = {
  model: string;
  originalText: string;
  structuredText: string;
};

export type TranslationResponse = {
  originalText: string;
  translatedText: string;
  model: string;
};

export type HealthResponse = {
  status: "ok";
  ollamaReachable: boolean;
  defaultModel: string;
};

export type AudioDevice = {
  id: number;
  name: string;
  maxInputChannels: number;
  defaultSampleRate: number;
};

export type RecordingStatus = {
  isRecording: boolean;
  startedAt: number | null;
  sampleRate: number;
  channels: number;
};

export type StartRecordingResponse = RecordingStatus;

export type StopRecordingResponse = {
  filePath: string;
  durationSeconds: number;
  sampleRate: number;
  channels: number;
  audioRms: number;
  audioPeak: number;
};

export type TranscriptSegment = {
  start: number;
  end: number;
  text: string;
};

export type TranscribeResponse = {
  provider: string;
  model: string;
  text: string;
  language: string;
  durationSeconds: number;
  sttElapsedMs: number;
  segments: TranscriptSegment[];
};

export type VoiceFinishResponse = {
  audioFilePath: string;
  durationSeconds: number;
  audioRms: number;
  audioPeak: number;
  transcript: string;
  structuredText: string;
  sttProvider: string;
  sttModel: string;
  llmModel: string;
  recordingStopElapsedMs: number;
  sttElapsedMs: number;
  llmElapsedMs: number;
  totalElapsedMs: number;
};

export type VoiceTranscribeResponse = {
  audioFilePath: string;
  durationSeconds: number;
  audioRms: number;
  audioPeak: number;
  transcript: string;
  sttProvider: string;
  sttModel: string;
  recordingStopElapsedMs: number;
  sttElapsedMs: number;
  totalElapsedMs: number;
};

export type VoicePreviewResponse = {
  durationSeconds: number;
  transcript: string;
  sttProvider: string;
  sttModel: string;
  sttElapsedMs: number;
};
