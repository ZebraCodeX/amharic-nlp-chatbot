# Packaging & distribution

ሕሳር ships three ways from one React codebase:

| Target | Tech | Artifact | Install |
| --- | --- | --- | --- |
| **Web / PWA** | Django + Vite build | — | Browser → “Install app” (Android, iOS, Windows, macOS, Linux) |
| **Android** | Capacitor | `Hisar.apk`, `Hisar.aab` | Sideload / Google Play |
| **iOS** | Capacitor | `.ipa` | App Store / TestFlight |
| **Windows** | Electron | `Hisar-Setup.exe` | Direct download / Microsoft Store |
| **macOS** | Electron | `Hisar.dmg` | Direct download / Mac App Store |
| **Linux** | Electron | `Hisar.AppImage`, `Hisar.deb` | Direct download / Snap / Flathub |

Everything is built by GitHub Actions. Pushing a tag like `v1.0.0` publishes all
artifacts to **GitHub Releases**
(`https://github.com/ZebraCodeX/amharic-nlp-chatbot/releases/latest`), so the
stable download URLs are:

```
…/releases/latest/download/Hisar.apk
…/releases/latest/download/Hisar.aab
…/releases/latest/download/Hisar-Setup.exe
…/releases/latest/download/Hisar.dmg
…/releases/latest/download/Hisar.AppImage
…/releases/latest/download/Hisar.deb
```

## App identity

| Thing | Value |
| --- | --- |
| App id / bundle id | `com.zebracodex.hisar` |
| Product name | `Hisar` (display name ሕሳር) |
| Backend API | `https://am-ai.fly.dev` |
| Privacy URL (stores) | `https://am-ai.fly.dev/privacy` |

The native/desktop apps **bundle the UI locally** and call the hosted Django API
(resolved at runtime — see `frontend/src/api/client.ts`). The backend allows
those origins via `CORS_ALLOW_ALL=1` in `fly.toml`.

## Build locally

```bash
# one-time
cd frontend && npm install
cd ../desktop && npm install

# React app bundle used by every native/desktop target (base "./")
cd frontend && npm run build:app          # → frontend/dist

# Android (needs Android SDK + JDK 21)
npx cap add android && npx cap sync android
cd android && ./gradlew assembleDebug      # → app/build/outputs/apk/debug/app-debug.apk

# iOS (needs macOS + Xcode)
npx cap add ios && npx cap sync ios && npx cap open ios

# Desktop installers (electron-builder)
cd ../desktop && npm run dist              # → desktop/release/
```

`npm run build` (no `:app`) is the **web** build → `backend/static/spa`, served
by Django/Fly.

## Signing & stores

### Android — Google Play
1. Create a keystore: `keytool -genkey -v -keystore hisar.keystore -alias hisar -keyalg RSA -keysize 2048 -validity 10000`.
2. Add repository secrets:
   `ANDROID_KEYSTORE_BASE64` (`base64 -w0 hisar.keystore`),
   `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`.
3. Push a tag; the `Android app` workflow signs `Hisar.aab`.
4. Upload the `.aab` in **Play Console → Production → Create release**.
   The debug `Hisar.apk` is installable for direct downloads/sideloading.

### iOS — App Store
1. Apple Developer Program membership; create an App ID `com.zebracodex.hisar`.
2. Export a distribution certificate + provisioning profile; add secrets
   `IOS_CERTIFICATE_BASE64`, `IOS_CERTIFICATE_PASSWORD`,
   `IOS_PROVISIONING_PROFILE_BASE64`, `IOS_TEAM_ID`, `IOS_KEYCHAIN_PASSWORD`.
3. The `iOS app` workflow currently builds an unsigned simulator app for
   validation. To produce a store `.ipa`, add the signing steps documented at
   the bottom of `.github/workflows/ios.yml`, then upload with Transporter /
   `xcrun altool` to App Store Connect.

### Windows
- The NSIS installer (`Hisar-Setup.exe`) works unsigned (SmartScreen warns).
- For a clean experience buy a code-signing certificate and set
  `win.certificateFile` / `certificatePassword` in `desktop/package.json`, or
  submit the installer to the **Microsoft Store** via Partner Center (MSIX
  packaging is also possible with `electron-builder --win msix`).

