// Interpose the exported installed 0.21.13 method. All arguments and result go
// unchanged to the original method via RTLD_NEXT; no numerical code copied.
#include <rtabmap/core/RegistrationIcp.h>
#include <slam_audit/Trace.h>
#include <dlfcn.h>
#include <stdexcept>
#include <utility>
namespace rtabmap {
Transform RegistrationIcp::computeTransformationImpl(Signature &from,Signature &to,Transform guess,RegistrationInfo &info) const {
 using Fn=Transform(*)(const RegistrationIcp*,Signature&,Signature&,Transform,RegistrationInfo&);
 static Fn original=reinterpret_cast<Fn>(dlsym(RTLD_NEXT,"_ZNK7rtabmap15RegistrationIcp25computeTransformationImplERNS_9SignatureES2_NS_9TransformERNS_16RegistrationInfoE"));
 if(!original)throw std::runtime_error("Cannot resolve pinned original RegistrationIcp method");
 auto h=slam_audit::context();if(!h.stamp.toNSec())h.stamp.fromSec(to.getStamp());
 std::string ids="{\"from_id\":"+std::to_string(from.id())+",\"to_id\":"+std::to_string(to.id())+"}";
 slam_audit::emit(h,"ICP_BEGIN",ids);
 Transform out=original(this,from,to,guess,info);
 slam_audit::emit(h,out.isNull()?"ICP_FAILED":"ICP_SUCCESS",ids);
 return out;
}
}
