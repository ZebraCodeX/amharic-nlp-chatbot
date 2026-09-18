from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers

from .models import Conversation, Memory, Turn

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'display_name', 'name', 'date_joined']

    def get_name(self, obj):
        return obj.name()


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=6)
    email = serializers.EmailField(required=False, allow_blank=True)
    display_name = serializers.CharField(required=False, allow_blank=True)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('username already taken')
        return value

    def create(self, validated):
        return User.objects.create_user(
            username=validated['username'],
            password=validated['password'],
            email=validated.get('email', ''),
            display_name=validated.get('display_name', ''),
        )


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(username=attrs['username'], password=attrs['password'])
        if user is None:
            raise serializers.ValidationError('invalid credentials')
        attrs['user'] = user
        return attrs


class TurnSerializer(serializers.ModelSerializer):
    class Meta:
        model = Turn
        fields = ['id', 'role', 'text', 'lang', 'source', 'created']


class ConversationSerializer(serializers.ModelSerializer):
    turn_count = serializers.IntegerField(source='turns.count', read_only=True)
    preview = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ['id', 'title', 'lang', 'created', 'updated', 'turn_count', 'preview']

    def get_preview(self, obj):
        first = obj.turns.filter(role='user').first()
        return (first.text[:80] if first else '')


class ConversationDetailSerializer(ConversationSerializer):
    turns = TurnSerializer(many=True, read_only=True)

    class Meta(ConversationSerializer.Meta):
        fields = ConversationSerializer.Meta.fields + ['turns']


class MemorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Memory
        fields = ['id', 'fact', 'created', 'updated']


class ChatRequestSerializer(serializers.Serializer):
    text = serializers.CharField(allow_blank=True, trim_whitespace=True)
    history = serializers.ListField(child=serializers.DictField(), required=False)
    lang = serializers.CharField(required=False, allow_blank=True)


class ChatTurnSerializer(serializers.Serializer):
    """One stored conversation turn (matches chatbot.normalize_history)."""
    user = serializers.CharField(allow_blank=True, required=False)
    reply = serializers.CharField(allow_blank=True, required=False)
    source = serializers.CharField(required=False)


class TranslateQuerySerializer(serializers.Serializer):
    text = serializers.CharField(allow_blank=True, trim_whitespace=True)
    to = serializers.ChoiceField(choices=['en', 'am'], default='en')


class VerifySerializer(serializers.Serializer):
    text = serializers.CharField(trim_whitespace=True)
    src = serializers.CharField(required=False, default='am')
    dst = serializers.CharField(required=False, default='en')
    translation = serializers.CharField(required=False, allow_blank=True, default='')
    correct = serializers.CharField(required=False, allow_blank=True, default='')
    engine = serializers.CharField(required=False, allow_blank=True, default='user')

    def validate(self, attrs):
        if not attrs.get('translation') and not attrs.get('correct'):
            raise serializers.ValidationError('text and translation required')
        return attrs
