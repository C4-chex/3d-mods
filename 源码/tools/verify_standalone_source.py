import ast, json, importlib.util, os, pathlib, subprocess, zipfile
root=pathlib.Path(__file__).resolve().parents[1]
checks=[]
def check(name,condition):
    checks.append({'name':name,'passed':bool(condition)})
    if not condition: raise AssertionError(name)
try:
    for p in (root/'CT3D').rglob('*.py'): ast.parse(p.read_text(encoding='utf-8-sig'))
    check('all_module_python_syntax_valid',True)
    for p in (root/'desktop').rglob('*'):
        if p.suffix in ('.cxx','.h','.txt','.cmake','.qrc','.ini'):
            text=p.read_text()
            check('rendered_'+str(p.relative_to(root)), '{{cookiecutter' not in text and '{% github' not in text)
    cmake=(root/'desktop'/'CMakeLists.txt').read_text()
    check('pinned_kernel',json.loads((root/'desktop'/'upstream-lock.json').read_text())['slicer'] in cmake)
    provenance=json.loads((root/'desktop'/'archive-provenance.json').read_text(encoding='utf-8-sig'))
    check('archive_provenance_matches_kernel_lock',provenance['slicer']['revision']==json.loads((root/'desktop'/'upstream-lock.json').read_text())['slicer'])
    build_number=provenance['ct3d']['local_build_number']
    check('local_build_number_fits_mrml_integer',isinstance(build_number,int) and 0 < build_number < 2**31)
    check('local_build_number_configured',f'set(CT3DApp_WC_COMMIT_COUNT_OFFSET {build_number}' in cmake)
    check('archive_provenance_tool_packaged_source_exists',(root/'tools'/'prepare-archive-metadata.py').is_file())
    check('user_bat_forwards_arguments','%*' in (root/'启动 CT3D.bat').read_text(encoding='utf-8-sig'))
    check('home_ct3d','set(Slicer_DEFAULT_HOME_MODULE "CT3D")' in cmake)
    check('integrated_existing_module','${CT3DDesktop_SOURCE_DIR}/../CT3D' in cmake)
    check('dicom_and_python_retained','Slicer_BUILD_DICOM_SUPPORT' in cmake and 'Slicer_USE_PYTHONQT' in cmake)
    check('no_external_slicer_reference_main_launcher','SLICER_EXE' not in (root/'launch.bat').read_text())
    check('development_launcher_exists',(root/'tools'/'launch-development.bat').exists())
    paths=root/'CT3D'/'CT3DLib'/'CT3DPaths.py'
    spec=importlib.util.spec_from_file_location('paths_check',paths);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    previous=os.environ.pop('CT3D_WORKSPACE_ROOT',None)
    try:
        check('source_workspace_n2',pathlib.Path(mod.workspaceRoot())==root)
        os.environ['CT3D_WORKSPACE_ROOT']=str(root/'verification'/'override')
        check('explicit_workdir_override',pathlib.Path(mod.workspaceRoot())==root/'verification'/'override')
        os.environ.pop('CT3D_WORKSPACE_ROOT')
        mod.__file__=str(root/'verification'/'installed'/'lib'/'qt-scripted-modules'/'CT3DLib'/'CT3DPaths.py')
        check('installed_layout_writable_user_workspace',pathlib.Path(mod.workspaceRoot())==pathlib.Path.home()/'CT3D')
    finally:
        if previous is not None:os.environ['CT3D_WORKSPACE_ROOT']=previous
    if not (root/'runtime'/'CT3D.exe').exists():
        launch=subprocess.run(['cmd.exe','/d','/c',str(root/'launch.bat'),'--testing'],capture_output=True,text=True)
        check('unbuilt_launcher_fails_explicitly',launch.returncode==2 and 'not been built' in launch.stdout)
    else:
        check('built_runtime_has_native_launcher',(root/'runtime'/'CT3D.exe').read_bytes()[:2]==b'MZ')
    pre=json.loads((root/'verification'/'standalone-preflight.json').read_text(encoding='utf-8-sig'))
    check('compile_prerequisite_report_consistent',pre['ready']==(not bool(pre['missing'])))
    with zipfile.ZipFile(root/'dist'/'CT3D-desktop-source.zip') as z:
        names=z.namelist()
        check('custom_app_source_packaged','desktop/Applications/CT3DApp/Main.cxx' in names and 'CT3D/CMakeLists.txt' in names)
        check('local_slicer_config_excluded',not any('slicer-path.cmd' in n or 'legacy-slicer/' in n for n in names))
        check('download_build_runtime_excluded',not any(n.startswith(('build-support/','build/','b/','core/','runtime/','runtime-stage-','runtime-previous-','verification/')) for n in names))
        check('recovery_and_portability_tools_packaged',all(name in names for name in ('tools/prepare-archive-metadata.py','tools/run-native-portable-acceptance.ps1','desktop/archive-provenance.json')))
        check('input_output_only_readmes',[n for n in names if n.startswith(('input/','output/'))]==['input/README.md','output/README.md'])
    result={'status':'passed','scope':'source/configuration checks; no native compilation or standalone executable acceptance','checks':checks}
except Exception as error:
    result={'status':'failed','error':str(error),'checks':checks}
(root/'verification'/'standalone-source-results.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps({'status':result['status'],'checks':len(checks),'error':result.get('error')}))
