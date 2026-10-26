"""Minimal Supabase REST + Storage client (requests only)."""
import os, requests

CONCEPT_URL = os.environ.get('CONCEPT_SUPABASE_URL', 'https://mmaqwemqbxwngqxtnsug.supabase.co')
CRM_URL = os.environ.get('CRM_SUPABASE_URL', 'https://qrmqmtcxrkexazovtlev.supabase.co')


class Supa:
    def __init__(self, url, key):
        self.url = url.rstrip('/')
        self.h = {'apikey': key}
        if not key.startswith('sb_'):          # legacy JWT service_role key
            self.h['Authorization'] = f'Bearer {key}'

    # ---- PostgREST
    def select(self, table, params):
        r = requests.get(f'{self.url}/rest/v1/{table}', headers=self.h, params=params, timeout=60)
        r.raise_for_status(); return r.json()

    def insert(self, table, row):
        r = requests.post(f'{self.url}/rest/v1/{table}', headers={**self.h, 'Prefer': 'return=representation'},
                          json=row, timeout=60)
        r.raise_for_status(); return r.json()[0]

    def update(self, table, match, patch):
        params = {k: f'eq.{v}' for k, v in match.items()}
        r = requests.patch(f'{self.url}/rest/v1/{table}', headers={**self.h, 'Prefer': 'return=representation'},
                           params=params, json=patch, timeout=60)
        r.raise_for_status(); return r.json()

    def rpc(self, fn, args):
        r = requests.post(f'{self.url}/rest/v1/rpc/{fn}', headers=self.h, json=args, timeout=60)
        r.raise_for_status(); return r.json()

    # ---- Storage
    def download(self, bucket, path, dest):
        r = requests.get(f'{self.url}/storage/v1/object/{bucket}/{path}', headers=self.h, timeout=300)
        r.raise_for_status()
        with open(dest, 'wb') as f: f.write(r.content)
        return dest

    def upload(self, bucket, path, src, content_type):
        with open(src, 'rb') as f:
            r = requests.post(f'{self.url}/storage/v1/object/{bucket}/{path}',
                              headers={**self.h, 'Content-Type': content_type, 'x-upsert': 'true'},
                              data=f, timeout=600)
        r.raise_for_status(); return path

    def signed_url(self, bucket, path, expires=7 * 24 * 3600):
        r = requests.post(f'{self.url}/storage/v1/object/sign/{bucket}/{path}', headers=self.h,
                          json={'expiresIn': expires}, timeout=60)
        r.raise_for_status()
        return f"{self.url}/storage/v1{r.json()['signedURL']}"


def concept():
    return Supa(CONCEPT_URL, os.environ['CONCEPT_SUPABASE_KEY'])


def crm():
    return Supa(CRM_URL, os.environ['CRM_SUPABASE_KEY'])
