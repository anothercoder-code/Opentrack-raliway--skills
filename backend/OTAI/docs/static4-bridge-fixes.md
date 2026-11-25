> Historical development/audit snapshot. The stage/version in this filename
> scopes "current", "remaining", cloud/platform blockers, integration status and
> test results below. Read the [current backend entrypoint](../README.md) and
> enclosing Skill before treating a statement as current capability or permission.
> Preserve actual function/input contracts; do not turn an old no-GUI/cloud-only
> task boundary into a general ban on authorized local work. A currently applicable
> approval rejection still governs that exact action and cannot be bypassed.

# static4：本地检查发现的桥接问题整改

## 证据分层

用户授权的Windows只读检查报告确认：static3配套版本及工具发现、中文空格常规配置和旧版本拒绝已可工作；当前档案读取实际返回 `UNSUPPORTED_SECURE_FILESYSTEM`，不是工具未知。该证据属于static3，不自动认证static4或Windows存档读取。

本地报告发现三类真实CLI问题：Python3.6在友好提示前因importlib.metadata失败；显式空 `--root=` 被发现阶段当作环境默认、实际调用却使用空值；重复root/profile导致发现取首项、实际argparse取末项。空 `--profile=` 的原发现仅为mock证据，不能写成本地CLI已复现。

## 本轮修复合同

- 脚本仅import sys后先检查Python门槛，再导入metadata等模块；非Python3.13.x退出码2，不执行后端。
- 全局root/profile只解析一次，支持 `--root value` 与 `--root=value` 两形式。
- 同名参数重复即拒绝，即使值相同；混用两种形式也拒绝。
- 显式空、全空白或缺值拒绝，不回退环境或当前目录。
- 有效CLI值优先于对应环境；未给CLI时，显式空环境变量也拒绝。后端选择OTAI_ROOT仍独立校验，错误不回退。
- 工具发现与最终调用使用同一规范化root/profile，命令之后JSON内容不被当全局参数扫描。

## 未改变

文件系统安全gate、存档读写与原版运行能力没有改变。static4仅是桥接修复，真实Windows重测需单独记录；云端模拟旧版本/参数测试不能冒充实际Python3.6或Windows验收。

## 当前Python范围

按最新用户要求，仅支持Python3.13.x。不再开展旧Python兼容工程；其他版本仅保留简单不支持提示。之前3.12测试为历史，不作为本包当前验收。真实3.13测试与解释器记录见artifacts/static4。
