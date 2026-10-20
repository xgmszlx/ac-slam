#include "Combo.h"
#include <deque>
#include <cmath>
#include <chrono>
#include <algorithm>
namespace combo {
struct Input {cv::Mat gray,depth,des;std::vector<cv::KeyPoint> keys;double stamp;};
struct State {int mode=0,frame=0;double stamp=0;std::deque<Input> history;std::vector<unsigned char> tags;std::vector<double> s;};
thread_local State g;
void configure(int mode){g=State();g.mode=mode;cv::setNumThreads(1);}
float z(const cv::Mat& d,cv::Point2f p){return d.at<float>((int)p.y,(int)p.x);}
bool reliable(const cv::Mat& d,cv::Point2f p){float c=z(d,p);if(c<.3f||c>6.f)return false;int n=0;float lo=1e9f,hi=0;
 for(int y=std::max(0,(int)p.y-1);y<=std::min(d.rows-1,(int)p.y+1);++y)for(int x=std::max(0,(int)p.x-1);x<=std::min(d.cols-1,(int)p.x+1);++x){float a=d.at<float>(y,x);if(a>0){++n;lo=std::min(lo,a);hi=std::max(hi,a);}}
 return n>=5 && hi-lo<=std::max(.05f,.03f*c);
}
cv::Point3f xyz(cv::Point2f und,float dep){return {und.x*dep,und.y*dep,dep};}
void before(const cv::Mat& gray,const cv::Mat& depth,double stamp,const cv::Mat& K,const cv::Mat& dist,std::vector<cv::KeyPoint>& keys,cv::Mat& des){
 auto start=std::chrono::steady_clock::now();g.stamp=stamp;g.tags.assign(keys.size(),0);g.s.assign(19,0);g.s[0]=keys.size();g.s[1]=keys.size();g.s[15]=-1;
 if(g.mode==0){++g.frame;return;}
 Input now{gray.clone(),depth.clone(),des.clone(),keys,stamp};int ref=-1;double best=1e9;
 for(size_t j=0;j<g.history.size();++j){double dt=stamp-g.history[j].stamp;if(dt>=.18&&dt<=.28&&fabs(dt-.2)<best){best=fabs(dt-.2);ref=j;}}
 std::vector<unsigned char> drop(keys.size(),0),tag(keys.size(),0);
 if(ref>=0 && !des.empty() && !g.history[ref].des.empty()){
  const auto& a=g.history[ref];g.s[15]=a.stamp;
  cv::BFMatcher bf(cv::NORM_HAMMING);std::vector<std::vector<cv::DMatch>> fw,bw;bf.knnMatch(a.des,des,fw,2);bf.knnMatch(des,a.des,bw,2);
  std::vector<cv::DMatch> matches;std::vector<cv::Point2f> p,q;
  for(auto& row:fw){if(row.size()!=2)continue;auto m=row[0];auto& r=bw[m.trainIdx];if(r.size()==2 && r[0].trainIdx==m.queryIdx && m.distance<=50 && m.distance<.75*row[1].distance && r[0].distance<.75*r[1].distance){matches.push_back(m);p.push_back(a.keys[m.queryIdx].pt);q.push_back(keys[m.trainIdx].pt);}}
  g.s[2]=matches.size();
  if(!p.empty()){
   std::vector<cv::Point2f> flow,back,un1,un2;std::vector<uchar> ok1,ok2;std::vector<float> err;
   cv::calcOpticalFlowPyrLK(a.gray,gray,p,flow,ok1,err,cv::Size(21,21),3);cv::calcOpticalFlowPyrLK(gray,a.gray,flow,back,ok2,err,cv::Size(21,21),3);
   cv::undistortPoints(p,un1,K,dist);cv::undistortPoints(q,un2,K,dist);
   std::vector<unsigned char> good(matches.size(),0);std::vector<cv::Point3f> object;std::vector<cv::Point2f> image;
   for(size_t j=0;j<matches.size();++j){int i=matches[j].trainIdx;bool pass=ok1[j]&&ok2[j]&&cv::norm(back[j]-p[j])<=1.&&cv::norm(flow[j]-q[j])<=2.;
    if(!pass){if(g.mode!=4){drop[i]=1;g.s[4]++;}continue;}good[j]=1;g.s[3]++;
    float zz=z(a.depth,p[j]);if(zz>=.3 && zz<=6){object.push_back(xyz(un1[j],zz));image.push_back(q[j]);}
   }
   cv::Mat rv,tv,inliers;bool pose=false;
   if(object.size()>=8){auto saved=cv::theRNG().state;cv::theRNG().state=20261019+g.frame;pose=cv::solvePnPRansac(object,image,K,dist,rv,tv,false,100,3.,.99,inliers,cv::SOLVEPNP_EPNP);cv::theRNG().state=saved;pose=pose&&inliers.rows>=8;}
   g.s[5]=pose;g.s[6]=inliers.rows;
   if(pose){cv::Mat R;cv::Rodrigues(rv,R);R.convertTo(R,CV_64F);tv.convertTo(tv,CV_64F);
    for(size_t j=0;j<matches.size();++j){if(!good[j])continue;int i=matches[j].trainIdx;float z1=z(a.depth,p[j]),z2=z(depth,q[j]);bool both=z1>0&&z2>0;
     bool depthOK=reliable(a.depth,p[j])&&reliable(depth,q[j]);bool motion=false;
     if(both){auto X=xyz(un1[j],z1),Y=xyz(un2[j],z2);cv::Mat src=(cv::Mat_<double>(3,1)<<X.x,X.y,X.z),dst=(cv::Mat_<double>(3,1)<<Y.x,Y.y,Y.z);motion=cv::norm(dst-(R*src+tv))>.05;g.s[7]++;}
     if(g.mode==2 && !depthOK){if(z2>0){tag[i]=1;g.s[9]++;if(z1<.3||z1>6||z2<.3||z2>6)g.s[16]++;else g.s[17]++;}else g.s[18]++;g.s[10]++;}
     else if(motion && g.mode!=3){drop[i]=1;g.s[8]++;}
    }
   }
  }
 }
 // Keep a strict subset of original keypoints/descriptors, before Frame depth/grid indexing.
 std::vector<cv::KeyPoint> kept;cv::Mat selected;g.tags.clear();
 for(size_t i=0;i<keys.size();++i)if(!drop[i]){kept.push_back(keys[i]);selected.push_back(des.row(i));g.tags.push_back(tag[i]);}
 keys.swap(kept);des=selected;g.s[1]=keys.size();g.history.push_back(now);
 while(!g.history.empty()&&stamp-g.history.front().stamp>.4)g.history.pop_front();++g.frame;
 g.s[14]=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
}
void invalidate(std::vector<float>& depth,std::vector<float>& right){if(g.mode!=2)return;CV_Assert(depth.size()==g.tags.size()&&right.size()==g.tags.size());for(size_t i=0;i<g.tags.size();++i)if(g.tags[i]){depth[i]=-1;right[i]=-1;}}
bool fallback(int i,double stamp){return fabs(stamp-g.stamp)<1e-6 && i>=0 && i<(int)g.tags.size() && g.tags[i];}
void edges(double stamp,const std::vector<size_t>& mono,const std::vector<size_t>& stereo,const std::vector<bool>& outlier){
 if(fabs(stamp-g.stamp)>1e-6||g.s.size()!=19)return;
 // Last actual PoseOptimization call: observed edge indices, not a post-hoc geometric probe.
 g.s[11]=0;g.s[12]=0;g.s[13]=0;
 for(size_t i:mono)if(fallback((int)i,stamp)){g.s[11]++;if(!outlier[i])g.s[13]++;}
 for(size_t i:stereo)if(fallback((int)i,stamp))g.s[12]++;
}
std::vector<double> stats(){return g.s;}
}
