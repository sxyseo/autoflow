# Autoflow 测试指南

## 概述

本指南介绍如何使用Autoflow的多层次测试框架，包括E2E测试、集成测试和完成标准检查系统。

## 测试层次

### 1. 单元测试 (Unit Tests)
**位置**: `tests/unit/`

**目的**: 快速验证单个函数/类的行为

**运行**:
```bash
# 运行所有单元测试
pytest tests/unit/ -v

# 运行特定文件
pytest tests/unit/test_scheduler.py -v

# 运行特定测试
pytest tests/unit/test_scheduler.py::test_parse_interval -v
```

**编写单元测试**:
```python
# tests/unit/test_example.py
def test_function_behavior():
    """测试函数的基本行为"""
    result = function_under_test(input_value)
    assert result == expected_output

def test_edge_case():
    """测试边界条件"""
    result = function_under_test(extreme_value)
    assert result is not None
```

### 2. 集成测试 (Integration Tests)
**位置**: `tests/integration/`

**目的**: 验证多个组件的协作，使用真实依赖

**运行**:
```bash
# 运行所有集成测试
pytest tests/integration/ -v

# 运行真实环境测试
pytest tests/integration/test_real_state_manager.py -v
```

**编写集成测试**:
```python
# tests/integration/test_integration.py
import pytest
from autoflow.core.state import StateManager

@pytest.fixture
async def state_manager():
    """提供真实的state manager实例"""
    temp_dir = tempfile.mkdtemp()
    manager = StateManager(temp_dir)
    await manager.initialize()
    yield manager
    await manager.close()
    # 清理
    shutil.rmtree(temp_dir, ignore_errors=True)

async def test_component_integration(state_manager):
    """测试组件集成"""
    # 使用真实的文件系统，不mock
    spec = await state_manager.create_spec("test", {...})
    assert spec.exists()
```

**关键原则**:
- 最小化mock使用
- 使用测试数据库/文件系统
- 测试完整的数据流
- 确保测试隔离

### 3. E2E测试 (End-to-End Tests)
**位置**: `tests/e2e/`

**目的**: 验证完整的用户场景和工作流

**运行**:
```bash
# 运行所有E2E测试
pytest tests/e2e/ -v

# 运行特定E2E测试
pytest tests/e2e/test_complete_workflow.py -v

# 带详细输出
pytest tests/e2e/ -v -s
```

**编写E2E测试**:
```python
# tests/e2e/test_workflow.py
from tests.e2e.base import E2EEnvironment, E2ETestCase

class TestMyWorkflow(E2ETestCase):
    """测试完整工作流"""

    async def test_complete_workflow(self, e2e_env: E2EEnvironment):
        """测试从spec到完成的完整流程"""
        # 1. 创建spec
        await e2e_env.create_spec(
            slug="test-spec",
            title="测试规格",
            summary="测试规格描述"
        )

        # 2. 创建任务
        await e2e_env.create_tasks(
            spec_slug="test-spec",
            tasks=[...]
        )

        # 3. 创建并执行run
        run = await e2e_env.create_run(...)
        result = await e2e_env.wait_for_run_completion(run["run_id"])

        # 4. 验证结果
        assert result["status"] == "success"
```

**E2E测试最佳实践**:
- 测试真实用户场景
- 不mock任何外部依赖
- 每个测试独立运行
- 清晰的业务价值
- 详细的错误信息

### 4. 性能测试 (Performance Tests)
**位置**: `tests/performance/`

**目的**: 验证系统在负载下的表现

**运行**:
```bash
pytest tests/performance/ -v
```

### 5. 安全测试 (Security Tests)
**位置**: `tests/security/`

**目的**: 验证系统的安全性

**运行**:
```bash
pytest tests/security/ -v
```

## 完成标准检查系统

### 使用Completion Checker

**CLI使用**:
```bash
# 运行所有完成标准检查
python3 -m autoflow.quality.completion_checker

# 指定项目目录
python3 -m autoflow.quality.completion_checker /path/to/project

# 在Python中使用
import asyncio
from autoflow.quality import CompletionChecker

async def check_completion():
    checker = CompletionChecker("/path/to/project")
    result = await checker.check_all(task_id="T1")
    print(checker.generate_report())
    await checker.save_report("report.json")

asyncio.run(check_completion())
```

**完成标准类型**:
1. **unit_tests**: 单元测试通过
2. **integration_tests**: 集成测试通过
3. **e2e_tests**: E2E测试通过
4. **performance**: 性能基准达标
5. **security**: 安全检查通过
6. **documentation**: 文档完整
7. **code_quality**: 代码质量达标
8. **user_acceptance**: 用户验收标准满足

**集成到CI/CD**:
```yaml
# .github/workflows/test.yml
name: Quality Checks

on: [push, pull_request]

jobs:
  completion-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.14'
      - name: Install dependencies
        run: |
          pip install -e .
      - name: Run completion checks
        run: |
          python3 -m autoflow.quality.completion_checker
```

