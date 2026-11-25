> Historical development/audit snapshot. The stage/version in this filename
> scopes "current", "remaining", cloud/platform blockers, integration status and
> test results below. Read the [current backend entrypoint](../README.md) and
> enclosing Skill before treating a statement as current capability or permission.
> Preserve actual function/input contracts; do not turn an old no-GUI/cloud-only
> task boundary into a general ban on authorized local work. A currently applicable
> approval rejection still governs that exact action and cannot be bypassed.

# static5 兼容性边界（静态独立审查）

本表区分“模块可发现”“可读取真实存档”“可保存”“原版运行”。本包开发不调用用户电脑或Wine。另据用户授权本地static3报告，桥接/工具发现已实测，安全档案读取仍明确拒绝；这不等于static5已在Windows重测。云端模拟平台标记不等于原生验收。

| 范围 | 已知实现与证据 | Windows 结论 |
|---|---|---|
| Python 后端/工具发现 | 注册器使用标准库、Pydantic 与惰性 native facade；未发现直接在模块顶层导入 fcntl/msvcrt 或加载 kernel32 的路径 | 静态上无该类导入即崩证据；仍需正确 Python/依赖，非实机验证 |
| 平台特有原生调用 | editor 锁按 os.name 分支导入；WinDLL 在 runtime 方法中；bundle 的 CDLL 在提交方法中 | 工具发现不等于允许或已验证这些执行路径 |
| 纯 bytes 编解码与构造器 | 核心处理 bytes，无原版进程；不代表所有文件包装器跨平台 | 跨平台设计，不宣称已完成 Windows 回归 |
| ArchiveTools 文件读取/inspect/preview | parent_fd 使用 O_DIRECTORY、O_NOFOLLOW 与 dir_fd；读取必须保持无跟随与受限目录语义 | Windows 缺少所需 POSIX FD 能力；包括新初始化和当前档案检查，不只是保存 |
| 单文件及 catalog bundle 保存 | no-overwrite/dirfd 路径保护；bundle 额外需要 Linux renameat2 | 不能把工具注册或 schema 可见说成 Windows 可保存；本轮不提供替代发布器 |
| Skill 后端选择 | 精确包内位置或显式 OTAI_ROOT，版本及关键工具检查 | 解决误接旧后端，不解决档案 FD 能力或原版兼容 |
| 中文/空格路径、UTF-8 | argv list/shell=False 可避免 shell 拆分，JSON/文本还需显式编码及实际回归 | 云端路径测试仅证明云端行为；不得写成 Windows 路径已验收 |
| OpenTrack 原版读取、仿真及日志 | 本专项不运行原版、不修改运行完成状态 | 未验收；0.30 已知样例成功不认证 0.31 |

## 初始问题与必要修订

1. 旧 ArchiveTools 在不支持平台可能暴露 AttributeError/NotImplementedError，而非清晰的平台能力错误。应在文件访问前明确拒绝，不弱化 no-follow/dirfd 保护。
2. capabilities 中 current_archive 的实现能力 true 应与本机平台可用性分开。Windows 上不能笼统显示 inspect/save 可执行；工具列表只是注册证据。
3. 桥接应在调用前给出 Python/依赖/UTF-8 配置问题；错误必须区分缺后端、错版本、缺依赖与平台文件 API 不支持。

## 已修订并静态复核

- `ArchiveTools.parent_fd` 在首次文件打开前检查 POSIX/no-follow/dir_fd 读取能力；`save_copy` 在任何源/目标 IO 前检查写入原语。缺少能力返回 `UNSUPPORTED_SECURE_FILESYSTEM`，不采用普通 open/read_bytes 替代。
- 新能力报告把历史注册功能布尔值置于 `registered_operations`，本机文件 API 能力单列；旧布尔键保留，inspect 按安全读取能力判定，混合/保存能力保守为 false，不能把该 false 误读为源码不存在实现。Windows 档案检查及文件预览明确不可用；纯内存核心另列，不因工具可发现而宣称文件读取可用。
- Linux bundle 仅标前提存在，实际可用性保持未验证，仍需要 libc renameat2 及目标文件系统语义。本专项没有调用提交或安全门测试。
桥接仅允许Python3.13.x；3.12、3.14及其他版本均提前拒绝，不作为支持范围。依赖缺失或pydantic主版本不匹配明确报错，其余依赖锁定版本差异只提示未验证。
- 所有桥接后端子进程显式 UTF-8 环境，argv list 不经 shell；依赖安装提示使用同一解释器与正确路径引号，仅输出提示，不自动安装。

本轮为云服务器上的代码审查；现有 worker 的 Python/依赖/中文空格与平台缺失测试属于云端正常/模拟检查，不是 Windows 实机运行证据。最终源码哈希与审查范围记录在 `artifacts/compatibility/independent-review.json`。

## 最新支持范围

用户明确收窄为Python3.13.x。以前版本文档与3.12报告均仅为历史；当前不承诺3.12/3.14兼容。
