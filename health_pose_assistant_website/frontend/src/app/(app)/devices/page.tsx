"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type TouchEvent as ReactTouchEvent,
} from "react";
import {
  Device,
  listDevices,
  createDevice,
  updateDevice,
  deleteDevice,
  regenerateDeviceToken,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { toast } from "sonner";
import { useI18n } from "@/i18n/provider";

const REFRESH_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes

function isOnline(lastSeenAt: string | null): boolean {
  if (!lastSeenAt) return false;
  return Date.now() - new Date(lastSeenAt).getTime() < 60_000;
}

export default function DevicesPage() {
  const { t, languageTag } = useI18n();
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);

  // Register dialog
  const [showRegister, setShowRegister] = useState(false);
  const [regCode, setRegCode] = useState("");
  const [regName, setRegName] = useState("");
  const [regLoading, setRegLoading] = useState(false);

  // Token display dialog
  const [tokenToShow, setTokenToShow] = useState<string | null>(null);

  // Rename dialog
  const [renameDevice, setRenameDevice] = useState<Device | null>(null);
  const [renameName, setRenameName] = useState("");

  // Delete dialog
  const [deleteTarget, setDeleteTarget] = useState<Device | null>(null);

  // Regen token confirm
  const [regenTarget, setRegenTarget] = useState<Device | null>(null);

  // Video stream dialog
  const [videoDevice, setVideoDevice] = useState<Device | null>(null);
  const [streamKey] = useState(0);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchDevices = useCallback(async () => {
    try {
      const data = await listDevices();
      setDevices(data);
    } catch {
      toast.error(t("devices.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchDevices();
    intervalRef.current = setInterval(fetchDevices, REFRESH_INTERVAL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchDevices]);

  async function handleRegister() {
    setRegLoading(true);
    try {
      const data = await createDevice(regCode.trim(), regName.trim());
      setDevices((prev) => [...prev, data.device]);
      setShowRegister(false);
      setRegCode("");
      setRegName("");
      setTokenToShow(data.plain_token);
      toast.success(t("devices.registerSuccess"));
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t("devices.registerFailed");
      toast.error(msg);
    } finally {
      setRegLoading(false);
    }
  }

  async function handleRename() {
    if (!renameDevice) return;
    try {
      const updated = await updateDevice(renameDevice.id, renameName.trim());
      setDevices((prev) =>
        prev.map((d) => (d.id === updated.id ? updated : d)),
      );
      setRenameDevice(null);
      toast.success(t("devices.renameSuccess"));
    } catch {
      toast.error(t("devices.updateFailed"));
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    try {
      await deleteDevice(deleteTarget.id);
      setDevices((prev) => prev.filter((d) => d.id !== deleteTarget.id));
      setDeleteTarget(null);
      toast.success(t("devices.deleteSuccess"));
    } catch {
      toast.error(t("devices.deleteFailed"));
    }
  }

  async function handleRegenToken() {
    if (!regenTarget) return;
    try {
      const data = await regenerateDeviceToken(regenTarget.id);
      setDevices((prev) =>
        prev.map((d) => (d.id === data.device.id ? data.device : d)),
      );
      setRegenTarget(null);
      setTokenToShow(data.plain_token);
      toast.success(t("devices.tokenRegenSuccess"));
    } catch {
      toast.error(t("devices.tokenRegenFailed"));
    }
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">{t("devices.title")}</h1>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchDevices}>
            {t("common.refresh")}
          </Button>
          <Button size="sm" onClick={() => setShowRegister(true)}>
            {t("devices.register")}
          </Button>
        </div>
      </div>

      {loading ? (
        <p className="text-muted-foreground">{t("common.loading")}</p>
      ) : devices.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            {t("devices.empty")}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              {t("devices.total", { count: devices.length })}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("devices.code")}</TableHead>
                  <TableHead>{t("devices.name")}</TableHead>
                  <TableHead>{t("devices.status")}</TableHead>
                  <TableHead>{t("devices.lastSeen")}</TableHead>
                  <TableHead className="text-right">
                    {t("devices.actions")}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {devices.map((device) => (
                  <TableRow key={device.id}>
                    <TableCell className="font-mono text-sm">
                      {device.device_code}
                    </TableCell>
                    <TableCell>{device.name}</TableCell>
                    <TableCell>
                      {isOnline(device.last_seen_at) ? (
                        <Badge className="bg-green-600">
                          {t("devices.online")}
                        </Badge>
                      ) : (
                        <Badge variant="secondary">
                          {t("devices.offline")}
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {device.last_seen_at
                        ? new Date(device.last_seen_at).toLocaleString(
                            languageTag,
                          )
                        : t("devices.neverSeen")}
                    </TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger className="inline-flex h-8 items-center justify-center rounded-md px-3 text-sm font-medium ring-offset-background transition-colors hover:bg-accent hover:text-accent-foreground">
                          ⋯
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          {isOnline(device.last_seen_at) &&
                            device.stream_url && (
                              <DropdownMenuItem
                                onClick={() => setVideoDevice(device)}
                              >
                                {t("devices.viewVideo")}
                              </DropdownMenuItem>
                            )}
                          <DropdownMenuItem
                            onClick={() => {
                              window.location.href = `/stats?device_id=${device.id}`;
                            }}
                          >
                            {t("devices.viewStats")}
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onClick={() => {
                              setRenameDevice(device);
                              setRenameName(device.name);
                            }}
                          >
                            {t("devices.rename")}
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onClick={() => setRegenTarget(device)}
                          >
                            {t("devices.regenToken")}
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            className="text-red-600"
                            onClick={() => setDeleteTarget(device)}
                          >
                            {t("devices.delete")}
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Register Dialog */}
      <Dialog open={showRegister} onOpenChange={setShowRegister}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("devices.registerDialogTitle")}</DialogTitle>
            <DialogDescription>
              {t("devices.registerDialogDescription")}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="device-code">{t("devices.deviceCode")}</Label>
              <Input
                id="device-code"
                placeholder={t("devices.exampleCode")}
                value={regCode}
                onChange={(e) => setRegCode(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="device-name">{t("devices.deviceName")}</Label>
              <Input
                id="device-name"
                placeholder={t("devices.exampleName")}
                value={regName}
                onChange={(e) => setRegName(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={handleRegister}
              disabled={regLoading || !regCode.trim() || !regName.trim()}
            >
              {regLoading ? t("devices.registering") : t("devices.register")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Token Display Dialog */}
      <Dialog
        open={!!tokenToShow}
        onOpenChange={(open) => {
          if (!open) setTokenToShow(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("devices.tokenTitle")}</DialogTitle>
            <DialogDescription>
              {t("devices.tokenDescription")}
            </DialogDescription>
          </DialogHeader>
          <div className="rounded-md bg-muted p-3">
            <code className="break-all text-sm">{tokenToShow}</code>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                if (tokenToShow) {
                  navigator.clipboard.writeText(tokenToShow);
                  toast.success(t("devices.copied"));
                }
              }}
            >
              {t("devices.copyToken")}
            </Button>
            <Button onClick={() => setTokenToShow(null)}>
              {t("common.close")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Rename Dialog */}
      <Dialog
        open={!!renameDevice}
        onOpenChange={(open) => {
          if (!open) setRenameDevice(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("devices.rename")}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-2 py-4">
            <Label htmlFor="rename-input">{t("devices.newName")}</Label>
            <Input
              id="rename-input"
              value={renameName}
              onChange={(e) => setRenameName(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button onClick={handleRename} disabled={!renameName.trim()}>
              {t("devices.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirm */}
      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t("devices.deleteConfirmTitle")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t("devices.deleteConfirmDescription", {
                name: deleteTarget?.name ?? "",
                code: deleteTarget?.device_code ?? "",
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-red-600 hover:bg-red-700"
              onClick={handleDelete}
            >
              {t("common.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Regenerate Token Confirm */}
      <AlertDialog
        open={!!regenTarget}
        onOpenChange={(open) => {
          if (!open) setRegenTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t("devices.regenConfirmTitle")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t("devices.regenConfirmDescription", {
                name: regenTarget?.name ?? "",
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={handleRegenToken}>
              {t("devices.regenConfirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Video Stream — Draggable & Resizable Floating Window */}
      {videoDevice && (
        <VideoWindow
          device={videoDevice}
          streamKey={streamKey}
          onClose={() => setVideoDevice(null)}
          title={t("devices.liveVideo")}
          altTemplate={t("devices.videoAlt", { name: videoDevice.name })}
        />
      )}
    </div>
  );
}

/* ── Draggable / Resizable Video Window ────────────────────── */

function VideoWindow({
  device,
  streamKey,
  onClose,
  title,
  altTemplate,
}: {
  device: Device;
  streamKey: number;
  onClose: () => void;
  title: string;
  altTemplate: string;
}) {
  const DEFAULT_W = 640;
  const DEFAULT_H = 520;
  const MIN_W = 320;
  const MIN_H = 280;
  const MOBILE_MIN_W = 240;
  const MOBILE_BREAKPOINT = 768;

  const isMobileViewport = () => window.innerWidth <= MOBILE_BREAKPOINT;
  const centerMobilePos = (width: number, height: number) => ({
    x: Math.max(0, Math.floor((window.innerWidth - width) / 2)),
    y: Math.max(0, Math.floor((window.innerHeight - height) / 2)),
  });
  const getMobileSize = () => ({
    w: window.innerWidth,
    h: Math.min(
      window.innerHeight,
      Math.max(280, Math.floor(window.innerWidth * 0.75) + 40),
    ),
  });

  const [pos, setPos] = useState(() => ({
    ...(isMobileViewport()
      ? centerMobilePos(window.innerWidth, getMobileSize().h)
      : {
          x: Math.max(0, Math.floor((window.innerWidth - DEFAULT_W) / 2)),
          y: Math.max(0, Math.floor((window.innerHeight - DEFAULT_H) / 2)),
        }),
  }));
  const [size, setSize] = useState(() =>
    isMobileViewport() ? getMobileSize() : { w: DEFAULT_W, h: DEFAULT_H },
  );
  const [isMobile, setIsMobile] = useState(() => isMobileViewport());

  const dragRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    origX: number;
    origY: number;
  } | null>(null);
  const resizeRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    origW: number;
    origH: number;
  } | null>(null);
  const pinchRef = useRef<{
    startDistance: number;
    startW: number;
    startH: number;
  } | null>(null);

  function getTouchDistance(touches: TouchList): number {
    if (touches.length < 2) return 0;
    const dx = touches[0].clientX - touches[1].clientX;
    const dy = touches[0].clientY - touches[1].clientY;
    return Math.hypot(dx, dy);
  }

  const clampPosition = useCallback(
    (nextX: number, nextY: number, width: number, height: number) => {
      if (isMobileViewport()) {
        return centerMobilePos(width, height);
      }
      return {
        x: Math.max(0, Math.min(nextX, window.innerWidth - width)),
        y: Math.max(0, Math.min(nextY, window.innerHeight - height)),
      };
    },
    [],
  );

  useEffect(() => {
    function handleViewportChange() {
      const mobile = isMobileViewport();
      setIsMobile(mobile);

      if (mobile) {
        const mobileSize = getMobileSize();
        setSize(mobileSize);
        setPos(centerMobilePos(mobileSize.w, mobileSize.h));
        return;
      }

      setSize((prev) => {
        const nextW = Math.min(Math.max(prev.w, MIN_W), window.innerWidth);
        const nextH = Math.min(Math.max(prev.h, MIN_H), window.innerHeight);
        return { w: nextW, h: nextH };
      });
      setPos((prev) => {
        const next = clampPosition(prev.x, prev.y, size.w, size.h);
        return next;
      });
    }

    handleViewportChange();
    window.addEventListener("resize", handleViewportChange);
    return () => window.removeEventListener("resize", handleViewportChange);
  }, [clampPosition, size.w, size.h]);

  useEffect(() => {
    function onPointerMove(e: PointerEvent) {
      if (dragRef.current && dragRef.current.pointerId === e.pointerId) {
        const d = dragRef.current;
        const unclampedX = d.origX + (e.clientX - d.startX);
        const unclampedY = d.origY + (e.clientY - d.startY);
        setPos(clampPosition(unclampedX, unclampedY, size.w, size.h));
      }
      if (resizeRef.current && resizeRef.current.pointerId === e.pointerId) {
        const r = resizeRef.current;
        const nextW = Math.max(MIN_W, r.origW + (e.clientX - r.startX));
        const nextH = Math.max(MIN_H, r.origH + (e.clientY - r.startY));
        setSize({
          w: Math.min(nextW, window.innerWidth),
          h: Math.min(nextH, window.innerHeight),
        });
      }
    }
    function onPointerUp(e: PointerEvent) {
      if (dragRef.current?.pointerId === e.pointerId) {
        dragRef.current = null;
      }
      if (resizeRef.current?.pointerId === e.pointerId) {
        resizeRef.current = null;
      }
    }
    function onPointerCancel() {
      dragRef.current = null;
      resizeRef.current = null;
    }

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("pointercancel", onPointerCancel);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      window.removeEventListener("pointercancel", onPointerCancel);
    };
  }, [clampPosition, size.w, size.h]);

  function onMobileTouchStart(e: ReactTouchEvent<HTMLDivElement>) {
    if (!isMobile || e.touches.length < 2) return;
    const startDistance = getTouchDistance(e.touches);
    if (!startDistance) return;
    pinchRef.current = {
      startDistance,
      startW: size.w,
      startH: size.h,
    };
  }

  function onMobileTouchMove(e: ReactTouchEvent<HTMLDivElement>) {
    if (!isMobile || !pinchRef.current || e.touches.length < 2) return;
    e.preventDefault();

    const currentDistance = getTouchDistance(e.touches);
    if (!currentDistance) return;

    const scale = currentDistance / pinchRef.current.startDistance;
    const nextW = Math.max(
      MOBILE_MIN_W,
      Math.min(window.innerWidth, Math.round(pinchRef.current.startW * scale)),
    );
    const ratio = pinchRef.current.startH / pinchRef.current.startW;
    const nextH = Math.max(
      MIN_H,
      Math.min(window.innerHeight, Math.round(nextW * ratio)),
    );

    setSize({ w: nextW, h: nextH });
    setPos(centerMobilePos(nextW, nextH));
  }

  function onMobileTouchEnd(e: ReactTouchEvent<HTMLDivElement>) {
    if (e.touches.length < 2) {
      pinchRef.current = null;
    }
  }

  return (
    <div
      className="fixed z-50 flex flex-col overflow-hidden border bg-background shadow-xl"
      style={{
        left: pos.x,
        top: pos.y,
        width: size.w,
        height: size.h,
        borderRadius: isMobile ? 0 : 8,
      }}
    >
      {/* Title bar — draggable */}
      <div
        className={`flex h-10 shrink-0 items-center justify-between border-b bg-muted px-3 ${isMobile ? "cursor-default" : "cursor-move"}`}
        onPointerDown={(e) => {
          if (isMobile) return;
          e.preventDefault();
          (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
          dragRef.current = {
            pointerId: e.pointerId,
            startX: e.clientX,
            startY: e.clientY,
            origX: pos.x,
            origY: pos.y,
          };
        }}
      >
        <span className="select-none text-sm font-medium truncate">
          {title} - {device.name} ({device.device_code})
        </span>
        <div className="ml-2 flex items-center gap-1">
          <button
            onPointerDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              onClose();
            }}
            className="shrink-0 rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Video content */}
      <div
        className="flex flex-1 items-center justify-center bg-black"
        style={{ touchAction: isMobile ? "none" : "auto" }}
        onTouchStart={onMobileTouchStart}
        onTouchMove={onMobileTouchMove}
        onTouchEnd={onMobileTouchEnd}
        onTouchCancel={onMobileTouchEnd}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`/api/admin/devices/${device.id}/stream?t=${streamKey}`}
          alt={altTemplate}
          className="h-full w-full object-contain"
          draggable={false}
        />
      </div>

      {/* Resize handle — bottom-right corner */}
      {!isMobile && (
        <div
          className="absolute bottom-0 right-0 h-6 w-6 cursor-nwse-resize touch-none"
          onPointerDown={(e) => {
            e.preventDefault();
            (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
            resizeRef.current = {
              pointerId: e.pointerId,
              startX: e.clientX,
              startY: e.clientY,
              origW: size.w,
              origH: size.h,
            };
          }}
        >
          <svg viewBox="0 0 16 16" className="h-6 w-6 text-muted-foreground/50">
            <path d="M14 14L8 14L14 8Z" fill="currentColor" />
            <path d="M14 14L11 14L14 11Z" fill="currentColor" />
          </svg>
        </div>
      )}
    </div>
  );
}