## 测试环境设置

### 本地开发环境
```bash
# 安装测试依赖
pip install -e ".[test]"

# 运行快速测试（单元测试）
pytest tests/unit/ -v

# 运行完整测试套件
pytest tests/ -v
```

### CI环境
```yaml
# GitHub Actions示例
jobs:
  test:
    strategy:
      matrix:
        python-version: [3.12, 3.13, 3.14]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v2
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install dependencies
        run: |
          pip install -e ".[test]"
      - name: Run tests
        run: |
          pytest tests/ -v --cov=autoflow --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

## 测试覆盖率

### 查看覆盖率
```bash
# 生成覆盖率报告
pytest --cov=autoflow --cov-report=html

# 在浏览器中查看
open htmlcov/index.html

# 终端输出
pytest --cov=autoflow --cov-report=term-missing
```

### 覆盖率目标
- **整体覆盖率**: ≥ 70%
- **核心模块覆盖率**: ≥ 80%
- **分支覆盖率**: ≥ 60%

## Mock使用原则

### 允许使用Mock的场景
1. **外部服务**: 云API、第三方服务
2. **不可控资源**: 随机数、时间（需要固定）
3. **性能隔离**: 避免网络延迟影响单元测试速度

### 禁止使用Mock的场景
1. **数据库**: 使用测试数据库
2. **文件系统**: 使用临时目录
3. **内部组件**: 测试真实交互

### Mock使用率目标
- 单元测试: < 40%
- 集成测试: < 20%
- E2E测试: 0%

## 测试最佳实践

### 1. 测试命名
```python
# 好的测试名称
def test_user_login_with_valid_credentials_succeeds():
    """清楚描述测试场景和预期结果"""
    pass

# 避免模糊的名称
def test_login():
    """不明确测试了什么"""
    pass
```

### 2. 测试结构（AAA模式）
```python
def test_calculate_total():
    # Arrange（准备）
    cart = ShoppingCart()
    cart.add_item(Item(price=100))

    # Act（执行）
    total = cart.calculate_total()

    # Assert（断言）
    assert total == 100
```

### 3. 测试隔离
```python
# 每个测试应该独立运行
@pytest.fixture
async def clean_state():
    """每个测试都有干净的状态"""
    state = StateManager()
    await state.initialize()
    yield state
    await state.cleanup()  # 自动清理
```

### 4. 异步测试
```python
# 使用pytest-asyncio
@pytest.mark.asyncio
async def test_async_operation():
    """测试异步操作"""
    result = await async_function()
    assert result is not None
```

### 5. 参数化测试
```python
# 使用参数化减少重复代码
@pytest.mark.parametrize("input,expected", [
    (1, 2),
    (2, 4),
    (3, 6),
])
def test_multiply_by_two(input, expected):
    assert multiply_by_two(input) == expected
```

## 调试测试

### 查看详细输出
```bash
# 打印print输出
pytest tests/ -v -s

# 只显示失败的测试
pytest tests/ -v --tb=short

# 显示完整的traceback
pytest tests/ -v --tb=long
```

### 调试特定测试
```bash
# 在第一个失败时停止
pytest tests/ -v -x

# 进入调试器
pytest tests/ -v --pdb

# 只运行失败的测试
pytest tests/ -v --lf
```

### 性能分析
```bash
# 查看最慢的10个测试
pytest tests/ --durations=10

# 分析测试性能
pytest tests/ -v --profile
```

## 持续改进

### 定期审查
- 每周审查测试覆盖率
- 每月审查测试质量
- 每季度审查测试策略

### 指标追踪
- 测试通过率（目标 > 95%）
- 测试执行时间
- Mock使用率
- 缺陷逃逸率

### 反馈循环
- 分析测试失败原因
- 识别常见问题模式
- 更新测试策略
- 分享最佳实践

## 常见问题

### Q: 测试运行太慢怎么办？
A:
1. 确保单元测试快速运行（< 5分钟）
2. 将慢速测试移到集成/E2E测试
3. 使用并行测试执行
4. 考虑使用test fixtures优化

### Q: 如何测试异步代码？
A: 使用pytest-asyncio:
```python
@pytest.mark.asyncio
async def test_async_function():
    result = await async_func()
    assert result is not None
```

### Q: 如何处理需要认证的测试？
A: 使用测试账户或mock认证服务：
```python
@pytest.fixture
def auth_client():
    return AuthClient(test_mode=True)

async def test_authenticated_request(auth_client):
    response = await auth_client.get("/protected")
    assert response.status_code == 200
```

### Q: 测试数据库如何管理？
A: 使用pytest fixtures管理测试数据库：
```python
@pytest.fixture
async def test_db():
    db = create_test_db()
    yield db
    drop_test_db(db)
```

## 参考资源

- [Pytest文档](https://docs.pytest.org/)
- [pytest-asyncio文档](https://pytest-asyncio.readthedocs.io/)
- [测试最佳实践](https://docs.python-guide.org/writing/tests/)
