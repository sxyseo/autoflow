#!/usr/bin/env python3
"""
Autoflow 智能任务调度器

支持定时任务、循环任务、监控任务等功能，类似 OpenClaw、Claude Code、CodeX 的调度功能。

功能特性：
- 定时监控项目进度
- 自动生成日报、周报
- 自然语言创建任务
- 任务完成自动清理
- 灵活的调度策略
"""

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union
import subprocess
import argparse

ROOT = Path(__file__).resolve().parent.parent.parent
STATE_DIR = ROOT / ".autoflow"
TASKS_DIR = STATE_DIR / "scheduled_tasks"


class TaskStatus(str, Enum):
    """定时任务状态"""
    ACTIVE = "active"      # 活跃运行
    PAUSED = "paused"      # 已暂停
    COMPLETED = "completed" # 已完成
    FAILED = "failed"      # 失败
    CANCELLED = "cancelled" # 已取消


class TaskType(str, Enum):
    """任务类型"""
    MONITOR = "monitor"        # 监控任务
    REPORT = "report"          # 报告任务
    CLEANUP = "cleanup"        # 清理任务
    NOTIFICATION = "notification" # 通知任务
    CUSTOM = "custom"          # 自定义任务


class ScheduleType(str, Enum):
    """调度类型"""
    ONCE = "once"              # 一次性
    INTERVAL = "interval"      # 固定间隔
    CRON = "cron"              # Cron 表达式
    EVENT = "event"            # 事件触发


