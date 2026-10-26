"""Make one Short end-to-end: pick a project -> script -> voice -> render -> upload -> review notification.

Env: ANTHROPIC_API_KEY, CONCEPT_SUPABASE_KEY, CRM_SUPABASE_KEY, KOKORO_DIR
Optional: PROJECT_ID (force a project), MAX_PENDING (default 4), DRY_RUN=1 (render locally, no upload)
"""
import os, sys, json, hashlib, secrets, pathlib, subprocess, tempfile, shutil
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from supa import concept, crm
from write_script import facts_from_job, write_script, vo_script
from render import render
from notify import push, review_actions

ROOT = pathlib.Path(__file__).resolve().parent.parent
DRY = os.environ.get('DRY_RUN') == '1'
MAX_PENDING = int(os.environ.get('MAX_PENDING', '4'))


def parcel_key(job):
    lab = ((job.get('geocode') or {}).get('label') or job['id']).upper().split('[')[0].strip()
    return hashlib.sha1(lab.encode()).hexdigest()[:16]


def pick_project(cdb, rdb):
    forced = os.environ.get('PROJECT_ID')
    cols = 'id,created_at,geocode,outputs,program,summary,zoning,status,render_status'
    if forced:
        return cdb.select('pipeline_jobs', {'select': cols, 'id': f'eq.{forced}'})[0]
    used = {r['parcel_key'] for r in rdb.select('social_posts', {'select': 'parcel_key'})}
    jobs = cdb.select('pipeline_jobs', {'select': cols, 'render_status': 'eq.completed',
                                        'order': 'created_at.desc', 'limit': '200'})
    for j in jobs:
        o = j.get('outputs') or {}
        if not ((o.get('ec') or {}).get('aerial.jpg') and (o.get('render') or {}).get('render.jpg')):
            continue
        if parcel_key(j) not in used:
            return j
    return None


def fit(src, dest, max_side=2400):
    im = Image.open(src).convert('RGB')
    im.thumbnail((max_side, max_side))
    im.save(dest, quality=92)
    return str(dest)


def fetch_assets(cdb, job, d):
    o = job['outputs']; raw = d / 'raw'; raw.mkdir()
    def get(group, name):
        p = (o.get(group) or {}).get(name)
        return cdb.download('pipeline', p, raw / name) if p else None
    aerial, render_img = get('ec', 'aerial.jpg'), get('render', 'render.jpg')
    plan = get('layout', 'concept_plan.png') or get('design', 'sheet_C3.png') or get('ec', 'existing_conditions.png')
    model = get('render', 'model_front.png') or render_img
    a = {'TODAY': fit(aerial, d / 'today.jpg'), 'RENDER': fit(render_img, d / 'render.jpg'),
         'LAYOUT': fit(plan, d / 'layout.jpg'), 'MODEL': fit(model, d / 'model.jpg')}
    # package pages 2-5 (skip the cover, which carries the address)
    pkg = get('package', 'package.pdf')
    pages = []
    if pkg:
        subprocess.run(['pdftoppm', '-jpeg', '-r', '80', '-f', '2', '-l', '5', pkg, str(d / 'pg')], check=False)
        pages = sorted(str(p) for p in d.glob('pg*.jpg'))
    if len(pages) < 4:
        pages = sorted(str(p) for p in (ROOT / 'assets' / 'fallback').glob('*.jpg'))
    for i, p in enumerate(pages[:4]):
        a[f'P{i + 1}'] = p
    return a


def main():
    cdb, rdb = concept(), crm()
    if not DRY and not os.environ.get('PROJECT_ID'):
        pending = rdb.select('social_posts', {'select': 'id', 'status': 'eq.pending_review'})
        if len(pending) >= MAX_PENDING:
            print(f'{len(pending)} posts already waiting for review; skipping'); return
    job = pick_project(cdb, rdb)
    if not job:
        push('Forma Shorts: out of fresh projects', 'Every rendered project has a Short. Run more concepts through the pipeline.', tags=['warning'])
        print('no unused projects'); return
    print('project', job['id'])

    d = pathlib.Path(tempfile.mkdtemp(prefix='job_'))
    try:
        assets = fetch_assets(cdb, job, d)
        facts = facts_from_job(job)
        recent = [] if DRY else [r['script']['vo']['hook1'] for r in rdb.select(
            'social_posts', {'select': 'script', 'order': 'created_at.desc', 'limit': '8'}) if r.get('script')]
        s = write_script(facts, recent)
        print(json.dumps(s, indent=1))
        (d / 'vo_script.json').write_text(json.dumps(vo_script(s)))
        subprocess.run([sys.executable, str(ROOT / 'engine' / 'vo.py'), str(d / 'vo_script.json'), str(d / 'vo')], check=True)
        (d / 'spec.json').write_text(json.dumps({'template': 'flip', 'assets': assets, 'text': s['text'],
                                                  'stat_value': s['stat_value']}))
        out = d / 'short.mp4'
        render(d, out)

        if DRY:
            dest = ROOT / 'out'; dest.mkdir(exist_ok=True)
            shutil.copy(out, dest / f"{job['id']}.mp4"); print('dry run ->', dest); return

        token = secrets.token_urlsafe(18)
        row = rdb.insert('social_posts', {
            'project_id': job['id'], 'parcel_key': parcel_key(job), 'platform': 'youtube',
            'status': 'rendering', 'script': s, 'facts': facts, 'title': s['title'],
            'description': s['description'], 'tags': s['tags'], 'review_token': token})
        pid = row['id']
        rdb.upload('shorts', f'{pid}.mp4', out, 'video/mp4')
        rdb.upload('shorts', f'{pid}.jpg', out.with_suffix('.jpg'), 'image/jpeg')
        rdb.update('social_posts', {'id': pid}, {'status': 'pending_review', 'video_path': f'{pid}.mp4',
                                                 'thumb_path': f'{pid}.jpg'})
        thumb = rdb.signed_url('shorts', f'{pid}.jpg')
        push('New Short ready for review', f"{s['title']}\n\n“{s['vo']['hook1']} And this... {s['vo']['hook2b']}”",
             actions=review_actions(pid, token), attach=thumb, tags=['clapper'])
        print('queued', pid)
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == '__main__':
    main()
