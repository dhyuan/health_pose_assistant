"use client";

import { useEffect, useMemo, useState } from "react";
import { format, subDays } from "date-fns";
import { zhCN } from "date-fns/locale";
import {
  LineChart,
  Line,
  ScatterChart,
  Scatter,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

import {
  DailyStat,
  Device,
  SittingSession,
  DeviceStatusSpan,
  getStats,
  getSittingSessions,
  listDevices,
} from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Calendar } from "@/components/ui/calendar";
import { toast } from "sonner";
import { SittingTimeline } from "@/components/sitting-timeline";

const CHART_COLORS = {
  bad_posture_count: "#ef4444",
  prolonged_alert_count: "#f97316",
  sitting_minutes: "#3b82f6",
  away_count: "#22c55e",
};

const CHART_LABELS: Record<string, string> = {
  bad_posture_count: "不良姿势次数",
  prolonged_alert_count: "久坐提醒次数",
  sitting_minutes: "久坐分钟数",
  away_count: "离开次数",
};

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

function StatsPageInner() {
  const searchParams = useSearchParams();
  const [devices, setDevices] = useState<Device[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>("all");

  // 只在组件顶层同步 URL 参数 device_id 到 selectedDeviceId，避免 hydration mismatch
  useEffect(() => {
    const deviceId = searchParams?.get("device_id");
    // 只在首次加载或 selectedDeviceId 仍为 'all' 时同步 URL
    if (selectedDeviceId === "all" && deviceId) {
      setSelectedDeviceId(deviceId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);
  const [stats, setStats] = useState<DailyStat[]>([]);
  const [loading, setLoading] = useState(false);

  const [fromDate, setFromDate] = useState<Date>(subDays(new Date(), 29));
  const [toDate, setToDate] = useState<Date>(new Date());

  // Sitting sessions timeline state
  const [sessionsDate, setSessionsDate] = useState<Date>(new Date());
  const [sessions, setSessions] = useState<SittingSession[]>([]);
  const [sittingAlertMinutes, setSittingAlertMinutes] = useState(20);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [deviceStatusSpans, setDeviceStatusSpans] = useState<
    DeviceStatusSpan[]
  >([]);

  useEffect(() => {
    listDevices()
      .then(setDevices)
      .catch(() => toast.error("加载设备列表失败"));
  }, []);

  useEffect(() => {
    async function fetch() {
      setLoading(true);
      try {
        const params: {
          device_id?: number;
          from?: string;
          to?: string;
          tz?: string;
        } = {
          from: format(fromDate, "yyyy-MM-dd"),
          to: format(toDate, "yyyy-MM-dd"),
          tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
        };
        if (selectedDeviceId !== "all") {
          params.device_id = Number(selectedDeviceId);
        }
        const data = await getStats(params);
        setStats(data);
      } catch {
        toast.error("加载统计数据失败");
      } finally {
        setLoading(false);
      }
    }
    fetch();
  }, [selectedDeviceId, fromDate, toDate]);

  // Fetch sitting sessions for timeline
  useEffect(() => {
    async function fetchSessions() {
      setSessionsLoading(true);
      try {
        const params: { date: string; device_id?: number; tz?: string } = {
          date: format(sessionsDate, "yyyy-MM-dd"),
          tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
        };
        if (selectedDeviceId !== "all") {
          params.device_id = Number(selectedDeviceId);
        }
        const data = await getSittingSessions(params);
        setSessions(data.sessions);
        setSittingAlertMinutes(data.sitting_alert_minutes);
        setDeviceStatusSpans(data.device_status_spans || []);
      } catch {
        toast.error("加载坐立时间线失败");
      } finally {
        setSessionsLoading(false);
      }
    }
    fetchSessions();
  }, [selectedDeviceId, sessionsDate]);

  // Aggregate by date when "all" devices selected
  const chartData = useMemo(() => {
    const map = new Map<
      string,
      {
        date: string;
        bad_posture_count: number;
        prolonged_alert_count: number;
        sitting_minutes: number;
        away_count: number;
      }
    >();
    for (const s of stats) {
      const existing = map.get(s.stat_date);
      if (existing) {
        existing.bad_posture_count += s.bad_posture_count;
        existing.prolonged_alert_count += s.prolonged_alert_count;
        existing.sitting_minutes += s.sitting_minutes;
        existing.away_count += s.away_count;
      } else {
        map.set(s.stat_date, {
          date: s.stat_date,
          bad_posture_count: s.bad_posture_count,
          prolonged_alert_count: s.prolonged_alert_count,
          sitting_minutes: s.sitting_minutes,
          away_count: s.away_count,
        });
      }
    }
    return Array.from(map.values()).sort((a, b) =>
      a.date.localeCompare(b.date),
    );
  }, [stats]);

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">统计数据</h1>

      {/* Filters */}
      <div className="mb-6 flex flex-wrap items-end gap-4">
        <div className="grid gap-1.5">
          <label className="text-sm font-medium">设备</label>
          <Select
            value={selectedDeviceId}
            onValueChange={(v) => setSelectedDeviceId(v ?? "all")}
          >
            <SelectTrigger className="w-50">
              <SelectValue placeholder="全部设备">
                {selectedDeviceId === "all"
                  ? "全部设备"
                  : (() => {
                      const d = devices.find(
                        (d) => String(d.id) === selectedDeviceId,
                      );
                      return d
                        ? `${d.name} (${d.device_code})`
                        : selectedDeviceId;
                    })()}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部设备</SelectItem>
              {devices.map((d) => (
                <SelectItem key={d.id} value={String(d.id)}>
                  {d.name} ({d.device_code})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="grid gap-1.5">
          <label className="text-sm font-medium">开始日期</label>
          <Popover>
            <PopoverTrigger className="inline-flex h-9 w-40 items-center justify-start rounded-md border border-input bg-background px-3 text-sm ring-offset-background hover:bg-accent hover:text-accent-foreground">
              {format(fromDate, "yyyy-MM-dd")}
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0">
              <Calendar
                mode="single"
                locale={zhCN}
                selected={fromDate}
                onSelect={(d) => d && setFromDate(d)}
              />
            </PopoverContent>
          </Popover>
        </div>

        <div className="grid gap-1.5">
          <label className="text-sm font-medium">结束日期</label>
          <Popover>
            <PopoverTrigger className="inline-flex h-9 w-40 items-center justify-start rounded-md border border-input bg-background px-3 text-sm ring-offset-background hover:bg-accent hover:text-accent-foreground">
              {format(toDate, "yyyy-MM-dd")}
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0">
              <Calendar
                mode="single"
                locale={zhCN}
                selected={toDate}
                onSelect={(d) => d && setToDate(d)}
              />
            </PopoverContent>
          </Popover>
        </div>
      </div>

      {/* Sitting Timeline */}
      <Card className="mb-6">
        <CardHeader>
          <div className="flex flex-wrap items-center gap-4">
            <CardTitle className="text-base">坐立时间线</CardTitle>
            <Popover>
              <PopoverTrigger className="inline-flex h-9 w-40 items-center justify-start rounded-md border border-input bg-background px-3 text-sm ring-offset-background hover:bg-accent hover:text-accent-foreground">
                {format(sessionsDate, "yyyy-MM-dd")}
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0">
                <Calendar
                  mode="single"
                  locale={zhCN}
                  selected={sessionsDate}
                  onSelect={(d) => d && setSessionsDate(d)}
                />
              </PopoverContent>
            </Popover>
          </div>
        </CardHeader>
        <CardContent>
          {sessionsLoading ? (
            <p className="text-sm text-muted-foreground">加载中…</p>
          ) : (
            <SittingTimeline
              sessions={sessions}
              sittingAlertMinutes={sittingAlertMinutes}
              deviceStatusSpans={deviceStatusSpans}
              lastSeenAt={(() => {
                if (selectedDeviceId === "all") return null;
                const d = devices.find(
                  (d) => String(d.id) === selectedDeviceId,
                );
                return d?.last_seen_at || null;
              })()}
            />
          )}
        </CardContent>
      </Card>

      {loading ? (
        <p className="text-muted-foreground">加载中…</p>
      ) : chartData.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            所选范围内无数据
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-6 md:grid-cols-2">
          {(Object.keys(CHART_LABELS) as Array<keyof typeof CHART_LABELS>).map(
            (key) => {
              // Dot plot for 不良姿势次数、久坐提醒次数、离开次数
              if (
                key === "bad_posture_count" ||
                key === "prolonged_alert_count" ||
                key === "away_count"
              ) {
                return (
                  <Card key={key}>
                    <CardHeader>
                      <CardTitle className="text-base">
                        {CHART_LABELS[key]}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ResponsiveContainer width="100%" height={250}>
                        <ScatterChart data={chartData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis
                            dataKey="date"
                            tick={{ fontSize: 12 }}
                            tickFormatter={(v: string) => v.slice(5)} // MM-DD
                          />
                          <YAxis tick={{ fontSize: 12 }} />
                          <Tooltip
                            labelFormatter={(label) =>
                              format(new Date(String(label)), "yyyy年M月d日", {
                                locale: zhCN,
                              })
                            }
                          />
                          <Legend />
                          <Scatter
                            name={CHART_LABELS[key]}
                            dataKey={key}
                            fill={
                              CHART_COLORS[key as keyof typeof CHART_COLORS]
                            }
                            shape="circle"
                          />
                        </ScatterChart>
                      </ResponsiveContainer>
                    </CardContent>
                  </Card>
                );
              }
              // Bar chart for 久坐分钟数
              if (key === "sitting_minutes") {
                return (
                  <Card key={key}>
                    <CardHeader>
                      <CardTitle className="text-base">
                        {CHART_LABELS[key]}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ResponsiveContainer width="100%" height={250}>
                        <BarChart data={chartData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis
                            dataKey="date"
                            tick={{ fontSize: 12 }}
                            tickFormatter={(v: string) => v.slice(5)} // MM-DD
                          />
                          <YAxis tick={{ fontSize: 12 }} />
                          <Tooltip
                            labelFormatter={(label) =>
                              format(new Date(String(label)), "yyyy年M月d日", {
                                locale: zhCN,
                              })
                            }
                          />
                          <Legend />
                          <Bar
                            dataKey={key}
                            name={CHART_LABELS[key]}
                            fill={
                              CHART_COLORS[key as keyof typeof CHART_COLORS]
                            }
                          />
                        </BarChart>
                      </ResponsiveContainer>
                    </CardContent>
                  </Card>
                );
              }
              // Default: Line chart
              return (
                <Card key={key}>
                  <CardHeader>
                    <CardTitle className="text-base">
                      {CHART_LABELS[key]}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={250}>
                      <LineChart data={chartData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis
                          dataKey="date"
                          tick={{ fontSize: 12 }}
                          tickFormatter={(v: string) => v.slice(5)} // MM-DD
                        />
                        <YAxis tick={{ fontSize: 12 }} />
                        <Tooltip
                          labelFormatter={(label) =>
                            format(new Date(String(label)), "yyyy年M月d日", {
                              locale: zhCN,
                            })
                          }
                        />
                        <Legend />
                        <Line
                          type="monotone"
                          dataKey={key}
                          name={CHART_LABELS[key]}
                          stroke={
                            CHART_COLORS[key as keyof typeof CHART_COLORS]
                          }
                          strokeWidth={2}
                          dot={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              );
            },
          )}
        </div>
      )}
    </div>
  );
}

export default function StatsPage() {
  return (
    <Suspense fallback={<div>加载中…</div>}>
      <StatsPageInner />
    </Suspense>
  );
}
