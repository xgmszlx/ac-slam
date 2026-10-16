import pathlib,json,hashlib,subprocess,shutil,datetime
N=pathlib.Path(__file__).resolve().parents[1]; O=N.parent; S=O/'sources/ORB_SLAM3-4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4'
if (N/'protocol/design_frozen.json').exists(): raise SystemExit('Frozen workspace already exists; use a new independent directory. No files changed.')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((O/'MANIFEST.json').read_text()); check={k:sha(O/k)==v['sha256'] for k,v in manifest.items()}
assert all(check.values()), [k for k,v in check.items() if not v]
git=lambda *a:subprocess.check_output(['git','-C','/home/wcqw/ac-slam',*a],text=True)
(N/'audit/protection_before.json').write_text(json.dumps({'old_manifest':sha(O/'MANIFEST.json'),'old_files':check,'git_head':git('rev-parse','HEAD'),'git_status':git('status','--porcelain=v1'),'git_diff_sha':hashlib.sha256(git('diff').encode()).hexdigest()},indent=2))
shutil.copyfile('/home/wcqw/.codex/attachments/fbb93ef9-52e1-4461-b773-f4d453362ffd/已粘贴的文本.txt',N/'protocol/user_request.txt')
shutil.copyfile(O/'code/evaluate.py',N/'code/evaluate.py')
y=(S/'Examples/RGB-D/TUM3.yaml').read_text(); assert y.count('Camera.RGB: 1')==1
(N/'config/P0.yaml').write_text(y); (N/'config/P1.yaml').write_text(y.replace('Camera.RGB: 1','Camera.RGB: 0'))
s=(S/'Examples/RGB-D/rgbd_tum_headless.cc').read_text()
s=s.replace('#include<chrono>','#include<chrono>\n#include<iomanip>\n#include<Eigen/Geometry>')
s=s.replace('    // Main loop','    struct Observation { double stamp, seconds, getter_us; int state; Sophus::SE3f Twc; };\n    vector<Observation> observations; observations.reserve(nImages);\n\n    // Main loop')
s=s.replace('SLAM.TrackRGBD(imRGB,imD,tframe);','Sophus::SE3f Tcw = SLAM.TrackRGBD(imRGB,imD,tframe);')
s=s.replace('        vTimesTrack[ni]=ttrack;','''        vTimesTrack[ni]=ttrack;
        auto g0=std::chrono::steady_clock::now();
        int state=SLAM.GetTrackingState();
        Sophus::SE3f Twc=Tcw.inverse();
        auto g1=std::chrono::steady_clock::now();
        observations.push_back({tframe,ttrack,std::chrono::duration<double,std::micro>(g1-g0).count(),state,Twc});''')
