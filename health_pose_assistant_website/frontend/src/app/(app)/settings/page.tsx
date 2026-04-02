"use client";

import { useEffect, useState, useCallback } from "react";
import { getConfig, updateConfig, type ConfigProfile } from "@/lib/api";
import { DEFAULT_CONFIG, HIDDEN_KEYS } from "@/lib/default-config";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

type Config = Record<string, unknown>;

// ── Field metadata for rendering controls ──

interface FieldMeta {
  label: string;
  description: string;
  tab: "common" | "advanced";
}

const FIELD_META: Record<string, FieldMeta> = {
  // Common — Feature toggles
  enable_posture: {
    label: "坐姿/驼背检测",
    description: "启用坐姿和驼背检测功能",
    tab: "common",
  },
  enable_exercise: {
    label: "运动计数",
    description: "启用运动计数（需要全身正面视角，桌前请关闭）",
    tab: "common",
  },
  enable_sitting: {
    label: "久坐提醒",
    description: "启用久坐提醒功能",
    tab: "common",
  },
  // Common — Video
  video_rotation_angle: {
    label: "视频旋转角度",
    description: "摄像头画面旋转角度",
    tab: "common",
  },
  // Common — Posture
  posture_torso_threshold: {
    label: "躯干角度阈值（度）",
    description: "躯干角度 < 此值 → 驼背警告",
    tab: "common",
  },
  posture_head_forward_threshold: {
    label: "头部前倾阈值",
    description: "鼻子相对肩膀的 x 位移 > 此值 → 头部前倾",
    tab: "common",
  },
  posture_alert_seconds: {
    label: "坐姿不良持续秒数",
    description: "不良坐姿持续多少秒后触发提醒",
    tab: "common",
  },
  // Common — Sitting
  sitting_alert_minutes: {
    label: "久坐提醒分钟数",
    description: "连续坐满多少分钟后提醒",
    tab: "common",
  },
  sitting_stand_seconds: {
    label: "站立确认秒数",
    description: "站立持续多少秒才算真正站起（重置计时器）",
    tab: "common",
  },
  sitting_repeat_alert_minutes: {
    label: "重复提醒间隔（分钟）",
    description: "没站起时，每隔多少分钟重复提醒",
    tab: "common",
  },
  // Common — Voice
  alert_voice: {
    label: "提醒语音",
    description: "文字转语音引擎的 voice 名称",
    tab: "common",
  },
  alert_message: {
    label: "久坐提醒消息",
    description: "久坐提醒时播放的语音内容",
    tab: "common",
  },
  // Common — Messages
  leave_messages: {
    label: "离开画面消息",
    description: "用户离开摄像头画面时随机播放的消息列表",
    tab: "common",
  },
  welcome_back_messages: {
    label: "回到画面消息",
    description: "用户回到摄像头画面时随机播放的消息列表",
    tab: "common",
  },
  // Advanced — Exercise
  squat_down_angle: {
    label: "深蹲下蹲角度",
    description: "髋-膝-踝角度 < 此值 → 蹲下",
    tab: "advanced",
  },
  squat_up_angle: {
    label: "深蹲站立角度",
    description: "髋-膝-踝角度 > 此值 → 站立",
    tab: "advanced",
  },
  pushup_down_angle: {
    label: "俯卧撑下压角度",
    description: "肩-肘-腕角度 < 此值 → 下压",
    tab: "advanced",
  },
  pushup_up_angle: {
    label: "俯卧撑撑起角度",
    description: "肩-肘-腕角度 > 此值 → 撑起",
    tab: "advanced",
  },
  // Advanced — Sitting thresholds
  sitting_torso_span_threshold: {
    label: "肩髋距离阈值",
    description: "肩髋距离 < 此值 → 判定为坐姿",
    tab: "advanced",
  },
  sitting_hip_y_threshold: {
    label: "髋部 Y 坐标阈值",
    description: "髋 Y > 此值 → 判定为坐姿",
    tab: "advanced",
  },
  sitting_knee_angle_threshold: {
    label: "膝角阈值",
    description: "膝角 < 此值 → 判定为坐姿（腿可见时）",
    tab: "advanced",
  },
  sitting_torso_lean_threshold: {
    label: "躯干倾角阈值",
    description: "躯干倾角 < 此值 → 明显前倾",
    tab: "advanced",
  },
  sitting_knee_straight_threshold: {
    label: "膝角伸直阈值",
    description: "膝角 > 此值 → 腿伸直（弯腰特征）",
    tab: "advanced",
  },
  sitting_frame_smoothing: {
    label: "帧平滑数",
    description: "连续 N 帧判断为同一状态才切换（避免抖动）",
    tab: "advanced",
  },
};

// ── Component ──

