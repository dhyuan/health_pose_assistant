"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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

const REFRESH_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes

function isOnline(lastSeenAt: string | null): boolean {
  if (!lastSeenAt) return false;
  return Date.now() - new Date(lastSeenAt).getTime() < 60_000;
}

export default function DevicesPage() {
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
  const [streamKey, setStreamKey] = useState(0);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchDevices = useCallback(async () => {
    try {
      const data = await listDevices();
      setDevices(data);
    } catch {
      toast.error("加载设备列表失败");
    } finally {
      setLoading(false);
    }
  }, []);

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
      toast.success("设备注册成功");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "注册失败";
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
      toast.success("设备名称已更新");
    } catch {
      toast.error("更新失败");
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    try {
      await deleteDevice(deleteTarget.id);
      setDevices((prev) => prev.filter((d) => d.id !== deleteTarget.id));
      setDeleteTarget(null);
      toast.success("设备已删除");
    } catch {
      toast.error("删除失败");
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
      toast.success("Token 已重新生成");
    } catch {
      toast.error("重新生成失败");
    }
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">设备管理</h1>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchDevices}>
            刷新
          </Button>
          <Button size="sm" onClick={() => setShowRegister(true)}>
            注册设备
          </Button>
        </div>
      </div>

      {loading ? (
        <p className="text-muted-foreground">加载中…</p>
      ) : devices.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            暂无设备，点击「注册设备」添加第一台设备。
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              共 {devices.length} 台设备
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>设备编号</TableHead>
                  <TableHead>名称</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>最后在线</TableHead>
                  <TableHead className="text-right">操作</TableHead>
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
                        <Badge className="bg-green-600">在线</Badge>
                      ) : (
                        <Badge variant="secondary">离线</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {device.last_seen_at
                        ? new Date(device.last_seen_at).toLocaleString("zh-CN")
                        : "从未连接"}
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
                                查看视频
                              </DropdownMenuItem>
                            )}
                          <DropdownMenuItem
                            onClick={() => {
                              window.location.href = `/stats?device_id=${device.id}`;
                            }}
                          >
                            查看统计
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onClick={() => {
                              setRenameDevice(device);
                              setRenameName(device.name);
                            }}
                          >
                            重命名
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onClick={() => setRegenTarget(device)}
                          >
                            重新生成 Token
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            className="text-red-600"
                            onClick={() => setDeleteTarget(device)}
                          >
                            删除设备
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
            <DialogTitle>注册新设备</DialogTitle>
            <DialogDescription>
              输入设备编号和名称。注册后会生成一个 Token，请立即复制保存。
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="device-code">设备编号</Label>
              <Input
                id="device-code"
                placeholder="例如: PI-001"
                value={regCode}
                onChange={(e) => setRegCode(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="device-name">设备名称</Label>
              <Input
                id="device-name"
                placeholder="例如: 客厅"
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
              {regLoading ? "注册中…" : "注册"}
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
            <DialogTitle>设备 Token</DialogTitle>
            <DialogDescription>
              请立即复制此 Token。关闭对话框后将无法再次查看。
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
                  toast.success("已复制到剪贴板");
                }
              }}
            >
              复制 Token
            </Button>
            <Button onClick={() => setTokenToShow(null)}>关闭</Button>
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
            <DialogTitle>重命名设备</DialogTitle>
          </DialogHeader>
          <div className="grid gap-2 py-4">
            <Label htmlFor="rename-input">新名称</Label>
            <Input
              id="rename-input"
              value={renameName}
              onChange={(e) => setRenameName(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button onClick={handleRename} disabled={!renameName.trim()}>
              保存
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
            <AlertDialogTitle>确认删除设备？</AlertDialogTitle>
            <AlertDialogDescription>
              将永久删除设备「{deleteTarget?.name}」(
              {deleteTarget?.device_code})及其所有关联数据。此操作不可撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-red-600 hover:bg-red-700"
              onClick={handleDelete}
            >
              删除
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
            <AlertDialogTitle>重新生成 Token？</AlertDialogTitle>
            <AlertDialogDescription>
              旧 Token 将立即失效，设备「{regenTarget?.name}」需要更新为新 Token
              才能继续连接。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleRegenToken}>
              确认重新生成
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
}: {
  device: Device;
  streamKey: number;
  onClose: () => void;
}) {
  const DEFAULT_W = 640;
  const DEFAULT_H = 520;
  const MIN_W = 320;
  const MIN_H = 280;

  const [pos, setPos] = useState(() => ({
    x: Math.max(0, Math.floor((window.innerWidth - DEFAULT_W) / 2)),
    y: Math.max(0, Math.floor((window.innerHeight - DEFAULT_H) / 2)),
  }));
  const [size, setSize] = useState({ w: DEFAULT_W, h: DEFAULT_H });

  const dragRef = useRef<{
    startX: number;
    startY: number;
    origX: number;
    origY: number;
  } | null>(null);
  const resizeRef = useRef<{
    startX: number;
    startY: number;
    origW: number;
    origH: number;
  } | null>(null);

  useEffect(() => {
    function onMouseMove(e: MouseEvent) {
      if (dragRef.current) {
        const d = dragRef.current;
        setPos({
          x: d.origX + (e.clientX - d.startX),
          y: d.origY + (e.clientY - d.startY),
        });
      }
      if (resizeRef.current) {
        const r = resizeRef.current;
        setSize({
          w: Math.max(MIN_W, r.origW + (e.clientX - r.startX)),
          h: Math.max(MIN_H, r.origH + (e.clientY - r.startY)),
        });
      }
    }
    function onMouseUp() {
      dragRef.current = null;
      resizeRef.current = null;
    }
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, []);

  return (
    <div
      className="fixed z-50 flex flex-col overflow-hidden rounded-lg border bg-background shadow-xl"
      style={{ left: pos.x, top: pos.y, width: size.w, height: size.h }}
    >
      {/* Title bar — draggable */}
      <div
        className="flex h-10 shrink-0 cursor-move items-center justify-between border-b bg-muted px-3"
        onMouseDown={(e) => {
          e.preventDefault();
          dragRef.current = {
            startX: e.clientX,
            startY: e.clientY,
            origX: pos.x,
            origY: pos.y,
          };
        }}
      >
        <span className="select-none text-sm font-medium truncate">
          实时视频 — {device.name} ({device.device_code})
        </span>
        <button
          onClick={onClose}
          className="ml-2 shrink-0 rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          ✕
        </button>
      </div>

      {/* Video content */}
      <div className="flex flex-1 items-center justify-center bg-black">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`/api/admin/devices/${device.id}/stream?t=${streamKey}`}
          alt={`${device.name} 视频流`}
          className="h-full w-full object-contain"
          draggable={false}
        />
      </div>

      {/* Resize handle — bottom-right corner */}
      <div
        className="absolute bottom-0 right-0 h-4 w-4 cursor-nwse-resize"
        onMouseDown={(e) => {
          e.preventDefault();
          resizeRef.current = {
            startX: e.clientX,
            startY: e.clientY,
            origW: size.w,
            origH: size.h,
          };
        }}
      >
        <svg viewBox="0 0 16 16" className="h-4 w-4 text-muted-foreground/50">
          <path d="M14 14L8 14L14 8Z" fill="currentColor" />
          <path d="M14 14L11 14L14 11Z" fill="currentColor" />
        </svg>
      </div>
    </div>
  );
}
