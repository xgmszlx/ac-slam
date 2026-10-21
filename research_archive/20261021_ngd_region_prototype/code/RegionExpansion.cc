#include "RegionExpansion.h"
#include <opencv2/imgproc.hpp>
#include <opencv2/calib3d.hpp>
#include <opencv2/video/tracking.hpp>
#include <algorithm>
#include <numeric>
#include <random>
#include <set>
#include <deque>
#include <chrono>
#include <cmath>
#include <stdexcept>
#include <time.h>
#include "Frame.h"
#include "MapPoint.h"
namespace region {
thread_local Stats stats;
static int mode_=0;
static thread_local double module_cpu_ms=0;
static double threadCPU(){timespec t;clock_gettime(CLOCK_THREAD_CPUTIME_ID,&t);return t.tv_sec*1000.0+t.tv_nsec/1e6;}
double LastModuleCPU(){return module_cpu_ms;}
struct Cache {bool valid=false;double stamp=0;int map=-1;cv::Mat gray,depth,R,t;std::vector<cv::Point2f> raw;std::vector<cv::Point3f> world;};
static thread_local Cache cache;
static Params params;
using Clock=std::chrono::steady_clock;
static double ms(Clock::time_point t){return std::chrono::duration<double,std::milli>(Clock::now()-t).count();}
static bool finite(const cv::Mat&m){return !m.empty()&&cv::checkRange(m,true,nullptr,-1e100,1e100);}
static bool inside(const cv::Point2f&p,cv::Size s,int b=0){return std::isfinite(p.x)&&std::isfinite(p.y)&&p.x>=b&&p.y>=b&&p.x<s.width-b&&p.y<s.height-b;}
static bool on(const cv::Mat&m,const cv::Point2f&p){return inside(p,m.size())&&m.at<uchar>((int)p.y,(int)p.x)!=0;}
static bool zvalid(float z){return std::isfinite(z)&&z>=.05f;}
static double med(std::vector<double> v){if(v.empty())return 1e50;std::nth_element(v.begin(),v.begin()+v.size()/2,v.end());return v[v.size()/2];}
static cv::Point3f transform(const cv::Mat&R,const cv::Mat&t,const cv::Point3f&x){return cv::Point3f(R.at<double>(0,0)*x.x+R.at<double>(0,1)*x.y+R.at<double>(0,2)*x.z+t.at<double>(0),R.at<double>(1,0)*x.x+R.at<double>(1,1)*x.y+R.at<double>(1,2)*x.z+t.at<double>(1),R.at<double>(2,0)*x.x+R.at<double>(2,1)*x.y+R.at<double>(2,2)*x.z+t.at<double>(2));}
int Mode(){return mode_;}void SetMode(int mode){if(mode<0||mode>2)throw std::invalid_argument("mode");mode_=mode;cache=Cache();}
void Begin(double stamp){static thread_local int i=0;stats=Stats();module_cpu_ms=0;stats.index=i++;stats.stamp=stamp;stats.mode=mode_;}
uint64_t HashMask(const cv::Mat&m){uint64_t h=1469598103934665603ULL;for(int y=0;y<m.rows;y++)for(int x=0;x<m.cols;x++){h^=m.at<uchar>(y,x)?1:0;h*=1099511628211ULL;}return h;}
std::vector<Candidate> Generate(const cv::Mat& mask,const cv::Mat& depth,const Params&p,int& oversized){
 oversized=0;std::vector<Candidate> out;
 if(mask.empty()||depth.empty()||mask.type()!=CV_8UC1||depth.type()!=CV_32FC1||mask.size()!=depth.size())return out;
 if(cv::countNonZero(mask)==0)return out;
 int g=p.grid,nx=(mask.cols+g-1)/g,ny=(mask.rows+g-1)/g;std::vector<float> z(nx*ny,0);std::vector<uchar> masked(nx*ny,0),seen(nx*ny,0);
 for(int y=0;y<ny;y++)for(int x=0;x<nx;x++){int id=y*nx+x;cv::Rect r(x*g,y*g,std::min(g,mask.cols-x*g),std::min(g,mask.rows-y*g));masked[id]=cv::countNonZero(mask(r))>0;z[id]=depth.at<float>(std::min(y*g+g/2,mask.rows-1),std::min(x*g+g/2,mask.cols-1));}
 int dx[]={1,-1,0,0},dy[]={0,0,1,-1};
 for(int sy=0;sy<ny;sy++)for(int sx=0;sx<nx;sx++){
  int seed=sy*nx+sx;if(masked[seed]||seen[seed]||!zvalid(z[seed]))continue;bool touches=false;
  for(int k=0;k<4;k++){int x=sx+dx[k],y=sy+dy[k];if(x>=0&&x<nx&&y>=0&&y<ny){int j=y*nx+x;if(masked[j]&&zvalid(z[j])&&std::abs(z[j]-z[seed])<=p.depth_gate)touches=true;}}
  if(!touches)continue;
  float anchor=z[seed];std::deque<int> q;q.push_back(seed);seen[seed]=1;std::vector<int> component;
  while(!q.empty()){int i=q.front();q.pop_front();component.push_back(i);int x=i%nx,y=i/nx;
   for(int k=0;k<4;k++){int u=x+dx[k],v=y+dy[k];if(u<0||v<0||u>=nx||v>=ny)continue;int j=v*nx+u;if(!masked[j]&&!seen[j]&&zvalid(z[j])&&std::abs(z[i]-z[j])<=p.depth_gate&&std::abs(z[j]-anchor)<=p.depth_gate){seen[j]=1;q.push_back(j);}}
  }
  if(component.size()*g*g<p.min_pixels)continue;
  cv::Mat proposal=cv::Mat::zeros(mask.size(),CV_8U);
  for(int i:component){int x=i%nx,y=i/nx;for(int v=y*g;v<std::min((y+1)*g,mask.rows);v++)for(int u=x*g;u<std::min((x+1)*g,mask.cols);u++){float d=depth.at<float>(v,u);if(!mask.at<uchar>(v,u)&&zvalid(d)&&std::abs(d-anchor)<=p.depth_gate)proposal.at<uchar>(v,u)=1;}}
  int area=cv::countNonZero(proposal);if(area<p.min_pixels)continue;if(area>p.max_region_fraction*mask.total()){oversized++;continue;}Candidate c;c.mask=proposal;c.pixels=area;c.hash=HashMask(proposal);out.push_back(c);
 }
 std::stable_sort(out.begin(),out.end(),[](const Candidate&a,const Candidate&b){return a.pixels>b.pixels;});if(out.size()>(size_t)p.max_regions)out.resize(p.max_regions);
 int total=0;std::vector<Candidate> bounded;for(auto &c:out){if(total+c.pixels>p.max_extra_fraction*mask.total()){oversized++;continue;}c.id=bounded.size();total+=c.pixels;bounded.push_back(c);}return bounded;
}
static bool spread(const std::vector<cv::Point3f>&pts,const std::vector<int>&ids,const Params&p,double*ratio=nullptr){
 if(ids.size()<3)return false;cv::Mat m((int)ids.size(),3,CV_64F);cv::Vec3d center(0,0,0);for(int i:ids)center+=cv::Vec3d(pts[i].x,pts[i].y,pts[i].z);center*=1.0/ids.size();for(size_t k=0;k<ids.size();k++){auto x=pts[ids[k]];for(int j=0;j<3;j++)m.at<double>(k,j)=cv::Vec3d(x.x,x.y,x.z)[j]-center[j];}
 cv::SVD sv(m,cv::SVD::NO_UV);double s0=sv.w.at<double>(0),s1=sv.w.at<double>(1);if(ratio)*ratio=s1/std::max(s0,1e-30);return std::isfinite(s0)&&s0/std::sqrt((double)ids.size())>=p.min_spread&&s1/std::max(s0,1e-30)>=p.min_second_ratio;
}
static bool rigid(const std::vector<cv::Point3f>&a,const std::vector<cv::Point3f>&b,const std::vector<int>&idx,cv::Mat&R,cv::Mat&t){
 if(idx.size()<3)return false;cv::Vec3d ca(0,0,0),cb(0,0,0);for(int i:idx){ca+=cv::Vec3d(a[i].x,a[i].y,a[i].z);cb+=cv::Vec3d(b[i].x,b[i].y,b[i].z);}ca*=1.0/idx.size();cb*=1.0/idx.size();cv::Mat H=cv::Mat::zeros(3,3,CV_64F);for(int i:idx){cv::Vec3d x=cv::Vec3d(a[i].x,a[i].y,a[i].z)-ca,y=cv::Vec3d(b[i].x,b[i].y,b[i].z)-cb;for(int u=0;u<3;u++)for(int v=0;v<3;v++)H.at<double>(u,v)+=x[u]*y[v];}
 cv::SVD sv(H);cv::Mat V=sv.vt.t(),Q=cv::Mat::eye(3,3,CV_64F);Q.at<double>(2,2)=cv::determinant(V*sv.u.t())<0?-1:1;R=V*Q*sv.u.t();t=cv::Mat(cb)-R*cv::Mat(ca);return finite(R)&&finite(t)&&std::abs(cv::determinant(R)-1)<1e-5;
}
Verdict FitValidate(const std::vector<cv::Point3f>&a,const std::vector<cv::Point3f>&b,const std::vector<cv::Point2f>&pix,const cv::Mat&Rbg,const cv::Mat&tbg,const Params&p){
 Verdict v;v.pairs=a.size();if(a.size()!=b.size()||a.size()!=pix.size()||a.size()<(size_t)p.min_pairs||!finite(Rbg)||!finite(tbg)){v.reason="insufficient_pairs_or_background";return v;}
 for(size_t i=0;i<a.size();i++)if(!std::isfinite(cv::norm(a[i]))||!std::isfinite(cv::norm(b[i]))){v.reason="nonfinite_pair";return v;}
 std::vector<int> train,hold;for(size_t i=0;i<a.size();i++)((i%3==0)?hold:train).push_back(i);v.train=train.size();v.validation=hold.size();if(hold.size()<(size_t)p.min_validation){v.reason="few_holdout";return v;}
 if(!spread(a,train,p,&v.ratio)||!spread(b,train,p)||!spread(a,hold,p)||!spread(b,hold,p)){v.reason="degenerate_3d";return v;}
 std::set<std::pair<int,int>> cells;cv::Rect2f bounds;float xmin=1e8,xmax=-1e8,ymin=1e8,ymax=-1e8;for(int i:hold){cells.insert({(int)pix[i].x/20,(int)pix[i].y/20});xmin=std::min(xmin,pix[i].x);xmax=std::max(xmax,pix[i].x);ymin=std::min(ymin,pix[i].y);ymax=std::max(ymax,pix[i].y);}if(cells.size()<4||xmax-xmin<20||ymax-ymin<20){v.reason="narrow_image_support";return v;}
 std::mt19937 rng(1729);std::uniform_int_distribution<int> pick(0,train.size()-1);std::vector<int> best;
 Params samplep=p;samplep.min_spread=.005;samplep.min_second_ratio=.01;
 for(int k=0;k<p.ransac;k++){std::vector<int>s={train[pick(rng)],train[pick(rng)],train[pick(rng)]};if(s[0]==s[1]||s[1]==s[2]||s[0]==s[2]||!spread(a,s,samplep)||!spread(b,s,samplep))continue;cv::Mat R,t;if(!rigid(a,b,s,R,t))continue;std::vector<int>in;for(int i:train)if(cv::norm(transform(R,t,a[i])-b[i])<=p.fit_gate)in.push_back(i);if(in.size()>best.size())best=in;}
 v.train_inliers=best.size();if(best.size()<(size_t)p.min_train_inliers||best.size()*2<train.size()||!spread(a,best,p)||!rigid(a,b,best,v.R,v.t)){v.reason="rigid_train_failed";return v;}
 std::vector<double> er,es;int good=0;for(int i:hold){double e=cv::norm(transform(v.R,v.t,a[i])-b[i]);er.push_back(e);es.push_back(cv::norm(transform(Rbg,tbg,a[i])-b[i]));if(e<=p.fit_gate)good++;}
 v.rigid_error=med(er);v.static_error=med(es);if(!std::isfinite(v.rigid_error)||!std::isfinite(v.static_error)){v.reason="nonfinite_validation";return v;}
 if(good*5<(int)hold.size()*4||v.rigid_error>p.fit_gate){v.reason="heldout_inconsistent";return v;}
 if(v.static_error-v.rigid_error<=p.motion_gain){v.reason="static_or_indistinguishable";return v;}
 v.accepted=true;v.reason="rigid_motion_validated";return v;
}
bool FitBackground(const std::vector<cv::Point3f>&world,const std::vector<cv::Point2f>&raw,const cv::Mat&K,const cv::Mat&dist,const Params&p,cv::Mat&R,cv::Mat&t,std::string&reason,int&inliers,int&cells){
 inliers=0;cells=0;for(auto &x:world)if(!std::isfinite(cv::norm(x))){reason="nonfinite_background";return false;}for(auto &x:raw)if(!std::isfinite(x.x)||!std::isfinite(x.y)){reason="nonfinite_background";return false;}if(world.size()!=raw.size()||world.size()<(size_t)p.min_bg){reason="few_background_pairs";return false;}
 std::vector<int> ids(world.size());std::iota(ids.begin(),ids.end(),0);if(!spread(world,ids,p)){reason="background_3d_degenerate";return false;}
 cv::Mat rv,in;uint64_t rng=cv::theRNG().state;bool okay=false;try{cv::theRNG().state=73;okay=cv::solvePnPRansac(world,raw,K,dist,rv,t,false,100,5,.99,in,cv::SOLVEPNP_ITERATIVE);}catch(const cv::Exception&){okay=false;}cv::theRNG().state=rng;
 if(!okay||!finite(rv)||!finite(t)){reason="PnP_failed";return false;}cv::Rodrigues(rv,R);R.convertTo(R,CV_64F);t.convertTo(t,CV_64F);inliers=in.rows;std::set<int> occupied;std::vector<int> kept;
 for(int k=0;k<in.rows;k++){int i=in.at<int>(k);if(i<0||i>=(int)raw.size())continue;occupied.insert(std::max(0,std::min(5,(int)(raw[i].y/80)))*8+std::max(0,std::min(7,(int)(raw[i].x/80))));kept.push_back(i);}cells=occupied.size();
 if(inliers<p.min_bg||cells<p.min_bg_cells||!spread(world,kept,p)||!finite(R)||!finite(t)){reason="weak_background_support";return false;}reason="background_PnP_valid";return true;
}
static bool stableDepth(const cv::Mat&z,cv::Point2f uv,float&value){if(!inside(uv,z.size(),1))return false;int x=cvRound(uv.x),y=cvRound(uv.y);if(x<1||y<1||x>=z.cols-1||y>=z.rows-1)return false;value=z.at<float>(y,x);if(!zvalid(value))return false;float lo=value,hi=value;int n=0;for(int v=y-1;v<=y+1;v++)for(int u=x-1;u<=x+1;u++){float d=z.at<float>(v,u);if(zvalid(d)){n++;lo=std::min(lo,d);hi=std::max(hi,d);}}return n>=5&&hi-lo<=params.depth_gate;}
static cv::Point3f backproject(cv::Point2f raw,float z,const cv::Mat&K,const cv::Mat&dist){std::vector<cv::Point2f>a={raw},u;cv::undistortPoints(a,u,K,dist);return cv::Point3f(u[0].x*z,u[0].y*z,z);}
static void flow(const cv::Mat&a,const cv::Mat&b,const std::vector<cv::Point2f>&x,std::vector<cv::Point2f>&y,std::vector<uchar>&good){
 good.assign(x.size(),0);if(x.empty())return;std::vector<uchar>s1,s2;std::vector<float>e;std::vector<cv::Point2f>back;cv::calcOpticalFlowPyrLK(a,b,x,y,s1,e,cv::Size(21,21),3);cv::calcOpticalFlowPyrLK(b,a,y,back,s2,e,cv::Size(21,21),3);for(size_t i=0;i<x.size();i++)good[i]=s1[i]&&s2[i]&&inside(x[i],a.size(),2)&&inside(y[i],b.size(),2)&&cv::norm(x[i]-back[i])<=params.fb_gate;
}
static cv::Mat ApplyImpl(const cv::Mat&base,const cv::Mat&depth,const cv::Mat&gray,const cv::Mat&K,const cv::Mat&dist,double stamp,int map){
 auto start=Clock::now();cv::Mat output=base.clone();stats.base=base.clone();stats.extra=cv::Mat::zeros(base.size(),CV_8U);stats.candidate_union=cv::Mat::zeros(base.size(),CV_8U);stats.base_pixels=cv::countNonZero(base);stats.base_hash=HashMask(base);
 auto cstart=Clock::now();auto candidates=Generate(base,depth,params,stats.oversize);stats.candidate_ms=ms(cstart);stats.candidates=candidates.size();for(auto&c:candidates){stats.candidate_union|=c.mask;stats.region_pixels.push_back(c.pixels);}stats.candidate_pixels=cv::countNonZero(stats.candidate_union);stats.candidate_hash=HashMask(stats.candidate_union);
 if(candidates.empty()){stats.bg_reason="no_candidates";stats.module_ms=ms(start);stats.full=output;return output;}
 bool bgvalid=false;cv::Mat Rbg,tbg;auto bs=Clock::now();
 if(mode_==2){
  stats.bg_attempt=1;
  if(!cache.valid||cache.map!=map||stamp<=cache.stamp||stamp-cache.stamp>.2){stats.bg_reason="previous_completed_frame_unavailable";}
  else{std::vector<cv::Point2f>curr;std::vector<uchar>okay;flow(cache.gray,gray,cache.raw,curr,okay);std::vector<cv::Point2f>raw;std::vector<cv::Point3f>world;for(size_t i=0;i<okay.size();i++)if(okay[i]&&!on(base,curr[i])&&!on(stats.candidate_union,curr[i])){raw.push_back(curr[i]);world.push_back(cache.world[i]);}stats.bg_pairs=world.size();bgvalid=FitBackground(world,raw,K,dist,params,Rbg,tbg,stats.bg_reason,stats.bg_inliers,stats.bg_cells);}
 }
 stats.bg_ms=ms(bs);auto rs=Clock::now();
 for(auto &c:candidates){Verdict v;
  if(mode_==1){v.accepted=true;v.reason="simple_depth_extension";}
  else if(!bgvalid){v.reason=stats.bg_reason;}
  else{
   std::vector<cv::Point2f>points;
   for(int y=7;y<gray.rows;y+=15)for(int x=7;x<gray.cols;x+=15)if(c.mask.at<uchar>(y,x)){float z;if(stableDepth(depth,cv::Point2f(x,y),z))points.emplace_back(x,y);}
   if(points.size()>400)points.resize(400);
   std::vector<cv::Point2f>prev;std::vector<uchar>okay;flow(gray,cache.gray,points,prev,okay);std::vector<cv::Point3f>a,b;std::vector<cv::Point2f>pix;
   for(size_t i=0;i<okay.size();i++)if(okay[i]){float z1,z2;if(stableDepth(cache.depth,prev[i],z1)&&stableDepth(depth,points[i],z2)){a.push_back(backproject(prev[i],z1,K,dist));b.push_back(backproject(points[i],z2,K,dist));pix.push_back(points[i]);}}
   cv::Mat relativeR=Rbg*cache.R.t(),relativet=tbg-relativeR*cache.t;
   v=FitValidate(a,b,pix,relativeR,relativet,params);
   if(v.accepted){
    // Conservative held-out visibility: either hypothesis behind a nearer measured surface is ambiguous, never a dynamic label.
    int visible=0;for(size_t i=0;i<a.size();i+=3){bool valid=true;for(int hypothesis=0;hypothesis<2;hypothesis++){cv::Point3f x=transform(hypothesis?v.R:relativeR,hypothesis?v.t:relativet,a[i]);if(!zvalid(x.z)){valid=false;break;}std::vector<cv::Point3f>X={x};std::vector<cv::Point2f>uv;cv::projectPoints(X,cv::Vec3d(0,0,0),cv::Vec3d(0,0,0),K,dist,uv);if(!inside(uv[0],depth.size(),1)){valid=false;break;}float z=depth.at<float>(cvRound(uv[0].y),cvRound(uv[0].x));if(!zvalid(z)||z+.05<x.z){valid=false;break;}}
     if(valid)visible++;else v.occluded++;
    }
    if(visible<params.min_validation||v.occluded*3>v.validation){v.accepted=false;v.reason="visibility_ambiguous";}
   }
  }
  if(v.accepted){cv::Mat merged=output|c.mask;if(cv::countNonZero(merged)>params.max_union_fraction*base.total()){v.accepted=false;v.reason="union_area_guard";}else{output=merged;stats.extra|=c.mask;stats.accepted++;}}
  stats.verdicts.push_back(v);
 }
 stats.region_ms=ms(rs);stats.extra_pixels=cv::countNonZero(stats.extra);stats.full=output.clone();stats.module_ms=ms(start);return output;
}
cv::Mat Apply(const cv::Mat&base,const cv::Mat&depth,const cv::Mat&gray,const cv::Mat&K,const cv::Mat&dist,double stamp,int map){
 uint64_t original_rng=cv::theRNG().state;double cpu_start=threadCPU();
 try {auto result=ApplyImpl(base,depth,gray,K,dist,stamp,map);cv::theRNG().state=original_rng;module_cpu_ms=threadCPU()-cpu_start;return result;}
 catch(const cv::Exception&){cv::theRNG().state=original_rng;stats.bg_reason="opencv_exception_safe_fallback";stats.extra=cv::Mat::zeros(base.size(),CV_8U);stats.extra_pixels=0;stats.accepted=0;stats.full=base.clone();module_cpu_ms=threadCPU()-cpu_start;return base.clone();}
}
void RecordCompleted(ORB_SLAM3::Frame&f,int state,int map,int maps,const cv::Mat&gray,const cv::Mat&depth,const cv::Mat&K,const cv::Mat&dist){
 stats.state=state;stats.map=map;stats.map_count=maps;stats.frame_N=f.N;stats.pose_valid=f.isSet()&&f.GetPose().matrix().allFinite();
 for(size_t i=0;i<f.mvpMapPoints.size();i++)if(f.mvpMapPoints[i]){stats.associations++;if(i>=f.mvbOutlier.size()||!f.mvbOutlier[i])stats.returned_inliers++;}
 if(mode_!=2)return;
 cache=Cache();if(state!=2||!stats.pose_valid)return;cache.stamp=stats.stamp;cache.map=map;cache.gray=gray.clone();cache.depth=depth.clone();cache.R=cv::Mat(3,3,CV_64F);cache.t=cv::Mat(3,1,CV_64F);auto pose=f.GetPose();for(int y=0;y<3;y++){cache.t.at<double>(y)=pose.translation()[y];for(int x=0;x<3;x++)cache.R.at<double>(y,x)=pose.rotationMatrix()(y,x);}
 for(size_t i=0;i<f.mvpMapPoints.size();i++){auto mp=f.mvpMapPoints[i];if(!mp||mp->isBad()||mp->Observations()<3||(i<f.mvbOutlier.size()&&f.mvbOutlier[i]))continue;if(i>=f.mvKeysUn.size())continue;cv::Point2f uv=(i<f.mvKeys.size())?f.mvKeys[i].pt:f.mvKeysUn[i].pt;if(!inside(uv,gray.size(),2))continue;auto w=mp->GetWorldPos();if(!w.allFinite())continue;cache.raw.push_back(uv);cache.world.emplace_back(w[0],w[1],w[2]);if(cache.raw.size()>=400)break;}
 cache.valid=cache.raw.size()>=20;
}
void NoteLK(const cv::Point2f&p,bool removed){if(stats.index<0)return;stats.lk_checked++;if(removed){if(!stats.extra.empty()&&on(stats.extra,p))stats.lk_deleted_extra++;else stats.lk_deleted_base++;}else stats.lk_retained++;}
void NoteORB(const cv::Point2f&p,bool removed){if(stats.index<0)return;stats.orb_raw++;if(removed){if(!stats.extra.empty()&&on(stats.extra,p))stats.orb_deleted_extra++;else stats.orb_deleted_base++;}else stats.orb_retained++;}
void NoteOptimization(int edges,int inliers){if(stats.index<0)return;stats.opt_calls++;stats.opt_edges_sum+=edges;stats.opt_inliers_sum+=inliers;stats.opt_last_edges=edges;stats.opt_last_inliers=inliers;}
}
