"""Reuse validated native dependencies; replace only CT3D scripts and docs."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import zipfile

parser=argparse.ArgumentParser()
parser.add_argument('baseline',type=Path)
parser.add_argument('destination',type=Path)
parser.add_argument('--report',type=Path,required=True)
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
if args.baseline.resolve()==args.destination.resolve() or args.destination.exists():
    raise SystemExit('Destination must be a new file; baseline is retained.')
if hashlib.sha256(args.baseline.read_bytes()).hexdigest().upper()!='E692F4B91F4CA58ECFD0E3788801ACCA942BC50F4ABEED08A66E3904E8A06CFF':
    raise SystemExit('Baseline archive differs from the validated release.')
prefix=args.destination.stem
changes={}
for file in (root/'CT3D').rglob('*.py'):
    changes['lib/CT3D-5.12/qt-scripted-modules/'+file.relative_to(root/'CT3D').as_posix()]=file
changes['切片展开使用说明.md']=root/'docs/切片展开使用说明.md'
changes['README-切片展开.md']=root/'docs/切片展开发布说明.md'
records=[]
with zipfile.ZipFile(args.baseline) as src, zipfile.ZipFile(args.destination,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as dest:
    for entry in src.infolist():
        parts=entry.filename.split('/',1)
        if len(parts)!=2 or not parts[1]:
            continue
        relative=parts[1]
        if relative in changes or (relative.endswith('.pyc') and ('qt-scripted-modules/CT3DLib/' in relative or 'qt-scripted-modules/__pycache__/CT3D.' in relative)):
            continue
        info=copy.copy(entry)
        info.filename=prefix+'/'+relative
        digest=hashlib.sha256()
        with src.open(entry) as reader,dest.open(info,'w') as writer:
            for block in iter(lambda:reader.read(1024*1024),b''):
                digest.update(block)
                writer.write(block)
        records.append({'path':relative,'sha256':digest.hexdigest(),'kind':'unchanged_native_payload'})
    for relative,path in changes.items():
        dest.write(path,prefix+'/'+relative)
        records.append({'path':relative,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'kind':'updated_script_or_document'})
with zipfile.ZipFile(args.destination) as result:
    bad=result.testzip()
    if bad:
        raise RuntimeError('ZIP integrity failed: '+bad)
args.report.parent.mkdir(parents=True,exist_ok=True)
args.report.write_text(json.dumps({'status':'packaged_not_yet_accepted','archive':str(args.destination),
                                 'archive_sha256':hashlib.sha256(args.destination.read_bytes()).hexdigest(),
                                 'native_kernel_build':'2026-10-11; unchanged','feature_update':'2026-10-13',
                                 'payload_files':records},ensure_ascii=False,indent=2),encoding='utf-8')
print(args.destination)
