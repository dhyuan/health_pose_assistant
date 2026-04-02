"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { SittingSession } from "@/lib/api";
import { useMemo } from "react";

import type { DeviceStatusSpan } from "@/lib/api";

interface SittingTimelineProps {
  sessions: SittingSession[];
  sittingAlertMinutes: number;
  deviceStatusSpans?: DeviceStatusSpan[];
  lastSeenAt?: string | null;
}

const START_HOUR = 0;
const END_HOUR = 24;
const TOTAL_HOURS = END_HOUR - START_HOUR; // 24 hours
const MIN_ZOOM = 1;
const MAX_ZOOM = 10;

function toHourFraction(iso: string): number {
  const d = new Date(iso);
  return d.getHours() + d.getMinutes() / 60 + d.getSeconds() / 3600;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Choose a nice tick interval (in hours) based on visible range. */
function tickInterval(visibleHours: number): number {
  if (visibleHours <= 2) return 0.25;
  if (visibleHours <= 5) return 0.5;
  if (visibleHours <= 10) return 1;
  return 2;
}

export function SittingTimeline(props: SittingTimelineProps) {
  const {
    sessions,
    sittingAlertMinutes,
    deviceStatusSpans = [],
    lastSeenAt,
  } = props;
  // 计算累计坐立时间（小时）
  const totalHours = useMemo(() => {
    return (
      sessions.reduce((sum, s) => sum + (s.duration_seconds || 0), 0) / 3600
    );
  }, [sessions]);
  const totalHoursText = useMemo(() => {
    return totalHours.toFixed(1).replace(/\.0$/, "");
  }, [totalHours]);
  const CHART_WIDTH = 800;
  const MARGIN_LEFT = 44;
  const MARGIN_RIGHT = 16;
  const BAR_Y = 24;
  const BAR_HEIGHT = 10;
  const CHART_HEIGHT = 56;
  const INNER_WIDTH = CHART_WIDTH - MARGIN_LEFT - MARGIN_RIGHT;

  const alertSeconds = sittingAlertMinutes * 60;

  // --- zoom / pan state ---
  const [zoom, setZoom] = useState(1); // 1 = full view
  const [offset, setOffset] = useState(0); // 0..1-1/zoom, left edge as fraction of total
  const dragRef = useRef<{ startX: number; startOffset: number } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  // visible window in hours
  const clampOffset = useCallback(
    (o: number, z: number) => Math.max(0, Math.min(o, 1 - 1 / z)),
    [],
  );
  const visibleHours = TOTAL_HOURS / zoom;
  const viewStartHour = START_HOUR + offset * TOTAL_HOURS;
  /** Convert an hour fraction to x pixel. */
  const hourToX = useCallback(
    (h: number) =>
      ((h - viewStartHour) / visibleHours) * INNER_WIDTH + MARGIN_LEFT,
    [viewStartHour, visibleHours, INNER_WIDTH, MARGIN_LEFT],
  );

  // 设备在线/离线区间渲染
  const statusLine = useMemo(() => {
    if (!deviceStatusSpans.length) return [];
    const now = new Date();
    return deviceStatusSpans.map((span) => {
      const x1 = hourToX(toHourFraction(span.start));
      const x2 = hourToX(
        span.end
          ? toHourFraction(span.end)
          : now.getHours() + now.getMinutes() / 60 + now.getSeconds() / 3600,
      );
      return {
        x1,
        x2,
        color: span.status === "online" ? "#22c55e" : "#eab308",
      };
    });
  }, [deviceStatusSpans, hourToX]);

  // --- bars ---
  const bars = useMemo(() => {
    return sessions.map((s) => {
      const startH = toHourFraction(s.start_time);
      const endH = toHourFraction(s.end_time);
      const x = hourToX(startH);
      const x2 = hourToX(endH);
      const width = Math.max(x2 - x, 4);
      const isProlonged = s.duration_seconds >= alertSeconds;
      const durationMin = Math.round(s.duration_seconds / 60);
      const label = `${formatTime(s.start_time)} – ${formatTime(s.end_time)}（${durationMin}分钟${isProlonged ? "，久坐" : ""}）`;
      return { x, width, isProlonged, label };
    });
  }, [sessions, alertSeconds, hourToX]);

  // --- tick marks ---
  const timeLabels = useMemo(() => {
    const step = tickInterval(visibleHours);
    const labels: { x: number; text: string }[] = [];
    const first = Math.ceil(viewStartHour / step) * step;
    for (let h = first; h <= viewStartHour + visibleHours; h += step) {
      if (h < START_HOUR || h > END_HOUR) continue;
      const x = hourToX(h);
      if (x < MARGIN_LEFT - 1 || x > CHART_WIDTH - MARGIN_RIGHT + 1) continue;
      const mins = Math.round((h % 1) * 60);
      const text =
        mins === 0
          ? `${Math.floor(h)}:00`
          : `${Math.floor(h)}:${String(mins).padStart(2, "0")}`;
      labels.push({ x, text });
    }
    return labels;
  }, [
    viewStartHour,
    visibleHours,
    hourToX,
    MARGIN_LEFT,
    CHART_WIDTH,
    MARGIN_RIGHT,
  ]);

  // --- mouse handlers ---
  // const onWheel = ...
  // const onPointerDown = ...
  // const onPointerMove = ...
  // const onPointerUp = ...
  // 这些都不再绑定到SVG

  // --- slider (ruler) state ---
  // sliderStart/End: 0~1, fraction of total range
  const [slider, setSlider] = useState<{ start: number; end: number }>({
    start: 0,
    end: 1,
  });
  // Sync slider <-> zoom/offset
  // When zoom/offset changes, update slider
  useEffect(() => {
    setSlider({
      start: offset,
      end: offset + 1 / zoom,
    });
  }, [zoom, offset]);
  // When slider changes, update zoom/offset
  const onSliderChange = useCallback((start: number, end: number) => {
    const newZoom = 1 / (end - start);
    setZoom(Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, newZoom)));
    setOffset(Math.max(0, Math.min(start, 1 - 1 / newZoom)));
  }, []);

  // --- slider drag logic ---
  const sliderRef = useRef<SVGLineElement>(null);
  type SliderDrag = {
    type: "left" | "right" | "center";
    startX: number;
    start: number;
    end: number;
  };
  const sliderDrag = useRef<SliderDrag | null>(null);
  const onSliderPointerDown = (
    e: React.PointerEvent,
    type: "left" | "right" | "center",
  ) => {
    e.preventDefault();
    (e.target as Element).setPointerCapture?.(e.pointerId);
    sliderDrag.current = {
      type,
      startX: e.clientX,
      start: slider.start,
      end: slider.end,
    };
  };
  const onSliderPointerMove = (e: React.PointerEvent) => {
    if (!sliderDrag.current || !sliderRef.current) return;
    const rect = sliderRef.current.getBoundingClientRect();
    const dx = (e.clientX - sliderDrag.current.startX) / rect.width;
    let { start, end } = sliderDrag.current;
    if (sliderDrag.current.type === "left") {
      start = Math.max(0, Math.min(start + dx, end - 0.05));
    } else if (sliderDrag.current.type === "right") {
      end = Math.min(1, Math.max(end + dx, start + 0.05));
    } else if (sliderDrag.current.type === "center") {
      const width = end - start;
      const newStart = Math.max(0, Math.min(start + dx, 1 - width));
      start = newStart;
      end = newStart + width;
    }
    setSlider({ start, end });
    onSliderChange(start, end);
  };
  const onSliderPointerUp = () => {
    sliderDrag.current = null;
  };

  // --- slider visual ---
  const SLIDER_HEIGHT = 24;
  const handleW = 12;
  const trackH = 6;
  const sliderLeft = MARGIN_LEFT + slider.start * INNER_WIDTH;
  const sliderRight = MARGIN_LEFT + slider.end * INNER_WIDTH;
  const sliderWidth = sliderRight - sliderLeft;

  if (sessions.length === 0) {
    return (
      <div className="flex h-20 items-center justify-center text-sm text-muted-foreground">
        当天无坐立记录
      </div>
    );
  }

  return (
    <div className="w-full overflow-x-auto">
      <div className="mb-2 text-sm text-gray-700 font-medium">
        累计坐立时间：{totalHoursText} 小时
      </div>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT + SLIDER_HEIGHT}`}
        className="w-full min-w-150 select-none"
        aria-label="坐立时间线"
        onPointerMove={onSliderPointerMove}
        onPointerUp={onSliderPointerUp}
        onPointerLeave={onSliderPointerUp}
      >
        {/* Clip content to inner area */}
        <defs>
          <clipPath id="timeline-clip">
            <rect
              x={MARGIN_LEFT}
              y={0}
              width={INNER_WIDTH}
              height={CHART_HEIGHT}
            />
          </clipPath>
        </defs>

        <g clipPath="url(#timeline-clip)">
          {/* 在线/离线状态线段，画在坐立条下方，横轴上方 */}
          {statusLine.map((seg, i) => (
            <line
              key={i}
              x1={seg.x1}
              x2={seg.x2}
              y1={BAR_Y + BAR_HEIGHT + 4}
              y2={BAR_Y + BAR_HEIGHT + 4}
              stroke={seg.color}
              strokeWidth={2}
            />
          ))}
          {/* Grid lines + 时间刻度防裁剪 */}
          {timeLabels.map(({ x, text }) => {
            let adjX = x;
            if (text.startsWith("0:") && x === MARGIN_LEFT) adjX = x + 10;
            if (
              (text.startsWith("24:") || text === "24:00") &&
              x === CHART_WIDTH - MARGIN_RIGHT
            )
              adjX = x - 15;
            return (
              <g key={text}>
                <line
                  x1={x}
                  y1={BAR_Y - 4}
                  x2={x}
                  y2={BAR_Y + BAR_HEIGHT + 4}
                  stroke="#e5e7eb"
                  strokeWidth={1}
                />
                <text
                  x={adjX}
                  y={CHART_HEIGHT - 4}
                  textAnchor="middle"
                  fontSize={11}
                  fill="#6b7280"
                >
                  {text}
                </text>
              </g>
            );
          })}

          {/* Background track */}
          <rect
            x={hourToX(START_HOUR)}
            y={BAR_Y}
            width={hourToX(END_HOUR) - hourToX(START_HOUR)}
            height={BAR_HEIGHT}
            rx={4}
            fill="#f3f4f6"
          />

          {/* Session bars */}
          {bars.map((bar, i) => (
            <rect
              key={i}
              x={bar.x}
              y={BAR_Y}
              width={bar.width}
              height={BAR_HEIGHT}
              rx={2}
              fill={bar.isProlonged ? "#ef4444" : "#3b82f6"}
              opacity={0.85}
            >
              <title>{bar.label}</title>
            </rect>
          ))}
        </g>

        {/* Legend (outside clip) */}
        <rect
          x={MARGIN_LEFT}
          y={3}
          width={12}
          height={12}
          rx={2}
          fill="#3b82f6"
        />
        <text x={MARGIN_LEFT + 16} y={13} fontSize={11} fill="#374151">
          正常坐立
        </text>
        <rect
          x={MARGIN_LEFT + 76}
          y={3}
          width={12}
          height={12}
          rx={2}
          fill="#ef4444"
        />
        <text x={MARGIN_LEFT + 92} y={13} fontSize={11} fill="#374151">
          久坐（≥{sittingAlertMinutes}分钟）
        </text>

        {/* 缩放提示已移除，仅用滑块控制 */}
        {/* 滑块直接画在SVG横轴下方，避免嵌套SVG */}
        {/* 底部刻度线：由粗矩形改为细线 */}
        <line
          ref={sliderRef}
          x1={MARGIN_LEFT}
          y1={CHART_HEIGHT + SLIDER_HEIGHT / 2}
          x2={MARGIN_LEFT + INNER_WIDTH}
          y2={CHART_HEIGHT + SLIDER_HEIGHT / 2}
          stroke="#e5e7eb"
          strokeWidth={2}
        />
        {/* 滑块区间 */}
        <rect
          x={sliderLeft}
          y={CHART_HEIGHT + SLIDER_HEIGHT / 2 - trackH / 2}
          width={sliderWidth}
          height={trackH}
          fill="rgba(156,163,175,0.18)"
          stroke="#9ca3af"
          strokeWidth={2}
          rx={3}
          style={{ cursor: "grab" }}
          onPointerDown={(e) => onSliderPointerDown(e, "center")}
        />
        {/* 左滑块 */}
        <rect
          x={sliderLeft - handleW / 2}
          y={CHART_HEIGHT + SLIDER_HEIGHT / 2 - handleW / 2}
          width={handleW}
          height={handleW}
          fill="#9ca3af"
          rx={6}
          style={{ cursor: "ew-resize" }}
          onPointerDown={(e) => onSliderPointerDown(e, "left")}
        />
        {/* 右滑块 */}
        <rect
          x={sliderRight - handleW / 2}
          y={CHART_HEIGHT + SLIDER_HEIGHT / 2 - handleW / 2}
          width={handleW}
          height={handleW}
          fill="#9ca3af"
          rx={6}
          style={{ cursor: "ew-resize" }}
          onPointerDown={(e) => onSliderPointerDown(e, "right")}
        />
        {/* 刻度数字 */}
        {/* 滑块轴下方不再显示时间刻度数字 */}
        {/* 主时间轴刻度数字已移除，仅保留下方滑块和主轴 */}
      </svg>
    </div>
  );
}
