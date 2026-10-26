"""Upload approved Shorts whose slot has arrived to YouTube.

Env: CRM_SUPABASE_KEY, YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
"""
import os, sys, pathlib, tempfile, datetime as dt
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from supa import crm
from notify import push
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


def youtube():
    creds = Credentials(None, refresh_token=os.environ['YT_REFRESH_TOKEN'],
                        token_uri='https://oauth2.googleapis.com/token',
                        client_id=os.environ['YT_CLIENT_ID'], client_secret=os.environ['YT_CLIENT_SECRET'],
                        scopes=['https://www.googleapis.com/auth/youtube.upload'])
    return build('youtube', 'v3', credentials=creds, cache_discovery=False)


def upload(yt, path, post):
    body = {
        'snippet': {'title': post['title'][:100], 'description': post['description'][:4900],
                    'tags': (post.get('tags') or [])[:15], 'categoryId': '26'},  # Howto & Style
        'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False,
                   'containsSyntheticMedia': True},  # AI voice + rendered concept imagery
    }
    req = yt.videos().insert(part='snippet,status', body=body,
                             media_body=MediaFileUpload(path, mimetype='video/mp4', chunksize=-1, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return resp['id']


def main():
    db = crm()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    due = db.select('social_posts', {'select': '*', 'status': 'eq.approved', 'platform': 'eq.youtube',
                                     'scheduled_for': f'lte.{now}', 'order': 'scheduled_for.asc', 'limit': '1'})
    if not due:
        print('nothing due'); return
    post = due[0]
    db.update('social_posts', {'id': post['id']}, {'status': 'publishing'})
    try:
        with tempfile.TemporaryDirectory() as d:
            path = db.download('shorts', post['video_path'], pathlib.Path(d) / 'v.mp4')
            vid = upload(youtube(), str(path), post)
        url = f'https://youtube.com/shorts/{vid}'
        db.update('social_posts', {'id': post['id']}, {'status': 'posted', 'platform_post_id': vid,
                                                       'posted_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'error': None})
        push('Short is live', post['title'], click=url, tags=['rocket'])
        print('posted', url)
    except Exception as e:
        db.update('social_posts', {'id': post['id']}, {'status': 'failed', 'error': str(e)[:2000]})
        push('Short failed to post', f"{post['title']}\n{str(e)[:300]}", priority=4, tags=['warning'])
        raise


if __name__ == '__main__':
    main()
