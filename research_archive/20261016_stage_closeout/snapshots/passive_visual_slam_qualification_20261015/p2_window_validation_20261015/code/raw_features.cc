#include <ORBextractor.h>
#include <opencv2/opencv.hpp>
#include <fstream>
#include <sstream>
#include <iomanip>
#include <vector>
using namespace std;
int main(int argc,char**argv) {
 if(argc!=4)return 2;
 ifstream a(argv[2]);string line;vector<double>ts;vector<string>rgb,dep;
 while(getline(a,line)){if(line.empty()||line[0]=='#')continue;istringstream in(line);double t,d;string r,p;in>>t>>r>>d>>p;ts.push_back(t);rgb.push_back(r);dep.push_back(p);}
 ofstream out(argv[3]);out<<"index,stamp,x,y,octave,depth_m\n"<<fixed<<setprecision(9);
 ORB_SLAM3::ORBextractor ex(1000,1.2,8,20,7);
 for(size_t i=0;i<ts.size();++i){double rel=ts[i]-ts[0];if(rel<18||rel>27)continue;
  cv::Mat im=cv::imread(string(argv[1])+"/"+rgb[i],-1),depth=cv::imread(string(argv[1])+"/"+dep[i],-1),gray;cv::cvtColor(im,gray,cv::COLOR_BGR2GRAY);
  vector<cv::KeyPoint>keys;cv::Mat des;vector<int>lap(2,0);ex(gray,cv::Mat(),keys,des,lap);
  for(const auto&k:keys){auto d=depth.at<unsigned short>((int)k.pt.y,(int)k.pt.x);out<<i<<","<<ts[i]<<","<<k.pt.x<<","<<k.pt.y<<","<<k.octave<<","<<d/5000.0<<"\n";}
 }
}
