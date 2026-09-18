export interface VoicePrefs {
  voiceAm: string;
  voiceEn: string;
  rate: number;
  pitch: number;
  volume: number;
  gap: number;
}

// Neural voices by default (MMS for Amharic, Piper for English). If a provider
// is unavailable the server falls back automatically, so these are safe.
export const DEFAULT_VOICE: VoicePrefs = {
  voiceAm: 'mms:am',
  voiceEn: 'piper:en_US-amy-medium',
  rate: 150,
  pitch: 45,
  volume: 130,
  gap: 0,
};

const KEY = 'hisar.voice';

export function loadVoicePrefs(): VoicePrefs {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return { ...DEFAULT_VOICE, ...JSON.parse(raw) };
  } catch {
    /* ignore */
  }
  return { ...DEFAULT_VOICE };
}

export function saveVoicePrefs(prefs: VoicePrefs): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(prefs));
  } catch {
    /* ignore */
  }
}

/** Voice + tuning params to send for a given language. */
export function paramsFor(prefs: VoicePrefs, lang: 'am' | 'en') {
  return {
    voice: lang === 'am' ? prefs.voiceAm : prefs.voiceEn,
    rate: prefs.rate,
    pitch: prefs.pitch,
    volume: prefs.volume,
    gap: prefs.gap,
  };
}

/** Per-language voice params for a voice turn (language is detected server-side). */
export function turnParams(prefs: VoicePrefs) {
  return {
    voice_am: prefs.voiceAm,
    voice_en: prefs.voiceEn,
    rate: prefs.rate,
    pitch: prefs.pitch,
    volume: prefs.volume,
    gap: prefs.gap,
  };
}
