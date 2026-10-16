"""Offline geometric qualification from observed map only; never reads GT."""
from pathlib import Path
import csv,hashlib,json,math
import numpy as np
from PIL import Image
from scipy import ndimage

R=Path(__file__).resolve().parents[1]
SOURCE=Path('/home/wcqw/ac-slam/results/phase1/smoke_A_nearest_frontier_map3_run1')


def ray_free(free,start,end):
    n=max(abs(int(start[0])-int(end[0])),abs(int(start[1])-int(end[1])))+1
    rows=np.rint(np.linspace(start[0],end[0],n)).astype(int)
    cols=np.rint(np.linspace(start[1],end[1],n)).astype(int)
    return bool(np.all(free[rows,cols]))


def analyze(image,resolution=.1):
    free=image>=250;unknown=(image>10)&(image<250);occupied=image<=10
    boundary=free & ndimage.binary_dilation(unknown,structure=ndimage.generate_binary_structure(2,1))
    labels,count=ndimage.label(boundary,structure=np.ones((3,3)))
    distance=ndimage.distance_transform_edt(np.pad(free,1))[1:-1,1:-1]*resolution
    safe=free & (distance>=.5)
    component,ncomp=ndimage.label(safe)
    sizes=np.bincount(component.ravel());sizes[0]=0
    largest=component==int(np.argmax(sizes)) if ncomp else np.zeros_like(safe)
    occupied_distance=ndimage.distance_transform_edt(~occupied)*resolution
    entries=[]
    for label in range(1,count+1):
        points=np.argwhere(labels==label)
        if len(points)<4:continue
        center=points.mean(axis=0);representative=points[np.argmin(np.sum((points-center)**2,axis=1))]
        _,_,axes=np.linalg.svd(points-center,full_matrices=False)
        projection=(points-center)@axes[0];ends=points[[int(np.argmin(projection)),int(np.argmax(projection))]]
        flanks=[float(occupied_distance[tuple(point)]) for point in ends]
        entries.append({'id':len(entries),'type':'B_GEOMETRIC_HINT' if max(flanks)<=.3 else 'A_KNOWN_FRONTIER',
                        'cells':len(points),'row':int(representative[0]),'col':int(representative[1]),'flank_distances_m':flanks})
    potential=set();step=5
    for entry in entries:
        rr,cc=entry['row'],entry['col'];radius=30
        for row in range(max(0,rr-radius)//step*step,min(image.shape[0],rr+radius+1),step):
            for col in range(max(0,cc-radius)//step*step,min(image.shape[1],cc+radius+1),step):
                d=math.hypot(row-rr,col-cc)*resolution
                if .75<=d<=3 and largest[row,col] and ray_free(free,(row,col),(rr,cc)):potential.add((row,col))
    # Coordinate cap is fixed before reading outcomes, not chosen for best coverage.
    potential=sorted(potential)[:256];views=[]
    for row,col in potential:
        visible=[e['id'] for e in entries if math.hypot(row-e['row'],col-e['col'])*resolution<=3
                 and ray_free(free,(row,col),(e['row'],e['col']))]
        if visible:views.append({'row':row,'col':col,'clearance_m':float(distance[row,col]),'visible_ids':visible})
    pair=None
    for i,a in enumerate(views):
        for j in range(i+1,len(views)):
            b=views[j]
            if a['visible_ids']!=b['visible_ids'] and math.hypot(a['row']-b['row'],a['col']-b['col'])*resolution>=.5:
                pair=[i,j];break
        if pair is not None:break
    return entries,views,pair,safe


def main():
    source=SOURCE/'final_map.pgm';image=np.asarray(Image.open(source).convert('L'))
    entries,views,pair,safe=analyze(image)
    result={'input':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'shape':list(image.shape),
            'candidate_count':len(entries),'type_B_count':sum(e['type']=='B_GEOMETRIC_HINT' for e in entries),
            'safe_clearance_cells':int(safe.sum()),'geometric_views':len(views),
            'distinct_predicted_visibility_sets':len({tuple(v['visible_ids']) for v in views}),
            'different_view_pair':pair,'geometric_action_space':'TWO_DIFFERENT_VIEWS' if pair is not None else 'ACTION_SPACE_INSUFFICIENT_IN_THIS_SNAPSHOT',
            'runtime_safety':'UNQUALIFIED_NO_CURRENT_COSTMAP_OR_TIME_PAIRED_ROBOT_POSE',
            'missed_entrance_recall':'UNKNOWN_NO_CORRESPONDING_ROOM_TRUTH','false_positive_rate':'UNKNOWN',
            'hidden_type_C':'UNDETECTABLE_IF_NO_ONLINE_GEOMETRIC_CLUE',
            'known_metadata_issue':'Original PGM yaml yaw is NaN; recorded origin quaternion is all zeros. No silent coordinate repair; image-local geometry only.',
            'GT_used_in_candidate_generation':False,'entrances':entries,'views':views}
    (R/'results/phase1_candidates.json').write_text(json.dumps(result,indent=2))
    with (R/'data/geometric_views.csv').open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['row','col','clearance_m','visible_ids']);writer.writeheader();writer.writerows(views)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(8,8));ax.imshow(image,cmap='gray',vmin=0,vmax=255)
    if entries:ax.scatter([e['col'] for e in entries],[e['row'] for e in entries],c='red',s=12,label='Frontier proposal')
    if views:ax.scatter([v['col'] for v in views],[v['row'] for v in views],c='lime',s=4,label='Geometric view only')
    if pair:
        for i,color in zip(pair,['blue','magenta']):
            v=views[i];ax.scatter(v['col'],v['row'],c=color,s=60)
            for eid in v['visible_ids']:
                e=entries[eid];ax.plot([v['col'],e['col']],[v['row'],e['row']],color=color,alpha=.6)
    ax.set_title('Observed Karto map: geometry only; runtime safety unqualified')
    ax.set_xlabel('Original image column (0.1m/cell)');ax.legend(loc='upper right');fig.tight_layout()
    fig.savefig(R/'figures/phase1_native_candidates.png',dpi=130);plt.close(fig)
    print(json.dumps({k:v for k,v in result.items() if k not in ('entrances','views')},indent=2))


if __name__=='__main__':main()
