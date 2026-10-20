#include "Combo.cc"
#include <cassert>
#include <iostream>
int main(){
 cv::Mat im(240,320,CV_8U);cv::RNG rng(74);rng.fill(im,cv::RNG::UNIFORM,0,255);cv::Mat initial=im.clone(),depth(240,320,CV_32F,cv::Scalar(3));cv::Mat K=(cv::Mat_<double>(3,3)<<300,0,160,0,300,120,0,0,1),dist=cv::Mat::zeros(5,1,CV_64F);
 std::vector<cv::KeyPoint> raw;for(int y=40;y<=200;y+=40)for(int x=40;x<=280;x+=40)raw.emplace_back((float)x,(float)y,31.f);
 cv::Mat desc(raw.size(),32,CV_8U);rng.fill(desc,cv::RNG::UNIFORM,0,255);cv::Mat bad=depth.clone();bad.at<float>(40,40)=.1f;
 for(int mode: {0,1,3,4}){
  combo::configure(mode);auto k=raw;auto d=desc.clone();combo::before(im,depth,1.,K,dist,k,d);
  auto current=raw;current[1].pt.x+=10; // fixed descriptor match with intentionally inconsistent LK endpoint
  k=current;d=desc.clone();combo::before(im,bad,1.2,K,dist,k,d);auto s=combo::stats();
  assert(cv::norm(im,initial,cv::NORM_INF)==0);assert(s[9]==0);for(size_t i=0;i<k.size();++i){int j=-1;for(size_t a=0;a<current.size();++a)if(current[a].pt==k[i].pt)j=a;assert(j>=0&&cv::norm(d.row(i),desc.row(j),cv::NORM_INF)==0);}
  if(mode==0){assert(k.size()==raw.size()&&s[4]==0&&s[8]==0);}
  else{assert(s[5]==1);assert(s[3]==raw.size()-1);if(mode==1)assert(s[4]==1&&s[8]==1&&k.size()==raw.size()-2);if(mode==3)assert(s[4]==1&&s[8]==0&&k.size()==raw.size()-1);if(mode==4)assert(s[4]==0&&s[8]==1&&k.size()==raw.size()-1);}
  std::vector<float> dd(k.size(),3),rr(k.size(),5);combo::invalidate(dd,rr);for(size_t i=0;i<dd.size();++i)assert(dd[i]==3&&rr[i]==5);
 }
 std::cout<<"PASS switches: E1 deletes only fixed bad2D, E2 preserves bad2D and deletes only good2D bad-depth motion candidate; S0/S1 controls, unchanged RGB/descriptor subsets/depth. Synthetic only.\n";
}
