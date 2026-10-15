"""Local QA references decoded by the freshly compiled upstream DCMTK."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

import numpy as np
import pydicom
from pydicom.pixels import apply_modality_lut

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r"D:\dicom文件\dcm")
OUT = ROOT / "verification" / "native-mr-reference"
OUT.mkdir(parents=True, exist_ok=True)
decoder = Path(os.environ.get("CT3D_REFERENCE_DECODER", str(ROOT / "b" / "DCMTK-build" / "bin" / "Release" / "dcmdjpeg.exe")))
if not decoder.is_file():
    raise RuntimeError("Compiled DCMTK JPEG decoder is not available")
environment = dict(os.environ)
library_dirs = (decoder.parent, ROOT / "b" / "zlib-install" / "bin", ROOT / "b" / "OpenJPEG-install" / "bin", ROOT / "b" / "OpenSSL-install" / "bin")
environment["PATH"] = os.pathsep.join(map(str, library_dirs)) + os.pathsep + environment.get("PATH", "")
files = sorted(SOURCE.glob("*.dcm"))
before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
records = []
for path in files:
    digest = before[str(path)]
    # ASCII temporary names keep this reference CLI independent of Chinese argv handling.
    temporary_directory = tempfile.TemporaryDirectory(prefix="ct3d-reference-")
    temporary_input = Path(temporary_directory.name) / "decoder-input.dcm"
    temporary_output = Path(temporary_directory.name) / "decoder-output.dcm"
    temporary_input.write_bytes(path.read_bytes())
    process = subprocess.run([str(decoder), "-q", str(temporary_input), str(temporary_output)], env=environment, capture_output=True)
    if process.returncode:
        raise RuntimeError(f"DCMTK reference decode failed ({process.returncode}): {process.stderr.decode(errors='replace')}")
    ds = pydicom.dcmread(temporary_output)
    pixels = apply_modality_lut(ds.pixel_array, ds)
    np.savez_compressed(OUT / (digest + ".npz"), pixels=pixels)
    records.append({"source_sha256": digest, "shape": list(pixels.shape), "dtype": str(pixels.dtype)})
    temporary_input.unlink()
    temporary_output.unlink()
    temporary_directory.cleanup()
after = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
if before != after:
    raise AssertionError("Source DICOM changed while preparing references")
(OUT / "manifest.json").write_text(json.dumps({"status": "passed", "reference_decoder": "DCMTK/dcmdjpeg", "upstream_revision": "2dd54ca1c28100b820ccf1383a0948e889246f96", "scope": "local QA only; references excluded from release", "source_unchanged": True, "records": records}, indent=2), encoding="utf-8")
print("Prepared verified lossless references:", len(records))
