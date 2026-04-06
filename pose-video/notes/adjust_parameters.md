我先看当前姿态识别和筛选逻辑，重点找关节点置信度、人体存在性判定、以及站立/坐姿状态切换前的门槛，这样才能明确为什么这类桌椅轮廓会被当成人体。

Searched for regex `visibility|presence|confidence|min_detection|min_tracking|landmark|threshold|standing|sitting|bending|person` (`**/pose-video/**`), 120 results

Read memory

Read memory [](file:///Users/dhyuan/Library/Application%20Support/Code/User/workspaceStorage/52f9f9218cba69eebd0e3d38ed6a7b8e/GitHub.copilot-chat/memory-tool/memories/repo/pose-visibility-tuning.md)

Read memory [](file:///Users/dhyuan/Library/Application%20Support/Code/User/workspaceStorage/52f9f9218cba69eebd0e3d38ed6a7b8e/GitHub.copilot-chat/memory-tool/memories/repo/sitting-classification-tuning.md)

我接着看具体判定代码，目标是把“为什么会把桌椅边缘当人”对应到现有门槛上，再给你一组可直接调的参数和更稳妥的新增参数。

Read [](file:///Users/dhyuan/github/health-video-assistant/pose-video/pose_detect_mediapipe.py#1-1), lines 1 to 240

Read [](file:///Users/dhyuan/github/health-video-assistant/pose-video/pose_detect_mediapipe.py#240-240), lines 240 to 520

Read [](file:///Users/dhyuan/github/health-video-assistant/pose-video/config_client.py)

还需要看主循环里“只要拿到 landmarks 就算有人在场”这一步，因为误检通常不是出在坐/站分类，而是更前面的“人体存在”门槛太宽。

Searched for regex `pose_landmarks|results.pose_landmarks|core_visibility|DETECT_FAILED|AWAY|core_filtered|detect_rate|diagnostics` (`**/pose-video/pose_detect_mediapipe.py`), 77 results

Read [](file:///Users/dhyuan/github/health-video-assistant/pose-video/pose_detect_mediapipe.py#520-520), lines 520 to 920

我已经确认状态机会把“只剩肩和髋”也当成可检测人体，最后再看一眼主循环的预过滤，确定现在到底缺了哪些前置拦截。

Read [](file:///Users/dhyuan/github/health-video-assistant/pose-video/pose_detect_mediapipe.py#1190-1190), lines 1190 to 1278

Read [](file:///Users/dhyuan/github/health-video-assistant/pose-video/CONFIG_GUIDE.md)

我已经把根因缩小到两个点了：前置过滤只看“肩+髋平均可见度”，状态机又只要求“任一肩 + 任一髋”可见，所以这种桌子/显示器形成的人形轮廓会被放行。最后我补一下精确位置，方便你直接改参数或代码。

Read [](file:///Users/dhyuan/github/health-video-assistant/pose-video/pose_detect_mediapipe.py#64-64), lines 64 to 76

Read [](file:///Users/dhyuan/github/health-video-assistant/pose-video/pose_detect_mediapipe.py#534-534), lines 534 to 592

Read [](file:///Users/dhyuan/github/health-video-assistant/pose-video/pose_detect_mediapipe.py#1238-1238), lines 1238 to 1256

这个误检模式已经比较清楚了：不是后面的坐/站规则先出错，而是前面的“这是不是一个人”放得太宽。我先把这个结论记到仓库记忆里，后面如果你让我直接改代码，我会按这条做。

Created memory file [](file:///Users/dhyuan/Library/Application%20Support/Code/User/workspaceStorage/52f9f9218cba69eebd0e3d38ed6a7b8e/GitHub.copilot-chat/memory-tool/memories/repo/false-positive-person-gating.md)

这种情况本质上是“人体关键点模型的幻觉误检”。MediaPipe Pose 不是先做严格的人体框检测再做骨架回归，它会直接在整张图里找“像人体拓扑结构的边缘和拐点”。你这张图里，显示器边缘、桌面、桌腿、线缆、椅背这些高对比结构，刚好能拼出一个“头-肩-髋-膝”的形状，所以它给出了一组自洽的关键点。

在你当前代码里，这种误检又比较容易被放行，原因有两个：

1. 前置过滤只看四个核心点的平均可见度，门槛不高。
位置在 pose_detect_mediapipe.py 和 pose_detect_mediapipe.py。
现在只要左右肩、左右髋这 4 个点的平均 `visibility` 高于 `pose_core_visibility_threshold=0.5`，这一帧就继续往下走。

2. 状态机的人体存在判定太宽，只要求“任一肩膀 + 任一髋部”可见。
位置在 pose_detect_mediapipe.py。
这意味着哪怕模型只在桌子上胡乱放出一侧肩和一侧髋，也会被当成“有人”。

所以这不是“站立/坐姿阈值调错”导致的，根因在更前面的“是否接受这组 landmarks 作为人体”。

**先调现有参数**
如果你想先不改代码，直接靠参数压掉这类误检，优先调这 3 个：

1. `pose_min_detection_confidence`
位置在 pose_detect_mediapipe.py
建议先从 `0.5 -> 0.65`，必要时到 `0.7`。
作用：减少“凭背景纹理重新检出一个人”。

2. `pose_min_tracking_confidence`
位置在 pose_detect_mediapipe.py
建议先从 `0.5 -> 0.7`，必要时到 `0.8`。
作用：减少“人走了以后，模型还沿着桌椅继续跟踪出一个假人”。

3. `pose_core_visibility_threshold`
位置在 pose_detect_mediapipe.py
建议先从 `0.5 -> 0.65`，必要时到 `0.75`。
作用：当前这是最后一道“假骨架过滤”。提高它，最直接。

如果你要一个保守但常见有效的组合，我建议先试：

- `pose_min_detection_confidence = 0.65`
- `pose_min_tracking_confidence = 0.75`
- `pose_core_visibility_threshold = 0.7`

**再加哪些参数最有效**
如果目标是“尽量禁止这种情况”，只调上面三个参数还不够稳，建议新增下面几类参数：

1. `pose_min_core_visible_count`
建议默认 `3` 或 `4`
含义：左右肩+左右髋中，至少有多少个点的 `visibility` 必须超过阈值。
为什么有效：现在用的是“平均值”，很容易被 2 个很高的假点拉上去。改成“至少 3 个核心点真实可见”会稳很多。

2. `pose_require_same_side_torso`
建议默认 `True`
含义：必须满足“左肩+左髋”或“右肩+右髋”至少一侧同时成立。
为什么有效：现在代码允许“左肩 + 右髋”这种跨身体拼接，假骨架很容易过。

3. `pose_head_visibility_threshold` 或 `pose_require_head_landmark`
建议默认可选，别强制开
含义：要求鼻子、耳朵、眼睛里至少有一个头部点可见。
为什么有效：你这类桌面/显示器误检通常最不稳定的就是头部。
限制：如果你经常是背对/侧对镜头，这个条件不能设太严格。

4. `pose_person_confirm_frames`
建议默认 `3~5`
含义：连续 N 帧都满足“人体存在”才允许从 `AWAY` 进入 `STANDING/SITTING`。
为什么有效：很多假骨架只会闪几帧，连续确认能压掉大部分瞬时误检。

5. `pose_min_torso_span` 和 `pose_max_torso_span`
含义：限制肩髋纵向跨度必须落在合理人体范围。
为什么有效：家具拼出来的“肩-髋”距离经常过小或过大。
这比现在只在坐/站投票里用 `span` 更前置，也更合适。

6. `pose_min_bbox_area`
含义：可见关键点的包围盒面积必须大于某个比例。
为什么有效：如果假人只出现在屏幕右上角一小块区域，直接过滤。

**我最推荐的代码级修正**
如果你要我改代码，我建议不要只继续堆置信度阈值，而是直接把“人体存在性”改严：

1. 把 pose_detect_mediapipe.py 的 `_can_detect()` 改成：
要求同侧肩髋成立，并且核心点至少 3 个过阈值。

2. 把 pose_detect_mediapipe.py 的平均可见度过滤改成：
“平均可见度 + 最少核心点数”双重过滤，而不是只看平均值。

3. 增加“连续 N 帧确认有人”参数：
避免一两帧假骨架直接把状态从 `AWAY` 拉回来。

这三项会比单纯调 `sitting_*` 那些坐姿参数有效得多，因为你现在的问题发生在“根本没人，但系统已经相信画面里有个人”这一步。

**结论**
你这类误检不是异常，属于姿态模型在复杂背景上的典型假阳性。现有代码里最该动的不是 `sitting_torso_span_threshold`、`sitting_hip_y_threshold` 这些坐站参数，而是“人体存在判定”这层。

如果你要，我下一步可以直接帮你做两种之一：

1. 只给现有配置新增 3 到 5 个参数，不改整体结构，做最小侵入式修复。
2. 直接把人体存在判定逻辑重构成“核心点数量 + 同侧肩髋 + 连续帧确认”的 stricter gate。
