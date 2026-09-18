export interface ChatTurn {
  user?: string;
  reply?: string;
  source?: string;
  role?: string;
  content?: string;
}

export interface ChatReply {
  reply: string;
  source: string;
  confidence: number;
  lang?: string;
  followups?: string[];
  detail?: boolean;
  elapsed_ms?: number;
  conversation?: number;
}

export interface TranslateResult {
  translated: string;
  score: number;
  engine: string;
  verified: boolean;
  correction_id?: string;
  reasons?: string[];
  word_evidence?: unknown[];
  elapsed_ms?: number;
}

export type ReviewStatus = 'suggested' | 'verified' | 'corrected' | 'untranslated';

export interface ReviewItem {
  am: string;
  en: string;
  status: ReviewStatus;
  source: string;
  endorsed: number;
  verified: boolean;
  confidence: number;
  letter?: string | null;
}

export interface ReviewList {
  total: number;
  offset: number;
  limit: number;
  threshold: number;
  items: ReviewItem[];
}

export interface ReviewStats {
  total: number;
  verified: number;
  corrected: number;
  review: number;
  untranslated: number;
  glossary: number;
  threshold: number;
  low_confidence: number;
  high_confidence: number;
}

export interface LlmStatus {
  available: boolean;
  backend: string | null;
  model: string | null;
}

export interface VerifyResult {
  ok: boolean;
  id: string;
  corrected: string;
  endorsed: number;
}

export interface LetterCount {
  letter: string;
  count: number;
}

export interface User {
  id: number;
  username: string;
  email: string;
  display_name: string;
  name: string;
  date_joined?: string;
  conversations?: number;
  memories?: number;
}

export interface AuthPayload {
  token: string;
  user: User;
}

export interface Turn {
  id: number;
  role: 'user' | 'assistant';
  text: string;
  lang?: string;
  source?: string;
  created?: string;
}

export interface Conversation {
  id: number;
  title: string;
  lang?: string;
  created: string;
  updated: string;
  turn_count?: number;
  preview?: string;
  turns?: Turn[];
}

export interface MemoryItem {
  id: number;
  fact: string;
  created: string;
}

export interface VoiceOption {
  value: string;
  lang: string;
  label: string;
}

export interface VoiceSettings {
  voice?: string;
  rate?: number;
  pitch?: number;
  volume?: number;
  gap?: number;
}

export interface VoicesResponse {
  voices: VoiceOption[];
  defaults: Record<string, VoiceSettings>;
  ranges: Record<string, [number, number]>;
  engine: string;
}

export interface Health {
  status: string;
  llm?: LlmStatus;
  translations?: number;
}

export interface LearningStats {
  learned: number;
  recent: { am: string; en: string }[];
}

export interface LettersList {
  total?: number;
  count?: number;
  letters: LetterCount[];
}

export interface SpeechStatus {
  stt: { available: boolean; provider?: string; model?: string; languages?: string[] };
  tts: { available: boolean; espeak?: boolean; mms?: boolean; languages?: string[] };
}

export interface VoiceTurn {
  transcript: string;
  language: string;
  language_probability?: number;
  reply: string;
  source?: string;
  followups?: string[];
  stt_provider?: string;
  tts_provider?: string;
  audio_mime?: string;
  audio_b64?: string | null;
}
