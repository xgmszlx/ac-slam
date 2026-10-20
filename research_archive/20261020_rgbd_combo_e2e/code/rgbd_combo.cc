#include <System.h>
#include <opencv2/opencv.hpp>
#include <Eigen/Geometry>
#include <fstream>
#include <sstream>
#include <iostream>
#include <iomanip>
#include <chrono>
#include <thread>
#include "Combo.h"
using Clock=std::chrono::steady_clock;
struct Record{double stamp,track;int state;Sophus::SE3f pose;std::vector<double> native,front;};
int main(int argc,char** argv){
 if(argc!=7){std::cerr<<"vocabulary yaml data associations S0|S1|S2 output\n";return 2;}
 std::string condition=argv[5];if(condition!="S0"&&condition!="S1"&&condition!="S2")return 3;combo::configure(condition[1]-'0');
 std::ifstream f(argv[4]);std::string line;std::vector<double> stamps;std::vector<std::string> rgb,dep;
 while(std::getline(f,line)){if(line.empty()||line[0]=='#')continue;std::istringstream s(line);double a,b;std::string r,d;s>>a>>r>>b>>d;if(!s)return 4;stamps.push_back(a);rgb.push_back(r);dep.push_back(d);}
 ORB_SLAM3::System slam(argv[1],argv[2],ORB_SLAM3::System::RGBD,false);if(slam.GetImageScale()!=1)return 5;
 std::vector<Record> records;records.reserve(stamps.size());std::cout<<"INPUT "<<stamps.size()<<" CONDITION "<<condition<<std::endl;
 for(size_t i=0;i<stamps.size();++i){cv::Mat im=cv::imread(std::string(argv[3])+"/"+rgb[i],-1),depth=cv::imread(std::string(argv[3])+"/"+dep[i],-1);if(im.empty()||depth.type()!=CV_16UC1)return 6;
  auto t=Clock::now();auto Tcw=slam.TrackRGBD(im,depth,stamps[i]);auto e=Clock::now();auto native=slam.AuditRGBD(depth,cv::Mat::zeros(depth.size(),CV_8U),stamps[i]);auto front=combo::stats();int state=slam.GetTrackingState();
  if(front.size()!=19)return 7;
  records.push_back({stamps[i],std::chrono::duration<double>(e-t).count(),state,Tcw.inverse(),native,front});
  auto end=Clock::now();double dt=i+1<stamps.size()?stamps[i+1]-stamps[i]:(i?stamps[i]-stamps[i-1]:0);double elapsed=std::chrono::duration<double>(end-t).count();if(dt>elapsed)std::this_thread::sleep_for(std::chrono::duration<double>(dt-elapsed));
 }
 slam.Shutdown();slam.SaveTrajectoryTUM("CameraTrajectory.txt");slam.SaveKeyFrameTrajectoryTUM("KeyFrameTrajectory.txt");
 std::ofstream out("frame_states.csv"),online("OnlineTrajectory.txt");out<<"index,stamp,state,track_seconds,frame_stamp,frame_id,N,valid_depth,boundary_features,invalid_boundary,valid_boundary,both_minus_one,associated_points,retained_2d,retained_3d,boundary_associated,map_id,map_count,current_map_points,current_keyframes,atlas_points,atlas_keyframes,fallback_retained_2d,fallback_retained_3d,raw_N,kept_N,mutual_matches,good_2d,bad_2d_rejected,pnp_ok,pnp_inliers,both_depth_tested,motion_rejected,depth_invalidated,fallback_candidates,fallback_pose_edges_2d_last,fallback_pose_edges_3d_last,fallback_pose_inlier2d_last,frontend_seconds,reference_stamp,fallback_range_reason,fallback_neighborhood_reason,fallback_already_invalid\n"<<std::fixed<<std::setprecision(9);online<<std::fixed<<std::setprecision(9);
 for(size_t i=0;i<records.size();++i){auto&r=records[i];out<<i<<","<<r.stamp<<","<<r.state<<","<<r.track;for(double v:r.native)out<<","<<v;for(double v:r.front)out<<","<<v;out<<"\n";if(r.state==2&&r.native[2]>=0){auto t=r.pose.translation();auto q=r.pose.unit_quaternion();online<<r.stamp<<" "<<t.x()<<" "<<t.y()<<" "<<t.z()<<" "<<q.x()<<" "<<q.y()<<" "<<q.z()<<" "<<q.w()<<"\n";}}
 std::cout<<"COMPLETE "<<records.size()<<std::endl;return 0;
}
