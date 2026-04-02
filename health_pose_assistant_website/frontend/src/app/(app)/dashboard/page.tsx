"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { DashboardData, getDashboard } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

const REFRESH_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchDashboard = useCallback(async () => {
    try {
      const d = await getDashboard();
      setData(d);
    } catch {
      toast.error("加载仪表盘失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboard();
    intervalRef.current = setInterval(fetchDashboard, REFRESH_INTERVAL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchDashboard]);

  if (loading) {
    return <p className="text-muted-foreground">加载中…</p>;
  }

  if (!data) {
    return <p className="text-muted-foreground">无法加载数据</p>;
  }

  const statCards = [
    {
      title: "不良姿势",
      value: data.today.bad_posture_count,
      unit: "次",
      color: "text-red-600",
    },
    {
      title: "久坐提醒",
      value: data.today.prolonged_alert_count,
      unit: "次",
      color: "text-orange-600",
    },
    {
      title: "久坐时长",
      value: data.today.sitting_minutes,
      unit: "分钟",
      color: "text-blue-600",
    },
    {
      title: "离开次数",
      value: data.today.away_count,
      unit: "次",
      color: "text-green-600",
    },
  ];

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">仪表盘</h1>
        <Button variant="outline" size="sm" onClick={fetchDashboard}>
          刷新
        </Button>
      </div>

      {/* Device overview */}
      <div className="mb-6 grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              设备总数
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{data.total_devices}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              在线设备
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold text-green-600">
              {data.online_devices}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Today stats */}
      <h2 className="mb-4 text-lg font-semibold">今日统计</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {statCards.map((card) => (
          <Card key={card.title}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {card.title}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className={`text-3xl font-bold ${card.color}`}>
                {card.value}
                <span className="ml-1 text-sm font-normal text-muted-foreground">
                  {card.unit}
                </span>
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
