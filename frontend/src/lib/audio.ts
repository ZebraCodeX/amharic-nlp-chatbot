/** Browser audio helpers for the Zer voice conversation. */

export function base64ToBlobUrl(b64: string, mime = 'audio/wav'): string {
  const bytes = atob(b64);
  const arr = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i += 1) arr[i] = bytes.charCodeAt(i);
  return URL.createObjectURL(new Blob([arr], { type: mime }));
}

export interface Recorder {
  /** Resolves whenever recording ends — by silence, max duration, or stop(). */
  done: Promise<Blob>;
  stop(): Promise<Blob>;
  cancel(): void;
}

/** Best recording format this browser supports (iOS Safari uses audio/mp4). */
export function pickAudioMime(): { mime: string; ext: string } {
  const candidates: [string, string][] = [
    ['audio/webm;codecs=opus', 'webm'],
    ['audio/webm', 'webm'],
    ['audio/ogg;codecs=opus', 'ogg'],
    ['audio/mp4;codecs=mp4a.40.2', 'm4a'],
    ['audio/mp4', 'm4a'],
    ['audio/aac', 'aac'],
  ];
  const MR = (window as unknown as { MediaRecorder?: { isTypeSupported?: (t: string) => boolean } }).MediaRecorder;
  if (MR?.isTypeSupported) {
    for (const [mime, ext] of candidates) {
      try {
        if (MR.isTypeSupported(mime)) return { mime, ext };
      } catch {
        /* ignore */
      }
    }
  }
  return { mime: '', ext: 'm4a' }; // let the browser choose
}

/** Unlock audio + speech output on a user gesture (required on mobile). */
let _audioUnlocked = false;
export function unlockAudio(): void {
  if (_audioUnlocked) return;
  _audioUnlocked = true;
  try {
    const Ctx = (window as unknown as { AudioContext?: typeof AudioContext; webkitAudioContext?: typeof AudioContext });
    const C = Ctx.AudioContext || Ctx.webkitAudioContext;
    if (C) {
      const ctx = new C();
      const src = ctx.createBufferSource();
      src.buffer = ctx.createBuffer(1, 1, 22050);
      src.connect(ctx.destination);
      src.start(0);
      ctx.resume?.();
    }
  } catch {
    /* ignore */
  }
  try {
    const a = new Audio(
      'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA=',
    );
    a.volume = 0;
    a.play().catch(() => {});
  } catch {
    /* ignore */
  }
}

/**
 * Record the mic to webm/opus.
 * - `autoStopMs`: stop after this much silence once speech was heard (0 = never)
 * - `maxMs`: hard stop after this long
 */
export async function startRecording(autoStopMs = 0, maxMs = 15000): Promise<Recorder> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true },
  });
  const picked = pickAudioMime();
  const rec = picked.mime
    ? new MediaRecorder(stream, { mimeType: picked.mime })
    : new MediaRecorder(stream); // Safari: let it pick (audio/mp4)
  const mime = picked.mime || rec.mimeType || 'audio/webm';
  const chunks: BlobPart[] = [];
  rec.ondataavailable = (e) => {
    if (e.data.size) chunks.push(e.data);
  };

  let finished = false;
  let resolveDone: (b: Blob) => void = () => {};
  const done = new Promise<Blob>((res) => {
    resolveDone = res;
  });

  let raf = 0;
  let maxTimer = 0;
  let ctx: AudioContext | null = null;
  const silenceTimer = { id: 0 as number };

  const cleanup = () => {
    cancelAnimationFrame(raf);
    clearTimeout(maxTimer);
    clearTimeout(silenceTimer.id);
    stream.getTracks().forEach((t) => t.stop());
    ctx?.close().catch(() => {});
  };
  const finish = () => {
    if (finished) return;
    finished = true;
    cleanup();
    resolveDone(new Blob(chunks, { type: mime }));
  };
  rec.onstop = finish;

  rec.start(250);
  if (maxMs > 0) maxTimer = window.setTimeout(() => rec.state !== 'inactive' && rec.stop(), maxMs);

  if (autoStopMs > 0) {
    ctx = new AudioContext();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const data = new Uint8Array(analyser.frequencyBinCount);
    let spoke = false;
    const resetTimer = () => {
      clearTimeout(silenceTimer.id);
      silenceTimer.id = window.setTimeout(() => {
        if (spoke && rec.state !== 'inactive') rec.stop();
      }, autoStopMs);
    };
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i += 1) {
        const x = (data[i] - 128) / 128;
        sum += x * x;
      }
      const rms = Math.sqrt(sum / data.length);
      if (rms > 0.02) {
        spoke = true;
        resetTimer();
      }
      raf = requestAnimationFrame(tick);
    };
    resetTimer();
    tick();
  }

  return {
    done,
    stop: async () => {
      if (rec.state !== 'inactive') rec.stop();
      return done;
    },
    cancel() {
      if (rec.state !== 'inactive') rec.stop();
      cleanup();
      if (!finished) {
        finished = true;
        resolveDone(new Blob([], { type: mime }));
      }
    },
  };
}

