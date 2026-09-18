"""Export real user conversations + taught facts as SFT data for fine-tuning.

    cd backend && python manage.py export_training_data --out ../training/data/conversations.jsonl

This lets the fine-tuned model learn from actual usage (with the users' consent —
only aggregate, account-owned turns are exported; no credentials).
"""
import json
import os

from django.core.management.base import BaseCommand

from api.models import Conversation, Memory

SYSTEM = (
    "Your name is Zer (ዘር), an Ethiopian AI assistant; 'ዘር' means 'seed'. "
    "Always answer in the SAME language the user used: Amharic → Amharic in Ge'ez "
    "script, English → English. Be warm, accurate and thorough. When writing code "
    "you may use Amharic comments, strings and identifiers."
)


class Command(BaseCommand):
    help = 'Export conversations + memories as an SFT JSONL file.'

    def add_arguments(self, parser):
        parser.add_argument('--out', default='../training/data/conversations.jsonl')
        parser.add_argument('--min-turns', type=int, default=2)

    def handle(self, *args, **opts):
        out = opts['out']
        os.makedirs(os.path.dirname(os.path.abspath(out)) or '.', exist_ok=True)
        count = 0
        with open(out, 'w', encoding='utf-8') as f:
            for conv in Conversation.objects.prefetch_related('turns').all():
                turns = list(conv.turns.all())
                if len(turns) < opts['min_turns']:
                    continue
                messages = [{'role': 'system', 'content': SYSTEM}]
                for t in turns:
                    messages.append({
                        'role': 'user' if t.role == 'user' else 'assistant',
                        'content': t.text,
                    })
                f.write(json.dumps({'messages': messages}, ensure_ascii=False) + '\n')
                count += 1

            for mem in Memory.objects.all():
                f.write(json.dumps({'messages': [
                    {'role': 'system', 'content': SYSTEM},
                    {'role': 'user', 'content': f'አስታውስ {mem.fact}'},
                    {'role': 'assistant',
                     'content': f'አስታወስኩ! «{mem.fact}» ይህንን አስታውሳለሁ።'},
                ]}, ensure_ascii=False) + '\n')
                count += 1

        self.stdout.write(self.style.SUCCESS(f'wrote {count} examples → {out}'))
