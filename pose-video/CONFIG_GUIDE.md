# pose_detect_mediapipe.py — 配置参数说明

所有参数集中在文件顶部的 `CONFIG` 字典中，按需修改后重启程序即生效。

---

## 一、功能开关

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enable_posture` | bool | `True` | 开启坐姿/驼背检测并在画面上显示提示 |
| `enable_exercise` | bool | `False` | 开启运动计数（深蹲/俯卧撑）。需要全身正面入镜，桌前坐用时请关闭，否则会产生大量误计数 |
| `enable_sitting` | bool | `True` | 开启久坐提醒计时 |

---

## 二、网络

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `host` | str | `""` | 接收视频流的监听地址。空字符串 = 监听所有网卡（`0.0.0.0`） |
| `port` | int | `9999` | 接收视频流的 TCP 端口，须与 Pi 端发送端口一致 |

---

## 三、视频旋转

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `video_rotation_angle` | int | `180` | 收到帧后先旋转再推理，防止摄像头安装方向导致检测率极低。可选值：`0` / `90` / `180` / `270` |

---

## 四、MediaPipe 检测参数

这三个参数决定 **"画面里有没有人"** 的判断质量，是误检的主要来源。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `pose_min_detection_confidence` | float | `0.5` | **初次检测置信度阈值**。画面中没有跟踪目标时，模型重新检测人体所需的最低置信度（0~1）。值越高越不容易检测到人，误报越少，但真实用户进入画面时反应稍慢 |
| `pose_min_tracking_confidence` | float | `0.5` | **跟踪置信度阈值**。一旦检测到人，后续帧使用跟踪模式（比重新检测快）。值越低，人离开后模型继续"预测"关节点的帧数越多，越容易出现无人画面仍被判为有人的情况。**建议不低于 0.5** |
| `pose_core_visibility_threshold` | float | `0.5` | **核心关节可见度过滤阈值**。MediaPipe 输出姿态后，程序计算左右肩 + 左右髋四个核心关节的平均 `visibility` 分数。若均值低于此阈值，则直接丢弃本帧结果，当作无人处理。这是防止背景物体（椅子靠背、深色家具）被误识为人体的最后一道防线。**建议不低于 0.5** |
| `pose_presence_landmark_threshold` | float | `0.35` | **人体存在单点阈值**。核心点数量、头部点数量、同侧肩髋检查都使用这个单点可见度门槛。值越高，要求每个关键点越可靠 |
| `pose_presence_in_frame_margin` | float | `0.02` | **关键点画面边界容差**。关键点必须落在画面内或边界附近才计入人体门槛。用于拦截坐标已经漂到画面外的假骨架 |
| `pose_min_core_visible_count` | int | `3` | **最少核心点数量**。左右肩 + 左右髋中，至少有多少个点可见才接受这一帧为人体。用于避免 1 到 2 个高置信假点把整帧抬过去 |
| `pose_min_head_visible_count` | int | `1` | **最少头部点数量**。鼻子、眼睛、耳朵中至少多少个点可见才接受这一帧为人体。对显示器边缘、桌角等假人体很有效 |
| `pose_require_same_side_torso` | bool | `True` | **要求同侧肩髋**。必须同时看到左肩+左髋或右肩+右髋，避免左肩和右髋这种跨侧拼接出来的假躯干 |
| `pose_min_torso_span` | float | `0.16` | **最小躯干跨度**。同侧肩髋的最小纵向距离。用于拦截缩成一小团、但 visibility 偏高的假人体关键点 |
| `pose_presence_confirm_frames` | int | `3` | **人体确认帧数**。从 `AWAY` / `DETECT_FAILED` 恢复前，连续多少帧通过人体存在门槛才确认有人，抑制闪烁式误检 |

### YOLO11n 人体框预检测（bbox-first）

当 `pose_bbox_first_enabled=True` 时，程序会先使用 **YOLO11n** 检测 `person` 框，再只在该 bbox crop 内运行 MediaPipe Pose，最后把 landmarks 映射回全图坐标，继续复用现有的人体 presence gate、骨骼 overlay、坐姿/久坐/驼背逻辑。

如果本机尚未缓存权重，`ultralytics` 会在第一次启用 bbox-first 时自动下载 `yolo11n.pt`。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `pose_bbox_first_enabled` | bool | `False` | 是否启用 `YOLO11n -> person bbox -> crop 内 Pose` 的前置检测方案。关闭时保持原有全图 MediaPipe Pose 流程 |
| `pose_bbox_confidence_threshold` | float | `0.35` | YOLO11n 接受 `person` bbox 的最低置信度。值越高越保守，值越低越容易引入背景误检 |
| `pose_bbox_padding_ratio` | float | `0.12` | bbox 四周的扩边比例。用于给 MediaPipe Pose 留出手臂、头顶等边缘区域，避免裁得过紧 |
| `pose_bbox_min_area_ratio` | float | `0.02` | bbox 至少要占整帧面积的多少比例才会被接受。适合过滤很远、很小或碎片化的 `person` 误检 |
| `pose_bbox_confirm_frames` | int | `2` | 连续多少帧检测到相近 bbox 后才把它视为稳定人体框，减少抖动和闪烁 |
| `pose_bbox_lost_frames` | int | `5` | 稳定 bbox 丢失后，最多还能沿用上一次 bbox 多少帧。用于平滑短时 detector 抖动 |
| `pose_bbox_fallback_to_full_frame` | bool | `True` | 如果 YOLO11n 没找到稳定 bbox，或者 crop 内的 MediaPipe Pose 没出结果，是否回退到旧的全图 Pose 路径 |
| `pose_bbox_overlay_debug_enabled` | bool | `False` | 是否把 bbox 调试文字直接叠加到视频画面右侧中部。适合远程看流调参；关闭后仍保留 bbox 矩形 |

> 建议从 `pose_bbox_first_enabled=True`、`pose_bbox_fallback_to_full_frame=True` 开始验证；这样即使 YOLO11n 暂时失手，也不会直接让整条链路退化成“无人”。

> `pose_bbox_confirm_frames` 和 `pose_bbox_lost_frames` 是 bbox-first 自身的稳定化层；即使开启 bbox-first，现有 `pose_presence_*` 人体存在门槛仍会作为第二层过滤继续生效。

### diagnostics 下可见的 bbox 信息

当 `pose_bbox_overlay_debug_enabled=True` 时，画面右侧中部会额外显示：

- 当前 bbox 状态：`candidate / confirmed / holding`
- 当前 Pose 来源：`bbox / full_frame_fallback / full_frame`
- bbox 置信度、面积占比、confirm/lost 计数
- 当前 fallback 原因（例如 `no_person`、`below_min_area`、`crop_pose_failed`）

开启 `--diagnostics` 后，终端日志还会增加 bbox 相关统计：raw bbox 命中数、confirmed 命中数、holding 次数、full-frame fallback 次数。

### 运行方式

首次安装新增依赖：

```bash
pip install -r requirements.txt
```

启用 bbox-first 的典型运行方式不变，配置建议优先通过后端 settings 页面下发；本地直跑时也可以直接修改 `CONFIG` 默认值：

```bash
python pose_detect_mediapipe.py \
 --api-url http://localhost:8000 \
 --stream-port 8080 \
 --device-token <your-device-token> \
 --config-interval 10 \
 --diagnostics --diag-interval 5