class ScheduledTask:
    """定时任务"""

    def __init__(
        self,
        task_id: str,
        name: str,
        task_type: TaskType,
        schedule_type: ScheduleType,
        schedule_value: str,
        command: Optional[str] = None,
        callback: Optional[str] = None,
        enabled: bool = True,
        auto_cleanup: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.task_id = task_id
        self.name = name
        self.task_type = task_type
        self.schedule_type = schedule_type
        self.schedule_value = schedule_value
        self.command = command
        self.callback = callback
        self.enabled = enabled
        self.auto_cleanup = auto_cleanup
        self.metadata = metadata or {}

        # 状态
        self.status = TaskStatus.ACTIVE if enabled else TaskStatus.PAUSED
        self.created_at = datetime.now(timezone.utc)
        self.last_run = None
        self.next_run = None
        self.run_count = 0
        self.last_result = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "name": self.name,
            "task_type": self.task_type.value,
            "schedule_type": self.schedule_type.value,
            "schedule_value": self.schedule_value,
            "command": self.command,
            "callback": self.callback,
            "enabled": self.enabled,
            "auto_cleanup": self.auto_cleanup,
            "metadata": self.metadata,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "run_count": self.run_count,
            "last_result": self.last_result,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduledTask":
        """从字典创建"""
        task = cls(
            task_id=data["task_id"],
            name=data["name"],
            task_type=TaskType(data["task_type"]),
            schedule_type=ScheduleType(data["schedule_type"]),
            schedule_value=data["schedule_value"],
            command=data.get("command"),
            callback=data.get("callback"),
            enabled=data.get("enabled", True),
            auto_cleanup=data.get("auto_cleanup", False),
            metadata=data.get("metadata", {}),
        )

        task.status = TaskStatus(data.get("status", "active"))
        task.created_at = datetime.fromisoformat(data["created_at"])
        task.last_run = datetime.fromisoformat(data["last_run"]) if data.get("last_run") else None
        task.next_run = datetime.fromisoformat(data["next_run"]) if data.get("next_run") else None
        task.run_count = data.get("run_count", 0)
        task.last_result = data.get("last_result")

        return task

    def should_run(self) -> bool:
        """检查是否应该运行"""
        if not self.enabled or self.status != TaskStatus.ACTIVE:
            return False

        now = datetime.now(timezone.utc)

        if self.schedule_type == ScheduleType.ONCE:
            return self.next_run and now >= self.next_run

        elif self.schedule_type == ScheduleType.INTERVAL:
            if not self.last_run:
                return self.next_run and now >= self.next_run
            interval_seconds = self._parse_interval()
            next_run = self.last_run + timedelta(seconds=interval_seconds)
            return now >= next_run

        elif self.schedule_type == ScheduleType.CRON:
            # 简化的 cron 匹配（实际应用中可用 croniter）
            return self._match_cron(now)

        return False

    def _parse_interval(self) -> int:
        """解析间隔时间（秒）"""
        try:
            return int(self.schedule_value)
        except ValueError:
            # 支持格式: "5m", "1h", "30s" 等
            match = re.match(r'(\d+)([smh])', self.schedule_value)
            if match:
                value, unit = match.groups()
                value = int(value)
                if unit == 's':
                    return value
                elif unit == 'm':
                    return value * 60
                elif unit == 'h':
                    return value * 3600
            return 300  # 默认 5 分钟

    def _match_cron(self, now: datetime) -> bool:
        """简单的 cron 匹配"""
        # 支持格式: "*/5 * * * *" (每5分钟)
        # 简化实现，实际应用中建议使用 croniter 库
        parts = self.schedule_value.split()
        if len(parts) >= 5:
            minute_part = parts[0]
            if minute_part.startswith("*/"):
                interval = int(minute_part[2:])
                return now.minute % interval == 0
        return False

    def calculate_next_run(self) -> Optional[datetime]:
        """计算下次运行时间"""
        now = datetime.now(timezone.utc)

        if self.schedule_type == ScheduleType.ONCE:
            return self.next_run

        elif self.schedule_type == ScheduleType.INTERVAL:
            interval = self._parse_interval()
            return now + timedelta(seconds=interval)

        elif self.schedule_type == ScheduleType.CRON:
            # 简化实现
            interval = self._parse_interval()
            return now + timedelta(seconds=interval)

        return None

    def execute(self) -> Dict[str, Any]:
        """执行任务"""
        start_time = datetime.now(timezone.utc)
        result = {
            "task_id": self.task_id,
            "started_at": start_time.isoformat(),
            "success": False,
            "output": "",
            "error": None,
        }

        try:
            if self.command:
                # 执行命令
                proc = subprocess.run(
                    self.command,
                    shell=True,
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 分钟超时
                )
                result["output"] = proc.stdout
                result["success"] = proc.returncode == 0
                if not result["success"]:
                    result["error"] = proc.stderr

            elif self.callback:
                # 调用回调函数
                result = self._execute_callback()
            else:
                # 默认行为
                result["success"] = True
                result["output"] = f"Task {self.name} executed"

        except Exception as e:
            result["error"] = str(e)
            result["success"] = False

        finally:
            end_time = datetime.now(timezone.utc)
            result["duration"] = (end_time - start_time).total_seconds()
            result["completed_at"] = end_time.isoformat()

        # 更新状态
        self.last_run = start_time
        self.run_count += 1
        self.last_result = result
        self.next_run = self.calculate_next_run()

        # 检查是否需要自动清理
        if self.auto_cleanup and self.schedule_type == ScheduleType.ONCE:
            if result["success"]:
                self.status = TaskStatus.COMPLETED

        return result

    def _execute_callback(self) -> Dict[str, Any]:
        """执行回调函数"""
        # 根据回调类型执行不同的操作
        if self.callback == "monitor_project":
            return self._monitor_project()
        elif self.callback == "generate_report":
            return self._generate_report()
        elif self.callback == "check_resources":
            return self._check_resources()
        else:
            return {
                "success": False,
                "error": f"Unknown callback: {self.callback}"
            }

    def _monitor_project(self) -> Dict[str, Any]:
        """监控项目状态"""
        try:
            # 运行 workflow-state 命令
            proc = subprocess.run(
                ["python3", "scripts/autoflow.py", "workflow-state", "--spec", "snake-game"],
                capture_output=True,
                text=True,
                timeout=30
            )

            return {
                "success": proc.returncode == 0,
                "output": proc.stdout,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _generate_report(self) -> Dict[str, Any]:
        """生成项目报告"""
        try:
            # 获取项目状态
            state_proc = subprocess.run(
                ["python3", "scripts/autoflow.py", "workflow-state", "--spec", "snake-game"],
                capture_output=True,
                text=True,
                timeout=30
            )

            # 获取任务历史
            history_proc = subprocess.run(
                ["python3", "scripts/autoflow.py", "task-history", "--spec", "snake-game"],
                capture_output=True,
                text=True,
                timeout=30
            )

            report = {
                "success": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "workflow_state": state_proc.stdout if state_proc.returncode == 0 else state_proc.stderr,
                "task_history": history_proc.stdout if history_proc.returncode == 0 else history_proc.stderr,
            }

            return report
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _check_resources(self) -> Dict[str, Any]:
        """检查系统资源"""
        try:
            proc = subprocess.run(
                ["python3", "scripts/resource-monitor.py", "--json"],
                capture_output=True,
                text=True,
                timeout=30
            )

            return {
                "success": proc.returncode == 0,
                "output": proc.stdout,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


class TaskScheduler:
    """任务调度器"""

    def __init__(self):
        """初始化调度器"""
        self.tasks: Dict[str, ScheduledTask] = {}
        self.running = False
        self._check_interval = 30  # 30 秒检查一次

        # 确保目录存在
        TASKS_DIR.mkdir(parents=True, exist_ok=True)

        # 加载已保存的任务
        self._load_tasks()

    def _load_tasks(self):
        """加载已保存的任务"""
        for task_file in TASKS_DIR.glob("*.json"):
            try:
                with open(task_file) as f:
                    data = json.load(f)
                task = ScheduledTask.from_dict(data)
                self.tasks[task.task_id] = task
            except Exception as e:
                print(f"Failed to load task {task_file}: {e}")

    def _save_task(self, task: ScheduledTask):
        """保存任务"""
        task_file = TASKS_DIR / f"{task.task_id}.json"
        with open(task_file, "w") as f:
            json.dump(task.to_dict(), f, indent=2, ensure_ascii=False)

    def create_task(
        self,
        name: str,
        task_type: Union[TaskType, str],
        schedule_type: Union[ScheduleType, str],
        schedule_value: str,
        command: Optional[str] = None,
        callback: Optional[str] = None,
        enabled: bool = True,
        auto_cleanup: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ScheduledTask:
        """创建新任务"""
        # 生成任务 ID
        task_id = f"task_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

        # 转换枚举
        if isinstance(task_type, str):
            task_type = TaskType(task_type)
        if isinstance(schedule_type, str):
            schedule_type = ScheduleType(schedule_type)

        task = ScheduledTask(
            task_id=task_id,
            name=name,
            task_type=task_type,
            schedule_type=schedule_type,
            schedule_value=schedule_value,
            command=command,
            callback=callback,
            enabled=enabled,
            auto_cleanup=auto_cleanup,
            metadata=metadata,
        )

        # 计算下次运行时间
        if schedule_type == ScheduleType.ONCE:
            delay = int(schedule_value) if schedule_value.isdigit() else 0
            task.next_run = datetime.now(timezone.utc) + timedelta(seconds=delay)
        else:
            task.next_run = task.calculate_next_run()

        self.tasks[task_id] = task
        self._save_task(task)

        return task

    def create_from_natural_language(self, description: str) -> ScheduledTask:
        """从自然语言描述创建任务"""
        description = description.lower().strip()

        # 解析常见模式
        # "每5分钟监控项目"
        if "每" in description and "监控" in description:
            match = re.search(r'每\s*(\d+)\s*(秒|分钟?|小时?)', description)
            if match:
                value = int(match.group(1))
                unit = match.group(2)

                if unit.startswith("秒"):
                    interval = value
                elif unit.startswith("分"):
                    interval = value * 60
                elif unit.startswith("小"):
                    interval = value * 3600
                else:
                    interval = 300

                return self.create_task(
                    name=f"项目监控 ({description})",
                    task_type=TaskType.MONITOR,
                    schedule_type=ScheduleType.INTERVAL,
                    schedule_value=str(interval),
                    callback="monitor_project",
                    metadata={"original_description": description}
                )

        # "每天早上9点生成日报"
        elif "日报" in description or "报告" in description:
            return self.create_task(
                name=f"日报生成 ({description})",
                task_type=TaskType.REPORT,
                schedule_type=ScheduleType.CRON,
                schedule_value="0 9 * * *",  # 每天早上9点
                callback="generate_report",
                metadata={"original_description": description}
            )

        # "每小时检查资源"
        elif "资源" in description:
            return self.create_task(
                name=f"资源监控 ({description})",
                task_type=TaskType.MONITOR,
                schedule_type=ScheduleType.INTERVAL,
                schedule_value="3600",  # 1小时
                callback="check_resources",
                metadata={"original_description": description}
            )

        # 默认：创建一个简单的监控任务
        return self.create_task(
            name=f"定时任务 ({description})",
            task_type=TaskType.MONITOR,
            schedule_type=ScheduleType.INTERVAL,
            schedule_value="300",  # 5分钟
            callback="monitor_project",
            metadata={"original_description": description}
        )

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """获取任务"""
        return self.tasks.get(task_id)

    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        task_type: Optional[TaskType] = None,
    ) -> List[ScheduledTask]:
        """列出任务"""
        tasks = list(self.tasks.values())

        if status:
            tasks = [t for t in tasks if t.status == status]
        if task_type:
            tasks = [t for t in tasks if t.task_type == task_type]

        return tasks

    def pause_task(self, task_id: str) -> bool:
        """暂停任务"""
        task = self.get_task(task_id)
        if task:
            task.status = TaskStatus.PAUSED
            task.enabled = False
            self._save_task(task)
            return True
        return False

    def resume_task(self, task_id: str) -> bool:
        """恢复任务"""
        task = self.get_task(task_id)
        if task:
            task.status = TaskStatus.ACTIVE
            task.enabled = True
            task.next_run = task.calculate_next_run()
            self._save_task(task)
            return True
        return False

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        task = self.get_task(task_id)
        if task:
            task.status = TaskStatus.CANCELLED
            task.enabled = False
            self._save_task(task)

            # 删除任务文件
            task_file = TASKS_DIR / f"{task_id}.json"
            if task_file.exists():
                task_file.unlink()

            del self.tasks[task_id]
            return True
        return False

    def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        return self.cancel_task(task_id)

    async def start(self):
        """启动调度器"""
        self.running = True
        print(f"任务调度器已启动 (检查间隔: {self._check_interval}秒)")

        while self.running:
            try:
                await self._check_and_run_tasks()
                await asyncio.sleep(self._check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"调度器错误: {e}")
                await asyncio.sleep(self._check_interval)

    def stop(self):
        """停止调度器"""
        self.running = False

    async def _check_and_run_tasks(self):
        """检查并运行到期的任务"""
        now = datetime.now(timezone.utc)
        tasks_to_run = []

        for task in self.tasks.values():
            if task.should_run():
                tasks_to_run.append(task)

        if tasks_to_run:
            print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')}] 运行 {len(tasks_to_run)} 个任务:")

            for task in tasks_to_run:
                print(f"  - {task.name} (类型: {task.task_type.value})")
                result = task.execute()
                self._save_task(task)

                if result["success"]:
                    print(f"    ✓ 成功 (耗时: {result.get('duration', 0):.2f}秒)")
                else:
                    print(f"    ✗ 失败: {result.get('error', 'Unknown error')}")

                # 检查是否需要清理
                if task.status == TaskStatus.COMPLETED:
                    print(f"    🗑️  任务已完成并自动清理")
                    self.delete_task(task.task_id)

    def generate_report(self) -> Dict[str, Any]:
        """生成调度器报告"""
        active_tasks = self.list_tasks(status=TaskStatus.ACTIVE)
        paused_tasks = self.list_tasks(status=TaskStatus.PAUSED)

        report = {
            "total_tasks": len(self.tasks),
            "active_tasks": len(active_tasks),
            "paused_tasks": len(paused_tasks),
            "tasks": [],
        }

        for task in self.tasks.values():
            report["tasks"].append({
                "id": task.task_id,
                "name": task.name,
                "type": task.task_type.value,
                "status": task.status.value,
                "schedule": f"{task.schedule_type.value}:{task.schedule_value}",
                "run_count": task.run_count,
                "last_run": task.last_run.isoformat() if task.last_run else None,
                "next_run": task.next_run.isoformat() if task.next_run else None,
            })

        return report


# CLI 接口
def main():
    parser = argparse.ArgumentParser(
        description="Autoflow 智能任务调度器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 从自然语言创建任务
  python3 -m autoflow.scheduler.task_scheduler create "每5分钟监控项目"

  # 列出所有任务
  python3 -m autoflow.scheduler.task_scheduler list

  # 启动调度器
  python3 -m autoflow.scheduler.task_scheduler start

  # 暂停任务
  python3 -m autoflow.scheduler.task_scheduler pause <task_id>

  # 恢复任务
  python3 -m autoflow.scheduler.task_scheduler resume <task_id>

  # 取消任务
  python3 -m autoflow.scheduler.task_scheduler cancel <task_id>
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # 创建任务
    create_parser = subparsers.add_parser("create", help="创建新任务")
    create_parser.add_argument("description", help="任务描述（支持自然语言）")
    create_parser.add_argument("--type", choices=["monitor", "report", "cleanup", "custom"], default="monitor", help="任务类型")
    create_parser.add_argument("--schedule", help="调度配置 (间隔/ cron)")
    create_parser.add_argument("--command", help="要执行的命令")
    create_parser.add_argument("--callback", help="回调函数")
    create_parser.add_argument("--auto-cleanup", action="store_true", help="完成后自动删除")

    # 列出任务
    list_parser = subparsers.add_parser("list", help="列出任务")
    list_parser.add_argument("--status", help="按状态过滤")
    list_parser.add_argument("--type", help="按类型过滤")
    list_parser.add_argument("--json", action="store_true", help="JSON 格式输出")

    # 启动调度器
    start_parser = subparsers.add_parser("start", help="启动调度器")
    start_parser.add_argument("--interval", type=int, default=30, help="检查间隔（秒）")

    # 暂停任务
    pause_parser = subparsers.add_parser("pause", help="暂停任务")
    pause_parser.add_argument("task_id", help="任务 ID")

    # 恢复任务
    resume_parser = subparsers.add_parser("resume", help="恢复任务")
    resume_parser.add_argument("task_id", help="任务 ID")

    # 取消任务
    cancel_parser = subparsers.add_parser("cancel", help="取消任务")
    cancel_parser.add_argument("task_id", help="任务 ID")

    # 删除任务
    delete_parser = subparsers.add_parser("delete", help="删除任务")
    delete_parser.add_argument("task_id", help="任务 ID")

    # 生成报告
    report_parser = subparsers.add_parser("report", help="生成报告")
    report_parser.add_argument("--json", action="store_true", help="JSON 格式输出")

    args = parser.parse_args()

    scheduler = TaskScheduler()

    if args.command == "create":
        if args.schedule or args.command:
            task = scheduler.create_task(
                name=args.description,
                task_type=args.type,
                schedule_type=ScheduleType.INTERVAL,
                schedule_value=args.schedule or "300",
                command=args.command,
                callback=args.callback,
                auto_cleanup=args.auto_cleanup,
            )
        else:
            task = scheduler.create_from_natural_language(args.description)

        print(f"✓ 任务已创建: {task.task_id}")
        print(f"  名称: {task.name}")
        print(f"  类型: {task.task_type.value}")
        print(f"  调度: {task.schedule_type.value}:{task.schedule_value}")
        print(f"  下次运行: {task.next_run}")

    elif args.command == "list":
        tasks = scheduler.list_tasks(
            status=TaskStatus(args.status) if args.status else None,
            task_type=TaskType(args.type) if args.type else None,
        )

        if args.json:
            print(json.dumps([t.to_dict() for t in tasks], indent=2, ensure_ascii=False))
        else:
            if not tasks:
                print("没有找到任务")
            else:
                for task in tasks:
                    status_emoji = {
                        TaskStatus.ACTIVE: "🟢",
                        TaskStatus.PAUSED: "⏸️",
                        TaskStatus.COMPLETED: "✅",
                        TaskStatus.FAILED: "❌",
                        TaskStatus.CANCELLED: "🚫",
                    }.get(task.status, "•")

                    print(f"{status_emoji} {task.task_id}")
                    print(f"   名称: {task.name}")
                    print(f"   类型: {task.task_type.value}")
                    print(f"   状态: {task.status.value}")
                    print(f"   调度: {task.schedule_type.value}:{task.schedule_value}")
                    print(f"   运行次数: {task.run_count}")
                    print(f"   下次运行: {task.next_run}")
                    print()

    elif args.command == "start":
        scheduler._check_interval = args.interval
        asyncio.run(scheduler.start())

    elif args.command == "pause":
        if scheduler.pause_task(args.task_id):
            print(f"✓ 任务已暂停: {args.task_id}")
        else:
            print(f"✗ 任务未找到: {args.task_id}")

    elif args.command == "resume":
        if scheduler.resume_task(args.task_id):
            print(f"✓ 任务已恢复: {args.task_id}")
        else:
            print(f"✗ 任务未找到: {args.task_id}")

    elif args.command == "cancel" or args.command == "delete":
        if scheduler.cancel_task(args.task_id):
            print(f"✓ 任务已取消: {args.task_id}")
        else:
            print(f"✗ 任务未找到: {args.task_id}")

    elif args.command == "report":
        report = scheduler.generate_report()
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print("\n📊 任务调度器报告")
            print("=" * 60)
            print(f"总任务数: {report['total_tasks']}")
            print(f"活跃任务: {report['active_tasks']}")
            print(f"暂停任务: {report['paused_tasks']}")
            print()

            for task_info in report["tasks"]:
                status_emoji = {
                    TaskStatus.ACTIVE: "🟢",
                    TaskStatus.PAUSED: "⏸️",
                    TaskStatus.COMPLETED: "✅",
                    TaskStatus.FAILED: "❌",
                    TaskStatus.CANCELLED: "🚫",
                }.get(task_info["status"], "•")

                print(f"{status_emoji} {task_info['id']}")
                print(f"   {task_info['name']}")
                print(f"   状态: {task_info['status']} | 运行: {task_info['run_count']}次")
                print(f"   调度: {task_info['schedule']}")
                if task_info["next_run"]:
                    print(f"   下次: {task_info['next_run']}")
                print()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
