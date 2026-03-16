# Autoflow 测试框架架构设计

## 概述

本文档定义了Autoflow框架的多层次测试架构，旨在解决过度依赖单元测试和Mock对象的问题，建立全面的测试质量保证体系。

## 测试金字塔

```
        /\
       /  \      E2E测试 (5-10%)
      /____\     - 完整工作流
     /      \    - 真实环境
    /        \   - 用户场景
   /__________\  集成测试 (20-30%)
  /            \ - 真实依赖
 /  单元测试    \- 组件交互
/______________\ (60-70%)
- 快速反馈
- 单一功能
- 最小化mock
```

## 测试层次

### 1. 单元测试 (Unit Tests)
**目的**: 验证单个函数、类的行为

**位置**: `tests/unit/`

**特点**:
- 执行速度快（< 1秒）
- 隔离性强
- 覆盖边界条件

**示例**:
```python
# tests/unit/test_scheduler.py
def test_parse_interval_natural_language():
    """测试自然语言间隔解析"""
    scheduler = TaskScheduler()
    result = scheduler._parse_schedule("每5分钟执行", "monitor")
    assert result["type"] == "interval"
    assert result["interval_seconds"] == 300
```

**准则**:
- 只在必要时使用mock（< 30%）
- 优先使用真实的小型依赖
- 测试必须有断言
- 每个测试只验证一个行为

### 2. 集成测试 (Integration Tests)
**目的**: 验证多个组件协作的正确性

**位置**: `tests/integration/`

**特点**:
- 使用真实的依赖
- 测试组件间接口
- 验证数据流

**示例**:
```python
# tests/integration/test_state_manager.py
async def test_state_lifecycle():
    """测试状态管理器完整生命周期"""
    # 使用真实的文件系统，不mock
    state_mgr = StateManager("/tmp/test_autoflow_state")
    await state_mgr.initialize()

    # 创建spec
    spec = await state_mgr.create_spec("test-spec", {...})
    assert spec.exists()

    # 创建任务
    task = await state_mgr.create_task("test-spec", {...})
    assert task.id == "T1"

    # 清理
    await state_mgr.cleanup()
```

**准则**:
- 最小化mock使用
- 使用测试数据库/文件系统
- 测试必须有完整的数据流
- 确保测试隔离

### 3. E2E测试 (End-to-End Tests)
**目的**: 验证完整的用户场景和工作流

**位置**: `tests/e2e/`

**特点**:
- 完整的工作流
- 真实的环境
- 用户视角

**示例**:
```python
# tests/e2e/test_complete_workflow.py
async def test_autonomous_development_workflow():
    """测试完整的自主开发流程"""
    # 1. 初始化环境
    async with E2EEnvironment() as env:
        # 2. 创建spec
        spec = await env.create_spec({
            "slug": "test-project",
            "title": "测试项目"
        })

        # 3. 生成任务
        tasks = await env.generate_tasks(spec.slug)
        assert len(tasks) > 0

        # 4. 执行任务
        for task in tasks:
            run = await env.create_run(task.id, agent="claude")
            result = await env.wait_for_completion(run.id)
            assert result in ["success", "needs_changes"]

        # 5. 验证结果
        state = await env.get_final_state()
        assert state["status"] == "completed"
```

**准则**:
- 测试真实用户场景
- 不mock任何外部依赖
- 测试必须有明确的业务价值
- 测试结果有详细报告

### 4. 性能测试 (Performance Tests)
**目的**: 验证系统在负载下的表现

**位置**: `tests/performance/`

**特点**:
- 基准测试
- 压力测试
- 资源使用监控

**示例**:
```python
# tests/performance/test_scheduler.py
async def test_scheduler_throughput():
    """测试调度器吞吐量"""
    scheduler = TaskScheduler()

    # 创建100个任务
    for i in range(100):
        await scheduler.schedule(f"task-{i}", {...})

    # 测量执行时间
    start = time.time()
    await scheduler.run_all()
    duration = time.time() - start

    # 断言：100个任务在10秒内完成
    assert duration < 10.0
    assert scheduler.success_rate >= 0.95
```

### 5. 安全测试 (Security Tests)
**目的**: 验证系统的安全性

**位置**: `tests/security/`

**特点**:
- 权限检查
- 注入攻击测试
- 数据验证

**示例**:
```python
# tests/security/test_state_validation.py
async def test_reject_malicious_spec():
    """测试拒绝恶意spec"""
    state_mgr = StateManager()

    # 尝试创建路径遍历攻击
    with pytest.raises(ValidationError):
        await state_mgr.create_spec("../../etc/passwd", {})

    # 测试注入攻击
    with pytest.raises(ValidationError):
        await state_mgr.create_spec("'; DROP TABLE specs; --", {})
```

## 测试环境架构

### 开发环境
```yaml
environment: development
database: sqlite://tmp/dev.db
logs: console
features:
  - debug_mode
  - hot_reload
```

