# 时间戳和静止对齐修正

Q3独立Recorder，不继承旧阻塞扫描回调，也不恢复Doc79 latest-TF兜底。
scan callback立即写原index/seq/stamp/stamp_ns/scan_received_wall_time及原始ranges，加入待处理队列。
后台工作线程只读取这个独立观测缓存，不读写mapper graph；不是旧禁止的异步graph dump。

原/tf被保存并构成只读SE(2)观测缓存：动态历史20sim秒、每边最多4096条；
待处理scan最多200条，等待2wall秒。容量溢出、超时和shutdown均保留明确missing记录，不删除身份。
每个动态edge必须精确stamp或在0.15s以内的已知区间插值，禁止外推和最新TF替代。
只有明确来自/tf_static的固定变换可作为时间不变的边。所有后续评价仍请求原扫描时间。

原始/tf到达与scan评价文件分开保存，能区分收到时不可用、稍后在线解决和严格事后可重建。
记录tf_resolved_wall_time、tf_interpolation_span、tf_status及逐边时间支持。控制估计可读最新公共
有效时间的TF，但该值不能填入历史扫描评价。

初始化成功后先按odom确认持续静止，再取固定2sim秒静止窗口；封存窗口输入文件。
一个不导入ROS的独立离线子进程仅从该文件计算初始SE(2)规范，至少15对、GT括夹≤0.15s、
最大静止残差≤原0.03m。变换文件创建后才发送任务目标；不使用后续GT拟合。
GT仅用于已关闭记录的离线评价，既不生成目标、速度或航向，也不做动态停止/恢复决策。
资格不满足对齐条件时允许阻止任务启动；这属于测量资格，不是GT导航策略。
