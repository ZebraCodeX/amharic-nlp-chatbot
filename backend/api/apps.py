import os

from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'
    verbose_name = 'ዘር (Zer) API'

    def ready(self):
        # Pre-warm the embedded Zer model in the background so the first chat
        # request never pays the ~seconds-long GGUF load. Silent no-op when
        # llama-cpp-python or the model file is missing.
        try:
            import threading
            import zer_model

            def _warm():
                try:
                    zer_model.load()
                except Exception:
                    pass

            threading.Thread(target=_warm, name='zer-model-warm',
                             daemon=True).start()
        except Exception:
            pass

        # Optionally pre-load the neural Amharic voice (MMS-TTS) so the first
        # spoken reply is instant and any load failure is surfaced early.
        # Off by default to keep boot light; enable with ZER_WARM_TTS=1.
        if os.environ.get('ZER_WARM_TTS', '0').strip().lower() not in (
                '', '0', 'false', 'no'):
            try:
                import threading
                import zer_speech

                def _warm_tts():
                    try:
                        zer_speech.warm_tts('am')
                    except Exception:
                        pass

                threading.Thread(target=_warm_tts, name='zer-tts-warm',
                                 daemon=True).start()
            except Exception:
                pass