### 测试环境
```yaml
environment: testing
database: postgresql://test-user:test-pass@localhost:5432/autoflow_test
logs: file
fixtures: tests/fixtures/
isolation: true
```

### CI环境
```yaml
environment: ci
database: postgresql://ci:ci@localhost:5432/autoflow_ci
parallel: 4
timeout: 3600
artifacts:
  - test-results/
  - coverage/
  - screenshots/
```

## 测试数据管理

### Fixture策略
```python
# tests/fixtures/specs.py
@pytest.fixture
async def sample_spec():
    """提供示例spec"""
    return {
        "slug": "test-spec",
        "title": "测试规格",
        "summary": "用于测试的规格",
        "goals": ["目标1", "目标2"],
        "acceptance_criteria": ["标准1"]
    }

@pytest.fixture
async def initialized_state(sample_spec):
    """提供初始化的状态管理器"""
    state_mgr = StateManager(":memory:")
    await state_mgr.initialize()
    yield state_mgr
    await state_mgr.cleanup()
```

### 数据清理
```python
# tests/conftest.py
@pytest.fixture(autouse=True)
async def clean_test_data():
    """每个测试后自动清理"""
    yield
    # 清理测试数据库
    await test_db.cleanup()
    # 清理测试文件
    await test_fs.cleanup()
```

## E2E测试框架接口

### 基类设计
```python
# tests/e2e/base.py
class E2ETestCase:
    """E2E测试基类"""

    async def setup_environment(self):
        """设置测试环境"""
        self.env = await E2EEnvironment.create()

    async def teardown_environment(self):
        """清理测试环境"""
        await self.env.cleanup()

    async def create_spec(self, data: dict) -> Spec:
        """创建spec"""
        return await self.env.create_spec(data)

    async def run_workflow(self, spec_slug: str) -> WorkflowResult:
        """运行完整工作流"""
        return await self.env.run_workflow(spec_slug)
```

### 辅助函数
```python
# tests/e2e/helpers.py
async def wait_for_condition(
    condition: Callable[[], bool],
    timeout: float = 60.0,
    poll_interval: float = 0.5
) -> bool:
    """等待条件满足"""

async def capture_logs() -> List[LogEntry]:
    """捕获日志"""

async def verify_task_completion(task_id: str) -> bool:
    """验证任务完成"""
```

## 测试执行策略

### 本地开发
```bash
# 快速反馈：只运行单元测试
pytest tests/unit/ -v

# 中等反馈：单元+集成测试
pytest tests/unit/ tests/integration/ -v

# 完整验证：所有测试
pytest tests/ -v
```

### CI/CD
```yaml
stages:
  - quick_test:
      - tests/unit/
      - timeout: 5m

  - integration:
      - tests/integration/
      - timeout: 15m

  - e2e:
      - tests/e2e/
      - timeout: 30m
      - parallel: 4
```

## 覆盖率要求

| 测试类型 | 覆盖率目标 | 说明 |
|---------|----------|------|
| 单元测试 | 80% | 核心逻辑模块 |
| 集成测试 | 60% | 关键集成路径 |
| E2E测试 | 80% | 核心用户场景 |
| 分支覆盖率 | 70% | 所有代码 |

## Mock使用原则

### 允许使用Mock的场景
1. **外部服务**: 云API、第三方服务
2. **不可控资源**: 随机数、时间（需要固定）
3. **性能隔离**: 避免网络/IO延迟影响单元测试速度

### 禁止使用Mock的场景
1. **数据库**: 使用测试数据库
2. **文件系统**: 使用临时目录
3. **内部组件**: 测试真实交互

### Mock使用率目标
- 单元测试: < 40%
- 集成测试: < 20%
- E2E测试: 0%

## 持续改进

### 指标追踪
1. **测试通过率**: 目标 > 95%
2. **测试执行时间**: 单元< 5min，集成< 15min，E2E< 30min
3. **Mock使用率**: 持续降低
4. **缺陷逃逸率**: 生产缺陷 < 5%

### 定期审查
- 每周审查测试覆盖率
- 每月审查测试质量
- 每季度审查测试策略

## 工具和依赖

```python
# pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = [
    "-v",
    "--strict-markers",
    "--tb=short",
    "--cov=autoflow",
    "--cov-report=term-missing",
    "--cov-report=html"
]

[tool.coverage.run]
branch = true
omit = [
    "tests/*",
    "*/__pycache__/*",
    "*/conftest.py"
]
```

## 下一步行动

1. ✅ 架构设计（本文档）
2. ⏳ 实现E2E测试框架基础设施
3. ⏳ 实现核心场景E2E测试
4. ⏳ 重构集成测试使用真实环境
5. ⏳ 实现UAT框架
6. ⏳ 实现完成标准检查系统
7. ⏳ 集成到CI/CD
8. ⏳ 编写文档和指南
