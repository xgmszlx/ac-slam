from pathlib import Path
import difflib
D=Path(__file__).resolve().parents[1];P=Path('/media/wcqw/KESU/slam_research');S=P/'ngd_region_prototype_20261021/NGD-SLAM';V=P/'ngd_ccl_compat_v2_20261020/NGD-SLAM'
for name in ['Tracking.cc','Frame.cc','ORBmatcher.cc','Optimizer.cc']:
 p=S/'src'/name;original=(V/'src'/name).read_text();s='#include "RegionExpansion.h"\n'+original
 if name=='Tracking.cc':
  a='Sophus::SE3f Tracking::GrabImageRGBD(const cv::Mat &imRGB, const cv::Mat &imD, const double &timestamp, string filename)\n{';assert s.count(a)==1;s=s.replace(a,a+'\n    region::Begin(timestamp);')
  a='    if(mFrameNum > 1) PredictCurrentMask();';assert s.count(a)==1;s=s.replace(a,a+'''
    region::stats.base = mImMask.clone();
    region::stats.base_pixels = cv::countNonZero(mImMask);
    region::stats.base_hash = region::HashMask(mImMask);
    if(region::Mode() != 0)
        mImMask = region::Apply(mImMask, mImDepth2, mImGray, mK, mDistCoef, timestamp, mpAtlas->GetCurrentMap()->GetId());
    else {
        region::stats.extra = cv::Mat::zeros(mImMask.size(), CV_8U);
        region::stats.candidate_union = cv::Mat::zeros(mImMask.size(), CV_8U);
        region::stats.full = mImMask.clone();
    }
''')
  a='    return mCurrentFrame.GetPose();\n}\n\nvoid Tracking::ChangeCalibration';# use exact scoped function end instead
  start=s.index('Sophus::SE3f Tracking::GrabImageRGBD(');end=s.index('\n}',start);chunk=s[start:end];needle='    return mCurrentFrame.GetPose();';assert chunk.count(needle)==1;chunk=chunk.replace(needle,'''    region::RecordCompleted(mCurrentFrame, mState, mpAtlas->GetCurrentMap()->GetId(), mpAtlas->GetAllMaps().size(), mImGray, mImDepth2, mK, mDistCoef);
'''+needle);s=s[:start]+chunk+s[end:]
  a='    cv::solvePnPRansac(currMapPoints, currKeyPoints, mK, mDistCoef , R_vector, T, false, 100, 5, 0.99, ransacInlier, cv::SOLVEPNP_ITERATIVE);';assert s.count(a)==1;s=s.replace(a,a+'\n    region::stats.pnp_calls++;\n    region::stats.pnp_inliers += ransacInlier.size();')
 elif name=='Frame.cc':
  a='        int val = (int)imMask.at<uchar>(mvKeys[i].pt.y,mvKeys[i].pt.x);';assert s.count(a)==1;s=s.replace(a,a+'\n        region::NoteORB(mvKeys[i].pt, val != 0);')
 elif name=='ORBmatcher.cc':
  a='            if (status[i] && imMask.at<uchar>(currKeyPoints[i].y, currKeyPoints[i].x) == 0)';assert s.count(a)==1;s=s.replace(a,'''            if(status[i]) {
                const auto &p = currKeyPoints[i];
                bool inside = std::isfinite(p.x) && std::isfinite(p.y) && p.x >= 0 && p.y >= 0 && p.x < imMask.cols && p.y < imMask.rows;
                region::NoteLK(p, inside && imMask.at<uchar>((int)p.y,(int)p.x) != 0);
            }
'''+a)
 elif name=='Optimizer.cc':
  a='    if(nInitialCorrespondences<3)\n        return 0;';assert s.count(a)==1;s=s.replace(a,'    if(nInitialCorrespondences<3) { region::NoteOptimization(nInitialCorrespondences, 0); return 0; }')
  a='    return nInitialCorrespondences-nBad;';assert s.count(a)==3;s=s.replace(a,'    region::NoteOptimization(nInitialCorrespondences, nInitialCorrespondences-nBad);\n'+a,1)
 p.write_text(s);(D/'audit'/(name+'.patch')).write_text(''.join(difflib.unified_diff(original.splitlines(True),s.splitlines(True),fromfile='a/src/'+name,tofile='b/src/'+name)))
print('Source instrumentation installed: common counters; region helper only if mode !=0; original formulas unchanged')
