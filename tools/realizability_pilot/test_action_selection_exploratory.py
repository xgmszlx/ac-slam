#!/usr/bin/python3
"""No ROS: Jacobian, graph gauge and edge-quality regression tests."""
import copy
import math
import unittest
import numpy as np
from action_selection_exploratory import jacobian, score, keyscans, save, ROOT

def relative(a,b):
    c,s=math.cos(a[2]),math.sin(a[2]);x,y=b[0]-a[0],b[1]-a[1]
    return np.array([c*x+s*y,-s*x+c*y,b[2]-a[2]])

def fixture():
    nodes=[{'state_id':i,'unique_id':i,'x':float(i),'y':.1*i*i,'theta':.02*i} for i in range(6)]
    edges=[{'index':i-1,'source_state_id':i-1,'target_state_id':i,
            'covariance_3x3':np.diag([.1,.2,.01]).tolist()} for i in range(1,6)]
    return {'nodes':nodes,'edges':edges}

class AnalysisTests(unittest.TestCase):
    def test_jacobian_matches_finite_difference(self):
        a=np.array([1.2,2.3,.4]);b=np.array([3.5,-.7,-.2]);x=np.r_[a,b];delta=1e-6
        numeric=np.zeros((3,6))
        for i in range(6):
            plus=x.copy();minus=x.copy();plus[i]+=delta;minus[i]-=delta
            numeric[:,i]=(relative(plus[:3],plus[3:])-relative(minus[:3],minus[3:]))/(2*delta)
        self.assertLess(np.max(abs(jacobian(a,b)-numeric)),1e-8)

    def test_cholesky_matches_repository_and_global_gauge(self):
        graph=fixture();j,audit=score(graph,[1,2,3,4,5],crosscheck=True)
        self.assertLess(audit['cholesky_vs_repository_inverse_abs_difference'],1e-10)
        other=copy.deepcopy(graph);yaw=.7;c,s=math.cos(yaw),math.sin(yaw)
        for n in other['nodes']:
            x,y=n['x'],n['y'];n['x']=c*x-s*y+5;n['y']=s*x+c*y-3;n['theta']+=yaw
        j2,_=score(other,[1,2,3,4,5]);self.assertLess(abs(j-j2),1e-10)

    def test_informative_edge_improves_same_state_marginal(self):
        graph=fixture();j,_=score(graph,[1,2,3,4,5]);graph['edges'].append({'index':5,'source_state_id':0,'target_state_id':5,'covariance_3x3':np.diag([.01,.01,.001]).tolist()})
        j2,_=score(graph,[1,2,3,4,5]);self.assertGreater(j2,j)

    def test_static_raw_budget_does_not_create_keyframes(self):
        rows=[{'x':1.,'y':2.,'yaw':0.} for _ in range(348)]
        indices,okay=keyscans(rows,1,0);self.assertEqual(indices,[]);self.assertTrue(okay)

    def test_heading_filter_uses_float32_wire_value(self):
        rows=[{'x':0.,'y':0.,'yaw':0.},{'x':0.,'y':0.,'yaw':.52}]
        indices,okay=keyscans(rows,1,0)
        self.assertTrue(okay);self.assertEqual(indices,[])

    def test_edge_count_is_not_information_utility(self):
        weak=fixture();strong=fixture()
        for graph,cov in [(weak,1.0),(strong,.001)]:
            graph['edges'].append({'index':5,'source_state_id':0,'target_state_id':5,
                                   'covariance_3x3':np.eye(3).tolist()})
            graph['edges'][-1]['covariance_3x3']=(cov*np.eye(3)).tolist()
        self.assertEqual(len(weak['edges']),len(strong['edges']))
        self.assertGreater(score(strong,[1,2,3,4,5])[0],score(weak,[1,2,3,4,5])[0])

    def test_json_output_cannot_modify_old_result_root(self):
        with self.assertRaises(ValueError):
            save(ROOT/'results/realizability_pilot/p1_context_disentangle_confirmatory_amendment1_20260930/forbidden.json',{})

if __name__=='__main__':unittest.main()
