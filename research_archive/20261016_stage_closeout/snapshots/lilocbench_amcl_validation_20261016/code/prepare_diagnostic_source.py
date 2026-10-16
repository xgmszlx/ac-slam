from pathlib import Path
import shutil,subprocess,json
p=Path(__file__).resolve().parents[1]
original=next((p/'sources/pristine').glob('navigation-*'))/'amcl'
new=p/'diagnostic_ws/src/amcl';shutil.copytree(original,new)
# Fixed random seeds control only pseudo-random initialization, not motion/measurement formulas.
f=new/'src/amcl/pf/pf.c';s=f.read_text();assert s.count('srand48(time(NULL));')==1
s=s.replace('srand48(time(NULL));','/* Experimental reproducibility control; default remains native wall-time seed. */\n  const char *audit_seed_env = getenv("AMCL_EXPERIMENT_SEED");\n  long audit_seed = audit_seed_env ? strtol(audit_seed_env, NULL, 10) : (long)time(NULL);\n  srand48(audit_seed);\n  fprintf(stderr, "AUDIT_SEED %ld\\n", audit_seed);')
s=s.replace('#include <time.h>','#include <time.h>\n#include <stdio.h>');f.write_text(s)
# Exact scan identity immediately before the native sensor update. One front laser only.
f=new/'src/amcl_node.cpp';s=f.read_text();key='    lasers_[laser_index]->UpdateSensor(pf_, (AMCLSensorData*)&ldata);';assert s.count(key)==1
s=s.replace(key,'    fprintf(stderr, "AUDIT_SCAN %u %u %u %d %d\\n", laser_scan->header.seq, laser_scan->header.stamp.sec, laser_scan->header.stamp.nsec, pf_->sets[pf_->current_set].sample_count, pf_->sets[pf_->current_set].converged);\n'+key);f.write_text(s)
# Read-only beam state: report native slot mask, physical sampled/valid beams and fallback.
f=new/'src/amcl/sensors/amcl_laser.cpp';s=f.read_text();key='  if(do_beamskip){\n    int skipped_beam_count = 0;';assert s.count(key)==1
s=s.replace(key,'  int audit_slots = (data->range_count + step - 1) / step;\n  int audit_valid = 0;\n  for (int ai=0; ai<data->range_count; ai+=step) {\n    if(data->ranges[ai][0] == data->ranges[ai][0] && data->ranges[ai][0] < data->range_max) ++audit_valid;\n  }\n  if (!do_beamskip) fprintf(stderr, "AUDIT_BEAMS %d %d %d 0 %d %d -1 -1 0\\n", self->do_beamskip, set->converged, set->sample_count, audit_slots, audit_valid);\n'+key)
key='    for (j = 0; j < set->sample_count; j++)\n      {';assert s.count(key)==1
s=s.replace(key,'    int audit_physical_skipped = 0;\n    for(int ai=0; ai<audit_slots; ++ai) if(!obs_mask[ai]) ++audit_physical_skipped;\n    fprintf(stderr, "AUDIT_BEAMS %d %d %d 1 %d %d %d %d %d\\n", self->do_beamskip, set->converged, set->sample_count, audit_slots, audit_valid, skipped_beam_count, audit_physical_skipped, error);\n'+key);f.write_text(s)
with (p/'audit/amcl_diagnostic.patch').open('w') as out:
 r=subprocess.run(['diff','-ruN',str(original),str(new)],stdout=out)
 assert r.returncode==1
print(new)
