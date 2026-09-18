from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Zer account. Users are tracked so conversations and memories persist."""

    display_name = models.CharField(max_length=80, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    def name(self):
        return self.display_name or self.get_full_name() or self.username

    def __str__(self):
        return self.username


class Conversation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations')
    title = models.CharField(max_length=140, blank=True)
    lang = models.CharField(max_length=8, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated']

    def __str__(self):
        return self.title or f'Conversation {self.pk}'


class Turn(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='turns')
    role = models.CharField(max_length=10)          # 'user' | 'assistant'
    text = models.TextField()
    lang = models.CharField(max_length=8, blank=True)
    source = models.CharField(max_length=40, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']


class Memory(models.Model):
    """Facts a user taught Zer — used to ground replies and remembered later."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memories')
    fact = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated']
