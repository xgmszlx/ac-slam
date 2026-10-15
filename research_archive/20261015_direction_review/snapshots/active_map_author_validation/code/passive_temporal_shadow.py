#!/usr/bin/env python3
"""B2 causal commit-layer shadow. Five DISTINCT processed scans, not duplicate map messages.
Does not replay altered recovery feedback; therefore not a full closed-loop B2 result.
"""
import argparse,collections,json
from pathlib import Path
import numpy as np
import rosbag
R=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('source');ap.add_argument('--world',required=True);args=ap.parse_args();src=Path(args.source);out=R/'results'/('B2_shadow_'+src.name);out.mkdir(exist_ok=False)
with (out/'frozen.json').open('x') as f:json.dump(dict(window=5,evidence='one latest available candidate map per distinct author processed-scan stamp; all five agree before commit',gt_role='evaluation only',feedback='original B0 pose/recovery stream fixed'),f,indent=2)
window=collections.deque(maxlen=5);latest=None;old=None;committed=None;seen=set();history=[]
with rosbag.Bag(str(src/'raw.bag')) as b:
    for topic,msg,t in b.read_messages():
        if topic=='/prior_map':old=np.array(msg.data).reshape(msg.info.height,msg.info.width)==100;committed=old.copy()
        elif topic=='/processed_map':latest=np.array(msg.data).reshape(msg.info.height,msg.info.width)==100
        elif topic=='/author_audit' and latest is not None and committed is not None:
            event=json.loads(msg.data);stamp=event['stamp']
            if stamp in seen:continue
            seen.add(stamp);window.append(latest.copy())
            if len(window)==5:
                a=np.array(window);same=np.all(a==a[0],axis=0);committed[same]=a[0][same]
            history.append(dict(stamp=stamp,committed_cells=int(np.count_nonzero(committed!=old)),event=event['event']))
# Hidden world only enters this final evaluation block.
truth=np.load(R/'protocol/scenes/truth_maps.npz')[args.world];changed=truth!=old;written=committed!=old
summary=dict(processed_observation_votes=len(seen),added_scans=0,added_motion=0,window=5,
             false_update_cells=int(np.count_nonzero(written&~changed)),correct_update_cells=int(np.count_nonzero(written&changed&(committed==truth))),map_error_cells=int(np.count_nonzero(committed!=truth)),
             evidence_scope='causal commit shadow only; altered-map recovery feedback not tested')
(out/'result.json').write_text(json.dumps(summary,indent=2));(out/'history.json').write_text(json.dumps(history,indent=2));np.savez_compressed(out/'final_map.npz',committed=committed);print(json.dumps(summary,indent=2))
