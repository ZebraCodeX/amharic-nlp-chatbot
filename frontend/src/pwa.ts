/** Register the service worker so the web app is installable (PWA). */
export function registerServiceWorker(): void {
  if (typeof window === 'undefined' || !('serviceWorker' in navigator)) return;
  // Native shells (Capacitor) already bundle the app — no SW needed there.
  if (window.Capacitor?.isNativePlatform?.()) return;
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {
      /* offline shell is a bonus; ignore failures (e.g. dev server) */
    });
  });
}

export function isStandalone(): boolean {
  if (typeof window === 'undefined') return false;
  return (
    window.matchMedia?.('(display-mode: standalone)').matches ||
    (window.navigator as unknown as { standalone?: boolean }).standalone === true ||
    !!window.Capacitor?.isNativePlatform?.()
  );
}