export default function SettingsPage() {
  const [profile, setProfile] = useState<ConfigProfile | null>(null);
  const [config, setConfig] = useState<Config | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [noConfig, setNoConfig] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const p = await getConfig();
      setProfile(p);
      // Merge with defaults so newly-added keys are visible in the UI
      setConfig({ ...(DEFAULT_CONFIG as Config), ...p.config_json });
      setNoConfig(false);
    } catch (e: unknown) {
      if (
        e &&
        typeof e === "object" &&
        "status" in e &&
        (e as { status: number }).status === 404
      ) {
        setNoConfig(true);
      } else {
        setError(String(e));
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  function updateField(key: string, value: unknown) {
    setConfig((prev) => (prev ? { ...prev, [key]: value } : prev));
    setDirty(true);
    setSuccessMsg("");
  }

  async function handleSave() {
    if (!config) return;
    setSaving(true);
    setError("");
    setSuccessMsg("");
    try {
      const cleaned = { ...config };
      for (const k of HIDDEN_KEYS) delete cleaned[k];
      const p = await updateConfig(cleaned);
      setProfile(p);
      setConfig({ ...(DEFAULT_CONFIG as Config), ...p.config_json });
      setDirty(false);
      setSuccessMsg(`已保存 (version ${p.version})`);
    } catch (e: unknown) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  async function handleCreateDefault() {
    setSaving(true);
    setError("");
    try {
      const p = await updateConfig(DEFAULT_CONFIG as Record<string, unknown>);
      setProfile(p);
      setConfig({ ...p.config_json });
      setNoConfig(false);
      setDirty(false);
      setSuccessMsg("已创建默认配置");
    } catch (e: unknown) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  // ── Loading state ──

  if (loading) {
    return (
      <div>
        <h1 className="text-2xl font-bold mb-4">Settings</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  // ── No config state ──

  if (noConfig) {
    return (
      <div>
        <h1 className="text-2xl font-bold mb-4">Settings</h1>
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle>暂无配置</CardTitle>
            <CardDescription>
              还没有创建配置档案。点击下方按钮用 pose-video 默认值初始化。
            </CardDescription>
          </CardHeader>
          <CardContent>
            {error && <p className="text-sm text-destructive mb-3">{error}</p>}
            <Button onClick={handleCreateDefault} disabled={saving}>
              {saving ? "创建中..." : "使用默认配置初始化"}
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!config) return null;

  // ── Render helpers ──

  function renderField(key: string) {
    const meta = FIELD_META[key];
    if (!meta) return null;
    const value = config![key];

    // Boolean → Switch
    if (typeof value === "boolean") {
      return (
        <div key={key} className="flex items-center justify-between py-3">
          <div className="space-y-0.5">
            <Label className="text-sm font-medium">{meta.label}</Label>
            <p className="text-xs text-muted-foreground">{meta.description}</p>
          </div>
          <Switch
            checked={value}
            onCheckedChange={(v) => updateField(key, v)}
          />
        </div>
      );
    }

    // video_rotation_angle → Select
    if (key === "video_rotation_angle") {
      return (
        <div key={key} className="space-y-2 py-3">
          <Label className="text-sm font-medium">{meta.label}</Label>
          <p className="text-xs text-muted-foreground">{meta.description}</p>
          <Select
            value={String(value)}
            onValueChange={(v) => updateField(key, Number(v))}
          >
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="0">0°</SelectItem>
              <SelectItem value="90">90°</SelectItem>
              <SelectItem value="180">180°</SelectItem>
              <SelectItem value="270">270°</SelectItem>
            </SelectContent>
          </Select>
        </div>
      );
    }

    // String arrays → individual text fields with add/remove
    if (Array.isArray(value)) {
      return (
        <div key={key} className="space-y-2 py-3">
          <Label className="text-sm font-medium">{meta.label}</Label>
          <p className="text-xs text-muted-foreground">{meta.description}</p>
          <div className="space-y-2">
            {(value as string[]).map((msg, i) => (
              <div key={i} className="flex items-center gap-2">
                <Input
                  value={msg}
                  onChange={(e) => {
                    const arr = [...(value as string[])];
                    arr[i] = e.target.value;
                    updateField(key, arr);
                  }}
                  className="flex-1"
                />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    const arr = (value as string[]).filter((_, j) => j !== i);
                    updateField(key, arr);
                  }}
                  className="text-destructive hover:text-destructive shrink-0"
                >
                  删除
                </Button>
              </div>
            ))}
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => updateField(key, [...(value as string[]), ""])}
          >
            + 添加消息
          </Button>
        </div>
      );
    }

    // String → Input
    if (typeof value === "string") {
      return (
        <div key={key} className="space-y-2 py-3">
          <Label className="text-sm font-medium">{meta.label}</Label>
          <p className="text-xs text-muted-foreground">{meta.description}</p>
          <Input
            value={value}
            onChange={(e) => updateField(key, e.target.value)}
            className="max-w-md"
          />
        </div>
      );
    }

    // Number → Slider + Input
    if (typeof value === "number") {
      const { min, max, step } = getNumberRange(key, value);
      return (
        <div key={key} className="space-y-2 py-3">
          <div className="flex items-center justify-between">
            <div>
              <Label className="text-sm font-medium">{meta.label}</Label>
              <p className="text-xs text-muted-foreground">
                {meta.description}
              </p>
            </div>
            <Input
              type="number"
              value={value}
              onChange={(e) => updateField(key, Number(e.target.value))}
              step={step}
              className="w-24 text-right"
            />
          </div>
          <Slider
            value={[value]}
            onValueChange={(v) => updateField(key, Array.isArray(v) ? v[0] : v)}
            min={min}
            max={max}
            step={step}
            className="max-w-md"
          />
        </div>
      );
    }

    return null;
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold">Settings</h1>
          {profile && (
            <p className="text-sm text-muted-foreground mt-1">
              Version {profile.version} · 最后更新{" "}
              {new Date(profile.updated_at).toLocaleString("zh-CN")}
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          {successMsg && (
            <Badge variant="outline" className="text-green-600">
              {successMsg}
            </Badge>
          )}
          {error && <Badge variant="destructive">{error}</Badge>}
          <Button onClick={handleSave} disabled={saving || !dirty}>
            {saving ? "保存中..." : "保存配置"}
          </Button>
        </div>
      </div>

      <Tabs defaultValue="common">
        <TabsList>
          <TabsTrigger value="common">常用设置</TabsTrigger>
          <TabsTrigger value="advanced">高级阈值</TabsTrigger>
        </TabsList>

        <TabsContent value="common" className="mt-4">
          <Card>
            <CardContent className="pt-6">
              <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                功能开关
              </h3>
              {["enable_posture", "enable_exercise", "enable_sitting"].map(
                renderField,
              )}
              <Separator className="my-4" />

              <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                视频
              </h3>
              {renderField("video_rotation_angle")}
              <Separator className="my-4" />

              <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                坐姿检测
              </h3>
              {[
                "posture_torso_threshold",
                "posture_head_forward_threshold",
                "posture_alert_seconds",
              ].map(renderField)}
              <Separator className="my-4" />

              <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                久坐提醒
              </h3>
              {[
                "sitting_alert_minutes",
                "sitting_stand_seconds",
                "sitting_repeat_alert_minutes",
              ].map(renderField)}
              <Separator className="my-4" />

              <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                语音提醒
              </h3>
              {["alert_voice", "alert_message"].map(renderField)}
              <Separator className="my-4" />

              <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                消息列表
              </h3>
              {["leave_messages", "welcome_back_messages"].map(renderField)}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="advanced" className="mt-4">
          <Card>
            <CardContent className="pt-6">
              <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                运动计数阈值
              </h3>
              {[
                "squat_down_angle",
                "squat_up_angle",
                "pushup_down_angle",
                "pushup_up_angle",
              ].map(renderField)}
              <Separator className="my-4" />

              <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                坐/站判断阈值
              </h3>
              {[
                "sitting_torso_span_threshold",
                "sitting_hip_y_threshold",
                "sitting_knee_angle_threshold",
                "sitting_torso_lean_threshold",
                "sitting_knee_straight_threshold",
                "sitting_frame_smoothing",
              ].map(renderField)}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ── Number range helpers ──

function getNumberRange(
  key: string,
  currentValue: number,
): { min: number; max: number; step: number } {
  if (
    key === "posture_torso_threshold" ||
    key === "sitting_torso_lean_threshold"
  ) {
    return { min: 100, max: 180, step: 1 };
  }
  if (
    key === "sitting_knee_angle_threshold" ||
    key === "sitting_knee_straight_threshold"
  ) {
    return { min: 90, max: 180, step: 1 };
  }
  if (key.includes("down_angle")) return { min: 60, max: 150, step: 1 };
  if (key.includes("up_angle")) return { min: 120, max: 180, step: 1 };
  if (key === "posture_head_forward_threshold")
    return { min: 0, max: 0.2, step: 0.01 };
  if (key === "sitting_torso_span_threshold")
    return { min: 0.1, max: 0.5, step: 0.01 };
  if (key === "sitting_hip_y_threshold")
    return { min: 0.2, max: 0.8, step: 0.01 };
  if (key === "posture_alert_seconds") return { min: 1, max: 60, step: 1 };
  if (key === "sitting_alert_minutes") return { min: 1, max: 120, step: 1 };
  if (key === "sitting_stand_seconds") return { min: 10, max: 300, step: 5 };
  if (key === "sitting_repeat_alert_minutes")
    return { min: 0.5, max: 30, step: 0.5 };
  if (key === "sitting_frame_smoothing") return { min: 1, max: 10, step: 1 };
  return { min: 0, max: Math.max(currentValue * 3, 100), step: 1 };
}
