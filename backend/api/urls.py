"""API routes — mirror the old stdlib server's endpoints 1:1.

Canonical routes end with a slash (Django style); no-slash aliases keep the
old clients working.
"""
from django.urls import path

from . import views

app_name = 'api'

urlpatterns = [
    path('chat/', views.ChatView.as_view(), name='chat'),
    path('chat', views.ChatView.as_view()),

    path('translate/', views.TranslateView.as_view(), name='translate'),
    path('translate', views.TranslateView.as_view()),
    path('translate/verify/', views.TranslationVerifyView.as_view()),
    path('translate/verify', views.TranslationVerifyView.as_view()),
    path('translate/review/', views.CorrectionsReviewView.as_view()),
    path('translate/review', views.CorrectionsReviewView.as_view()),

    path('translations/', views.TranslationsView.as_view(), name='translations'),
    path('translations', views.TranslationsView.as_view()),
    path('translations/stats/', views.TranslationStatsView.as_view(), name='translation-stats'),
    path('translations/stats', views.TranslationStatsView.as_view()),
    path('translations/letters/', views.TranslationLettersView.as_view(), name='translation-letters'),
    path('translations/letters', views.TranslationLettersView.as_view()),
    path('learning/stats/', views.LearningStatsView.as_view(), name='learning-stats'),
    path('learning/stats', views.LearningStatsView.as_view()),
    path('translations/verify/', views.TranslationVerifyView.as_view()),
    path('translations/verify', views.TranslationVerifyView.as_view()),

    path('speech/status/', views.SpeechStatusView.as_view(), name='speech-status'),
    path('speech/status', views.SpeechStatusView.as_view()),
    path('speech/transcribe/', views.TranscribeView.as_view(), name='speech-transcribe'),
    path('speech/transcribe', views.TranscribeView.as_view()),
    path('speech/synthesize/', views.SynthesizeView.as_view(), name='speech-synthesize'),
    path('speech/synthesize', views.SynthesizeView.as_view()),
    path('voice/turn/', views.VoiceTurnView.as_view(), name='voice-turn'),
    path('voice/turn', views.VoiceTurnView.as_view()),

    path('words/', views.WordsView.as_view(), name='words'),
    path('words', views.WordsView.as_view()),
    path('dictionary/letters/', views.DictionaryLettersView.as_view(), name='dict-letters'),
    path('dictionary/letters', views.DictionaryLettersView.as_view()),
    path('dictionary/', views.DictionaryView.as_view(), name='dictionary'),
    path('dictionary', views.DictionaryView.as_view()),
    path('ngram/', views.NgramView.as_view(), name='ngram'),
    path('ngram', views.NgramView.as_view()),
    path('suggest/', views.SuggestView.as_view(), name='suggest'),
    path('suggest', views.SuggestView.as_view()),
    path('llm-status/', views.LlmStatusView.as_view(), name='llm-status'),
    path('llm-status', views.LlmStatusView.as_view()),
    path('health/', views.HealthView.as_view(), name='health'),
    path('health', views.HealthView.as_view()),
]
