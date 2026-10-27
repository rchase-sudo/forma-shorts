"""Pull a pipeline job's Short media into media/<job_id>/. Usage: python engine/fetch_media.py JOB_ID [JOB_ID...]"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from supa import concept

db = concept()
WANT = [("ec", "aerial.jpg"), ("layout", "concept_plan.png"), ("render", "model_front.png"), ("render", "render.jpg"), ("package", "package.pdf")]
for job_id in sys.argv[1:]:
    job = db.select("pipeline_jobs", {"select": "id,outputs", "id": f"eq.{job_id}"})[0]
    out = pathlib.Path("media") / job_id
    out.mkdir(parents=True, exist_ok=True)
    for g, n in WANT:
        key = ((job.get("outputs") or {}).get(g) or {}).get(n)
        if key:
            db.download("pipeline", key, out / n)
            print(job_id, "fetched", n)
