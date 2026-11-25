# 原生工程编辑会话

`opentrack_start_native_editor` 使用所选 `.run` 的完整源目录清单和 SHA-256，初始修订另存到
独立 `session_directory`。源内未被该运行文件使用的成员仍保存在原目录。支持已排班工程，也支持
已有站场或车辆且车次及时刻表为空的工程。会话中的原生项目可作为现行几何、进路与运营写入工具的输入。

1. 读取 `opentrack_read_native_editor` 的 `current_project`、`revision` 与
   `event_sha256`。使用当前项目的运行文件、原生目录及图档调用写入工具，另存审定增量。
2. 用 `opentrack_edit_native_editor`，提交 `action: stage`、`expected_revision`、
   `expected_event_sha256` 与按 SHA-256 绑定的 `bundle_manifests`。一次可纳入同一
   快照上的几何、进路、目录及运营增量。每个成员在同一次提交只有一个替换件。
3. 用 `action: undo` 或 `redo` 重新选择已有修订。已选档案会独立核对散列。撤销后再次编辑
   会更新当前分支，原先已保存的快照仍可由编号发布。
4. 用 `opentrack_publish_native_editor` 选当前或具体 `snapshot_revision`，发布到新的
   `target_directory`。各修订的 `.run` 和跨图档引用根据实际目标目录重定位。

默认预览后用 `preview_only: false` 保存。保存使用 NTFS 的不覆盖目录发布，事件和同一修订的
全部原生文件一起提交。两个编辑者向同一修订提交时，先成功发布的事件占用该修订，另一提交须重新
读取当前状态。此处撤销重做的对象是 Skill 保存的原生文件快照。
