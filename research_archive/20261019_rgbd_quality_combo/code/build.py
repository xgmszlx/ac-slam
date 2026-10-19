from pathlib import Path
import json,subprocess,difflib,hashlib
P=Path(__file__).resolve().parents[1];O=Path('/home/wcqw/passive_rgbd_depth_screen_20261019');S=Path('/home/wcqw/passive_visual_slam_qualification_20261015/sources/ORB_SLAM3-4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4');base=json.loads((O/'audit/compile_commands.json').read_text());entry=json.loads((O/'audit/entry_build.json').read_text())[0]
# Modify only the RGB-D constructor. Other constructors and extraction stay original.
orig=(S/'src/Frame.cc').read_text();start=orig.index('Frame::Frame(const cv::Mat &imGray, const cv::Mat &imDepth');end=orig.index('Frame::Frame(',start+12);chunk=orig[start:end];assert chunk.count('ExtractORB(0,imGray,0,0);')==1
chunk=chunk.replace('ExtractORB(0,imGray,0,0);','ExtractORB(0,imGray,0,0);\n    combo::before(imGray,imDepth,timeStamp,K,distCoef,mvKeys,mDescriptors);').replace('ComputeStereoFromRGBD(imDepth);','ComputeStereoFromRGBD(imDepth);\n    combo::invalidate(mvDepth,mvuRight);')
frame='#include "Combo.h"\n'+orig[:start]+chunk+orig[end:];(P/'code/Frame_combo.cc').write_text(frame)
opt=(S/'src/Optimizer.cc').read_text();a=opt.index('int Optimizer::PoseOptimization(Frame *pFrame)');b=opt.index('return nInitialCorrespondences-nBad;',a);optnew='#include "Combo.h"\n'+opt[:b]+'combo::edges(pFrame->mTimeStamp,vnIndexEdgeMono,vnIndexEdgeStereo,pFrame->mvbOutlier);\n    '+opt[b:];(P/'code/Optimizer_trace.cc').write_text(optnew)
system=(O/'code/System_diagnostic.cc').read_text();systemnew='#include "Combo.h"\n'+system.replace('zeroBoth=0;','zeroBoth=0,tag2=0,tag3=0;').replace('if(f.mvuRight[i]<0)++i2;else ++i3;','if(f.mvuRight[i]<0){++i2;if(combo::fallback(i,expectedStamp))++tag2;}else{++i3;if(combo::fallback(i,expectedStamp))++tag3;}').replace('allpoints,allkf};','allpoints,allkf,tag2,tag3};');(P/'code/System_combo.cc').write_text(systemnew)
patch=''
for name,old,new in [('src/Frame.cc',orig,frame),('src/Optimizer.cc', (S/'src/Optimizer.cc').read_text(),optnew),('src/System.cc',(O/'code/System_diagnostic.cc').read_text(),systemnew)]:patch+=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+name,tofile='b/'+name))
(P/'audit/native_frontend_and_trace.patch').write_text(patch)
records=[]
for name in ['Frame_combo','Optimizer_trace','System_combo','Combo']:
 cmd=base['compile'].copy();idx=cmd.index('-c');cmd[idx+1]=str(P/'code'/f'{name}.cc');cmd[-1]=str(P/'build'/f'{name}.o');cmd.insert(1,'-I'+str(P/'code'));records.append(cmd)
 with (P/'audit'/f'build_{name}.log').open('w') as log:subprocess.run(cmd,cwd=S/'build',stdout=log,stderr=subprocess.STDOUT,check=True)
link=base['link'].copy();link=[x for x in link if not x.endswith(('System_diagnostic.o','src/Frame.cc.o','src/Optimizer.cc.o'))];link[link.index('-o')+1]=str(P/'build/libORB_SLAM3.so');link += [str(P/'build'/f'{n}.o') for n in ['Frame_combo','Optimizer_trace','System_combo','Combo']]
with (P/'audit/build_link.log').open('w') as log:subprocess.run(link,cwd=S/'build',stdout=log,stderr=subprocess.STDOUT,check=True)
(P/'audit/build_commands.json').write_text(json.dumps({'compile':records,'link':link},indent=2));print('New isolated library built; original source/objects untouched.')
