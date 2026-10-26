"""Turn a pipeline project's facts into a Short script (voiceover + on-screen text + YouTube metadata) with Claude."""
import os, re, json
import anthropic

MODEL = os.environ.get('CLAUDE_MODEL', 'claude-sonnet-5-5')
PHONE = '(978) 346-5818'

# Fixed lines: the flip lands on hook2a; the CTA never changes.
HOOK2A = 'And this...'
CTA = [
    {'id': 'cta1', 'text': 'Selling vacant land?', 'gap': 0.15},
    {'id': 'cta2', 'text': 'Text the word, LAND, to the number on screen.', 'gap': 0.15},
    {'id': 'cta3', 'text': "I'll get back to you in under five minutes.", 'gap': 1.3},
]

# max characters per on-screen field (sized to the template's type)
LIMITS = {'TODAY1': 9, 'TODAY2': 9, 'TODAYSUB': 34, 'STATUNIT': 6, 'STATSUB': 34,
          'S1A': 12, 'S1B': 12, 'S2A': 12, 'S2B': 12, 'S3A': 12, 'S3B': 12, 'S4A': 12, 'S4B': 12,
          'CHIP1': 12, 'CHIP2': 12, 'CHIP3': 12, 'CHIP4': 12}

STATE_RE = re.compile(r',\s*([A-Z]{2})\b(?:,|\s+\d{5})')


def facts_from_job(job):
    prog, summ, zon = job.get('program') or {}, job.get('summary') or {}, job.get('zoning') or {}
    blds = prog.get('buildings') or []
    gfa = sum(float(b.get('footprint_sf') or 0) * int(b.get('stories') or 1) for b in blds)
    label = ((job.get('geocode') or {}).get('label') or '').upper()
    m = STATE_RE.search(label)
    zcode = next((zon.get(k) for k in ('district', 'code', 'zone', 'district_code') if isinstance(zon.get(k), str)), None)
    f = {
        'state': m.group(1) if m else None,
        'parcel_acres': summ.get('parcel_acres'),
        'buildable_acres': summ.get('buildable_acres'),
        'wetland_acres': summ.get('wetland_acres'),
        'flood_zones': summ.get('flood_zones'),
        'flood_sfha_acres': summ.get('flood_sfha_acres'),
        'frontage_ft': summ.get('frontage_ft'),
        'setbacks_ft': summ.get('setbacks_ft'),
        'avg_slope_pct': (summ.get('topo') or {}).get('avg_slope_pct'),
        'zoning_district': zcode,
        'proposed_use': prog.get('use'),
        'building_count': len(blds),
        'buildings': [{'label': b.get('label'), 'use': b.get('use'), 'stories': b.get('stories'),
                       'footprint_sf': b.get('footprint_sf'), 'drive_thru': b.get('drive_thru')} for b in blds],
        'total_building_sf': round(gfa),
        'parking_stalls': (prog.get('parking') or {}).get('required'),
    }
    return {k: v for k, v in f.items() if v not in (None, [], {}, '')}


