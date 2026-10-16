"""Mechanical change-scope checks. Not estimator numerical-equivalence certification."""
from pathlib import Path
import json,re
p=Path(__file__).resolve().parents[1];a=next((p/'sources/pristine').glob('navigation-*'))/'amcl';b=p/'diagnostic_ws/src/amcl'
changed=[]
for f in a.rglob('*'):
 if f.is_file() and f.read_bytes()!=(b/f.relative_to(a)).read_bytes():changed.append(str(f.relative_to(a)))
assert sorted(changed)==sorted(['src/amcl/pf/pf.c','src/amcl/sensors/amcl_laser.cpp','src/amcl_node.cpp'])
# Strip the added diagnostics/control exactly, and require all original text back.
f='src/amcl/pf/pf.c';s=(b/f).read_text();s=s.replace('#include <stdio.h>\n','');s=re.sub(r'  /\* Experimental reproducibility control; default remains native wall-time seed\. \*/[\s\S]*?fprintf\(stderr, "AUDIT_SEED %ld\\n", audit_seed\);','  srand48(time(NULL));',s);assert s==(a/f).read_text()
f='src/amcl_node.cpp';s=(b/f).read_text();s='\n'.join(x for x in s.split('\n') if 'AUDIT_SCAN ' not in x);assert s==(a/f).read_text()
f='src/amcl/sensors/amcl_laser.cpp';s=(b/f).read_text();s=re.sub(r'  int audit_slots =[\s\S]*?\n  if\(do_beamskip\)\{','  if(do_beamskip){',s);s=re.sub(r'    int audit_physical_skipped =[\s\S]*?\n    for \(j = 0;','    for (j = 0;',s);assert s==(a/f).read_text()
observer=(p/'code/collect_amcl.py').read_text();runner=(p/'code/run_native_offline.py').read_text()
assert 'gt_poses' not in observer and 'gt_poses' not in runner
assert 'initialpose' not in observer.split('import rospy',1)[-1]
result={'only_three_source_files_changed':'PASS','remove_control_and_read_only_logs_recovers_original_text_exactly':'PASS','GT_files_not_read_by_online_runner_or_observer':'PASS','scope':'source/transport qualification, not a numerical-equality claim','physical_sample_slots_811_max100':(811+8)//9,'unused_allocated_slots':100-(811+8)//9}
(p/'audit/minimal_patch_tests.json').write_text(json.dumps(result,indent=2));print(result)
