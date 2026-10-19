#include <System.h>
#include <opencv2/opencv.hpp>
#include <Eigen/Geometry>
#include <fstream>
#include <sstream>
#include <iostream>
#include <iomanip>
#include <chrono>
#include <thread>
#include "depth_rule.h"
using Clock=std::chrono::steady_clock;
struct Record{double t,prep,track,audit;int state,pixels;Sophus::SE3f pose;std::vector<double> a;};
int main(int argc,char **argv){
 if(argc!=7){std::cerr<<"vocabulary yaml data associations B0|B1 output\n";return 2;}
 const bool apply=std::string(argv[5])=="B1";std::ifstream f(argv[4]);std::string line;std::vector<double>ts;std::vector<std::string>rgb,dep;
 while(std::getline(f,line)){if(line.empty()||line[0]=='#')continue;std::istringstream s(line);double t,d;std::string r,p;s>>t>>r>>d>>p;if(!s)return 3;ts.push_back(t);rgb.push_back(r);dep.push_back(p);}
 ORB_SLAM3::System slam(argv[1],argv[2],ORB_SLAM3::System::RGBD,false);if(slam.GetImageScale()!=1.f)return 4;
 std::vector<Record> rec;rec.reserve(ts.size());std::cout<<"input_frames "<<ts.size()<<" condition "<<argv[5]<<std::endl;
 for(size_t i=0;i<ts.size();++i){
  cv::Mat im=cv::imread(std::string(argv[3])+"/"+rgb[i],-1),original=cv::imread(std::string(argv[3])+"/"+dep[i],-1);if(im.empty()||original.type()!=CV_16UC1)return 5;
  auto b=Clock::now();cv::Mat mask=depthBoundary(original),depth=original.clone();if(apply)depth.setTo(0,mask);auto p=Clock::now();
  Sophus::SE3f Tcw=slam.TrackRGBD(im,depth,ts[i]);auto e=Clock::now();int state=slam.GetTrackingState();auto a=slam.AuditRGBD(original,mask,ts[i]);auto g=Clock::now();
  if(a[2]>=0 && ((apply && (a[4]!=a[5] || a[4]!=a[7])) || (!apply && a[4]!=a[6]))){std::cerr<<"DEPTH_PROPAGATION_FAIL "<<i<<std::endl;return 7;}
  rec.push_back({ts[i],std::chrono::duration<double>(p-b).count(),std::chrono::duration<double>(e-p).count(),std::chrono::duration<double>(g-e).count(),state,cv::countNonZero(mask),Tcw.inverse(),a});
  double dt=i+1<ts.size()?ts[i+1]-ts[i]:(ts.size()>1?ts[i]-ts[i-1]:0);double spent=std::chrono::duration<double>(g-b).count();if(dt>spent)std::this_thread::sleep_for(std::chrono::duration<double>(dt-spent));
 }
 slam.Shutdown();slam.SaveTrajectoryTUM("CameraTrajectory.txt");slam.SaveKeyFrameTrajectoryTUM("KeyFrameTrajectory.txt");
 std::ofstream ev("frame_states.csv"),online("OnlineTrajectory.txt");ev<<"index,stamp,state,pose_valid,preprocess_seconds,track_seconds,audit_seconds,boundary_pixels,frame_stamp,frame_id,N,valid_depth,boundary_features,invalid_boundary,valid_boundary,both_minus_one,associated_points,retained_2d,retained_3d,boundary_associated,map_id,map_count,current_map_points,current_keyframes,atlas_points,atlas_keyframes\n"<<std::fixed<<std::setprecision(9);online<<std::fixed<<std::setprecision(9);
 for(size_t i=0;i<rec.size();++i){const auto&r=rec[i];ev<<i<<","<<r.t<<","<<r.state<<","<<(r.state==2 && r.a[2]>=0)<<","<<r.prep<<","<<r.track<<","<<r.audit<<","<<r.pixels;for(double v:r.a)ev<<","<<v;ev<<"\n";if(r.state==2 && r.a[2]>=0){auto t=r.pose.translation();auto q=r.pose.unit_quaternion();online<<r.t<<" "<<t.x()<<" "<<t.y()<<" "<<t.z()<<" "<<q.x()<<" "<<q.y()<<" "<<q.z()<<" "<<q.w()<<"\n";}}
 std::cout<<"COMPLETE "<<rec.size()<<std::endl;return 0;
}
