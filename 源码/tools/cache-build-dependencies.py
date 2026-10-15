from pathlib import Path
import sys,json,hashlib,time,concurrent.futures,zipfile
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'build-support'/'python-tools'))
import requests
manifest=root/'desktop'/'dependency-lock.json'
items=json.loads(manifest.read_text())['archives'] if manifest.exists() else json.loads((root/'build-support'/'dependency-archives.json').read_text())
cache=root/'build-support'/'archive-cache';cache.mkdir(parents=True,exist_ok=True)
def fetch(item):
    out=cache/(item['project']+'.zip')
    for attempt in range(3):
        try:
            if not out.exists():
                temp=out.with_suffix('.part')
                with requests.get(item['url'],stream=True,timeout=(20,60)) as resp:
                    resp.raise_for_status()
                    with temp.open('wb') as f:
                        for block in resp.iter_content(1024*1024):f.write(block)
                temp.replace(out)
            with zipfile.ZipFile(out) as z:
                if not z.namelist():raise ValueError('Empty archive')
                if z.testzip():raise ValueError('Corrupt archive')
            digest=hashlib.sha256(out.read_bytes()).hexdigest()
            if item.get('sha256') and digest != item['sha256']:raise ValueError('Pinned archive checksum mismatch')
            return {**item,'archive':str(out),'sha256':digest,'bytes':out.stat().st_size}
        except Exception as error:
            print(item['project'],'attempt',attempt+1,type(error).__name__,flush=True)
            if attempt==2:raise
            time.sleep(2)
results=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    pending={pool.submit(fetch,item):item for item in items}
    for future in concurrent.futures.as_completed(pending):
        record=future.result();results.append(record)
        (root/'build-support'/'download-progress.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        print('Cached',record['project'],record['bytes'],flush=True)
(root/'build-support'/'archive-lock.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print('All',len(results),'archives verified',flush=True)
