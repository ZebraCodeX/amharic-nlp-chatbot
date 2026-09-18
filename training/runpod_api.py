#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
runpod_api.py — tiny RunPod helper (GraphQL, the same API runpodctl uses) so
GitHub Actions can rent a GPU pod, watch it, and terminate it.

Auth:   export RUNPOD_API_KEY=...            # runpod.io → Settings → API Keys
Endpoint override: RUNPOD_GRAPHQL=...         # default https://api.runpod.io/graphql

Examples
--------
    # rent an A100 80GB and run the bootstrap command on it
    python training/runpod_api.py create \
        --name zer-train --gpu "NVIDIA A100 80GB PCIe" --gpus 1 \
        --cloud SECURE --disk 200 \
        --command 'bash -lc "curl -fsSL https://raw.githubusercontent.com/ZebraCodeX/amharic-nlp-chatbot/main/training/runpod_bootstrap.sh | bash"' \
        --env-json /tmp/pod_env.json

    python training/runpod_api.py status --id POD_ID
    python training/runpod_api.py terminate --id POD_ID
    python training/runpod_api.py --dry-run create …     # print, don't send
"""
import argparse
import json
import os
import sys
import urllib.request

DEFAULT_ENDPOINT = 'https://api.runpod.io/graphql'
IMAGE_DEFAULT = 'runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04'


def _gql(endpoint, key, query, variables):
    body = json.dumps({'query': query, 'variables': variables}).encode('utf-8')
    req = urllib.request.Request(
        f'{endpoint}?api_key={key}', data=body,
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode('utf-8'))
    if data.get('errors'):
        raise SystemExit(f'RunPod error: {data["errors"]}')
    return data.get('data', {})


def _key():
    key = os.environ.get('RUNPOD_API_KEY')
    if not key:
        raise SystemExit('set RUNPOD_API_KEY (runpod.io → Settings → API Keys)')
    return key


def cmd_create(a):
    env = {}
    if a.env_json:
        with open(a.env_json, encoding='utf-8') as f:
            env = json.load(f)
    pod_input = {
        'name': a.name,
        'imageName': a.image,
        'gpuTypeId': a.gpu,
        'gpuCount': a.gpus,
        'cloudType': a.cloud,
        'containerDiskInGb': a.disk,
        'dockerArgs': a.command,
        'startSsh': True,
        'supportPublicIp': True,
        'env': [{'key': k, 'value': str(v)} for k, v in env.items()],
    }
    if a.volume > 0:
        pod_input['volumeInGb'] = a.volume
        pod_input['volumeMountPath'] = '/workspace'
    if a.dry_run:
        print(json.dumps(pod_input, indent=2))
        return
    query = ('mutation($input: PodFindAndDeployOnDemandInput!)'
             '{ podFindAndDeployOnDemand(input: $input) '
             '{ id costPerHr desiredStatus } }')
    out = _gql(a.endpoint, _key(), query, {'input': pod_input})
    pod = out.get('podFindAndDeployOnDemand') or {}
    print(json.dumps(pod))
    if pod.get('id'):
        sys.stderr.write(f"pod id: {pod['id']}\n"
                         f"console: https://console.runpod.io/pods/{pod['id']}\n")


def cmd_status(a):
    query = 'query { myself { pods { id name desiredStatus costPerHr } } }'
    if a.dry_run:
        print(query)
        return
    out = _gql(a.endpoint, _key(), query, {})
    pods = (out.get('myself') or {}).get('pods') or []
    if a.id:
        pods = [p for p in pods if p.get('id') == a.id]
    print(json.dumps(pods, indent=2))


def cmd_terminate(a):
    query = ('mutation($input: PodTerminateInput!) '
             '{ podTerminate(input: $input) }')
    if a.dry_run:
        print(json.dumps({'podId': a.id}))
        return
    out = _gql(a.endpoint, _key(), query, {'input': {'podId': a.id}})
    print(json.dumps(out))


def main():
    p = argparse.ArgumentParser(description='RunPod pod helper (GraphQL)')
    p.add_argument('--endpoint', default=os.environ.get('RUNPOD_GRAPHQL', DEFAULT_ENDPOINT))
    p.add_argument('--dry-run', action='store_true')
    sub = p.add_subparsers(dest='cmd', required=True)

    c = sub.add_parser('create')
    c.add_argument('--name', default='zer-train')
    c.add_argument('--image', default=IMAGE_DEFAULT)
    c.add_argument('--gpu', default='NVIDIA A100 80GB PCIe')
    c.add_argument('--gpus', type=int, default=1)
    c.add_argument('--cloud', default='SECURE', choices=['SECURE', 'COMMUNITY'])
    c.add_argument('--disk', type=int, default=200)
    c.add_argument('--volume', type=int, default=0)
    c.add_argument('--command', required=True)
    c.add_argument('--env-json', default='')
    c.set_defaults(func=cmd_create)

    s = sub.add_parser('status')
    s.add_argument('--id', default='')
    s.set_defaults(func=cmd_status)

    t = sub.add_parser('terminate')
    t.add_argument('--id', required=True)
    t.set_defaults(func=cmd_terminate)

    a = p.parse_args()
    a.func(a)


if __name__ == '__main__':
    main()
