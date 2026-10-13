"""Pure, offline SE(2) evaluation and an explicitly separate geometry proxy."""
import math
import numpy as np

def wrap(a): return math.atan2(math.sin(a), math.cos(a))
def compose(a,b):
    c,s=math.cos(a[2]),math.sin(a[2])
    return [a[0]+c*b[0]-s*b[1],a[1]+s*b[0]+c*b[1],wrap(a[2]+b[2])]
def inverse(a):
    c,s=math.cos(a[2]),math.sin(a[2])
    return [-c*a[0]-s*a[1],s*a[0]-c*a[1],-a[2]]
def between(a,b): return compose(inverse(a),b)
def error(est,gt): return math.hypot(est[0]-gt[0],est[1]-gt[1]),abs(wrap(est[2]-gt[2]))
def relative_error(e0,e1,g0,g1): return error(between(e0,e1),between(g0,g1))
def interpolate_gt(rows,stamp,max_gap=.15):
    import bisect
    times=[r['stamp'] for r in rows];i=bisect.bisect_left(times,stamp)
    if i<len(rows) and abs(times[i]-stamp)<1e-8:
        r=rows[i];return [r['x'],r['y'],r['theta']],0.
    if i==0 or i==len(rows):return None,None
    a,b=rows[i-1],rows[i];gap=b['stamp']-a['stamp']
    if gap<=0 or gap>max_gap:return None,gap
    t=(stamp-a['stamp'])/gap
    return [a['x']+t*(b['x']-a['x']),a['y']+t*(b['y']-a['y']),wrap(a['theta']+t*wrap(b['theta']-a['theta']))],gap
def events(rows,threshold,duration=2.,max_gap=.25):
    """Strict > threshold; count only measured continuous intervals, no gap bridging."""
    found=[];start=None;last=None;peak=0.
    for r in list(rows)+[{'stamp':None,'translation_error_m':0.}]:
        t=r['stamp'];high=t is not None and r['translation_error_m']>threshold
        if start is not None and (not high or last is not None and t-last>max_gap):
            if last-start>=duration-1e-9:found.append({'start':start,'end':last,'duration_s':last-start,'peak_error_m':peak})
            start=None;peak=0.
        if high:
            if start is None:start=t
            peak=max(peak,r['translation_error_m']);last=t
    return found
def exposure(rows,threshold,max_gap=.25):
    return sum(b['stamp']-a['stamp'] for a,b in zip(rows,rows[1:])
               if 0<b['stamp']-a['stamp']<=max_gap and a['translation_error_m']>threshold and b['translation_error_m']>threshold)
def geometry_proxy(scan,reference_length_m=1.):
    """Unit-weight point-to-local-line proxy, NOT OpenKarto's correlation Hessian.

    H uses [dx,dy,L*dtheta], divides by correspondence count. Normals are
    estimated from neighbouring beam hits, fixed before seeing any outcomes.
    Range-max/no-return rays and >0.3m neighbour chords are excluded.
    """
    rr=np.asarray(scan['ranges'],float);angles=scan['angle_min']+np.arange(len(rr))*scan['angle_increment']
    points=np.c_[rr*np.cos(angles),rr*np.sin(angles)]
    valid=np.isfinite(rr)&(rr>max(.05,scan['range_min']))&(rr<scan['range_max']-.01)
    idx=np.arange(1,len(rr)-1,4);idx=idx[valid[idx-1]&valid[idx]&valid[idx+1]]
    if not len(idx):return {'proxy_valid':False}
    tangent=points[idx+1]-points[idx-1];norm=np.linalg.norm(tangent,axis=1)
    keep=(norm>.002)&(norm<.3);idx=idx[keep];tangent=tangent[keep];norm=norm[keep]
    if len(idx)<10:return {'proxy_valid':False}
    normals=np.c_[-tangent[:,1],tangent[:,0]]/norm[:,None];p=points[idx]
    j=np.c_[normals,(-normals[:,0]*p[:,1]+normals[:,1]*p[:,0])/reference_length_m]
    h=j.T@j/len(j);eig=np.linalg.eigvalsh(h);te,tv=np.linalg.eigh(h[:2,:2])
    return {'proxy_valid':True,'normal_count':len(j),'scaled_hessian_eigenvalues':eig.tolist(),
            'translation_ratio':float(max(0,te[0])/max(te[-1],1e-12)),
            'translation_weak_axis_laser_rad':float(math.atan2(tv[1,0],tv[0,0])),
            'reference_length_m':reference_length_m,'weight_model':'unit weights, geometry proxy only',
            'is_karto_matcher_hessian':False}

def initial_state_difference(a,b):
    xy,yaw=error(a['map_base'],b['map_base'])
    return {'map_translation_m':xy,'map_heading_rad':yaw,
            'node_count_difference':b['nodes']-a['nodes'],'edge_count_difference':b['edges']-a['edges'],
            'exact_backend_state_claim':False}