SYSTEM = f"""You write scripts for 20-second YouTube Shorts for Forma Designs, a one-person business run by Ryan.
Forma turns vacant land listings into a concept site plan, a photoreal 3D render and a due diligence package,
so listing agents can show buyers what a lot could become. The audience is listing agents with vacant land.

The video template is fixed:
1. HOOK: full-screen aerial of the empty lot (voice: hook1), then a hard flip to the finished render on the
   words "{HOOK2A}" (fixed), then hook2b finishes the sentence. On-screen during the render: a big counting
   number (stat_value + STATUNIT) and one line under it (STATSUB).
2. PROCESS: four quick steps, one voice line each (p1..p4), ~2 seconds each:
   step 1 = reading the site (parcel, zoning, wetlands, flood, setbacks), step 2 = the site plan,
   step 3 = 3D model to photoreal render, step 4 = the due diligence package.
   Each step has a 2-line headline (S#A white + S#B gold). Step 1 also shows four chips (CHIP1..4).
3. CTA (fixed, you do not write it): text LAND to {PHONE}.

Rules:
- Every number you use must come from the facts given. Round sensibly (7,500 SF; 1.1 acres). Never invent numbers.
- Never mention a street address, town or owner. The state is fine.
- First person singular ("I"), never "we". Plain, confident, energetic. No hype words like "game-changer".
- Voice lines are spoken by a TTS voice: short, punchy, easy to say. hook1 <= 8 words, hook2b <= 6 words,
  each p# <= 8 words. Write numbers as you would say them ("seventy-five hundred square feet").
- Vary the hook angle between runs (e.g. "This lot has sat on the market..." is NOT allowed unless a fact says so;
  good angles: size of the lot, what the zoning allows, the constraint you solved, the buyer who would want it).
- On-screen character limits: {json.dumps(LIMITS)}. TODAY1/TODAY2 are a 2-line giant headline over the aerial
  (e.g. "1.1 acres." / "Empty."); TODAYSUB is a small mono caption (e.g. "Zoned LB · Flood zone X").
- Title <= 70 chars, ends with #shorts. Description: 2-3 short lines, then exactly this CTA line:
  "Selling vacant land? Text LAND to {PHONE}. I reply in under 5 minutes. formadesigns.io"
  then "Concept only. Not for construction." then 3-5 hashtags. 8-12 lowercase tags.

Return ONLY a JSON object:
{{"vo": {{"hook1": "", "hook2b": "", "p1": "", "p2": "", "p3": "", "p4": ""}},
 "text": {{"TODAY1": "", "TODAY2": "", "TODAYSUB": "", "STATUNIT": "", "STATSUB": "",
          "S1A": "", "S1B": "", "S2A": "", "S2B": "", "S3A": "", "S3B": "", "S4A": "", "S4B": "",
          "CHIP1": "", "CHIP2": "", "CHIP3": "", "CHIP4": ""}},
 "stat_value": 0, "title": "", "description": "", "tags": []}}"""


def check(s):
    errs = []
    for k, n in LIMITS.items():
        v = s.get('text', {}).get(k)
        if not v: errs.append(f'text.{k} missing')
        elif len(v) > n: errs.append(f'text.{k} is {len(v)} chars, max {n}')
    for k in ('hook1', 'hook2b', 'p1', 'p2', 'p3', 'p4'):
        if not s.get('vo', {}).get(k): errs.append(f'vo.{k} missing')
    if not isinstance(s.get('stat_value'), (int, float)) or s['stat_value'] <= 0: errs.append('stat_value must be > 0')
    if len(s.get('title', '')) > 100: errs.append('title too long')
    blob = json.dumps(s).lower()
    if re.search(r"\bwe\b|\bour\b|\bwe'", blob): errs.append('uses we/our; use I/my')
    return errs


def write_script(facts, recent_hooks=()):
    client = anthropic.Anthropic()
    msgs = [{'role': 'user', 'content': 'Facts for this project:\n' + json.dumps(facts, indent=1) +
             ('\n\nRecent hooks (do not repeat these angles):\n- ' + '\n- '.join(recent_hooks) if recent_hooks else '')}]
    for attempt in range(3):
        r = client.messages.create(model=MODEL, max_tokens=1500, system=SYSTEM, messages=msgs)
        raw = ''.join(b.text for b in r.content if b.type == 'text')
        try:
            s = json.loads(raw[raw.index('{'): raw.rindex('}') + 1])
        except Exception as e:
            errs = [f'not valid JSON: {e}']; s = None
        else:
            errs = check(s)
        if not errs:
            return s
        msgs += [{'role': 'assistant', 'content': raw}, {'role': 'user', 'content': 'Fix these and return the full JSON again:\n- ' + '\n- '.join(errs)}]
    raise RuntimeError(f'script failed validation: {errs}')


def vo_script(s, voice='am_michael', speed=1.12):
    v = s['vo']
    lines = [{'id': 'hook1', 'text': v['hook1'], 'gap': .15},
             {'id': 'hook2a', 'text': HOOK2A, 'gap': .12},
             {'id': 'hook2b', 'text': v['hook2b'], 'gap': .5},
             {'id': 'p1', 'text': v['p1'], 'gap': .12}, {'id': 'p2', 'text': v['p2'], 'gap': .12},
             {'id': 'p3', 'text': v['p3'], 'gap': .12}, {'id': 'p4', 'text': v['p4'], 'gap': .4}] + CTA
    return {'voice': voice, 'speed': speed, 'lead_in': .3, 'lines': lines}
