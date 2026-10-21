#include "RegionExpansion.h"
#include <opencv2/imgproc.hpp>
#include <opencv2/calib3d.hpp>
#include <iostream>
#include <stdexcept>
#include <cmath>
using namespace region;
void check(bool x,const std::string&name){std::cout<<(x?"PASS ":"FAIL ")<<name<<std::endl;if(!x)throw std::runtime_error(name);}
int main(){try{
 Params p;cv::Mat z(80,100,CV_32F,cv::Scalar(2)),mask=cv::Mat::zeros(z.size(),CV_8U);int over=0;
 check(Generate(mask,z,p,over).empty(),"empty_mask_no_candidates");
 mask(cv::Rect(40,20,20,40)).setTo(1);cv::Mat invalid=cv::Mat::zeros(z.size(),CV_32F);check(Generate(mask,invalid,p,over).empty(),"invalid_depth_no_candidates");
 cv::Mat disconnected(80,100,CV_32F,cv::Scalar(4));disconnected(cv::Rect(40,20,20,40)).setTo(2);check(Generate(mask,disconnected,p,over).empty(),"depth_disconnected_no_candidates");
 cv::Mat multi=disconnected.clone();multi(cv::Rect(28,24,12,20)).setTo(2);multi(cv::Rect(60,44,12,20)).setTo(2);auto c=Generate(mask,multi,p,over);check(c.size()==2,"multiple_adjacent_regions");
 int over2=0;SetMode(1);auto a=Generate(mask,multi,p,over2);SetMode(2);auto b=Generate(mask,multi,p,over2);check(a.size()==b.size()&&a[0].hash==b[0].hash&&a[1].hash==b[1].hash,"identical_candidate_generator_across_modes");
 cv::Mat untouched=multi.clone();for(auto &v:c)check(cv::countNonZero(v.mask&mask)==0,"candidate_only_outside_M0");check(cv::countNonZero(multi!=untouched)==0,"input_depth_unchanged");
 auto huge=Generate(mask,z,p,over);check(huge.empty()&&over>0,"oversized_region_rejected");
 cv::Mat K=(cv::Mat_<double>(3,3)<<500,0,50,0,500,40,0,0,1),dist=cv::Mat::zeros(5,1,CV_64F),gray(80,100,CV_8U,cv::Scalar(80));
 Begin(1);SetMode(2);auto fallback=Apply(mask,multi,gray,K,dist,1,0);check(cv::countNonZero(fallback!=mask)==0&&stats.accepted==0,"no_previous_completed_frame_falls_back");
 SetMode(1);Begin(1);auto grown=Apply(mask,multi,gray,K,dist,1,0);check(stats.accepted==2&&stats.extra_pixels>0&&cv::countNonZero(grown)>cv::countNonZero(mask),"M1_actual_expansion");
 cv::Mat denseMask(80,100,CV_8U,cv::Scalar(1));denseMask(cv::Rect(0,0,20,80)).setTo(0);Begin(1);auto limited=Apply(denseMask,z,gray,K,dist,1,0);check(cv::countNonZero(limited!=denseMask)==0,"union_area_limit_falls_back");
 std::vector<cv::Point3f>x,y;std::vector<cv::Point2f>pix;cv::Mat I=cv::Mat::eye(3,3,CV_64F),zero=cv::Mat::zeros(3,1,CV_64F);
 for(int v=0;v<8;v++)for(int u=0;u<9;u++){x.emplace_back(u*.06f,v*.06f,2+.01f*std::sin(float(u*v)));y.push_back(x.back()+cv::Point3f(.2f,0,0));pix.emplace_back(30+u*24,20+v*24);}
 auto moving=FitValidate(x,y,pix,I,zero,p);check(moving.accepted&&moving.rigid_error<1e-5&&moving.validation>=6,"heldout_rigid_motion_accept");
 auto stationary=FitValidate(x,x,pix,I,zero,p);check(!stationary.accepted&&stationary.reason=="static_or_indistinguishable","static_region_not_dynamic");
 auto tampered=y;for(size_t i=0;i<tampered.size();i+=3)tampered[i].y+=.15f*(int(i)%2?1:-1);auto held=FitValidate(x,tampered,pix,I,zero,p);check(!held.accepted&&held.reason=="heldout_inconsistent","training_fit_cannot_hide_holdout_error");
 std::vector<cv::Point3f>line(30);std::vector<cv::Point2f>lp(30);for(int i=0;i<30;i++){line[i]=cv::Point3f(i*.1,0,2);lp[i]=cv::Point2f(i*3,30);}check(!FitValidate(line,line,lp,I,zero,p).accepted,"collinear_3d_degeneracy");
 auto bad=x;bad[0].x=std::nanf("");check(!FitValidate(bad,y,pix,I,zero,p).accepted,"nonfinite_region_fallback");
 std::vector<cv::Point3f>world;std::vector<cv::Point2f>image;cv::Mat R,t;std::string reason;int in=0,cells=0;check(!FitBackground(world,image,K,dist,p,R,t,reason,in,cells),"background_PnP_empty_failure");
 K=(cv::Mat_<double>(3,3)<<542.822841,0,315.593520,0,542.57687,237.756098,0,0,1);dist=(cv::Mat_<double>(5,1)<<.039903,-.099343,-.000730,-.000144,0);
 for(int v=0;v<8;v++)for(int u=0;u<9;u++)world.emplace_back((u-4)*.18,(v-3.5)*.16,2+.03*((u+v)%3));cv::Vec3d rv(.01,-.02,.015),tv(.1,-.02,.03);cv::projectPoints(world,rv,tv,K,dist,image);uint64_t rng=cv::theRNG().state;check(FitBackground(world,image,K,dist,p,R,t,reason,in,cells),"nonzero_distortion_PnP_raw_pixel_test");check(cv::norm(t-cv::Mat(tv))<1e-4,"PnP_metric_pose_correct");check(cv::theRNG().state==rng,"helper_preserves_native_OpenCV_RNG");
 // Candidate current mask reads must be bounds safe for input features with NaN/outside pixels.
 Begin(1);stats.extra=cv::Mat::zeros(80,100,CV_8U);NoteLK(cv::Point2f(-99,-1),false);NoteORB(cv::Point2f(std::nanf(""),3),false);check(stats.lk_retained==1&&stats.orb_retained==1,"read_only_counter_bounds_safe");
 cv::Mat border=cv::Mat::zeros(z.size(),CV_8U);border(cv::Rect(0,0,4,4)).setTo(1);Generate(border,z,p,over);check(true,"border_mask_safe");
 std::cout<<"ALL_TESTS_PASS"<<std::endl;return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<std::endl;return 1;}}
