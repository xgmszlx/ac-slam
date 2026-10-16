import pathlib,shutil,re,json,hashlib,difflib,datetime
N=pathlib.Path(__file__).resolve().parents[1];O=N.parent;S=O/'sources/ORB_SLAM3-4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4'
assert not json.loads((N/'audit/P1_gate.json').read_text())['solves']
D=N/'masked_source';D.mkdir(exist_ok=False);(D/'src').mkdir();shutil.copytree(S/'include',D/'include');(D/'Thirdparty').symlink_to(S/'Thirdparty',target_is_directory=True)
def block(s,marker):
 start=s.index(marker);b=s.index('{',start);depth=1;i=b+1
 while depth:
  depth+=(s[i]=='{')-(s[i]=='}');i+=1
 return start,i,s[start:i]
changes={}
# Add methods, preserving every original method definition and all class layouts.
for name in ['System','Tracking','Frame']:
 s=(S/'src'/(name+'.cc')).read_text();h=(S/'include'/(name+'.h')).read_text()
 if name=='System':
  marker='Sophus::SE3f System::TrackRGBD(';a,b,original=block(s,marker)
  added=original.replace('System::TrackRGBD(const cv::Mat &im,','System::TrackRGBDMasked(const cv::Mat &exclusionMask, const cv::Mat &im,',1).replace('mpTracker->GrabImageRGBD(imToFeed,','mpTracker->GrabImageRGBDMasked(exclusionMask,imToFeed,',1)
  decl=next(l for l in h.splitlines() if 'Sophus::SE3f TrackRGBD(' in l);newdecl=decl.replace('TrackRGBD(const cv::Mat &im,','TrackRGBDMasked(const cv::Mat &exclusionMask, const cv::Mat &im,',1)
 elif name=='Tracking':
  marker='Sophus::SE3f Tracking::GrabImageRGBD(';a,b,original=block(s,marker)
  added=original.replace('Tracking::GrabImageRGBD(const cv::Mat &imRGB,','Tracking::GrabImageRGBDMasked(const cv::Mat &exclusionMask, const cv::Mat &imRGB,',1).replace('Frame(mImGray,imDepth,','Frame(exclusionMask,mImGray,imDepth,')
  decl=next(l for l in h.splitlines() if 'Sophus::SE3f GrabImageRGBD(' in l);newdecl=decl.replace('GrabImageRGBD(const cv::Mat &imRGB,','GrabImageRGBDMasked(const cv::Mat &exclusionMask, const cv::Mat &imRGB,',1)
 else:
  marker='Frame::Frame(const cv::Mat &imGray, const cv::Mat &imDepth,';a,b,original=block(s,marker)
  added=original.replace('Frame::Frame(const cv::Mat &imGray,','Frame::Frame(const cv::Mat &exclusionMask, const cv::Mat &imGray,',1)
  needle='    ExtractORB(0,imGray,0,0);';assert added.count(needle)==1
  added=added.replace(needle,needle+'\n    diagnostic::ExcludeFeatures(exclusionMask,imGray.size(),mvKeys,mDescriptors);')
  decl=next(l for l in h.splitlines() if 'Frame(const cv::Mat &imGray, const cv::Mat &imDepth,' in l);newdecl=decl.replace('Frame(const cv::Mat &imGray,','Frame(const cv::Mat &exclusionMask, const cv::Mat &imGray,',1)
 s=s[:b]+'\n\n// Diagnostic person-exclusion overload; original path above remains unchanged.\n'+added+'\n'+s[b:]
 if name=='Frame':s='#include "FeatureExclusion.h"\n'+s
 h=h.replace(decl,decl+'\n'+newdecl,1)
 (D/'src'/(name+'.cc')).write_text(s);(D/'include'/(name+'.h')).write_text(h)
 for path,new in [('src/'+name+'.cc',s),('include/'+name+'.h',h)]:
  old=(S/path).read_text();changes[path]=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+path,tofile='b/'+path))
(D/'include/FeatureExclusion.h').write_text('''#pragma once
#include <opencv2/core.hpp>
#include <opencv2/features2d.hpp>
#include <vector>
namespace ORB_SLAM3 { namespace diagnostic {
inline void ExcludeFeatures(const cv::Mat &mask,const cv::Size &size,std::vector<cv::KeyPoint> &keys,cv::Mat &descriptors) {
    if(mask.empty()) return; // exact original output, no operation
    CV_Assert(mask.type()==CV_8UC1 && mask.size()==size);
    CV_Assert(descriptors.rows==static_cast<int>(keys.size()));
    std::vector<cv::KeyPoint> kept; kept.reserve(keys.size()); cv::Mat selected;
    for(size_t i=0;i<keys.size();++i) {
        const int x=static_cast<int>(keys[i].pt.x),y=static_cast<int>(keys[i].pt.y);
        CV_Assert(x>=0 && y>=0 && x<mask.cols && y<mask.rows);
        if(mask.at<unsigned char>(y,x)==0) { kept.push_back(keys[i]); selected.push_back(descriptors.row(i)); }
    }
    keys.swap(kept); descriptors=selected;
}
}}
''')
(N/'audit/feature_exclusion.patch').write_text(''.join(changes.values())+'\n# New helper: masked_source/include/FeatureExclusion.h\n')
s=(N/'code/rgbd_diagnostic.cc').read_text().replace('if(argc != 5)','if(argc != 6)').replace('Usage: ./rgbd_tum path_to_vocabulary path_to_settings path_to_sequence path_to_association','Usage: ./rgbd_masked vocabulary settings sequence associations mask_directory')
s=s.replace('        // Pass the image to the SLAM system\n        Sophus::SE3f Tcw = SLAM.TrackRGBD(imRGB,imD,tframe);','''        // Mask filename preserves the source RGB timestamp stem; no GT lookup.
        const string rgbName=vstrImageFilenamesRGB[ni];
        const string maskName=string(argv[5])+"/"+rgbName.substr(rgbName.find_last_of('/')+1);
        cv::Mat personMask=cv::imread(maskName,cv::IMREAD_GRAYSCALE);
        if(personMask.empty() || personMask.size()!=imRGB.size()) { cerr << "MASK_IDENTITY_OR_SIZE_FAILURE " << maskName << endl; return 8; }
        Sophus::SE3f Tcw = SLAM.TrackRGBDMasked(personMask,imRGB,imD,tframe);''')
# Mask disk IO is inside timed call block and native pacing, counted in tracking time.
assert 'TrackRGBDMasked' in s;(N/'code/rgbd_masked.cc').write_text(s)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
(N/'protocol/P2_code_frozen.json').write_text(json.dumps({'registered_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_sha256':{str(p.relative_to(N)):sha(p) for p in list((D/'src').glob('*.cc'))+[D/'include'/n for n in ['System.h','Tracking.h','Frame.h','FeatureExclusion.h']]+[N/'code/rgbd_masked.cc',N/'code/make_masks.py']},'original_methods_preserved':True,'class_layout_unchanged':True,'unchanged_backend_objects':'read-only linked from original build; no optimizer compilation/modification','mask_filter':'post ExtractORB, before N/depth/undistortion/grid in added RGBD Frame overload','map_point_boundary':'does not delete old map points or mark dynamic; descriptor matching uses remaining current-frame indices; no additional projection semantic filter','P2_order':['walking/P2_01','walking/P2_02','walking/P2_03','sitting/P2_01'],'order_limitation':'P2 qualification conditional on completed P1; P0/P1 interleaved, P2 runs later; no extra P1 runs authorized'},indent=2))
print(D)