# Export native trajectories immediately after Shutdown, before new buffered disk writes.
needle='    SLAM.SaveKeyFrameTrajectoryTUM("KeyFrameTrajectory.txt");'
assert needle in s
s=s.replace(needle,needle+'''
    std::ofstream events("frame_states.csv"), online("OnlineTrajectory.txt");
    events << "index,stamp,state,pose_valid,track_seconds,getter_us\\n";
    events << std::fixed << std::setprecision(9);
    online << std::fixed << std::setprecision(9);
    for(size_t i=0;i<observations.size();++i) {
        const auto &o=observations[i];
        const bool valid=o.state==2; // conservative OK only; never label invalid identity as a pose
        events << i << "," << o.stamp << "," << o.state << "," << valid << "," << o.seconds << "," << o.getter_us << "\\n";
        if(valid) {
            const auto t=o.Twc.translation(); const auto q=o.Twc.unit_quaternion();
            online << o.stamp << " " << t.x() << " " << t.y() << " " << t.z() << " " << q.x() << " " << q.y() << " " << q.z() << " " << q.w() << "\\n";
        }
    }
''')
(N/'code/rgbd_diagnostic.cc').write_text(s)
# Reuse the original generated compiler and link flags, changing only output/source objects.
b=S/'build'; flags=(b/'CMakeFiles/rgbd_tum_headless.dir/flags.make').read_text()
(N/'audit/original_flags.make').write_text(flags)
fields={l.split(' = ')[0]:l.split(' = ')[1] for l in flags.splitlines() if ' = ' in l}
import shlex
cmd=['/usr/bin/c++']+shlex.split(fields['CXX_DEFINES'])+shlex.split(fields['CXX_INCLUDES'])+shlex.split(fields['CXX_FLAGS'])+['-c',str(N/'code/rgbd_diagnostic.cc'),'-o',str(N/'build/rgbd_diagnostic.o')]
link=shlex.split((b/'CMakeFiles/rgbd_tum_headless.dir/link.txt').read_text()); link[link.index('CMakeFiles/rgbd_tum_headless.dir/Examples/RGB-D/rgbd_tum_headless.cc.o')]=str(N/'build/rgbd_diagnostic.o'); link[link.index('-o')+1]=str(N/'build/rgbd_diagnostic')
protocol={'registered_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'stage':'MINIMAL_DIAGNOSTIC_COMPARISON','official_commit':'4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4','core_sha256':sha(S/'lib/libORB_SLAM3.so'),'P0':'unchanged imread BGR + RGB=1','P1':'unchanged imread BGR + RGB=0','P2':'conditional P1 + post-extraction feature/descriptor exclusion before depth association','sequence_order':['walking/P1_01','walking/P0_02','walking/P1_02','walking/P0_03','walking/P1_03','sitting/P1_01'],'historical_P0':'walking_xyz/headless01, not buffered; secondary comparator','maximum_additional_runs':{'walking_P0':2,'walking_P1':3,'sitting_P1':1,'walking_P2':3,'sitting_P2':1},'P1_solves_gate':{'all_3_walking_ATE_RMSE_m_max':.05,'all_3_walking_1s_RPE_translation_RMSE_m_max':.05,'all_3_pose_coverage_min':.99,'all_exits_zero':True},'P2_sufficiency_gate':'all walking P2 ATE and RPEt <=0.05m and coverage>=99%, zero exits; sitting no substantial regression (>0.02m ATE or RPEt) versus P1; false acceptance conclusions require evidence','mask_policy':{'local_search':'no onnx/caffemodel/prototxt found in /home/wcqw','fallback':'author MobileNet-SSD Caffe, CPU OpenCV DNN, <=30MB weights','current_RGB_only':True,'confidence':.5,'person_class_VOC':15,'bbox_expansion_pixels':0,'input_size':[300,300],'scale':.007843,'mean':127.5,'quality_sample':'every 83rd walking associated frame plus final; every 122nd sitting plus final, fixed before mask inference','error_or_missing_mask':'stop P2','manual_GT_masks':False},'evaluation':'frozen previous evaluate.py; SE3 no scale, unique timestamps <20ms, 1s RPE, all coverage; separate OK-only online and exported trajectories','timing':'native input pacing and unchanged Shutdown; buffer public return pose/state after TrackRGBD, write after native exports; small overhead quantified, no numerical equivalence claim','minimum_free_bytes':1000000000,'no_retry_failed_scientific_run':True,'new_dataset_downloads':False,'GT_online':False,'P2_stop':'if P1 solves gate stop; if credible masks or filtering tests fail stop; no area matched control this round','changes_frozen':{'example_sha256':sha(N/'code/rgbd_diagnostic.cc'),'P0_yaml':sha(N/'config/P0.yaml'),'P1_yaml':sha(N/'config/P1.yaml'),'eval_sha256':sha(N/'code/evaluate.py')},'compile_command':cmd,'link_command':link}
(N/'protocol/design_frozen.json').write_text(json.dumps(protocol,indent=2))
with (N/'audit/build_baseline.log').open('w') as f:
 subprocess.run(cmd,cwd=b,stdout=f,stderr=subprocess.STDOUT,check=True)
 subprocess.run(link,cwd=b,stdout=f,stderr=subprocess.STDOUT,check=True)
(N/'audit/baseline_binary.json').write_text(json.dumps({'sha256':sha(N/'build/rgbd_diagnostic'),'core_sha256':sha(S/'lib/libORB_SLAM3.so')},indent=2))
print(N)
