"""Supply explicit provenance for pinned archives, without inventing a Git checkout."""
from pathlib import Path
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
lock = json.loads((ROOT / "desktop/upstream-lock.json").read_text(encoding="utf-8-sig"))
metadata = json.loads((ROOT / "desktop/archive-provenance.json").read_text(encoding="utf-8-sig"))
if metadata["slicer"]["revision"] != lock["slicer"]:
    raise RuntimeError("Archive provenance does not match the locked Slicer commit")
for directory, record in ((ROOT / "core", metadata["slicer"]), (ROOT / "desktop", metadata["ct3d"])):
    if (directory / ".git").exists():
        raise RuntimeError("Use repository metadata for Git checkouts; do not override it")
    lines = []
    for name, value in record.items():
        if name not in ("revision", "date", "url"):
            continue
        if any(char in value for char in ('"', '\\', ';', '\n', '\r')):
            raise RuntimeError("Unsafe CMake provenance value")
        lines.append(f'set(CT3D_ARCHIVE_{name.upper()} "{value}")')
    (directory / "CT3DArchiveMetadata.cmake").write_text("\n".join(lines) + "\n", encoding="utf-8")

macro = ROOT / "core/CMake/SlicerMacroExtractRepositoryInfo.cmake"
backup = ROOT / "build-support/upstream-external-backups/SlicerMacroExtractRepositoryInfo.cmake"
if not backup.exists():
    shutil.copy2(macro, backup)
text = backup.read_text(encoding="utf-8-sig")
anchor = '    message(AUTHOR_WARNING "Skipping ${MY_VAR_PREFIX} repository info extraction: directory [${MY_SOURCE_DIR}] is not a GIT checkout")'
replacement = '''    # CT3D: retain archive provenance while explicitly reporting no Git history.
    if(EXISTS "${MY_SOURCE_DIR}/CT3DArchiveMetadata.cmake")
      include("${MY_SOURCE_DIR}/CT3DArchiveMetadata.cmake")
      set(${wc_info_prefix}_WC_TYPE "archive")
      set(${wc_info_prefix}_WC_URL "${CT3D_ARCHIVE_URL}")
      set(${wc_info_prefix}_WC_ROOT "${CT3D_ARCHIVE_URL}")
      set(${wc_info_prefix}_WC_REVISION "${CT3D_ARCHIVE_REVISION}")
      set(${wc_info_prefix}_WC_REVISION_NAME "${CT3D_ARCHIVE_REVISION}")
      set(${wc_info_prefix}_WC_REVISION_HASH "${CT3D_ARCHIVE_REVISION}")
      set(${wc_info_prefix}_WC_LAST_CHANGED_DATE "${CT3D_ARCHIVE_DATE}")
      # No repository history is present; display the explicit revision instead.
      set(${wc_info_prefix}_WC_COMMIT_COUNT 0)
    else()
''' + anchor + '\n    endif()'
if text.count(anchor) != 1:
    raise RuntimeError("Unexpected upstream repository metadata macro")
macro.write_text(text.replace(anchor, replacement), encoding="utf-8")
print("Archive provenance prepared; no Git checkout or history fabricated")
