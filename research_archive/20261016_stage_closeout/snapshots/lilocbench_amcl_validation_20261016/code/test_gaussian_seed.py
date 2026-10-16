"""Check RNG at the actual Gaussian allocator, independently of an SLAM/ROS run."""
from pathlib import Path
import ctypes as c,json,os
p=Path(__file__).resolve().parents[1]
class Vec(c.Structure):_fields_=[('v',c.c_double*3)]
class Mat(c.Structure):_fields_=[('m',(c.c_double*3)*3)]
lib=c.CDLL(str(p/'diagnostic_ws_v2/devel/lib/libamcl_pf.so'));lc=c.CDLL(None)
lc.srand48.argtypes=[c.c_long];lc.drand48.restype=c.c_double
lib.pf_pdf_gaussian_alloc.argtypes=[Vec,Mat];lib.pf_pdf_gaussian_alloc.restype=c.c_void_p;lib.pf_pdf_gaussian_free.argtypes=[c.c_void_p]
v=Vec();m=Mat()
for i in range(3):m.m[i][i]=1.
res=[]
for counter,seed in enumerate([1702,1702],1):
 os.environ['AMCL_EXPERIMENT_SEED']=str(seed);lc.srand48(seed+counter-1);expected=[lc.drand48() for _ in range(4)]
 ptr=lib.pf_pdf_gaussian_alloc(v,m);actual=[lc.drand48() for _ in range(4)];lib.pf_pdf_gaussian_free(ptr)
 assert actual==expected
 res.append({'allocator_call':counter,'expected_effective_seed':seed+counter-1,'uniform_draws_exactly_equal':True,'first_four':actual})
(p/'audit/gaussian_seed_test.json').write_text(json.dumps({'scope':'Gaussian RNG reseed-point qualification; not full trajectory determinism proof','status':'PASS','results':res},indent=2));print('PASS',res)
