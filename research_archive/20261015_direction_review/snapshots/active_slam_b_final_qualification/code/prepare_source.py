"""Patch fixed ROS1 copies only; no estimator equations or thresholds edited."""
import shutil,hashlib,json,difflib
from pathlib import Path
R=Path(__file__).resolve().parents[1];src=R/'sources/upstream';ws=R/'catkin_ws/src';ws.mkdir(parents=True,exist_ok=True)
for name in ['rtabmap_odom','rtabmap_slam']:shutil.copytree(src/name,ws/name,dirs_exist_ok=True)
checks={}
for file in ['OdometryROS.h','PluginInterface.h']:
 a=src/'rtabmap_odom/include/rtabmap_odom'/file;b=Path('/opt/ros/noetic/include/rtabmap_odom')/file;checks[file]=a.read_bytes()==b.read_bytes()
for f,sub in [('OdometryROS.cpp','rtabmap_odom/src'),('icp_odometry.cpp','rtabmap_odom/src/nodelets'),('CoreWrapper.cpp','rtabmap_slam/src')]:checks[f]=(src/sub/f).read_bytes()==(R/'sources'/f).read_bytes()
(R/'audit/source_version_match.json').write_text(json.dumps(checks,indent=2));assert all(checks.values())
def patch(path,old,new,expected=1):
 p=ws/path;s=p.read_text();assert s.count(old)==expected,(path,old[:60],s.count(old));p.write_text(s.replace(old,new,1))
odom='rtabmap_odom/src/OdometryROS.cpp';icp='rtabmap_odom/src/nodelets/icp_odometry.cpp';slam='rtabmap_slam/src/CoreWrapper.cpp'
for f in [odom,icp,slam]:
 p=ws/f;s=p.read_text();i=s.index('#include');p.write_text(s[:i]+'#include <slam_audit/Trace.h>\n'+s[i:])
patch(icp,'\t\tscanReceived_ = true;','\t\tslam_audit::emit(scanMsg->header,"CALLBACK_ENTER");\n\t\tscanReceived_ = true;')
patch(icp,'\t\tif(localScanTransform.isNull())','\t\tslam_audit::emit(scanMsg->header,localScanTransform.isNull()?"LASER_TF_FAIL":"LASER_TF_OK");\n\t\tif(localScanTransform.isNull())',expected=2)
patch(icp,'\t\tthis->processData(data, scanMsg->header);','\t\tslam_audit::emit(scanMsg->header,"PREPROCESS_COMPLETE");\n\t\tthis->processData(data, scanMsg->header);')
patch(odom,'\t//NODELET_WARN("Received image: %f delay=%f", data.stamp(), (ros::Time::now() - header.stamp).toSec());','\tslam_audit::emit(header,"SLOT_ATTEMPT");')
patch(odom,'\t\tdataToProcess_ = data;','\t\tslam_audit::emit(header,"SLOT_ACCEPTED");\n\t\tdataToProcess_ = data;')
patch(odom,'\t\tNODELET_DEBUG("Dropping image/scan data");','\t\tslam_audit::emit(header,"LOCK_DROP");\n\t\tNODELET_DEBUG("Dropping image/scan data");')
patch(odom,'\tUScopeMutex lock(dataMutex_);\n\n\t// aliases','\tslam_audit::End end; // declared before lock: emits AFTER mutex release\n\tUScopeMutex lock(dataMutex_);\n\n\t// aliases')
patch(odom,'\tstd_msgs::Header & header = dataHeaderToProcess_;','\tstd_msgs::Header & header = dataHeaderToProcess_;\n\tend.header=header; slam_audit::setContext(header);\n\tslam_audit::emit(header,"PROCESS_LOOP_ENTER");')
patch(odom,'\t\tguessCurrentPose = rtabmap_conversions::getTransform(guessFrameId_, frameId_, header.stamp, this->tfListener(), this->waitForTransformDuration());','\t\tslam_audit::emit(header,"GUESS_TF_BEGIN");\n\t\tguessCurrentPose = rtabmap_conversions::getTransform(guessFrameId_, frameId_, header.stamp, this->tfListener(), this->waitForTransformDuration());\n\t\tslam_audit::emit(header,guessCurrentPose.isNull()?"GUESS_TF_FAIL":"GUESS_TF_OK");')
patch(odom,'\t\tpose = odometry_->process(data, guess_, &info);','\t\tslam_audit::emit(header,"ESTIMATOR_BEGIN");\n\t\tpose = odometry_->process(data, guess_, &info);\n\t\tslam_audit::emit(header,pose.isNull()?"ESTIMATOR_FAILED":"ESTIMATOR_SUCCESS");')
patch(odom,'\t\t\todomInfoPub_.publish(infoMsg);','\t\t\todomInfoPub_.publish(infoMsg);\n\t\t\tslam_audit::emit(header,"ODOMINFO_PUBLISHED",std::string("{\\\"lost\\\":")+(infoMsg.lost?"true":"false")+"}");')
patch(slam,'\t\tif(rtabmap_.process(data, odom, covariance, odomVelocity, externalStats))','\t\tstd_msgs::Header auditHeader; auditHeader.stamp=stamp; slam_audit::setContext(auditHeader);\n\t\tslam_audit::emit(auditHeader,"GRAPH_PROCESS_BEGIN");\n\t\tif(rtabmap_.process(data, odom, covariance, odomVelocity, externalStats))')
patch(slam,'\t\tif(rtabmap_.process(data, odom, covariance, odomVelocity, externalStats))\n\t\t{\n\t\t\ttimeRtabmap = timer.ticks();','\t\tif(rtabmap_.process(data, odom, covariance, odomVelocity, externalStats))\n\t\t{\n\t\t\tslam_audit::emit(auditHeader,"GRAPH_PROCESS_SUCCESS",std::string("{\\\"last_node_id\\\":")+std::to_string(rtabmap_.getMemory()->getLastSignatureId())+"}");\n\t\t\ttimeRtabmap = timer.ticks();')
patch(slam,'\t\t\t\tmapsManager_.publishMaps(filteredPoses, stamp, mapFrameId_);','\t\t\t\tslam_audit::emit(auditHeader,"MAP_CACHE_SELECTED",slam_audit::ids(filteredPoses));\n\t\t\t\tmapsManager_.publishMaps(filteredPoses, stamp, mapFrameId_);\n\t\t\t\tslam_audit::emit(auditHeader,"MAP_PUBLISH_RETURN",slam_audit::ids(filteredPoses));')
for name,target in [('rtabmap_odom','rtabmap_odom'),('rtabmap_slam','rtabmap_slam_plugins')]:
 p=ws/name/'CMakeLists.txt';s=p.read_text();s=s.replace('find_package(catkin REQUIRED COMPONENTS','find_package(catkin REQUIRED COMPONENTS\n             slam_audit')
 if name=='rtabmap_odom':
  for x in ['rgbd_odometry.cpp','stereo_odometry.cpp','rgbdicp_odometry.cpp']:s=s.replace('   src/nodelets/'+x+'\n','')
 p.write_text(s+'\nadd_dependencies('+target+' ${catkin_EXPORTED_TARGETS})\n')
for name in ['rtabmap_odom','rtabmap_slam']:
 dif=[]
 for p in (ws/name).rglob('*'):
  if p.is_file():
   original=src/name/p.relative_to(ws/name)
   if p.read_bytes()!=original.read_bytes():dif.extend(difflib.unified_diff(original.read_text().splitlines(True),p.read_text().splitlines(True),fromfile=str(original),tofile=str(p)))
 (R/'patches'/(name+'.patch')).write_text(''.join(dif))
