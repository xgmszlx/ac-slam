"""Generate an example-only observer using existing System snapshot getters."""
from pathlib import Path
import difflib

p=Path(__file__).resolve().parents[1]
src=p/'sources/ORB_SLAM3-4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4'
path=src/'Examples/RGB-D/rgbd_tum.cc'
original=path.read_text()
code=original.replace('#include<chrono>','#include<chrono>\n#include<iomanip>\n#include<cmath>\n#include<array>')
code=code.replace('    // Main loop', '''    struct Observation {int index,state; double stamp,track_s,observer_s; vector<cv::KeyPoint> keys; vector<unsigned char> associated;};
    vector<Observation> observations; observations.reserve(nImages);
    // Main loop''')
code=code.replace('        vTimesTrack[ni]=ttrack;', '''        vTimesTrack[ni]=ttrack;
        auto observer_start=std::chrono::steady_clock::now();
        Observation row; row.index=ni; row.stamp=tframe; row.track_s=ttrack;
        row.state=SLAM.GetTrackingState();
        row.keys=SLAM.GetTrackedKeyPointsUn();
        auto points=SLAM.GetTrackedMapPoints();
        row.associated.reserve(points.size());
        for(auto point:points) row.associated.push_back(point!=nullptr);
        row.observer_s=std::chrono::duration<double>(std::chrono::steady_clock::now()-observer_start).count();
        observations.push_back(std::move(row));''')
code=code.replace('    // Tracking time statistics', '''    // Write buffered observations after estimator shutdown. No estimator setters used.
    ofstream statefile("frame_states.csv"), keyfile("keypoints.csv");
    statefile << "index,stamp,state,n_keypoints,n_nonnull_associations,track_s,observer_s\\n";
    keyfile << "index,x,y,octave,nonnull_association\\n";
    statefile << setprecision(17); keyfile << setprecision(8);
    for(const auto &row:observations) {
        int count=0; for(auto value:row.associated)count+=value;
        statefile << row.index << "," << row.stamp << "," << row.state << "," << row.keys.size() << "," << count << "," << row.track_s << "," << row.observer_s << "\\n";
        for(size_t k=0;k<row.keys.size();++k) {
            keyfile << row.index << "," << row.keys[k].pt.x << "," << row.keys[k].pt.y << "," << row.keys[k].octave << "," << (k<row.associated.size()?int(row.associated[k]):0) << "\\n";
        }
    }
    statefile.close();keyfile.close();
    // Tracking time statistics''')
target=src/'Examples/RGB-D/rgbd_tum_trace.cc';target.write_text(code)
(p/'patches/example_observer.patch').write_text(''.join(difflib.unified_diff(original.splitlines(True),code.splitlines(True),'a/Examples/RGB-D/rgbd_tum.cc','b/Examples/RGB-D/rgbd_tum_trace.cc')))
cmake=src/'CMakeLists.txt'
text=cmake.read_text()
text+='\nset(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${PROJECT_SOURCE_DIR}/Examples/RGB-D)\nadd_executable(rgbd_tum_trace Examples/RGB-D/rgbd_tum_trace.cc)\ntarget_link_libraries(rgbd_tum_trace ${PROJECT_NAME})\n'
cmake.write_text(text)
print('Example observer generated; native rgbd_tum and core source unchanged')
