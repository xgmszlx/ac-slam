# 2DLIW-SLAM 最小导出补丁 —— 逐帧激光信息矩阵

> 目标：每帧扫描匹配导出 `Hp = Σ JpᵀJp`（位置，3×3）和 `Hq = Σ JqᵀJq`（旋转，3×3），
> 以及该帧的估计位姿 `p`、`q` 和线数 `n_lines`。
> **不改任何数学、不改优化、不改状态**，只在 `clac_frame_J()` 里累加并写文件。

---

## 为什么改这里

`src/factor/solver.cpp` 的 `clac_frame_J()` 已经用 `auto_diff` 显式算出了
`laser_factor` 对当前帧 `p`、`q` 的 Jacobian（第 466 行附近）：

```cpp
auto_diff::compute_res_and_jacobi<laser_factor, 2, 3, 3, 3, 3>(functor, parametrs, res, jacobians);
...
J.template block<2, alpha_len>(r_index, all_status_block_indexs[index].p) = jacobians[2];
J.template block<2, gamma_len>(r_index, all_status_block_indexs[index].q) = jacobians[3];
```

- `jacobians[2]` = ∂res/∂p（2×3）
- `jacobians[3]` = ∂res/∂q（2×3）
- 残差里已经含 `sqrt_info = 1/line_to_line_sigma` 和长度权重 `sum`，
  **所以 `JpᵀJp` 直接就是信息矩阵（单位：1/m²）**

---

## 补丁（三处插入，都用注释标好，方便回退）

### ① 在 `clac_frame_J` 开头、`int r_index = ...` 那行之后插入

```cpp
        int r_index = all_status_block_indexs[index].laser_res_index;

        // ==== [DUMP-LASER-INFO 1/3] 累加器 ====
        Eigen::Matrix<double, 3, 3> _Hp = Eigen::Matrix<double, 3, 3>::Zero();
        Eigen::Matrix<double, 3, 3> _Hq = Eigen::Matrix<double, 3, 3>::Zero();
        int _n_lines = 0;
        // ==== end ====
```

### ② 在激光循环里、`assert(BUG::maxtirx_is_valid(res));` 之后插入

```cpp
                    assert(BUG::maxtirx_is_valid(res));

                    // ==== [DUMP-LASER-INFO 2/3] 累加 ====
                    {
                        Eigen::MatrixXd Jp = jacobians[2];
                        Eigen::MatrixXd Jq = jacobians[3];
                        _Hp += Jp.transpose() * Jp;
                        _Hq += Jq.transpose() * Jq;
                        _n_lines++;
                    }
                    // ==== end ====
```

### ③ 在激光 `if` 块结束、`assert(r_index == all_status_block_indexs[index].imu_res_index);` 之前插入

```cpp
        // ==== [DUMP-LASER-INFO 3/3] 写文件 ====
        {
            const char *_dump = getenv("LVIO_DUMP_LASER");
            if (_dump && _n_lines > 0)
            {
                FILE *_f = fopen(_dump, "a");
                if (_f)
                {
                    const auto &_p = frame_infos[index]->p;
                    const auto &_q = frame_infos[index]->q;
                    fprintf(_f, "%d,%d", index, _n_lines);
                    for (int _a = 0; _a < 3; _a++) fprintf(_f, ",%.12g", _p[_a]);
                    for (int _a = 0; _a < 3; _a++) fprintf(_f, ",%.12g", _q[_a]);
                    for (int _a = 0; _a < 3; _a++)
                        for (int _b = 0; _b < 3; _b++) fprintf(_f, ",%.12g", _Hp(_a, _b));
                    for (int _a = 0; _a < 3; _a++)
                        for (int _b = 0; _b < 3; _b++) fprintf(_f, ",%.12g", _Hq(_a, _b));
                    fprintf(_f, "\n");
                    fclose(_f);
                }
            }
        }
        // ==== end ====
```

> 需要 `#include <cstdio>` 和 `#include <cstdlib>`（`solver.cpp` 里通常已间接包含；
> 若不编译，在该文件顶部加这两行）。

---

## 字段含义（导出后的列序）

| 列 | 含义 |
|---|---|
| 1 | `index`（窗口内下标，仅参考） |
| 2 | `n_lines`（本帧匹配到的线数） |
| 3–5 | `p[0..2]` 当前帧估计位置（**用来和 GT 对齐**） |
| 6–8 | `q[0..2]` 当前帧旋转向量 |
| 9–17 | `Hp` 3×3，行优先 |
| 18–26 | `Hq` 3×3，行优先 |

**行优先 = `Hp(0,0), Hp(0,1), Hp(0,2), Hp(1,0), ...`**

---

## 编译与运行

```bash
cd ~/2dliw && catkin_make 2>&1 | tail -5

# 清空旧导出文件
rm -f /tmp/laser_info.csv

# 跑一段数据（换成你自己的 bag / OpenLORIS 序列）
LVIO_DUMP_LASER=/tmp/laser_info.csv \
  roslaunch lvio_2d lvio_2d_corridor.launch        # 或你的 launch

# 看有没有内容
wc -l /tmp/laser_info.csv && head -2 /tmp/laser_info.csv

# 拷进我的工作区
cp /tmp/laser_info.csv /home/wcqw/snap/dsh-desktop-community/2/dsh-work/
cp <你的GT轨迹TUM文件> /home/wcqw/snap/dsh-desktop-community/2/dsh-work/
```

---

## 我拿到之后会做什么

1. **看 `Hp` 的秩**：走廊里如果 x 方向信息≈0，`Hp` 会是近似 rank-1 —— 这就是"几何退化"的**实测量化**（不是靠特征值阈值猜）；
2. **把 `Hp`/`Hq` 投影到 SE(2) 切空间**，得到逐帧预测 σ_x / σ_y / σ_θ；
3. **与 GT 的相邻帧相对位姿误差做 NEES**，走我已经写好的 `cov_consistency.py`；
4. **分场景对比**（走廊 vs 房间）；若你愿意再跑一段"先建图、再回到改过家具的房间"，就能验证仿真里那条**"2 cm 地图误差 → 7 倍过度自信"**的结论。

---

## 一个已经能说的发现（不用等数据）

```cpp
const double eps = 1e-8;
Eigen::VectorXd S = (saes2.eigenvalues().array() > eps).select(...);
```

`solver.cpp:392` 用的是**绝对**特征值阈值 `1e-8` 来做退化截断。
但 Hessian 的数值依赖单位（米/弧度）、点数、线长权重 —— **这个 1e-8 不是尺度不变的**。
换成厘米或用不同点数的数据，截断行为就会变。

这正好对上子代理 B 的 **A1（6 个独立团队说阈值不跨环境迁移，无人给出可标定判据）**。
**这不是我推测的，是你系统里的一行代码。**
