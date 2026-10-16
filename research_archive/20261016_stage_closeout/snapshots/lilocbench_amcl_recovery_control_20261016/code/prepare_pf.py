from pathlib import Path
import json,subprocess,hashlib,difflib
p=Path(__file__).resolve().parents[1];b=Path('/home/wcqw/lilocbench_amcl_validation_20261016');src=b/'diagnostic_ws_v2/src/amcl';orig=(p/'sources/pf_v2_original.c').read_text();s=orig;edits=[]
def edit(old,new):
 global s
 assert s.count(old)==1,(old,s.count(old));s=s.replace(old,new);edits.append((old,new))
edit('  set->n_effective = 1.0/set->n_effective;\n  return;', '''  set->n_effective = 1.0/set->n_effective;
  /* AUDIT_BEGIN: read-only post-normalization statistics. */
  {
    int audit_nonfinite = 0;
    double audit_max_weight = 0.0, audit_sum_weight = 0.0;
    for (int audit_i = 0; audit_i < set->sample_count; ++audit_i) {
      double audit_weight = set->samples[audit_i].weight;
      if (!isfinite(audit_weight)) ++audit_nonfinite;
      if (audit_weight > audit_max_weight) audit_max_weight = audit_weight;
      audit_sum_weight += audit_weight;
    }
    fprintf(stderr, "RECOVERY_SENSOR %.17g %d %.17g %.17g %.17g %.17g %.17g %d %d %d\\n",
      total, set->sample_count, set->n_effective, pf->w_slow, pf->w_fast,
      audit_max_weight, audit_sum_weight, total == 0.0, !isfinite(total), audit_nonfinite);
  }
  /* AUDIT_END */
  return;''')
edit('  double w_diff;\n', '  double w_diff;\n  int audit_random_count = 0; /* AUDIT: local counter, no RNG call. */\n')
edit('  //printf("w_diff: %9.6f\\n", w_diff);', '''  //printf("w_diff: %9.6f\\n", w_diff);
  /* AUDIT_BEGIN */
  fprintf(stderr, "RECOVERY_RESAMPLE_BEGIN %.17g %.17g %.17g %d %.17g\\n",
    w_diff, pf->w_slow, pf->w_fast, set_a->sample_count, set_a->n_effective);
  /* AUDIT_END */''')
edit('    if(drand48() < w_diff)\n      sample_b->pose = (pf->random_pose_fn)(pf->random_pose_data);', '''    if(drand48() < w_diff)
    {
      ++audit_random_count; /* AUDIT: existing branch only. */
      sample_b->pose = (pf->random_pose_fn)(pf->random_pose_data);
    }''')
edit('  pf_update_converged(pf);\n\n  free(c);', '''  pf_update_converged(pf);
  /* AUDIT_BEGIN */
  fprintf(stderr, "RECOVERY_RESAMPLE_END %d %d %.17g %.17g %d\\n",
    audit_random_count, set_b->sample_count, pf->w_slow, pf->w_fast, set_b->cluster_count);
  /* AUDIT_END */

  free(c);''')
restored=s
for old,new in reversed(edits):assert restored.count(new)==1;restored=restored.replace(new,old)
assert restored==orig
assert s.count('drand48()')==orig.count('drand48()')
(p/'sources/pf.c').write_text(s)
(p/'audit/recovery_readonly.patch').write_text(''.join(difflib.unified_diff(orig.splitlines(True),s.splitlines(True),fromfile='v2/pf.c',tofile='recovery_stats/pf.c')))
flags=['/usr/bin/cc','-O3','-DNDEBUG','-fPIC','-DHAVE_DRAND48','-DHAVE_UNISTD_H','-DROSCONSOLE_BACKEND_LOG4CXX','-DROS_BUILD_SHARED_LIBS=1','-DROS_PACKAGE_NAME="amcl"','-Damcl_pf_EXPORTS','-I'+str(src/'include'),'-I'+str(src/'src/include'),'-c',str(p/'sources/pf.c'),'-o',str(p/'build/pf.c.o')]
subprocess.run(flags,check=True)
obj=b/'diagnostic_ws_v2/build/amcl/CMakeFiles/amcl_pf.dir/src/amcl/pf'
others=[obj/x for x in ['pf_kdtree.c.o','pf_pdf.c.o','pf_vector.c.o','eig3.c.o','pf_draw.c.o']]
link=['/usr/bin/cc','-fPIC','-O3','-DNDEBUG','-shared','-Wl,-soname,libamcl_pf.so','-o',str(p/'lib/libamcl_pf.so'),str(p/'build/pf.c.o')]+list(map(str,others))
subprocess.run(link,check=True)
(p/'audit/build.json').write_text(json.dumps({'compile':flags,'link':link,'reverse_edits_restore_v2_exactly':True,'RNG_call_text_unchanged':True,'unchanged_old_object_sha256':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in others},'scope':'Only pf.c rebuilt, old executable/sensors/map and pf_pdf allocator reused unchanged; no algorithm or sampling formulas modified; no claim of universal timing equivalence'},indent=2))
print('BUILD and structural patch reversal PASS')
