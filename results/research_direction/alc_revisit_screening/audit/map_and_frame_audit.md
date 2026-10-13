# 地图、时间与参考系审计

本轮只读原 `/home/wcqw/ac-slam` 数据；所有新增产物在独立 worktree。

## 完整探索轨迹

`phase4c/aggregate/run_table.csv` 的 45 条记录不是 45 条“新 Phase4C 独立重复”：
map3 的 15 条指向 Phase4B 原目录，不能再将 Phase4B 算一次。map3、map8 各 15 条
完整运行；Mexico 15 条保留为失败运行，不混入完成探索的效果比较。

`pubPathGT.cpp:52–71` 将 world-base GT 减去记录的起始平移，再加旋转后的
0.2 m 激光外参。作者 SLAM TUM 保存的是最终修正的 laser 轨迹。
本轮直接用 raw `ground_truth_samples.csv` 验证 GT 转换，45 条的最大残差
约 7.1e-5 m（文本舍入量级），没有再减一次 0.2 m。

时间配对：最近 GT，容差 0.05 s；不估计新的刚体对齐，不缩放。
重算 APE 与旧数值最大差 <5e-7 m。原始 native 接受日志的 state_id/unique_id
时间与作者 TUM 对应行时间还逐项核对到 1e-6 s。
这些检查排除了主要参考点/时间身份错误，但**转换残差不是全部评估噪声上界**：
native 接受时间不等于原始激光采集时间，仍须保留回调/TF 延迟限制。

每次回访的旧同步替代物只是发布缓存。当前离线检查观察到 before 缓存的最后
接受状态距动作开始 2.5–483 s（map3），map8 为 6.4–35 s。
缓存差分只能作结构诊断，不能给新增边可靠的动作创建时间。
`formal_preloop_headroom.csv` 只使用真正 before 缓存中的节点坐标；native
接受日志只提供这些既有节点的时间身份，没有从最终轨迹借用节点位置。

## Doc79 历史目标

同步图节点是 map-laser。使用 `T_laser_base=(-0.2,0,0)` 后，按照
state_id→unique_id→native 接受时间→GT 插值（0.06 s）恢复五个目标。
只以动作前 history+return 的 TF-base/GT 点对拟合一次 SE(2)，四阶段共用。
140 条目标·阶段位置误差从原图、原扫描、GT 和接受日志独立重算；与 Doc80
修正表一致到 1e-9 m 以内。这是局部对齐历史目标误差，不与全程零对齐 APE
混称同一个指标。

## 在线地图缺口与离线最终地图

七个 Doc79 可信 attempt 有 final_map，但未记录 G_before_return/G_arrival
在线 occupancy。扫描存在并不代表已重建一个具有机器人足迹/不确定性膨胀的
可导航栅格。历史关键帧连线也不等于无碰撞的实际连续走廊。

因此新增候选里的移动路线全部为几何假设，安全可达性不认证。Stage 世界图
没有进入候选模块，final_map 也没有充当动作前地图。

完整运行 45 张最终地图用原 `evaluate_mapping.py`、保存的 identity registration
和 0.2 m boundary tolerance 重算；图像/YAML SHA 对旧记录核验，F1 差为零。
Stage bitmap 仅作离线评价。边界 F1、占据 IoU 都受未覆盖区域和 GT 厚墙/估计
薄墙影响，不能将低 IoU 直接解释为闭环导致的重影，也没有同步地图可算动作级
地图改善。
