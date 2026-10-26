"""Render a Short from a job folder.

Usage: python3 engine/render.py JOB_DIR OUT.mp4 [--only t1,t2] [--fps 30]

JOB_DIR/spec.json  {"template": "flip", "assets": {"TODAY": path, ...}, "text": {"TODAY1": "...", ...}, "stat_value": 7500}
JOB_DIR/vo/        vo.wav + cues.json (from engine/vo.py)
"""
import sys, json, html, pathlib, subprocess, tempfile, shutil
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent

def render(job_dir, out, only=None, fps=30):
    job_dir, out = pathlib.Path(job_dir), pathlib.Path(out)
    spec = json.load(open(job_dir / 'spec.json'))
    cues = json.load(open(job_dir / 'vo' / 'cues.json'))
    page_src = (ROOT / 'template' / f"{spec.get('template', 'flip')}.html").read_text()
    # longest keys first so TXT_S1A doesn't clobber TXT_S1AB-style names
    for k in sorted(spec['text'], key=len, reverse=True):
        page_src = page_src.replace(f'TXT_{k}', html.escape(str(spec['text'][k])))
    for k, v in spec['assets'].items():
        page_src = page_src.replace(f'ASSET_{k}', pathlib.Path(v).resolve().as_uri())
    page_src = page_src.replace('STAT_VALUE', str(int(spec.get('stat_value', 0))))
    page_src = page_src.replace('<script>', f'<script>window.CUES={json.dumps(cues)};', 1)
    leftover = [w for w in ('TXT_', 'ASSET_', 'STAT_VALUE') if w in page_src]
    if leftover:
        raise SystemExit(f'unfilled placeholders: {leftover}')

    work = pathlib.Path(tempfile.mkdtemp(prefix='short_'))
    page = work / 'page.html'; page.write_text(page_src)
    frames = work / 'frames'; frames.mkdir()
    times = only or [i / fps for i in range(int(cues['_end'] * fps))]
    with sync_playwright() as p:
        b = p.chromium.launch(args=['--allow-file-access-from-files'])
        pg = b.new_page(viewport={'width': 1080, 'height': 1920})
        pg.goto(page.as_uri()); pg.wait_for_load_state('networkidle')
        pg.evaluate('document.fonts.ready')
        pg.wait_for_function('Array.from(document.images).every(i=>i.complete && i.naturalWidth>0)', timeout=60000)
        for i, t in enumerate(times):
            pg.evaluate(f'renderAt({t},{i})')
            name = f't{t:05.2f}.jpg' if only else f'f{i:05d}.jpg'
            pg.screenshot(path=str((out.parent if only else frames) / name), type='jpeg', quality=92)
        b.close()
    if only:
        shutil.rmtree(work); return
    mix = work / 'mix.wav'
    subprocess.run([sys.executable, str(ROOT / 'engine' / 'music.py'), str(job_dir / 'vo' / 'cues.json'),
                    str(job_dir / 'vo' / 'vo.wav'), str(mix)], check=True)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(fps), '-i', str(frames / 'f%05d.jpg'),
                    '-i', str(mix), '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p',
                    '-af', 'loudnorm=I=-14:TP=-1:LRA=9', '-ar', '48000', '-c:a', 'aac', '-b:a', '192k',
                    '-shortest', '-movflags', '+faststart', str(out)], check=True)
    # thumbnail: first frame after the flip
    flip_t = cues['hook2a'][0] + 1.4
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', f'{flip_t:.2f}', '-i', str(out), '-frames:v', '1',
                    '-q:v', '3', str(out.with_suffix('.jpg'))], check=True)
    shutil.rmtree(work)

if __name__ == '__main__':
    a = sys.argv[1:]
    only = None; fps = 30
    if '--only' in a:
        k = a.index('--only'); only = [float(x) for x in a[k + 1].split(',')]; a = a[:k] + a[k + 2:]
    if '--fps' in a:
        k = a.index('--fps'); fps = int(a[k + 1]); a = a[:k] + a[k + 2:]
    render(a[0], a[1], only, fps)
    print('done', a[1])
