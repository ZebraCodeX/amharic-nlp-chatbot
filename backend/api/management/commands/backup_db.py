"""Safely back up the SQLite database (on the persistent volume).

    cd backend && python manage.py backup_db --keep 7

Writes a consistent copy to <userdata>/backups/hisar-YYYYmmdd-HHMMSS.sqlite3
using SQLite's online backup API, and prunes to the newest ``--keep`` files.
"""
import glob
import os
import sqlite3
import time

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Back up the SQLite database to the user-data directory.'

    def add_arguments(self, parser):
        parser.add_argument('--keep', type=int, default=7)

    def handle(self, *args, **opts):
        src = str(settings.DATABASES['default']['NAME'])
        if not os.path.exists(src):
            self.stderr.write(f'no database at {src}')
            return
        bdir = os.path.join(str(settings.USER_DATA_DIR), 'backups')
        os.makedirs(bdir, exist_ok=True)
        dst = os.path.join(bdir, f'hisar-{time.strftime("%Y%m%d-%H%M%S")}.sqlite3')

        source = sqlite3.connect(src)
        target = sqlite3.connect(dst)
        with target:
            source.backup(target)
        source.close()
        target.close()

        backups = sorted(glob.glob(os.path.join(bdir, 'hisar-*.sqlite3')))
        for old in backups[:-opts['keep']]:
            os.remove(old)
        self.stdout.write(self.style.SUCCESS(f'backed up → {dst} ({len(backups[-opts["keep"]:])} kept)'))
