from pathlib import Path
import hashlib,json,re,shutil,sys,zipfile
root=Path(__file__).resolve().parents[1]
records=json.loads((root/'build-support'/'archive-lock.json').read_text())
backup=root/'build-support'/'upstream-external-backups';backup.mkdir(exist_ok=True)
cache=[];changed=[]
for record in records:
    name=record['project']
    if name == 'vtkAddon':
        archive_file=Path(record['archive'])
        if hashlib.sha256(archive_file.read_bytes()).hexdigest() != record['sha256']:
            raise RuntimeError('vtkAddon archive checksum mismatch')
        destination=root/'build-support'/'verified-sources'/'vtkAddon'
        destination.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(archive_file) as archive:
            prefix=archive.namelist()[0].split('/')[0]+'/'
            for member in archive.infolist():
                relative=member.filename.removeprefix(prefix)
                if not relative or member.is_dir():continue
                target=destination/relative
                if not target.resolve().is_relative_to(destination.resolve()):
                    raise RuntimeError('Archive path escapes verified source folder')
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(archive.read(member))
        cache.append('set(vtkAddon_SOURCE_DIR "R:/build-support/verified-sources/vtkAddon" CACHE PATH "Verified pinned vtkAddon source" FORCE)')
        changed.append(name)
        continue
    path=root/'core'/'SuperBuild'/('External_'+name+'.cmake')
    if not path.exists():continue
    original=path.read_text()
    # Use original once; all later updates derive from the unmodified pinned source.
    saved=backup/path.name
    if not saved.exists():shutil.copy2(path,saved)
    text=saved.read_text()
    pattern=r'    GIT_REPOSITORY "\$\{Slicer_\$\{proj\}_GIT_REPOSITORY\}"\s*\n    GIT_TAG "\$\{Slicer_\$\{proj\}_GIT_TAG\}"'
    replacement='    URL "${CT3D_ARCHIVE_'+name+'}"\n    URL_HASH "SHA256=${CT3D_ARCHIVE_SHA256_'+name+'}"\n    DOWNLOAD_EXTRACT_TIMESTAMP TRUE\n    UPDATE_COMMAND ""'
    if name in ('CTK','CTKAppLauncherLib'):
        replacement += '\n    PATCH_COMMAND "' + Path(sys.executable).as_posix() + '" "R:/tools/archive-version-metadata.py" <SOURCE_DIR> "' + record['tag'] + '"'
    text,n=re.subn(pattern,lambda _:replacement,text)
    if n!=1:raise RuntimeError('Unexpected dependency source pattern: '+name)
    text=text.replace('ExternalProject_GenerateProjectDescription_Step(${proj})',f'ExternalProject_GenerateProjectDescription_Step(${{proj}} VERSION "{record["tag"]}")')
    path.write_text(text,encoding='utf-8')
    archive=Path(record['archive']).as_posix().replace(root.as_posix(),'R:')
    cache += [f'set(CT3D_ARCHIVE_{name} "{archive}" CACHE FILEPATH "Verified upstream source archive" FORCE)',f'set(CT3D_ARCHIVE_SHA256_{name} "{record["sha256"]}" CACHE STRING "Pinned archive checksum" FORCE)']
    changed.append(name)
(root/'build-support'/'local-dependencies.cmake').write_text('\n'.join(cache)+'\n',encoding='utf-8')
(root/'build-support'/'archive-patches.json').write_text(json.dumps({'changed':changed,'scope':'only download/update mechanism and recorded upstream version; compiler/algorithm options unchanged'},indent=2),encoding='utf-8')
print('Patched download mechanism for',len(changed),'dependencies')
