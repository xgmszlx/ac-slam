// Actual installed RTAB-Map RegistrationIcp microprobe; no graph, odometry or ROS replay.
#include <rtabmap/core/Registration.h>
#include <rtabmap/core/RegistrationInfo.h>
#include <rtabmap/core/SensorData.h>
#include <rtabmap/core/Parameters.h>
#include <rtabmap/utilite/ULogger.h>
#include <fstream>
#include <iostream>
#include <memory>
#include <vector>
#include <algorithm>
using namespace rtabmap;
SensorData load(const std::string & file,int id) {
    std::ifstream f(file);std::vector<cv::Vec2f> v;float x,y;
    while(f>>x>>y)v.emplace_back(x,y);
    cv::Mat m(1,v.size(),CV_32FC2);
    for(size_t i=0;i<v.size();++i)m.at<cv::Vec2f>(0,i)=v[i];
    SensorData d;d.setId(id);d.setStamp(id);
    d.setLaserScan(LaserScan(m,901,25.f,LaserScan::kXY));return d;
}
int main(int argc,char **argv) {
    if(argc!=7)return 2;
    ULogger::setLevel(ULogger::kError);
    ParametersMap p=Parameters::getDefaultParameters();
    p["Reg/Strategy"]="1";p["Reg/Force3DoF"]="true";p["Icp/PointToPlane"]="true";
    std::ofstream params(std::string(argv[6])+".parameters.tsv");
    for(const auto & kv:p)if(kv.first.find("Icp/")==0 || kv.first.find("Reg/")==0)params<<kv.first<<'\t'<<kv.second<<'\n';
    std::unique_ptr<Registration> reg(Registration::create(p));
    SensorData a=load(argv[1],1),b=load(argv[2],2);RegistrationInfo info;
    Transform guess(std::stof(argv[3]),std::stof(argv[4]),std::stof(argv[5]));
    Transform t=reg->computeTransformation(a,b,guess,&info);
    std::string why=info.rejectedMsg;std::replace(why.begin(),why.end(),'\n',' ');std::replace(why.begin(),why.end(),'\t',' ');
    std::ofstream out(argv[6]);
    out<<"accepted\tx\ty\tyaw\tcorrespondences\tinliers_ratio\tcomplexity\ticp_rms\tcov_x\tcov_y\trejected\n";
    out<<(!t.isNull())<<'\t'<<(t.isNull()?0:t.x())<<'\t'<<(t.isNull()?0:t.y())<<'\t'<<(t.isNull()?0:t.theta())<<'\t'
       <<info.icpCorrespondences<<'\t'<<info.icpInliersRatio<<'\t'<<info.icpStructuralComplexity<<'\t'<<info.icpRMS<<'\t'
       <<(info.covariance.empty()?0:info.covariance.at<double>(0,0))<<'\t'<<(info.covariance.empty()?0:info.covariance.at<double>(1,1))<<'\t'<<why<<'\n';
    return 0;
}
