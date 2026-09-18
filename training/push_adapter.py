#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
push_adapter.py — upload a trained LoRA adapter (or a merged model) to the
Hugging Face Hub under YOUR account, so it survives the rented GPU being deleted.

The adapter is tiny (~50–150 MB) and is all you need: on your laptop you can
rebuild the merged model from it plus the public base. Keep the repo **private**
unless you want it public.

    export HF_TOKEN=hf_...            # a token with WRITE access
    python training/push_adapter.py \
        --folder training/out/zer-lora \
        --repo YOUR-NAME/zer-qwen14b-lora

Then, on the laptop, pull + merge + serve (see training/README.md).
"""
import argparse
import os
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--folder', default='training/out/zer-lora',
                    help='local folder to upload (adapter or merged model)')
    ap.add_argument('--repo', required=True,
                    help='HF repo id, e.g. yourname/zer-qwen14b-lora')
    ap.add_argument('--public', action='store_true',
                    help='make the repo public (default: private)')
    ap.add_argument('--message', default='Zer Amharic QLoRA adapter')
    args = ap.parse_args()

    if not os.path.isdir(args.folder):
        sys.exit(f'folder not found: {args.folder}')

    try:
        from huggingface_hub import HfApi
    except ImportError:
        sys.exit('install the hub client first:  pip install huggingface_hub')

    token = os.environ.get('HF_TOKEN') or os.environ.get('HUGGING_FACE_HUB_TOKEN')
    if not token:
        sys.exit('set HF_TOKEN to a token with WRITE access (https://huggingface.co/settings/tokens)')

    api = HfApi(token=token)
    api.create_repo(args.repo, repo_type='model', exist_ok=True,
                    private=not args.public)
    api.upload_folder(folder_path=args.folder, repo_id=args.repo,
                      repo_type='model', commit_message=args.message)
    print(f'✓ pushed {args.folder} → https://huggingface.co/{args.repo} '
          f'({"public" if args.public else "private"})')


if __name__ == '__main__':
    main()
