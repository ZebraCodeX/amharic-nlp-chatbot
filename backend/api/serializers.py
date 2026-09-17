from rest_framework import serializers


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