### macOS
- Unsigned `.dmg`s trigger Gatekeeper. For distribution, set `mac.identity`
  (Developer ID) and `mac.notarize` (Apple ID / API key) in
  `desktop/package.json` and run `electron-builder --mac`.

### Web / PWA
- Already installable: `manifest.webmanifest` + `sw.js` are served at the
  origin root by Django, and the header shows an **Install** button when the
  browser offers `beforeinstallprompt`.

## Microphone (voice chat “Hey Zer”)

Live voice conversation needs mic access on every target:

- **Web/PWA** — granted by the browser on `https://` (Fly). No setup.
- **Android** — CI adds `RECORD_AUDIO` + `MODIFY_AUDIO_SETTINGS` to
  `AndroidManifest.xml` after `cap add`. Capacitor's WebView prompts for the
  runtime permission.
- **iOS** — CI adds `NSMicrophoneUsageDescription` and
  `NSSpeechRecognitionUsageDescription` to `Info.plist` after `cap sync`.
- **Electron** — `desktop/main.cjs` allows the `media` permission; macOS builds
  set the same usage strings via `build.mac.extendInfo`.

## Assets
- App icons live in `frontend/public/` (`icon.svg`, `icon-192.png`, `icon-512.png`).
  Regenerate with `python3 tools/gen_icons.py`.
- Android/iOS icons are generated from these by `@capacitor/assets`
  (`npx capacitor-assets generate`) after `cap add`.
- Desktop icons come from `desktop/build/icon.png` (electron-builder derives
  `.ico`/`.icns`).

## Versioning
Bump `version` in `frontend/package.json` and `desktop/package.json`, then tag:
```bash
git tag v1.0.0 && git push origin v1.0.0
```

## Store submission checklist

The live backend is **https://am-ai.fly.dev**; the privacy policy is served at
**https://am-ai.fly.dev/privacy** (required by both stores). Nothing below can
be done from CI alone — it needs your store accounts and signing credentials.

### One-time setup
- [ ] Google Play Console account (one-off US$25) → creates the app under
      package `com.zebracodex.hisar`.
- [ ] Apple Developer Program (US$99/yr) → register App ID
      `com.zebracodex.hisar` in Certificates, Identifiers & Profiles.
- [ ] Generate the Android upload keystore and add the four repo secrets
      (see *Android — Google Play* above).
- [ ] Export the iOS distribution certificate + provisioning profile and add
      the five repo secrets (see *iOS — App Store* above).
- [ ] Push a `v*` tag so CI produces a **signed** `Hisar.aab` and `.ipa`.

### Store listing assets (same for both)
- [ ] App name and short/full description (Amharic + English).
- [ ] Feature graphic 1024×500 (Play) and 6.7"/+6.5" screenshots (both).
- [ ] App icon 512×512 (already in `frontend/public/`).
- [ ] Privacy policy URL: `https://am-ai.fly.dev/privacy`.
- [ ] Support contact (GitHub issues URL or an email).

### Google Play specifics
- [ ] **Data safety** form: account optional; if signed in, conversations,
      taught facts and translations are stored; audio is processed for speech
      recognition and **not** retained.
- [ ] Content rating questionnaire; declare the microphone permission
      (`RECORD_AUDIO`, added by `.github/workflows/android.yml`).
- [ ] Target API level / Play App Signing (upload the `.aab`, not the APK).
- [ ] Closed testing track first, then production rollout.

### App Store specifics
- [ ] **App Privacy** labels: *User Content* (conversations) and *Audio Data*
      (voice) collected only while using the feature; used for app
      functionality, not tracking.
- [ ] `NSMicrophoneUsageDescription` + `NSSpeechRecognitionUsageDescription`
      are already injected by `.github/workflows/ios.yml`.
- [ ] Export compliance: the app uses standard HTTPS (exempt encryption) — set
      `ITSAppUsesNonExemptEncryption = NO`.
- [ ] App Review notes: explain that the assistant answers offline and that
      live voice sends audio to the app's own server for transcription.
- [ ] Upload the `.ipa` with Transporter / `xcrun altool`, then TestFlight.

> **Naming:** the shipped product name is currently **Hisar** with bundle id
> `com.zebracodex.hisar`, while the assistant and docs call it **Zer (ዘር)**.
> Decide the public store name before submitting; changing it later means a new
> listing/identifier.

