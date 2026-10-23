// P1 unit tests for the mask-aware pre-culling path in ORBextractor.
// Every check is a property of the mechanism, not a tuned number.
#include <opencv2/opencv.hpp>
#include "ORBextractor.h"
#include <cstdlib>
#include <iostream>
#include <vector>

using namespace std;
using namespace ORB_SLAM3;
static int fails = 0;
static void ck(const char* name, bool ok, const string& detail="") {
    cout << (ok ? "  PASS  " : "  FAIL  ") << name;
    if(!detail.empty()) cout << " | " << detail;
    cout << endl;
    if(!ok) fails++;
}

static cv::Mat synth(int rows, int cols) {
    cv::Mat img(rows, cols, CV_8U);
    cv::RNG rng(12345);
    // dense texture so FAST always finds far more candidates than the budget
    for(int y=0;y<rows;y++) for(int x=0;x<cols;x++)
        img.at<uchar>(y,x) = (uchar)rng.uniform(0,255);
    return img;
}

static int countInMask(const vector<cv::KeyPoint>& kps, const cv::Mat& mask) {
    int n=0;
    for(size_t i=0;i<kps.size();++i){
        int x=cvRound(kps[i].pt.x), y=cvRound(kps[i].pt.y);
        if(x<0||y<0||x>=mask.cols||y>=mask.rows) continue;
        if(mask.at<uchar>(y,x)!=0) n++;
    }
    return n;
}

int main() {
    const int R=480, C=640, NF=1000;
    cv::Mat img = synth(R,C);

    // ---- T1 no mask, flag off vs on must produce the same keypoint count ----
    {
        ORBextractor ex(NF,1.2f,8,20,7);
        vector<cv::KeyPoint> k1,k2; cv::Mat d1,d2; vector<int> lap{0,0};
        ex(img, cv::Mat(), k1, d1, lap);
        setenv("NGD_ORB_PRECULL","1",1);
        ORBextractor ex2(NF,1.2f,8,20,7);
        ex2(img, cv::Mat(), k2, d2, lap);
        unsetenv("NGD_ORB_PRECULL");
        ck("empty mask: flag on/off give the same count", k1.size()==k2.size(),
           to_string(k1.size())+" vs "+to_string(k2.size()));
    }

    // ---- T2 full mask under pre-cull: no surviving keypoints in the mask ----
    {
        setenv("NGD_ORB_PRECULL","1",1);
        ORBextractor ex(NF,1.2f,8,20,7);
        cv::Mat full(R,C,CV_8U,cv::Scalar(1));
        vector<cv::KeyPoint> kk; cv::Mat dd; vector<int> lap{0,0};
        ex(img, full, kk, dd, lap);
        unsetenv("NGD_ORB_PRECULL");
        int inMask = countInMask(kk, full);
        ck("full mask: zero keypoints survive (pre-cull active)", kk.empty() && inMask==0,
           "n="+to_string(kk.size()));
    }

    // ---- T3 partial mask: pre-cull leaves none inside, and keeps the budget outside ----
    {
        cv::Mat m(R,C,CV_8U,cv::Scalar(0));
        m(cv::Rect(0,0,C/2,R)).setTo(1);            // left half dynamic
        // native path (flag off): extractor ignores mask entirely, Frame would delete later
        unsetenv("NGD_ORB_PRECULL");
        ORBextractor exA(NF,1.2f,8,20,7);
        vector<cv::KeyPoint> ka; cv::Mat da; vector<int> lap{0,0};
        exA(img, m, ka, da, lap);
        // pre-cull path
        setenv("NGD_ORB_PRECULL","1",1);
        ORBextractor exB(NF,1.2f,8,20,7);
        vector<cv::KeyPoint> kb; cv::Mat db; vector<int> lap2{0,0};
        exB(img, m, kb, db, lap2);
        unsetenv("NGD_ORB_PRECULL");
        int inA = countInMask(ka, m), inB = countInMask(kb, m);
        ck("pre-cull: zero keypoints inside a half-image mask", inB==0, "inside="+to_string(inB));
        ck("native path: extractor itself still returns keypoints inside the mask (it is ignored there)",
           inA>0, "inside="+to_string(inA));
        ck("pre-cull still fills most of the nominal budget from the valid half",
           (double)kb.size() > 0.5*NF, "n="+to_string(kb.size())+" target="+to_string(NF));
    }

    // ---- T4 mask on the right half: symmetry (no left/right bias in the filter) ----
    {
        cv::Mat m(R,C,CV_8U,cv::Scalar(0));
        m(cv::Rect(C/2,0,C/2,R)).setTo(1);
        setenv("NGD_ORB_PRECULL","1",1);
        ORBextractor ex(NF,1.2f,8,20,7);
        vector<cv::KeyPoint> kk; cv::Mat dd; vector<int> lap{0,0};
        ex(img, m, kk, dd, lap);
        unsetenv("NGD_ORB_PRECULL");
        ck("pre-cull symmetric: zero inside a right-half mask", countInMask(kk,m)==0,
           "inside="+to_string(countInMask(kk,m)));
    }

    // ---- T5 mask smaller than the image (pyramid scaling path) ----
    {
        cv::Mat m(R/2,C/2,CV_8U,cv::Scalar(1));   // deliberately wrong size: resize path must cope
        setenv("NGD_ORB_PRECULL","1",1);
        bool threw=false;
        try {
            ORBextractor ex(NF,1.2f,8,20,7);
            vector<cv::KeyPoint> kk; cv::Mat dd; vector<int> lap{0,0};
            ex(img, m, kk, dd, lap);
            ck("mask of a different size does not crash (resized per level)", kk.empty());
        } catch(const std::exception& e) { threw=true; ck("mask of a different size does not crash", false, e.what()); }
        unsetenv("NGD_ORB_PRECULL");
        (void)threw;
    }

    cout << endl;
    if(fails){ cout << "FAILED: " << fails << endl; return 1; }
    cout << "ALL PRE-CULL TESTS PASSED" << endl;
    return 0;
}
