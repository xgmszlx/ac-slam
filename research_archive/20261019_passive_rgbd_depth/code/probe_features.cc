#include <Frame.h>
#include <ORBextractor.h>
#include <CameraModels/Pinhole.h>
#include <fstream>
#include <iomanip>
#include "depth_rule.h"
using namespace ORB_SLAM3;
int main(int argc,char**argv){
 if(argc!=6)return 2;cv::FileStorage fs(argv[1],cv::FileStorage::READ);float fx=fs["Camera1.fx"],fy=fs["Camera1.fy"],cx=fs["Camera1.cx"],cy=fs["Camera1.cy"],base=fs["Stereo.b"],th=fs["Stereo.ThDepth"];
 cv::Mat K=(cv::Mat_<float>(3,3)<<fx,0,cx,0,fy,cy,0,0,1),dist=cv::Mat::zeros(5,1,CV_32F);dist.at<float>(0)=fs["Camera1.k1"];dist.at<float>(1)=fs["Camera1.k2"];dist.at<float>(2)=fs["Camera1.p1"];dist.at<float>(3)=fs["Camera1.p2"];if(!fs["Camera1.k3"].empty())dist.at<float>(4)=fs["Camera1.k3"];
 cv::Mat im=cv::imread(argv[2],-1),raw=cv::imread(argv[3],-1),gray,d;cv::cvtColor(im,gray,cv::COLOR_BGR2GRAY);raw.convertTo(d,CV_32F,1.f/5000.f);cv::Mat mask=depthBoundary(raw);cv::imwrite(argv[5],mask);
 Pinhole cam({fx,fy,cx,cy});ORBVocabulary voc;ORBextractor ex(1000,1.2,8,20,7);Frame f(gray,d,0,&ex,&voc,K,dist,fx*base,base*th,&cam);
 std::ofstream out(argv[4]);out<<"x,y,depth_m,boundary,close_3d_eligible\n"<<std::setprecision(9);
 for(int i=0;i<f.N;++i){auto k=f.mvKeys[i];out<<k.pt.x<<","<<k.pt.y<<","<<f.mvDepth[i]<<","<<(int)(mask.at<unsigned char>((int)k.pt.y,(int)k.pt.x)>0)<<","<<(f.mvDepth[i]>0 && f.mvDepth[i]<base*th)<<"\n";}
}
