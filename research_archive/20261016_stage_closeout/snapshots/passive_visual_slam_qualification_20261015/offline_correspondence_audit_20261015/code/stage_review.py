import pathlib,csv,json,numpy as np
N=pathlib.Path(__file__).resolve().parents[1];rows=list(csv.DictReader((N/'results/matches.csv').open()));pairs=list(csv.DictReader((N/'results/pairs.csv').open()));out=[]
for p in pairs:
 for stage in ['forward_NN','mutual_NN','forward_ratio','mutual_ratio']:
  sel=[r for r in rows if r['pair']==p['pair'] and (stage=='forward_NN' or r[stage]=='1')]
  for group in ['PP','BB','PU','UP','PB','BP','UU','BU','UB']:
   s=[r for r in sel if r['group']==group];v=[r for r in s if r['valid_3D']=='1'];out.append({'pair':p['pair'],'window':p['window'],'stage':stage,'group':group,'matches':len(s),'valid3D':len(v),'inconsistent':sum(r['consistent_primary']=='0' for r in v),'reprojection_median_px':float(np.median([float(r['reprojection_px']) for r in v])) if v else None})
with (N/'results/matching_stages.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
