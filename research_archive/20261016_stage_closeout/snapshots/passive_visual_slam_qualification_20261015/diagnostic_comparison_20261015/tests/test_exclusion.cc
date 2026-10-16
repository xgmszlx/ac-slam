#include <ORBextractor.h>
#include <FeatureExclusion.h>
#include <opencv2/opencv.hpp>
#include <iostream>
#include <cassert>
using namespace ORB_SLAM3;
bool equalkeys(const std::vector<cv::KeyPoint>& a,const std::vector<cv::KeyPoint>& b) {
 if(a.size()!=b.size())return false;
 for(size_t i=0;i<a.size();i++)if(a[i].pt!=b[i].pt||a[i].angle!=b[i].angle||a[i].size!=b[i].size||a[i].octave!=b[i].octave||a[i].response!=b[i].response)return false;
 return true;
}
int main(int argc,char**argv){
 assert(argc==2);auto im=cv::imread(argv[1],-1);auto before=im.clone();cv::Mat gray;cv::cvtColor(im,gray,cv::COLOR_BGR2GRAY);
 ORBextractor a(1000,1.2,8,20,7),b(1000,1.2,8,20,7);std::vector<cv::KeyPoint>ka,kb;cv::Mat da,db;std::vector<int>lap(2,0);cv::Mat full(gray.size(),CV_8UC1,cv::Scalar(255));
 a(gray,cv::Mat(),ka,da,lap);b(gray,full,kb,db,lap);assert(equalkeys(ka,kb));assert(cv::norm(da,db,cv::NORM_INF)==0);
 auto keys=ka;auto desc=da.clone();diagnostic::ExcludeFeatures(cv::Mat(),gray.size(),keys,desc);assert(equalkeys(ka,keys));assert(cv::norm(da,desc,cv::NORM_INF)==0);
 cv::Mat mask=cv::Mat::zeros(gray.size(),CV_8UC1);mask(cv::Rect(150,100,300,300)).setTo(255);keys=ka;desc=da.clone();diagnostic::ExcludeFeatures(mask,gray.size(),keys,desc);assert(keys.size()<ka.size());assert(desc.rows==(int)keys.size());size_t j=0;
 for(size_t i=0;i<ka.size();i++)if(mask.at<unsigned char>((int)ka[i].pt.y,(int)ka[i].pt.x)==0){assert(j<keys.size());assert(keys[j].pt==ka[i].pt);assert(cv::norm(desc.row(j),da.row(i),cv::NORM_INF)==0);++j;}
 assert(j==keys.size());assert(cv::norm(before,im,cv::NORM_INF)==0);
 size_t retained=keys.size();diagnostic::ExcludeFeatures(full,gray.size(),keys,desc);assert(keys.empty()&&desc.rows==0);
 bool bad_size_rejected=false;try{keys=ka;desc=da.clone();diagnostic::ExcludeFeatures(cv::Mat::zeros(3,3,CV_8UC1),gray.size(),keys,desc);}catch(const cv::Exception&){bad_size_rejected=true;}assert(bad_size_rejected);
 std::cout<<"{\"original_mask_ignored\":true,\"empty_helper_exact\":true,\"rectangle_excludes\":"<<ka.size()-retained<<",\"input_features\":"<<ka.size()<<",\"retained\":"<<retained<<",\"descriptors_consistent\":true,\"image_pixels_unchanged\":true,\"all_mask_removes_all\":true,\"wrong_size_rejected\":true,\"actual_Frame_depth_integration\":\"NOT_TESTED\",\"real_person_masks\":\"NOT_QUALIFIED\"}"<<std::endl;
}
