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
  followups?: string[];
  detail?: boolean;
  elapsed_ms?: number;
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
