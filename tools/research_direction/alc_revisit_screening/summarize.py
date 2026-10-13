"""Mechanical aggregation of audited tables, not statistical model fitting."""
import csv
import json
import statistics
from common import OUT,write_json,csv_out


def read(relative):
    with (OUT/relative).open() as f:return list(csv.DictReader(f))


def main():
    sources=json.loads((OUT/'literature/method_sources.json').read_text())
    for s in sources:
        if s['id']=='Kim2015':s['strongest_baseline']='simulation Active-SLAM-only; real OPL open-loop / DET deterministic revisit'
    csv_out('literature/literature_matrix.csv',sources)
    matrix=json.loads((OUT/'analysis/decision_matrix_source.json').read_text())
    csv_out('analysis/A1_A2_research_decision_matrix.csv',matrix)
    actual=read('analysis/whole_run_outcomes_and_cost.csv');summaries=[]
    for mapid in ['map3','map8','radish_mexico']:
        for method in sorted({x['method'] for x in actual if x['map']==mapid}):
            r=[x for x in actual if x['map']==mapid and x['method']==method]
            summaries.append({'map':mapid,'method':method,'runs':len(r),'validity':r[0]['validity'],
                'APE_median_m':statistics.median(float(x['whole_run_APE_m']) for x in r),
                'APE_range_m':[min(float(x['whole_run_APE_m']) for x in r),max(float(x['whole_run_APE_m']) for x in r)],
                'active_distance_mean_m':statistics.mean(float(x['active_loop_distance_m']) for x in r),
                'active_time_mean_s':statistics.mean(float(x['active_loop_time_s']) for x in r),
                'planned_loops':sum(int(x['planned_loops']) for x in r),'started_loops':sum(int(x['executed_loops']) for x in r),
                'old_explicit_target_attributable_loops':sum(int(x['old_explicit_target_attributable_loops']) for x in r),
                'closure_count_definition':'old explicit TryCloseLoop target attribution, NOT all historical information'})
    write_json('analysis/whole_run_summary.json',summaries)
    local=read('analysis/local_path_candidates.csv');global_=read('analysis/global_target_candidates.csv')
    scores=read('analysis/baseline_score_comparison.csv');rank_conflicts=[]
    for episode in sorted({r['episode_id'] for r in scores}):
        rr=[r for r in scores if r['episode_id']==episode]
        a=next(r for r in rr if r['B0_selected_proxy']=='True');b=next(r for r in rr if r['B3_selected_proxy']=='True')
        rank_conflicts.append({'episode_id':episode,'B0_candidate':a['candidate_id'],'B3_candidate':b['candidate_id'],
            'B0_target_gap':int(a['accepted_state_gap']),'B3_target_gap':int(b['accepted_state_gap']),
            'different_top_choice':a['candidate_id']!=b['candidate_id'],
            'interpretation':'pre-observation proxy conflict only; nearest eligibility/reachability incomplete; not an observed superior decision'})
    csv_out('analysis/pre_state_proxy_conflicts.csv',rank_conflicts)
    native=read('analysis/native_RAL_utility_diagnostic.csv')
    legacy=read('analysis/legacy_loop_endpoint_diagnostic.csv')
    write_json('analysis/screening_summary.json',{
        'local_pre_states':len({r['episode_id'] for r in local}),
        'local_geometric_hypotheses':len(local),'global_regions_per_state':19,
        'global_geometric_hypotheses_including_continue_skip':len(global_),
        'certified_safe_moving_alternatives':0,'observed_new_candidate_counterfactuals':0,
        'B0_B3_proxy_top_conflicts':sum(r['different_top_choice'] for r in rank_conflicts),
        'native_recomputed_recorded_paths_exact_matches':sum(r['recorded_path_matches_native_recalculation']=='True' for r in native),
        'legacy_started_loop_cache_diagnostics':len(legacy),
        'max_legacy_pre_cache_age_s':max(float(r['pre_cache_age_s']) for r in legacy),
        'legacy_cache_delta_does_not_prove_active_causality':True,
        'no_probability_model_or_new_planner':True})


if __name__=='__main__':main()
