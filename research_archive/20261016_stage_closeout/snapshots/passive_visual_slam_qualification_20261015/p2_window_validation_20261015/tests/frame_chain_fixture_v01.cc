#include <Frame.h>
#include <ORBextractor.h>
#include <ORBmatcher.h>
#include <Map.h>
#include <MapPoint.h>
#include <CameraModels/Pinhole.h>
#include <opencv2/opencv.hpp>
#include <fstream>
#include <sstream>
#include <cassert>
#include <memory>
#include <set>
#include <iomanip>
using namespace ORB_SLAM3;
using namespace std;
void same(const Frame&a,const Frame&b){
 assert(a.N==b.N&&a.mTimeStamp==b.mTimeStamp);assert(a.mDescriptors.size()==b.mDescriptors.size());assert(cv::norm(a.mDescriptors,b.mDescriptors,cv::NORM_INF)==0);
 for(int i=0;i<a.N;i++){
  const auto x=a.mvKeys[i],y=b.mvKeys[i];assert(x.pt==y.pt&&x.size==y.size&&x.angle==y.angle&&x.response==y.response&&x.octave==y.octave);
  assert(a.mvKeysUn[i].pt==b.mvKeysUn[i].pt);assert(a.mvDepth[i]==b.mvDepth[i]);assert(a.mvuRight[i]==b.mvuRight[i]);assert(a.mvpMapPoints[i]==b.mvpMapPoints[i]);
 }
 for(int x=0;x<FRAME_GRID_COLS;x++)for(int y=0;y<FRAME_GRID_ROWS;y++)assert(a.mGrid[x][y]==b.mGrid[x][y]);
}
void valid(Frame&f,const cv::Mat&mask,const cv::Mat&depth){
 assert(f.N==(int)f.mvKeys.size()&&f.N==f.mDescriptors.rows);assert(f.mvKeysUn.size()==(size_t)f.N&&f.mvDepth.size()==(size_t)f.N&&f.mvpMapPoints.size()==(size_t)f.N&&f.mvbOutlier.size()==(size_t)f.N);
 size_t cells=0;
 for(int x=0;x<FRAME_GRID_COLS;x++)for(int y=0;y<FRAME_GRID_ROWS;y++)for(auto i:f.mGrid[x][y]){assert(i<(size_t)f.N);cells++;}assert(cells==(size_t)f.N);
 for(int i=0;i<f.N;i++){
  const auto&k=f.mvKeys[i];int x=(int)k.pt.x,y=(int)k.pt.y;assert(mask.empty()||mask.at<unsigned char>(y,x)==0);float d=depth.at<float>(y,x);assert(f.mvDepth[i]==(d>0?d:-1));
  auto ids=f.GetFeaturesInArea(f.mvKeysUn[i].pt.x,f.mvKeysUn[i].pt.y,3);assert(find(ids.begin(),ids.end(),i)!=ids.end());for(auto j:ids)assert(j<(size_t)f.N);
 }
}
int main(int argc,char**argv){
 assert(argc==4);ifstream in(argv[2]);string l;vector<double> ts;vector<string>rgb,dep;
 while(getline(in,l)){if(l.empty()||l[0]=='#')continue;istringstream s(l);double t,d;string a,b;s>>t>>a>>d>>b;ts.push_back(t);rgb.push_back(a);dep.push_back(b);}
 vector<double> sample={0,18,21,22,22.5,23,23.5,24,24.5,25,26.8};set<size_t>indices;
 for(double t:sample){size_t k=0;for(size_t i=0;i<ts.size();i++)if(abs(ts[i]-ts[0]-t)<abs(ts[k]-ts[0]-t))k=i;indices.insert(k);}
 cv::Mat K=(cv::Mat_<float>(3,3)<<535.4,0,320.1,0,539.2,247.6,0,0,1),dist=cv::Mat::zeros(4,1,CV_32F);Pinhole cam({535.4f,539.2f,320.1f,247.6f});ORBVocabulary voc;ORBextractor ex1(1000,1.2,8,20,7),ex2(1000,1.2,8,20,7),ex3(1000,1.2,8,20,7);
 ofstream out(argv[3]);out<<"index,stamp,input_features,kept_features,removed,projection_associations,index_tests_PASS\n"<<fixed<<setprecision(9);
 for(size_t i:indices){
  cv::Mat im=cv::imread(string(argv[1])+"/"+rgb[i],-1),before=im.clone(),gray,depth,raw=cv::imread(string(argv[1])+"/"+dep[i],-1);cv::cvtColor(im,gray,cv::COLOR_BGR2GRAY);raw.convertTo(depth,CV_32F,1./5000.);
  Frame base(gray,depth,ts[i],&ex1,&voc,K,dist,535.4*.0747,40.,&cam);
  Frame empty(cv::Mat(),gray,depth,ts[i],&ex2,&voc,K,dist,535.4*.0747,40.,&cam);same(base,empty);valid(empty,cv::Mat(),depth);
  cv::Mat mask=cv::Mat::zeros(gray.size(),CV_8UC1);mask(cv::Rect(150,100,300,300)).setTo(255);
  Frame filtered(mask,gray,depth,ts[i],&ex3,&voc,K,dist,535.4*.0747,40.,&cam);valid(filtered,mask,depth);assert(filtered.N<base.N&&filtered.N>0);
  int j=0;for(int k=0;k<base.N;k++){auto p=base.mvKeys[k].pt;if(mask.at<unsigned char>((int)p.y,(int)p.x)==0){assert(filtered.mvKeys[j].pt==p);assert(cv::norm(filtered.mDescriptors.row(j),base.mDescriptors.row(k),cv::NORM_INF)==0);assert(filtered.mvDepth[j]==base.mvDepth[k]);++j;}}assert(j==filtered.N);assert(cv::norm(im,before,cv::NORM_INF)==0);
  base.SetPose(Sophus::SE3f());filtered.SetPose(Sophus::SE3f());Map map;vector<unique_ptr<MapPoint>> points;set<MapPoint*>known;
  for(int k=0;k<base.N;k++){Eigen::Vector3f xyz;if(base.UnprojectStereo(k,xyz)){points.emplace_back(new MapPoint(xyz,&map,&base,k));base.mvpMapPoints[k]=points.back().get();known.insert(points.back().get());}}
  ORBmatcher matcher(.6,true);int matches=matcher.SearchByProjection(filtered,base,1.,false);assert(matches>0);
  for(int k=0;k<filtered.N;k++)if(filtered.mvpMapPoints[k])assert(known.count(filtered.mvpMapPoints[k])==1);
  valid(filtered,mask,depth);
  // All-excluded Frame only tests the original early-return contract N=0; no claim about full tracker handling.
  cv::Mat all(gray.size(),CV_8UC1,cv::Scalar(255));Frame zero(all,gray,depth,ts[i],&ex3,&voc,K,dist,535.4*.0747,40.,&cam);assert(zero.N==0&&zero.mvKeys.empty()&&zero.mDescriptors.rows==0);
  out<<i<<","<<ts[i]<<","<<base.N<<","<<filtered.N<<","<<base.N-filtered.N<<","<<matches<<",1\n";
 }
 cout<<"Frame sample tests PASS: "<<indices.size()<<"; synthetic rectangles only; no real person-mask or SLAM system qualification"<<endl;
}
