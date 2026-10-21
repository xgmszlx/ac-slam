#pragma once
#include <opencv2/core.hpp>
#include <vector>
#include <string>
#include <array>
#include <cstdint>
namespace ORB_SLAM3 {class Frame;}
namespace region {
struct Params {
 int grid=4,max_regions=4,min_pixels=64,max_points=400;
 double depth_gate=.3,max_region_fraction=.35,max_extra_fraction=.45,max_union_fraction=.8;
 double fb_gate=1.5,fit_gate=.05,motion_gain=.05,min_second_ratio=.02,min_spread=.02;
 int min_bg=20,min_bg_cells=4,min_pairs=18,min_train_inliers=8,min_validation=6,ransac=100;
};
struct Candidate {int id=0;cv::Mat mask;int pixels=0;uint64_t hash=0;};
struct Verdict {bool accepted=false;std::string reason="unavailable";int pairs=0,train=0,train_inliers=0,validation=0,occluded=0;double static_error=-1,rigid_error=-1,ratio=-1;cv::Mat R,t;};
struct Stats {
 int mode=0,index=-1,state=-1,map=-1,map_count=0,pose_valid=0,frame_N=0,associations=0,returned_inliers=0;
 int base_pixels=0,candidates=0,candidate_pixels=0,accepted=0,extra_pixels=0,oversize=0;
 int bg_attempt=0,bg_pairs=0,bg_inliers=0,bg_cells=0;
 int lk_checked=0,lk_deleted_base=0,lk_deleted_extra=0,lk_retained=0,pnp_calls=0,pnp_inliers=0;
 int orb_raw=0,orb_deleted_base=0,orb_deleted_extra=0,orb_retained=0;
 int opt_calls=0,opt_edges_sum=0,opt_inliers_sum=0,opt_last_edges=0,opt_last_inliers=0;
 double stamp=0,module_ms=0,candidate_ms=0,bg_ms=0,region_ms=0;
 uint64_t base_hash=0,candidate_hash=0;std::string bg_reason="not_needed";
 cv::Mat base,extra,candidate_union,full;std::vector<Verdict> verdicts;std::vector<int> region_pixels;
};
extern thread_local Stats stats;
double LastModuleCPU();
int Mode();void SetMode(int mode);void Begin(double stamp);
uint64_t HashMask(const cv::Mat& m);
std::vector<Candidate> Generate(const cv::Mat& mask,const cv::Mat& depth,const Params& p,int& oversized);
Verdict FitValidate(const std::vector<cv::Point3f>& a,const std::vector<cv::Point3f>& b,const std::vector<cv::Point2f>& pix,const cv::Mat& Rbg,const cv::Mat& tbg,const Params& p);
bool FitBackground(const std::vector<cv::Point3f>& world,const std::vector<cv::Point2f>& current_raw,const cv::Mat& K,const cv::Mat& dist,const Params& p,cv::Mat& R,cv::Mat& t,std::string& reason,int& inliers,int& cells);
cv::Mat Apply(const cv::Mat& base,const cv::Mat& depth,const cv::Mat& gray,const cv::Mat& K,const cv::Mat& dist,double stamp,int map);
void RecordCompleted(ORB_SLAM3::Frame& frame,int state,int map,int maps,const cv::Mat& gray,const cv::Mat& depth,const cv::Mat& K,const cv::Mat& dist);
void NoteLK(const cv::Point2f& point,bool removed);
void NoteORB(const cv::Point2f& point,bool removed);
void NoteOptimization(int edges,int inliers);
}
