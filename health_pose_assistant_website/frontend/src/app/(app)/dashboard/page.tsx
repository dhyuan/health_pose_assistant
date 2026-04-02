"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { DashboardData, getDashboard } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { useI18n } from "@/i18n/provider";

const REFRESH_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes

export default function DashboardPage() {
  const { t } = useI18n();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchDashboard = useCallback(async () => {
    try {
      const d = await getDashboard();
      setData(d);
    } catch {
      toast.error(t("dashboard.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchDashboard();
    intervalRef.current = setInterval(fetchDashboard, REFRESH_INTERVAL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchDashboard]);

  if (loading) {
    return <p className="text-muted-foreground">{t("common.loading")}</p>;
  }

  if (!data) {
    return <p className="text-muted-foreground">{t("dashboard.noData")}</p>;
  }

  const statCards = [
    {
      title: t("dashboard.badPosture"),
      value: data.today.bad_posture_count,
      unit: t("dashboard.times"),
      color: "text-red-600",
    },
    {
      title: t("dashboard.prolongedAlert"),
      value: data.today.prolonged_alert_count,
      unit: t("dashboard.times"),
      color: "text-orange-600",
    },
    {
      title: t("dashboard.sittingDuration"),
      value: data.today.sitting_minutes,
      unit: t("dashboard.minutes"),
      color: "text-blue-600",
    },
    {
      title: t("dashboard.awayCount"),
      value: data.today.away_count,
      unit: t("dashboard.times"),
      color: "text-green-600",
    },
  ];

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">{t("dashboard.title")}</h1>
        <Button variant="outline" size="sm" onClick={fetchDashboard}>
          {t("common.refresh")}
        </Button>
      </div>

      {/* Device overview */}
      <div className="mb-6 grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t("dashboard.totalDevices")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{data.total_devices}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t("dashboard.onlineDevices")}
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
      <h2 className="mb-4 text-lg font-semibold">
        {t("dashboard.todayStats")}
      </h2>
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
