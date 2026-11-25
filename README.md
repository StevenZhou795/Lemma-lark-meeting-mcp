# Lark 会议任务导入

当前状态（2026-11-25）：按用户新规则补填 Project、支持多人 Owner，并明确采用 sitter → Zita。累计新增 28 条任务；原 13 条已使用 batchUpdate 按真实记录 ID 覆盖并全部回读确认，本次覆盖没有新增记录，线上全表仍为 59 条。28 条任务的 Project/Owner 均已核对。另有 5 项待业务定案或语义合并、2 项排除。详见 `revision-status.local.md`、`receipt-project-owner-revision.local.json` 和 `overwrite-13-receipt.local.json`；本地报告不提交到版本控制。历史会议日期不明，未据当前日期推算截止日。`payload-overwrite-ready.local.json` 已应用，不应再次提交。

用户提供的 `C:/Users/stevenzhou/Downloads/.codex-plugin` 只有 `plugin.json`，相邻 `.app.json` 只有应用标识。它们不是 MCP 服务端源码，修改清单无法增加 Base 工具。已连接的两个 Lark MCP 只有知识文档能力，没有本次所需的 Base 字段/记录读写接口。

方案复用 [Lark 官方 OpenAPI MCP](https://github.com/larksuite/lark-openapi-mcp)，不自行维护另一套鉴权和 Lark API 服务。独立命名为 `lark_meeting_tasks`，不替换现有知识库 MCP。

## 文件

| 文件 | 用途 |
|---|---|
| `start.ps1` | 启动固定版本 0.5.1 的官方 MCP；开放字段读取、记录读取/新增/批量更新及按企业邮箱解析人员 |
| `configure.ps1` | 用户在本机输入应用配置，使用 Windows 用户绑定的 DPAPI 加密保存 Secret |
| `codex-mcp.toml` | Codex 配置片段，合并使用 |
| `mcp.example.json` | 使用 JSON MCP 配置的客户端示例 |
| `target.json` | 用户指定表的 Base、table 和 view 标识 |
| `task-drafts.json` | 四份 txt 的任务候选、证据和待确认项；不等于可直接写入的任务 |
| `mapping.example.json` | 真实字段、人员及 Priority 标签映射模板 |
| `prepare-import.py` | 只在本地生成 batchCreate 参数，检查映射与精确重复 |
| `WORKFLOW.md` | 提取、语义查重、写入及结果回读流程 |

## 连接：由用户操作

前提：Windows、Node.js 20+、npx，以及可对目标 Base 读写的 Lark 国际版应用/账号。配置和授权请在本机完成，不要把 App Secret 或 Token 发到聊天里。

1. 在 Lark 国际版开发者后台为应用启用字段读取、记录查询、新增记录的权限；若需要通过企业邮箱解析人员，再启用对应用户 ID 查询权限。按后台要求发布/审批。用户账号同时须有目标表权限。若沿用原应用，需原应用管理员授权，不能只改插件描述。
2. 使用 OAuth 时，按官方文档在应用后台配置回调 `http://localhost:3000/callback`。下一步运行 configure.ps1，在本机输入应用信息；Secret 隐藏输入，保存为当前 Windows 用户和电脑绑定的加密凭据文件，已从版本控制排除。也可自行设置 APP_ID/APP_SECRET 环境变量。请勿发送或提交凭据文件。
3. 在用户自己的 PowerShell 执行：

   ```powershell
   Set-Location -LiteralPath 'J:\Vismed\Lemma-Website\testing\lark-meeting-mcp'
   .\configure.ps1
   .\start.ps1 -Mode login
   ```

   configure.ps1 仅保存本机配置，不联网。start.ps1 -Mode login 会从 npm 获取官方包、联系 Lark、打开授权页面并保存用户会话；不创建 Base 记录，不发送消息。按应用配置的权限审阅授权页面。若 PowerShell 提示脚本执行被策略阻止，请提供去除个人信息的错误文字，不修改系统安全策略。

4. 将 `codex-mcp.toml` 的独立段落合并到 Codex MCP 配置中，保留其他段落，重启客户端。标准 JSON MCP 客户端使用 `mcp.example.json` 并确保继承上述环境变量。不要将本地 stdio JSON 直接作为远程 HTTP 连接地址。
5. 让客户端列出 `lark_meeting_tasks` 工具。应包含 `bitable.v1.appTableField.list` 与 `bitable.v1.appTableRecord.batchCreate` 的对应工具。名字可能被客户端规范化，以实际 tools/list 为准。配置存在不代表连接成功；未出现在工具列表时，分享去除凭据的报错。

Codex 可使用全局或受信任项目的 `.codex/config.toml`；见 [官方 MCP 配置说明](https://learn.chatgpt.com/docs/extend/mcp)。本目录只准备配置片段，没有改动全局配置，没有启动服务。

## 第一组检查：只读

若启动时报 `Import-Clixml` 的 FormatException，表示本机凭据文件未能反序列化，不能据此判断 App Secret 是否正确。使用同一 Windows 账号、同一 PowerShell 执行 `./configure.ps1 -Replace`，在本机重新输入。脚本会先生成并读回新文件，再备份旧文件、替换配置；不访问 Lark。之后执行 `./start.ps1 -Mode login`。不要分享 `.clixml`、`.bak` 或 `.new` 凭据文件。

连接后先请助手按 `WORKFLOW.md` 执行：

- 读取 `target.json` 指定表的所有字段及标签选项，确认 Task/Owner/Priority/Deadline 的真实类型。只读，不新增字段。
- 分页读取全表，查找已存在的相同或相近任务，并匹配人员。不只查用户链接中的 view，以免漏掉被过滤的记录。只读，不发送消息。
- 列出匹配失败的负责人，以及推断 Priority 的映射。Deadline 无明确日期就留空。历史会议不能以当天推算“明天”。

预期结果是完整的字段及记录快照。403/权限错误应先处理应用和表权限；空结果不代表一定没有任务；has_more=true 表示不能停止翻页。不要把响应头或授权信息贴到聊天。

本地快照包装格式：

```json
{
  "app_token": "FLnbbaiBpaJwxWsi8yXlFpb3gyb",
  "table_id": "tblSGzNtCWry40ma",
  "complete": true,
  "fields": []
}
```

`schema.json` 的 fields 填所有字段。`existing-records.json` 使用同样的目标标识与 complete，改用 records 数组，每项为 `{ "record_id": "...", "fields": { ... } }`。只有实际已收齐所有分页，才可标记 complete=true。

## 准备本地写入参数

Python 3.10+，无需额外依赖。将 mapping.example.json 另存为 mapping.local.json，按 WORKFLOW.md 填真实映射与所选任务 ID。四份会议均纳入候选；只导入确认是行动、人员映射明确且查重后未存在的任务。

```powershell
Set-Location -LiteralPath 'J:\Vismed\Lemma-Website\testing\lark-meeting-mcp'
python .\prepare-import.py --mapping .\mapping.local.json --schema .\schema.json --existing .\existing-records.json --output .\payload.json
```

这条命令只读本地文件、创建一个新的 payload.json，不联网、不发消息、不写 Base。预期显示可写入/重复/待处理数量。文件已存在时会拒绝覆盖，应改用新的输出文件名。blocked 项包含未映射人员、标签、未确定的提议或同名冲突，不会被自动塞入 records。

Start date 本次保持 omit。以后新任务把 start_date_policy 设为 processing_day，并在 fields 里映射 start_date，使用处理当天的 UTC+08:00 日期；不会重置已存在任务的日期。Deadline 仍独立从会议内容解析。

## 真正写入与回读

用户已经要求直接填写该表，明确可映射的内容无需再次重复确认。助手在实际连接可用时先刷新完整查重数据，合并语义重复项，再使用官方 batchCreate 提交 payload 的 body.records。每批最多100条。目标表若有自动化或人员通知，新增可能触发既有规则；本工具不另发聊天消息。

写入是线上数据变更。返回成功后保存 record_id，并使用 batchGet 回读确认内容、人员、标签、日期。超时或返回不确定先查询，不直接重试。这个准备器只有本地精确查重，不能提供并发严格幂等保证。旧任务存在但字段不同，先说明冲突，不静默覆盖。

尚未运行任何测试、构建、lint、浏览器自动检查或脚本试运行，遵守仓库 AGENTS.md。浏览器交互尝试未能读取目标表，不是线上数据检查通过。当前所有内容仅做本地源文件阅读与实现。
