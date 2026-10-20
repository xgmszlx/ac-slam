from pathlib import Path
import json,re,csv,numpy as np
D=Path(__file__).resolve().parents[1];out={}
for tag in ['M0_02','M0_03','M0_04','M0_05']:
 R=D/'results'/tag;f=json.loads((R/'frozen.json').read_text());assoc=Path(f['item']['sequence'])/'associations.txt';stamps=[x.split()[0] for x in assoc.read_text().splitlines() if x.strip() and not x.startswith('#')]
 a=np.array([float(x) for x in re.findall(r'Average processing time of GrabImageRGBD\(\): ([\d.eE+-]+)ms',(R/'stdout.log').read_text())]);assert len(a)==len(stamps)
 # Tracking source increments mFrameNum before reporting cumulative time/(mFrameNum-1); denominator follows call count.
 delta=np.diff(np.r_[0,a*np.arange(1,len(a)+1)])
 with (R/'derived_Grab_stage_times.csv').open('w') as file:
  w=csv.writer(file);w.writerow(['input_stamp','call_index','printed_cumulative_mean_ms','derived_stage_time_ms']);w.writerows(zip(stamps,range(len(a)),a,delta))
 out[tag]={'calls':len(a),'mean_ms':float(delta.mean()),'median_ms':float(np.median(delta)),'p95_ms':float(np.quantile(delta,.95)),'max_ms':float(delta.max()),'negative_reconstructions':int(sum(delta<0)),'approximate_calls_over_33ms':int(sum(delta>33)),'warning':'reconstructed from rounded cumulative native text; not raw independent per-frame timing; excludes preprocessing before track_start, disk reads, pacing and separate detector execution'}
(D/'results/derived_Grab_stage_time_summary.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
