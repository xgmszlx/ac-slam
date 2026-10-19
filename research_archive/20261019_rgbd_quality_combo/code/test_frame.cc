#include <Frame.h>
#include <ORBextractor.h>
#include <CameraModels/Pinhole.h>
#include "Combo.h"
#include <cassert>
#include <iostream>
using namespace ORB_SLAM3;
int main(){
 cv::Mat gray(480,640,CV_8U);cv::RNG rng(19);rng.fill(gray,cv::RNG::UNIFORM,0,255);auto original=gray.clone();cv::Mat depth(480,640,CV_32F,cv::Scalar(3));cv::Mat K=(cv::Mat_<float>(3,3)<<500,0,320,0,500,240,0,0,1),dist=cv::Mat::zeros(5,1,CV_32F);Pinhole cam({500,500,320,240});ORBVocabulary voc;ORBextractor ext(1000,1.2,8,20,7);
 combo::configure(0);Frame first(gray,depth,1.,&ext,&voc,K,dist,40.,3.,&cam);cv::Mat bad=depth.clone();for(int i=0;i<60;++i)bad.at<float>((int)first.mvKeys[i].pt.y,(int)first.mvKeys[i].pt.x)=.1f;Frame raw(gray,bad,1.2,&ext,&voc,K,dist,40.,3.,&cam);
 combo::configure(2);Frame warm(gray,depth,1.,&ext,&voc,K,dist,40.,3.,&cam);Frame kept(gray,bad,1.2,&ext,&voc,K,dist,40.,3.,&cam);assert(raw.N==kept.N && cv::norm(raw.mDescriptors,kept.mDescriptors,cv::NORM_INF)==0);int changed=0;
 for(int i=0;i<kept.N;++i){assert(raw.mvKeys[i].pt==kept.mvKeys[i].pt);if(combo::fallback(i,1.2)){assert(kept.mvDepth[i]==-1&&kept.mvuRight[i]==-1);++changed;}else{assert(raw.mvDepth[i]==kept.mvDepth[i]);assert(raw.mvuRight[i]==kept.mvuRight[i]);}auto ids=kept.GetFeaturesInArea(kept.mvKeysUn[i].pt.x,kept.mvKeysUn[i].pt.y,1.);assert(std::find(ids.begin(),ids.end(),i)!=ids.end());}
 assert(changed>0);assert(kept.mvpMapPoints.size()==(size_t)kept.N&&kept.mvbOutlier.size()==(size_t)kept.N);
 combo::configure(1);Frame warm1(gray,depth,1.,&ext,&voc,K,dist,40.,3.,&cam);Frame rejected(gray,bad,1.2,&ext,&voc,K,dist,40.,3.,&cam);assert(rejected.N<raw.N);
 for(int i=0;i<rejected.N;++i){int j=-1;for(int k=0;k<raw.N;++k)if(raw.mvKeys[k].pt==rejected.mvKeys[i].pt&&raw.mvKeys[k].octave==rejected.mvKeys[i].octave)j=k;assert(j>=0);assert(cv::norm(raw.mDescriptors.row(j),rejected.mDescriptors.row(i),cv::NORM_INF)==0);assert(raw.mvDepth[j]==rejected.mvDepth[i]);}
 assert(cv::norm(gray,original,cv::NORM_INF)==0);std::cout<<"PASS actual Frame software chain: S2 N="<<kept.N<<" depth fallbacks="<<changed<<", S1 kept="<<rejected.N<<"; native descriptor/depth/grid indices consistent, pixels untouched. Synthetic, not SLAM or dataset evidence.\n";
}
