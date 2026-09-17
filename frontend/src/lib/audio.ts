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

/**
 * Record the mic to webm/opus.
 * - `autoStopMs`: stop after this much silence once speech was heard (0 = never)
 * - `maxMs`: hard stop after this long
 */
export async function startRecording(autoStopMs = 0, maxMs = 15000): Promise<Recorder> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true },
  });
  const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
    ? 'audio/webm;codecs=opus'
    : 'audio/webm';
  const rec = new MediaRecorder(stream, { mimeType: mime });
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
