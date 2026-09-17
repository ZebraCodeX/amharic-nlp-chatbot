import type { CapacitorConfig } from '@capacitor/cli';

/**
 * Native shells (Android + iOS) bundle the `npm run build:app` output and talk
 * to the hosted Django API (resolved at runtime in src/api/client.ts).
 */
const config: CapacitorConfig = {
  appId: 'com.zebracodex.hisar',
  appName: 'Hisar',
  webDir: 'dist',
  server: {
    androidScheme: 'https',
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 900,
      backgroundColor: '#14532d',
      showSpinner: false,
    },
    StatusBar: {
      style: 'DARK',
      backgroundColor: '#14532d',
    },
  },
};

export default config;
