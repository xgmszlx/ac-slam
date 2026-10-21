#include "System.h"
#include "RegionExpansion.h"
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <chrono>
#include <thread>
#include <sstream>
#include <array>
using namespace std;
struct Row{region::Stats d;Sophus::SE3f Tcw;double api_ms=0,module_cpu_ms=0;uint64_t full_hash=0;};
struct Shot{int index;cv::Mat rgb,base,extra,candidate;};
int main(int argc,char**argv){
 if(argc!=7){cerr<<"usage: voc yaml sequence association mode output_dir\n";return 2;}int mode=stoi(argv[5]);region::SetMode(mode);string output=argv[6];vector<double> stamps;vector<string>rgb,depth;ifstream input(argv[4]);string line;
 while(getline(input,line)){if(line.empty()||line[0]=='#')continue;istringstream s(line);double t,td;string a,b;if(!(s>>t>>a>>td>>b))return 3;stamps.push_back(t);rgb.push_back(a);depth.push_back(b);}
 vector<Row>rows;vector<Shot>shots;rows.reserve(stamps.size());ORB_SLAM3::System SLAM(argv[1],argv[2],ORB_SLAM3::System::RGBD,false);
 for(size_t i=0;i<stamps.size();i++){
  cv::Mat color=cv::imread(string(argv[3])+"/"+rgb[i],cv::IMREAD_UNCHANGED),z=cv::imread(string(argv[3])+"/"+depth[i],cv::IMREAD_UNCHANGED);if(color.empty()||z.empty()){cerr<<"decode failed at "<<i<<endl;return 4;}
  auto start=chrono::steady_clock::now();auto pose=SLAM.TrackRGBD(color,z,stamps[i]);double api_ms=chrono::duration<double,milli>(chrono::steady_clock::now()-start).count();
  Row r;r.d=region::stats;r.d.state=SLAM.GetTrackingState();r.Tcw=pose;r.api_ms=api_ms;r.module_cpu_ms=region::LastModuleCPU();r.full_hash=region::HashMask(region::stats.full);
  if(i==0||i==147||i==294||i==441||i+1==stamps.size())shots.push_back({(int)i,color.clone(),r.d.base.clone(),r.d.extra.clone(),r.d.candidate_union.clone()});
  r.d.base.release();r.d.extra.release();r.d.candidate_union.release();r.d.full.release();rows.push_back(r);
  double T=i+1<stamps.size()?stamps[i+1]-stamps[i]:(i?stamps[i]-stamps[i-1]:0);if(api_ms/1000<T)this_thread::sleep_for(chrono::duration<double>(T-api_ms/1000));
 }
 SLAM.Shutdown();SLAM.SaveTrajectoryTUM(output+"/CameraTrajectory.txt");SLAM.SaveKeyFrameTrajectoryTUM(output+"/KeyFrameTrajectory.txt");
 ofstream csv(output+"/frame_states.csv"),online(output+"/OnlineTrajectory.txt"),areas(output+"/regions.csv");csv<<setprecision(17);online<<fixed<<setprecision(9);areas<<setprecision(17);
 csv<<"index,stamp,state,map,map_count,pose_valid,N,associations,nonoutlier_flagged,base_pixels,candidates,candidate_pixels,accepted,extra_pixels,oversize,bg_attempt,bg_pairs,bg_inliers,bg_cells,bg_reason,lk_checked,lk_deleted_base,lk_deleted_extra,lk_retained,pnp_calls,pnp_inliers,orb_raw,orb_deleted_base,orb_deleted_extra,orb_retained,poseopt_calls,poseopt_edges_sum,poseopt_inliers_sum,poseopt_last_edges,poseopt_last_inliers,api_ms,module_ms,module_cpu_ms,candidate_ms,bg_ms,region_ms,base_hash,candidate_hash,full_hash,tx,ty,tz,qx,qy,qz,qw\n";
 areas<<"index,stamp,region,pixels,accepted,reason,pairs,train,train_inliers,validation,occluded,static_error_m,rigid_error_m,second_ratio\n";
 for(auto&r:rows){auto &s=r.d;auto Twc=r.Tcw.inverse();auto t=Twc.translation();auto q=Twc.unit_quaternion();csv<<s.index<<','<<s.stamp<<','<<s.state<<','<<s.map<<','<<s.map_count<<','<<s.pose_valid<<','<<s.frame_N<<','<<s.associations<<','<<s.returned_inliers<<','<<s.base_pixels<<','<<s.candidates<<','<<s.candidate_pixels<<','<<s.accepted<<','<<s.extra_pixels<<','<<s.oversize<<','<<s.bg_attempt<<','<<s.bg_pairs<<','<<s.bg_inliers<<','<<s.bg_cells<<','<<s.bg_reason<<','<<s.lk_checked<<','<<s.lk_deleted_base<<','<<s.lk_deleted_extra<<','<<s.lk_retained<<','<<s.pnp_calls<<','<<s.pnp_inliers<<','<<s.orb_raw<<','<<s.orb_deleted_base<<','<<s.orb_deleted_extra<<','<<s.orb_retained<<','<<s.opt_calls<<','<<s.opt_edges_sum<<','<<s.opt_inliers_sum<<','<<s.opt_last_edges<<','<<s.opt_last_inliers<<','<<r.api_ms<<','<<s.module_ms<<','<<r.module_cpu_ms<<','<<s.candidate_ms<<','<<s.bg_ms<<','<<s.region_ms<<','<<s.base_hash<<','<<s.candidate_hash<<','<<r.full_hash<<','<<t.x()<<','<<t.y()<<','<<t.z()<<','<<q.x()<<','<<q.y()<<','<<q.z()<<','<<q.w()<<'\n';
  if(s.pose_valid&&s.state==2)online<<s.stamp<<' '<<t.x()<<' '<<t.y()<<' '<<t.z()<<' '<<q.x()<<' '<<q.y()<<' '<<q.z()<<' '<<q.w()<<'\n';
  for(size_t j=0;j<s.verdicts.size();j++){auto &v=s.verdicts[j];areas<<s.index<<','<<s.stamp<<','<<j<<','<<s.region_pixels[j]<<','<<v.accepted<<','<<v.reason<<','<<v.pairs<<','<<v.train<<','<<v.train_inliers<<','<<v.validation<<','<<v.occluded<<','<<v.static_error<<','<<v.rigid_error<<','<<v.ratio<<'\n';}
 }
 for(auto &s:shots){cv::Mat im=s.rgb.clone();for(int y=0;y<im.rows;y++)for(int x=0;x<im.cols;x++){auto &p=im.at<cv::Vec3b>(y,x);if(!s.base.empty()&&s.base.at<uchar>(y,x))p=cv::Vec3b(p[0]/2,(p[1]+255)/2,p[2]/2);if(!s.extra.empty()&&s.extra.at<uchar>(y,x))p=cv::Vec3b((p[0]+255)/2,p[1]/2,(p[2]+255)/2);}
  cv::putText(im,"M"+to_string(mode)+" frame "+to_string(s.index)+" green=base magenta=extra",cv::Point(8,22),cv::FONT_HERSHEY_SIMPLEX,.55,cv::Scalar(0,0,255),1);cv::imwrite(output+"/mask_"+to_string(s.index)+".png",im);if(!s.candidate.empty())cv::imwrite(output+"/candidates_"+to_string(s.index)+".png",s.candidate*255);cv::imwrite(output+"/base_"+to_string(s.index)+".png",s.base*255);cv::imwrite(output+"/extra_"+to_string(s.index)+".png",s.extra*255);cv::imwrite(output+"/full_"+to_string(s.index)+".png",(s.base|s.extra)*255);
 }
 cout<<"REGION_COMPLETED_INPUTS "<<rows.size()<<endl;return 0;
}