/** Play an audio Blob once (used by the "test voice" button). */
export function playBlob(blob: Blob, onEnd?: () => void): void {
  const url = URL.createObjectURL(blob);
  const a = new Audio(url);
  const done = () => {
    URL.revokeObjectURL(url);
    onEnd?.();
  };
  a.onended = done;
  a.onerror = done;
  a.play().catch(done);
}

/** Speak with the browser voice; resolves when it finishes. */
export function speak(text: string, lang: 'am' | 'en', onEnd?: () => void): void {
  if (!('speechSynthesis' in window) || !text) {
    onEnd?.();
    return;
  }
  const u = new SpeechSynthesisUtterance(text);
  const target = lang === 'am' ? ['am', 'am-et'] : ['en-us', 'en-gb', 'en'];
  u.lang = lang === 'am' ? 'am-ET' : 'en-US';
  const voices = window.speechSynthesis.getVoices();
  const voice = voices.find((v) => target.some((t) => v.lang.toLowerCase().startsWith(t)));
  if (voice) u.voice = voice;
  u.onend = () => onEnd?.();
  u.onerror = () => onEnd?.();
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(u);
}

/** Which language is this text in? (Amharic Ge'ez vs English Latin) */
export function scriptLang(text: string): 'am' | 'en' | '' {
  const am = (text.match(/[\u1200-\u137f]/g) || []).length;
  const en = (text.match(/[a-z]/gi) || []).length;
  if (am && am >= en) return 'am';
  if (en) return 'en';
  return '';
}

/** One-shot browser speech recognition. Resolves with the transcript or ''. */
export function recognizeOnce(lang: string, maxMs = 12000): Promise<string> {
  const Ctor =
    (window as unknown as { SpeechRecognition?: unknown }).SpeechRecognition ||
    (window as unknown as { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition;
  if (!Ctor) return Promise.resolve('');
  return new Promise<string>((resolve) => {
    const rec = new (Ctor as new () => any)();
    rec.lang = lang;
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    let done = false;
    const finish = (t: string) => {
      if (done) return;
      done = true;
      try {
        rec.stop();
      } catch {
        /* ignore */
      }
      resolve(t);
    };
    rec.onresult = (e: any) => finish(String(e.results[0][0].transcript || ''));
    rec.onerror = () => finish('');
    rec.onend = () => finish('');
    try {
      rec.start();
    } catch {
      finish('');
    }
    window.setTimeout(() => finish(''), maxMs);
  });
}

/**
 * Recognize speech and decide its language: try Amharic first (this is an
 * Amharic app), then re-run in English if the transcript came back Latin-only.
 */
export async function recognizeDetected(
  mode: 'auto' | 'am' | 'en' = 'auto',
): Promise<{ text: string; lang: 'am' | 'en' }> {
  if (mode !== 'auto') {
    const text = await recognizeOnce(mode === 'am' ? 'am-ET' : 'en-US');
    return { text, lang: mode };
  }
  const first = await recognizeOnce('am-ET');
  const guess = scriptLang(first);
  if (first && (!guess || guess === 'en')) {
    const second = await recognizeOnce('en-US');
    if (second) return { text: second, lang: scriptLang(second) || 'en' };
  }
  return { text: first, lang: guess || 'am' };
}

export interface WakeWord {
  start(): void;
  stop(): void;
}

/** 'Hey Zer' wake word via the browser SpeechRecognition. */
export function createWakeWord(onWake: () => void): WakeWord | null {
  const Ctor =
    (window as unknown as { SpeechRecognition?: unknown }).SpeechRecognition ||
    (window as unknown as { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition;
  if (!Ctor) return null;

  const phrases = ['hey zer', 'hey z', 'heyz', 'ሄይ ዘር', 'ሃይ ዘር', 'ዘር'];
  const rec = new (Ctor as new () => {
    continuous: boolean;
    interimResults: boolean;
    lang: string;
    start(): void;
    stop(): void;
    onresult: ((e: { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
    onend: (() => void) | null;
  })();
  rec.continuous = true;
  rec.interimResults = true;
  rec.lang = 'en-US';
  let active = false;

  rec.onresult = (e) => {
    if (!active) return;
    for (let i = e.resultIndex; i < e.results.length; i += 1) {
      const text = String(e.results[i][0].transcript || '').toLowerCase();
      if (phrases.some((p) => text.includes(p))) {
        active = false;
        try {
          rec.stop();
        } catch {
          /* ignore */
        }
        onWake();
        return;
      }
    }
  };
  rec.onend = () => {
    if (active) {
      try {
        rec.start();
      } catch {
        /* ignore */
      }
    }
  };

  return {
    start() {
      active = true;
      try {
        rec.start();
      } catch {
        /* already started */
      }
    },
    stop() {
      active = false;
      try {
        rec.stop();
      } catch {
        /* ignore */
      }
    },
  };
}
