# Platform support — web, mobile, desktop

One React codebase, three delivery targets, one Django API.

| | Web / PWA | Android (Capacitor) | iOS (Capacitor) | Windows/macOS/Linux (Electron) |
|---|---|---|---|---|
| Chat + conversations + accounts | ✅ | ✅ | ✅ | ✅ |
| Amharic Fidel keyboard | ✅ | ✅ | ✅ | ✅ |
| Voice (STT, Whisper) | ✅ | ✅ | ✅ | ✅ |
| Spoken replies (TTS) | ✅ | ✅ | ✅ (system voice; eSpeak via server) | ✅ |
| Live (continuous) conversation | ✅ | ✅ | ✅ | ✅ |
| Language auto-detection (am/en) | ✅ | ✅ | ✅ | ✅ |
| Translation review | ✅ | ✅ | ✅ | ✅ |
| Install offline shell | ✅ PWA | ✅ APK/Play | ✅ App Store | ✅ installers |

## How each platform is wired

- **API origin** (`frontend/src/api/client.ts`): same-origin on web; Electron
  injects `window.hisar.apiBase`; Capacitor (native) uses the hosted backend.
- **Audio capture format** (`lib/audio.ts`): picks the first supported codec —
  `audio/webm;codecs=opus` on Chromium/Firefox, **`audio/mp4` on iOS Safari** —
  and the filename extension follows the blob type. The server decodes both
  (ffmpeg/PyAV).
- **Autoplay**: `unlockAudio()` runs on the first tap so replies can play after
  an async fetch (mobile browsers block otherwise).
- **Safe areas**: `env(safe-area-inset-*)` pads the mobile bar, drawer, composer
  and toast for the iPhone notch / Android gesture bar.
- **Touch**: `touch-action: manipulation` on controls (no double-tap zoom),
  `-webkit-tap-highlight-color: transparent`, `overscroll-behavior: none`.
- **Permissions**: Android `RECORD_AUDIO`/`MODIFY_AUDIO_SETTINGS` (CI patches the
  manifest), iOS `NSMicrophoneUsageDescription` +
  `NSSpeechRecognitionUsageDescription`, Electron `media` handler.
- **CORS**: the native/desktop origins are allowed (`CORS_ALLOW_ALL=1` on Fly).
- **Storage**: auth token + voice prefs in `localStorage`; conversations/memories
  server-side in SQLite on the persistent volume.

## Verify

```bash
make test                       # DRF (43) + brain (85) + keyboard smoke (21)
make frontend-build             # web bundle → backend/static/spa
make frontend-app-build         # native/desktop bundle → frontend/dist
node --check desktop/main.cjs && node --check desktop/preload.cjs
cd frontend && npx cap sync     # after `cap add android|ios` once
```

Manual checks worth doing on a real device:
1. **Web**: open the Fly URL → *Install app*; voice mic + Live; reload → still
   signed in; turn off the network → app shell still opens.
2. **Android** (APK): install, grant mic, run a Live turn, rotate the phone.
3. **iOS** (TestFlight): mic prompt appears, a Live turn records (`audio/mp4`),
   reply plays; notch not overlapping.
4. **Desktop**: install the app; mic permission prompt; window resize; copy/paste.

## Known limits

- The **offline brain is server-side** for chat; offline the installed app still
  opens (cached shell) with the keyboard/dictionary, and reconnects automatically.
- Amharic TTS quality depends on the server voice (MMS if enabled, else eSpeak)
  or the device voice when the server is unreachable.
- iOS/Android store submission needs your signing credentials (see PACKAGING.md).

## Release checklist

1. `make test` green.
2. `make frontend-build` and `make frontend-app-build` succeed.
3. `make deploy` (web) verified at https://hisar-amharic-ai.fly.dev.
4. `make release V=x.y.z` → CI builds APK/AAB, exe/dmg/AppImage/deb, iOS build,
   and publishes to GitHub Releases.
