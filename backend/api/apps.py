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
            import zer_model

            def _warm():
                try:
                    zer_model.load()
                except Exception:
                    pass

            thread = __import__('threading').Thread(
                target=_warm, name='zer-model-warm', daemon=True)
            thread.start()
        except Exception:
            pass
