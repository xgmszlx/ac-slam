"""Four small offline figures; English labels avoid missing CJK-font artifacts."""
import json
import csv
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from common import OUT,ASSETS,base_pose


def rows(name):
    with (OUT/'analysis'/name).open() as f:return list(csv.DictReader(f))


def save(fig,name):
    p=OUT/'figures';p.mkdir(parents=True,exist_ok=True)
    fig.savefig(p/(name+'.png'),dpi=150,bbox_inches='tight');fig.savefig(p/(name+'.svg'),bbox_inches='tight');plt.close(fig)


def main():
    data=rows('task_headroom_audit.csv');fig,axs=plt.subplots(1,3,figsize=(12,3.7))
    for k,mapid in enumerate(['map3','map8']):
        d=[r for r in data if r['map']==mapid and r['validity']=='VALID']
        for j,method in enumerate(sorted({r['method'] for r in d})):
            s=[r for r in d if r['method']==method];axs[k].scatter([j]*len(s),[float(r['recomputed_ape_rmse_m']) for r in s],label=method)
        axs[k].set(xticks=[],ylabel='Final corrected-trajectory APE RMSE [m]',title=mapid+' completed exploration (15 runs)');axs[k].legend(fontsize=7)
    local=rows('independent_doc79_target_GT.csv')
    for j,stage in enumerate(['before_return','arrival','action_done','final']):
        d=[float(r['target_position_error_m']) for r in local if r['stage']==stage];axs[2].scatter([j]*len(d),d,s=12,alpha=.6);axs[2].plot(j,np.mean(d),'kx')
    axs[2].set(xticks=range(4),xticklabels=['Before','Arrival','Motion end','Final'],title='Doc79 historical target errors (35 poses)',ylabel='Pre-action-aligned position error [m]');axs[2].tick_params(axis='x',rotation=25)
    for ax in axs:ax.title.set_fontsize(10)
    fig.suptitle('Global task headroom is not the same as local probe headroom',fontsize=12);fig.tight_layout(rect=[0,0,1,.90]);save(fig,'01_task_headroom')

    values=[r for r in rows('historical_constraint_value.csv') if r['stage']=='action_done'];fig,axs=plt.subplots(1,2,figsize=(10,3.8))
    for r in values:
        x=float(r['actual_delta_J']);y=1000*(float(r['target_mean_gt_after_m'])-float(r['target_mean_gt_before_m']))
        axs[0].scatter(x,y);axs[0].annotate(r['episode_id'].replace('D79_',''),(x,y),fontsize=7)
        axs[1].scatter(int(r['first_history_to_new_edges']),x)
    axs[0].axhline(0,c='gray',ls='--');axs[0].set(xlabel='Synchronous action delta J_T [nats]',ylabel='Historical target mean error change [mm]',title='Positive graph gain != GT improvement')
    axs[1].set(xlabel='New first-history crosslinks',ylabel='Synchronous action delta J_T [nats]',title='Mechanism only; edges are not equal-value labels');fig.tight_layout();save(fig,'02_graph_gain_and_task_error')

    geom=json.loads((OUT/'analysis/candidate_geometry.json').read_text());episode='D79_B_Lminus_1';fig,axs=plt.subplots(1,2,figsize=(11,5))
    bundles=OUT/'audit/pre_state_bundles'/episode
    for j,problem in enumerate(['A1','A2']):
        b=json.loads((bundles/(problem+'.json')).read_text());hist={i for i in b['history_state_ids']};pts=[n for n in b['graph']['nodes'] if n['state_id'] in hist]
        base=[base_pose(n) for n in pts]
        axs[j].plot([p[0] for p in base],[p[1] for p in base],c='gray',lw=.8,label='Pre-state historic base-pose chords')
        candidates=[c for c in geom[problem] if c['episode_id']==episode]
        if problem=='A1':
            for c in candidates:
                if len(c['path_base'])>1:axs[j].plot([p[0] for p in c['path_base']],[p[1] for p in c['path_base']],label=c['kind'],alpha=.7)
        else:
            c=[c for c in candidates if 'target_base' in c];axs[j].scatter([x['target_base'][0] for x in c],[x['target_base'][1] for x in c],c=[x['euclidean_lower_bound_m'] for x in c],cmap='viridis',label='19 historic-region medoids')
        axs[j].scatter(*b['current_base'][:2],marker='*',s=110,c='red',label='Current pre-decision base')
        axs[j].set_aspect('equal');axs[j].set(xlabel='map x [m]',ylabel='map y [m]',title=problem+' geometry hypotheses - safety NOT certified');axs[j].legend(fontsize=7)
    fig.tight_layout();save(fig,'03_candidate_geometry_only')

    native=[r for r in rows('native_RAL_utility_diagnostic.csv') if r['map'] in ['map3','map8'] and r['episode_id'].endswith('_A')]
    fig,axs=plt.subplots(1,2,figsize=(10,3.8));actual={r['episode_id']:r for r in rows('whole_run_outcomes_and_cost.csv')}
    for r in native:
        a=actual[r['episode_id']];color='tab:blue' if r['map']=='map3' else 'tab:orange'
        x=100*(float(r['modified_vs_tsp_utility_ratio'])-1)
        axs[0].scatter(x,float(a['active_loop_distance_m']),c=color)
        axs[1].scatter(x,float(a['whole_run_APE_m']),c=color)
    axs[0].set(xlabel='Native theoretical utility increase [%]',ylabel='Actual active-loop travel [m]',title='Same native objective, nontrivial actual cost')
    axs[1].set(xlabel='Native theoretical utility increase [%]',ylabel='Whole-run APE RMSE [m]',title='Descriptive only: no target counterfactuals')
    fig.suptitle('Blue map3 / orange map8; original fixed retrace policy (A)',fontsize=12);fig.tight_layout(rect=[0,0,1,.90]);save(fig,'04_native_utility_and_actual_outcome')


if __name__=='__main__':main()
