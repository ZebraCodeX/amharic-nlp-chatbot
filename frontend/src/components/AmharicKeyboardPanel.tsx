import { useEffect, useRef, type MutableRefObject } from 'react';
import '../vendor/amharic-keyboard.js';
import '../vendor/amharic-keyboard.css';

declare global {
  interface Window {
    AmharicKeyboard?: any;
  }
}

interface Props {
  targetRef: MutableRefObject<HTMLInputElement | HTMLTextAreaElement | null>;
  open: boolean;
  onSubmit?: (text: string) => void;
  translateEnabled: () => boolean;
  translateFetch: (text: string) => Promise<string>;
}

/**
 * React wrapper around the reusable Amharic keyboard web component.
 * The keyboard manipulates the target element's value directly, so the host
 * keeps it uncontrolled and reads the value on submit.
 */
export function AmharicKeyboardPanel({
  targetRef,
  open,
  onSubmit,
  translateEnabled,
  translateFetch,
}: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const kbdRef = useRef<any>(null);
  const onSubmitRef = useRef(onSubmit);
  const enabledRef = useRef(translateEnabled);
  const fetchRef = useRef(translateFetch);

  onSubmitRef.current = onSubmit;
  enabledRef.current = translateEnabled;
  fetchRef.current = translateFetch;

  useEffect(() => {
    const container = hostRef.current;
    const input = targetRef.current;
    const AK = window.AmharicKeyboard;
    if (!container || !input || !AK) return;

    const kbd = new AK({
      container,
      input,
      dictUrl: '/api/words/',
      ngramUrl: '/api/ngram/',
      suggestUrl: '/api/suggest/',
      phonetic: false, // Amharic Fidel layout by default; toggle for phonetic
      storageKey: 'hisar.phonetic.react',
      onSubmit: (t: string) => onSubmitRef.current?.(t),
      translate: {
        enabled: () => enabledRef.current(),
        fetch: (t: string) => fetchRef.current(t),
      },
    });
    kbdRef.current = kbd;
    return () => {
      try {
        kbd.destroy();
      } catch {
        /* ignore */
      }
      kbdRef.current = null;
    };
  }, [targetRef]);

  useEffect(() => {
    const kbd = kbdRef.current;
    if (!kbd) return;
    if (open) kbd.open();
    else kbd.close();
  }, [open]);

  return <div className="kbd-panel" ref={hostRef} />;
}
