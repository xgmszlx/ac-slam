#pragma once
#include <opencv2/opencv.hpp>
#include <vector>
namespace combo {
void configure(int mode);
void before(const cv::Mat& gray,const cv::Mat& depth,double stamp,const cv::Mat& K,const cv::Mat& dist,std::vector<cv::KeyPoint>& keys,cv::Mat& descriptors);
void invalidate(std::vector<float>& depth,std::vector<float>& right);
bool fallback(int i,double stamp);
void edges(double stamp,const std::vector<size_t>& mono,const std::vector<size_t>& stereo,const std::vector<bool>& outlier);
std::vector<double> stats();
}