```

> **调参建议**：像你截图里这种贴着地面的小团关键点，优先看 `pose_presence_in_frame_margin` 和 `pose_min_torso_span`。前者处理关键点跑出画面的问题，后者处理明明在画面里但整体尺寸明显不对的问题。

---

## 五、坐姿检测

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `posture_torso_threshold` | int | `145` | 躯干角阈值（度）。通过耳→肩→髋三点计算夹角；角度 **小于** 此值时判定为驼背/前倾 |
| `posture_head_forward_threshold` | float | `0.05` | 头部前倾阈值。鼻子 X 坐标与两肩中点 X 坐标的差值；差值 **大于** 此值时判定头部前倾（该值为归一化坐标，0.05 约等于画面宽度的 5%）|
| `posture_alert_seconds` | int | `10` | 坐姿不良持续多少秒后才触发语音提醒（避免短暂低头即报警） |

> 坐姿提醒触发后，每 5 秒重复提醒一次（硬编码，如需修改见源码 `posture_repeat_seconds`）。

---

## 六、运动计数（`enable_exercise=False` 时无效）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `squat_down_angle` | int | `100` | 髋-膝-踝角度 **小于** 此值时判定为蹲下到位 |
| `squat_up_angle` | int | `160` | 髋-膝-踝角度 **大于** 此值时判定为完全站立 |
| `pushup_down_angle` | int | `90` | 肩-肘-腕角度 **小于** 此值时判定为俯卧撑下压到位 |
| `pushup_up_angle` | int | `160` | 肩-肘-腕角度 **大于** 此值时判定为俯卧撑撑起到顶 |

角度迟滞（`down_angle` < `up_angle`）是防止计数在临界值附近反复跳变的标准做法。

---

## 七、久坐提醒

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `sitting_alert_minutes` | float | `20` | 连续坐满多少分钟触发久坐提醒。调试时可改为 `0.2`（约12秒）快速验证 |
| `sitting_stand_seconds` | int | `60` | 站立持续多少秒才算"真正站起"。站立不足此时长则不会重置久坐计时器，防止用户起身倒水又马上坐回导致计时归零 |
| `sitting_repeat_alert_minutes` | float | `1.0` | 久坐提醒触发后，如果用户仍未站起，每隔多少分钟再次提醒 |

> 久坐计时的两个隐式阈值（硬编码）：
>
> - 离开画面 **≥ 10 秒** → 视为主动休息，当前坐时段结束
> - 离开画面 **≥ 5 分钟** → 同时清零已显示的当前分钟数

---

## 八、语音提醒

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `alert_voice` | str | `"Meijia"` | macOS `say` 命令使用的中文语音名称。可用 `say -v ?` 查看所有可用语音 |
| `alert_message` | str | `"你已经坐了很久了，站起来活动一下吧！"` | 久坐触发时播报的文字 |

---

## 九、随机提示语

| 参数 | 类型 | 说明 |
|------|------|------|
| `leave_messages` | list[str] | 检测到人离开画面时，从列表中随机选一条播报 |
| `welcome_back_messages` | list[str] | 检测到人回到画面时，从列表中随机选一条播报 |

---

## 十、坐/站判断阈值（视摄像头位置而定）

这组参数是**多特征投票**机制的核心，需根据摄像头实际安装角度进行校准。可在诊断模式（`--diagnostics`）下观察 `span` / `hip_y` / `knee` 的实时输出来确定合适的取值。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `sitting_torso_span_threshold` | float | `0.27` | **肩髋竖向距离阈值**。左肩 Y 与左髋 Y 的差值（归一化坐标）。差值 **小于** 此值 → 投坐姿票。坐着时躯干被压缩，肩髋距离更小；站立时距离更大 |
| `sitting_hip_y_threshold` | float | `0.44` | **髋部 Y 坐标阈值**。归一化坐标（0=画面顶部，1=底部）。髋部 Y **大于** 此值 → 投坐姿票。坐着时髋部在画面中位置更低（Y 值更大） |
| `sitting_knee_angle_threshold` | int | `130` | **膝角投票阈值**（腿部可见时）。髋-膝-踝角度 **小于** 此值 → 投坐姿票。坐着时膝关节弯曲更明显 |
| `sitting_torso_lean_threshold` | int | `155` | 躯干倾角 **小于** 此值视为明显前倾（弯腰），用于辅助排除弯腰站立被误判为坐姿的情况（当前版本作强制站立条件的内部参考，阈值为 140°） |
| `sitting_knee_straight_threshold` | int | `150` | 弯腰站立特征判断——膝角 **大于** 此值且躯干明显前倾 → 判定为弯腰站立而非坐下 |
| `sitting_knee_strong_threshold` | int | `110` | **强制坐姿判断**。膝角 **小于** 此值且躯干角 ≥ 145° → 直接判坐姿，跳过投票。解决侧视桌前场景中 span/hip_y 受机位影响偏向站立的问题 |
| `sitting_frame_smoothing` | int | `3` | **帧平滑**。连续 N 帧判断为同一状态才触发状态切换，防止坐/站结果逐帧抖动 |

### 校准方法

在自己的摄像头位置下，以诊断模式运行程序，分别坐下和站立，观察终端输出的 `span=` / `hip_y=` 数值，然后将阈值设为坐/站两种状态数值的中间值。

```
# 示例：
# 坐着：span≈0.215, hip_y≈0.537
# 站立：span≈0.287, hip_y≈0.458
# → sitting_torso_span_threshold ≈ 0.25
# → sitting_hip_y_threshold ≈ 0.50
```
