"""Restore upstream revision metadata for an official archive without .git."""
import hashlib,json,sys,re
from pathlib import Path
source=Path(sys.argv[1]).resolve()
revision=sys.argv[2]
if not re.fullmatch(r'[a-f0-9]{40}',revision):raise ValueError('Expected fixed upstream SHA')
file=source/'CMake'/'ctkVersionSource.cmake'
if file.exists():
    text=file.read_text()
    variable=re.search(r'set\((\w+_VERSION_SOURCE) "unknown"\)',text)
    if not variable:raise RuntimeError('Unsupported version metadata script')
    if '# CT3D_ARCHIVE_METADATA' not in text:
        header=f'''# CT3D_ARCHIVE_METADATA: upstream archive without Git working tree.
if(NOT EXISTS "${{CMAKE_SOURCE_DIR}}/.git/HEAD")
  set({variable[1]} "g{revision[:7]}-archive")
  return()
endif()
'''
        file.write_text(header+text,encoding='utf-8')

# CTK's nested superbuild also defaults to Git clones. Change only the source
# transport, retaining the revisions parsed from the pinned CTK archive.
if source.name == 'CTK':
    root=Path(__file__).resolve().parents[1]
    lock=root/'build-support'/'ctk-archive-lock.json'
    for record in json.loads(lock.read_text()):
        archive=Path(record['archive'])
        if hashlib.sha256(archive.read_bytes()).hexdigest() != record['sha256']:
            raise RuntimeError('Nested archive checksum mismatch: '+record['project'])
        file=source/'CMakeExternals'/(record['project']+'.cmake')
        text=file.read_text()
        marker='# CT3D_VERIFIED_NESTED_ARCHIVE'
        if marker in text:continue
        pattern=r'  set\(location_args \).*?\n  endif\(\)'
        replacement=f'''  {marker}
  set(location_args URL "{archive.as_posix()}"
                    URL_HASH "SHA256={record['sha256']}"
                    DOWNLOAD_EXTRACT_TIMESTAMP TRUE UPDATE_COMMAND "")'''
        text,count=re.subn(pattern,lambda _:replacement,text,count=1,flags=re.S)
        if count != 1:raise RuntimeError('Unsupported nested source pattern: '+record['project'])
        file.write_text(text,encoding='utf-8')
