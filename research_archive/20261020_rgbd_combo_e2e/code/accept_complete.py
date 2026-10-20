"""Offline acceptance of the one official sequence; no network requests."""
from pathlib import Path
import sys,json,zipfile,hashlib,shutil
P=Path(__file__).resolve().parents[1];source=Path(sys.argv[1]);old=Path('/home/wcqw/passive_motion_evidence_20261019/data/rgbd_bonn_moving_obstructing_box.zip.partial');assert source.stat().st_size==320845314
# The already authenticated official prefix must be byte-identical.
with source.open('rb') as f:prefix=hashlib.sha256(f.read(old.stat().st_size)).hexdigest()
assert prefix==hashlib.sha256(old.read_bytes()).hexdigest(),'Official prefix mismatch'
with zipfile.ZipFile(source) as z:
 assert z.testzip() is None;size=sum(i.file_size for i in z.infolist());assert shutil.disk_usage(P).free-size>5*1024**3
 for i in z.infolist():assert not Path(i.filename).is_absolute() and '..' not in Path(i.filename).parts
 assert not list((P/'data').glob('**/rgb.txt')),'Do not overwrite existing extracted data'
 z.extractall(P/'data')
(P/'audit/data_acquisition.json').write_text(json.dumps({'qualified':True,'source':'Official Bonn URL file supplied offline, exact previously fetched official prefix and ZIP CRC verified','file':str(source),'bytes':source.stat().st_size,'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'CRC':'PASS','uncompressed_bytes':size},indent=2))
print('Offline full sequence accepted. Next prepare.py; does not run SLAM.')
