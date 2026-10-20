// Small deterministic software control; no System or sequence execution.
#include "Combo.cc"
#include <cassert>
#include <iostream>
int main(){
 cv::Mat im(240,320,CV_8U);cv::RNG rng(74);rng.fill(im,cv::RNG::UNIFORM,0,255);cv::Mat initial=im.clone(),depth(240,320,CV_32F,cv::Scalar(3));cv::Mat K=(cv::Mat_<double>(3,3)<<300,0,160,0,300,120,0,0,1),dist=cv::Mat::zeros(5,1,CV_64F);
 std::vector<cv::KeyPoint> raw;for(int y=40;y<=200;y+=40)for(int x=40;x<=280;x+=40)raw.emplace_back((float)x,(float)y,31.f);
 cv::Mat desc(raw.size(),32,CV_8U);rng.fill(desc,cv::RNG::UNIFORM,0,255);cv::Mat bad=depth.clone();bad.at<float>(40,40)=.1f;
 for(int mode=0;mode<=2;++mode){combo::configure(mode);auto k=raw;auto d=desc.clone();combo::before(im,depth,1.,K,dist,k,d);assert(k.size()==raw.size()&&cv::norm(desc,d,cv::NORM_INF)==0);k=raw;d=desc.clone();combo::before(im,bad,1.2,K,dist,k,d);
  auto stats=combo::stats();assert(cv::norm(im,initial,cv::NORM_INF)==0);
  if(mode==0){assert(k.size()==raw.size());assert(cv::norm(desc,d,cv::NORM_INF)==0);}
  else{assert(stats[5]==1);assert(stats[4]==0);for(size_t i=0;i<k.size();++i){int original=-1;for(size_t j=0;j<raw.size();++j)if(raw[j].pt==k[i].pt)original=j;assert(original>=0);assert(cv::norm(d.row(i),desc.row(original),cv::NORM_INF)==0);}
   if(mode==1){assert(k.size()==raw.size()-1&&stats[8]==1);}
   else{assert(k.size()==raw.size()&&stats[8]==0&&stats[9]==1);std::vector<float> dd(k.size(),3),right(k.size(),5);combo::invalidate(dd,right);assert(dd[0]==-1&&right[0]==-1);for(size_t i=1;i<k.size();++i)assert(dd[i]==3&&right[i]==5);}
  }
 }
 std::cout<<"PASS: no-action identity, unchanged pixels, descriptor subset alignment, common static PnP, S1 rejection, S2 low-depth 2D fallback, exact -1 propagation. Synthetic software control only.\n";
}
