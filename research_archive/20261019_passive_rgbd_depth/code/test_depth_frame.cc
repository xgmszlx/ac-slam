#include <Frame.h>
#include <ORBextractor.h>
#include <CameraModels/Pinhole.h>
#include <cassert>
#include <iostream>
#include "depth_rule.h"
using namespace ORB_SLAM3;
int main(int argc,char **argv){
 assert(argc==3);cv::Mat rgb=cv::imread(argv[1],-1),original=cv::imread(argv[2],-1),copy=rgb.clone(),gray;cv::cvtColor(rgb,gray,cv::COLOR_BGR2GRAY);
 cv::Mat mask=depthBoundary(original),filtered=original.clone();filtered.setTo(0,mask);cv::Mat outside=~mask;assert(cv::norm(original,filtered,cv::NORM_INF,outside)==0);assert(cv::norm(filtered,cv::NORM_INF,mask)==0);assert(cv::norm(copy,rgb,cv::NORM_INF)==0);
 cv::Mat d0,d1;original.convertTo(d0,CV_32F,1.f/5000.f);filtered.convertTo(d1,CV_32F,1.f/5000.f);cv::Mat K=(cv::Mat_<float>(3,3)<<535.4,0,320.1,0,539.2,247.6,0,0,1),dist=cv::Mat::zeros(4,1,CV_32F);Pinhole cam({535.4f,539.2f,320.1f,247.6f});ORBVocabulary voc;ORBextractor e0(1000,1.2,8,20,7),e1(1000,1.2,8,20,7);
 Frame a(gray,d0,1.,&e0,&voc,K,dist,535.4f*.0747f,.0747f*40.f,&cam),b(gray,d1,1.,&e1,&voc,K,dist,535.4f*.0747f,.0747f*40.f,&cam);assert(a.N==b.N);assert(cv::norm(a.mDescriptors,b.mDescriptors,cv::NORM_INF)==0);int affected=0;
 for(int i=0;i<a.N;++i){assert(a.mvKeys[i].pt==b.mvKeys[i].pt);int x=(int)a.mvKeys[i].pt.x,y=(int)a.mvKeys[i].pt.y;if(mask.at<unsigned char>(y,x)){assert(a.mvDepth[i]>0);assert(b.mvDepth[i]==-1 && b.mvuRight[i]==-1);++affected;}else{assert(a.mvDepth[i]==b.mvDepth[i]);assert(a.mvuRight[i]==b.mvuRight[i]);}}
 assert(affected>0);std::cout<<"PASS: RGB/keypoints/descriptors unchanged; nonboundary exact; native Frame changed "<<affected<<"/"<<a.N<<" depths to mvDepth=mvuRight=-1; 2D features retained\n";
}
