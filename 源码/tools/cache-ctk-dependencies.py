"""Cache exact nested dependency revisions from the pinned CTK archive."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build-support" / "python-tools"))
import requests

records = json.loads((ROOT / "build-support" / "archive-lock.json").read_text())
ctk = next(record for record in records if record["project"] == "CTK")
archive = Path(ctk["archive"])
if hashlib.sha256(archive.read_bytes()).hexdigest() != ctk["sha256"]:
    raise RuntimeError("CTK archive checksum mismatch")
items = []
with zipfile.ZipFile(archive) as z:
    for project in ("PythonQt", "qRestAPI", "QtSOAP", "qxmlrpc", "Log4Qt"):
        member = next(name for name in z.namelist() if name.endswith("/CMakeExternals/" + project + ".cmake"))
        text = z.read(member).decode("utf-8")
        tag = re.search(r'set\(revision_tag "?([a-f0-9]{40})"?\)', text)[1]
        repo = re.search(r'GIT_REPOSITORY "https://github.com/([^" ]+)\.git"', text)[1]
        items.append({"project": project, "repo": repo, "tag": tag, "url": f"https://codeload.github.com/{repo}/zip/{tag}"})


def fetch(item):
    path = ROOT / "build-support" / "archive-cache" / (item["project"] + ".zip")
    if not path.exists():
        temporary = path.with_suffix(".part")
        with requests.get(item["url"], stream=True, timeout=(20, 60)) as response:
            response.raise_for_status()
            with temporary.open("wb") as out:
                for block in response.iter_content(1024 * 1024):
                    out.write(block)
        temporary.replace(path)
    with zipfile.ZipFile(path) as z:
        if not z.namelist() or z.testzip():
            raise RuntimeError("Corrupt nested archive: " + item["project"])
    return {**item, "archive": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}


with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    results = list(pool.map(fetch, items))
(ROOT / "build-support" / "ctk-archive-lock.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
for record in results:
    print("Verified", record["project"], record["tag"], record["bytes"])
