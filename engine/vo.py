"""Generate voiceover line-by-line with Kokoro and emit cue timings.
Usage: python3 vo.py script.json out_dir
script.json: {"voice": "am_michael", "speed": 1.1, "lines": [{"id": "hook1", "text": "...", "gap": 0.25}, ...]}
Writes out_dir/vo.wav and out_dir/cues.json ({id: [start, end]} in seconds).
"""
import json, sys, pathlib, os
import numpy as np, soundfile as sf
from kokoro_onnx import Kokoro

spec = json.load(open(sys.argv[1]))
out = pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
mdir = pathlib.Path(os.environ.get('KOKORO_DIR', '.'))
k = Kokoro(str(mdir / 'kokoro.onnx'), str(mdir / 'voices.bin'))

def trim(a, thr=0.008):
    idx = np.where(np.abs(a) > thr)[0]
    return a[max(idx[0] - 240, 0): idx[-1] + 2400] if len(idx) else a

t = spec.get('lead_in', 0.35)
SR = 24000
chunks, cues = [np.zeros(int(t * SR))], {}
for ln in spec['lines']:
    a, sr = k.create(ln['text'], voice=spec.get('voice', 'am_michael'),
                     speed=ln.get('speed', spec.get('speed', 1.1)), lang='en-us')
    a = trim(a)
    cues[ln['id']] = [round(t, 3), round(t + len(a) / sr, 3)]
    chunks.append(a)
    t += len(a) / sr
    gap = ln.get('gap', 0.18)
    chunks.append(np.zeros(int(gap * SR))); t += gap
audio = np.concatenate(chunks)
audio = audio / (np.max(np.abs(audio)) + 1e-9) * 0.95
sf.write(out / 'vo.wav', audio, SR)
cues['_end'] = round(t, 3)
json.dump(cues, open(out / 'cues.json', 'w'), indent=1)
print(json.dumps(cues))
