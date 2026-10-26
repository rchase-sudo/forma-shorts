"""Phone push notifications via ntfy.sh (free app: subscribe to the topic below)."""
import os, json, requests

TOPIC = os.environ.get('NTFY_TOPIC') or 'forma-shorts-avcloe59ehqrn5'
REVIEW_FN = os.environ.get('REVIEW_URL', 'https://qrmqmtcxrkexazovtlev.supabase.co/functions/v1/shorts-review')


def push(title, message, actions=None, click=None, attach=None, priority=3, tags=None):
    body = {'topic': TOPIC, 'title': title, 'message': message, 'priority': priority}
    if actions: body['actions'] = actions
    if click: body['click'] = click
    if attach: body['attach'] = attach
    if tags: body['tags'] = tags
    try:
        requests.post('https://ntfy.sh/', data=json.dumps(body), timeout=20).raise_for_status()
    except Exception as e:  # notifications must never break the pipeline
        print('notify failed:', e)


def review_actions(post_id, token):
    u = f'{REVIEW_FN}?id={post_id}&t={token}'
    return [
        {'action': 'view', 'label': 'Watch', 'url': f'{u}&a=view'},
        {'action': 'http', 'label': 'Approve', 'url': f'{u}&a=approve', 'method': 'POST', 'clear': True},
        {'action': 'http', 'label': 'Kill', 'url': f'{u}&a=kill', 'method': 'POST', 'clear': True},
    ]
