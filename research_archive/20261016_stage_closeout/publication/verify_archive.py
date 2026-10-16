"""Publication/evidence consistency checks only. No SLAM execution."""
from pathlib import Path
import ast,csv,json,hashlib,re
ROOT=Path(__file__).resolve().parents[1];SNAP=ROOT/'snapshots'
def j(p):return json.loads((SNAP/p).read_text())
def csvrows(p):return list(csv.DictReader((SNAP/p).open()))
def main():
 inv=json.loads((ROOT/'publication/source_inventory.json').read_text());included=[r for r in inv['records'] if r['included']]
 for r in included:
  rel=Path(r['root'])/r['path'];pub=SNAP/rel;source=Path('/home/wcqw')/rel
  assert hashlib.sha256(pub.read_bytes()).hexdigest()==r['sha256'],pub
  assert hashlib.sha256(source.read_bytes()).hexdigest()==r['sha256'],source
 assert len(list(p for p in SNAP.rglob('*') if p.is_file()))==len(included)
 py=list(ROOT.rglob('*.py'))
 for p in py:ast.parse(p.read_text())
 rows=csvrows('lilocbench_aggregation_control_20261016/results/full_comparison.csv');d={x['condition']:x for x in rows}
 for name,value in [('A0 91 R0',.4453530932925367),('A1 R0',6.141905575189013),('A0 102 ON',.43175831206353943)]:
  assert abs(float(d[name]['official_position_RMSE_m'])-value)<1e-12
  assert int(d[name]['processed_sensor_updates'])==708 and int(d[name]['collector_scan_count'])==6540
 v=csvrows('passive_visual_slam_qualification_20261015/diagnostic_comparison_20261015/results/summary.csv');w=[x for x in v if x['sequence']=='walking' and x['tag'].startswith('P1_')];assert len(w)==3
 assert all(float(x['coverage'])==1 and .4136<float(x['ATE'])<.4376 for x in w)
 bad=next(x for x in v if x['tag']=='P0_02');assert bad['multiple_map_gauge_warning']=='True' and float(bad['coverage'])<.9
 a=j('passive_visual_slam_v3_cables3_20261015/DECISION.json');assert a['B0_runs']==a['B1_runs']==0
 z=csvrows('slam_stage_closeout_20261016/results/scan_diagnostics.csv');assert len(z)==27;assert all(float(x['native_additive_log_score_est_minus_GT'])<0 for x in z)
 assert j('slam_stage_closeout_20261016/DECISION.json')['overall']=='NO_METHOD_READY'
 assert j('slam_stage_closeout_20261016/DECISION.json')['L1']=='L1_NOT_YET_JUSTIFIED'
 calls=j('v3_cables3_data_gate_20261016/audit/download_results.json');assert len(calls)==2 and all(x['returncode']==35 and x['bytes_on_disk']==0 for x in calls)
 prohibited={'.bag','.db','.tar','.gz','.zip','.pdf','.pyc','.so','.o','.npz','.npy','.h5','.onnx','.caffemodel','.partial'}
 assert not [p for p in ROOT.rglob('*') if p.is_file() and p.suffix.lower() in prohibited]
 # Check credential-shaped values without logging contents. Hashes are deliberately not generic entropy-scanned.
 patterns=[r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----',r'gh[pousr]_[A-Za-z0-9]{30,}',r'github_pat_[A-Za-z0-9_]{30,}',r'AKIA[0-9A-Z]{16}',r'https?://[^\s/@:]+:[^\s/@]+@']
 suspicious=[]
 for p in ROOT.rglob('*'):
  if not p.is_file() or p.suffix=='.png' or p.name=='verify_archive.py':continue
  s=p.read_text(errors='replace')
  if any(re.search(q,s) for q in patterns):suspicious.append(str(p.relative_to(ROOT)))
 assert not suspicious,suspicious
 links=[]
 for p in ROOT.rglob('*.md'):
  for ref in re.findall(r'\]\(([^\n]+?)\)',p.read_text()):
   ref=ref.split(' "')[0].strip('<>')
   if re.match(r'^[a-z]+://',ref) or ref.startswith('#'):continue
   q=(p.parent/ref.split('#')[0]);exists=q.exists();links.append({'document':str(p.relative_to(ROOT)),'target':ref,'exists':exists,'category':'published_or_external_local_exists' if exists else 'omitted_local_attachment_or_original_relative_path'})
 # Fresh navigation must be self-contained; historical byte-exact reports retain omissions.
 assert all(x['exists'] for x in links if x['document'] in {'README.md','PUBLICATION_SCOPE.md'}),[x for x in links if not x['exists'] and x['document']=='README.md']
 (ROOT/'publication/link_audit.json').write_text(json.dumps({'links':links,'note':'Historical snapshots preserve original links. Missing attachments are not silently claimed public.'},ensure_ascii=False,indent=2))
 result={'status':'PASS','byte_exact_selected_files':len(included),'included_bytes':inv['included_bytes'],'report_count':len(list(SNAP.rglob('REPORT.md'))),'python_AST_files':len(py),'checks':['source and published hashes identical','AMCL final comparison and same input counts','three correct-format walking runs and failed P0 identity retained','V3 no scientific runs; both latest transfer failures retained','all 27 A0 diagnostic scans retain GT-higher scores','NO_METHOD_READY and L1_NOT_YET_JUSTIFIED preserved','prohibited artifacts and credential-shaped strings absent','new index local links valid; historical omissions documented'],'scope':'Archive/evidence consistency only, not scientific replication or standalone deployment'}
 (ROOT/'publication/archive_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
