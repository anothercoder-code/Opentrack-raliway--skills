# 批量信号显示和按车型控制

两个写入入口使用相对数据根路径和 SHA-256 绑定实际 `.run`、全部
`.opentrack` 和 `.dest`。按工具回执预览，确认后将 `preview_only` 设为
`false` 并选择源工程之外的全新输出目录。每次保存都回读原生档案并验证
未修改的图形和运营引用。已有工程可用
`opentrack_prepare_reviewed_movement_application` 保存前态和替换件。

## 批量添加信号显示

`opentrack_append_all_route_signal_aspects` 对 `start_ends` 选择的方向起始端
执行原版附加规则。省略该项时，遍历此运行配置的所有主进路起点。每条进路保留
既有显示代码，并按起点信号的原始顺序附加它尚未保存的显示代码。跨文档续接段
沿用主段的起点控制，原来的进路 ID、保护分组和关联径路不受此操作影响。

可为显示类型 2 的起点信号提供 `metric_signal_aspects`。
每项用 `start_end` 和 `speeds_kmh` 声明 10 至 300 km/h 范围内的整数速度。
工具采用原版显示类型 2 的速度编码，在同一原生事务里把显示同时写入信号和其主进路。

## 车型性能与惰行

`opentrack_edit_train_category_signals` 另外要求绑定 `.run` 指向的 `.trains`。
操作使用原始目录中的车型类别名称，序列化时保持 TrainList 的类别顺序。

| `kind` | 字段 |
|---|---|
| `performance_category` | 每行有 `category`、`performance_percent` 和 `delay_s`。性能范围大于 0 且不超过 200%，未配置类别使用 100% 和 0 秒。 |
| `coasting` | 每行有 `category` 和 `enabled`，未配置类别默认关闭。上下速度阈值用 `lower_speed_kmh`、`upper_speed_kmh`。 |

`insert` 在无信号和仪表的普通方向端插入相应类别信号，需要名称和图面坐标。
`edit` 使用实际 `signal_id` 和 `end_id` 定位，保留未列出的类别和其他信号参数。
性能类别原生类型为 50，惰行类型为 49。写入后复核列车是否实际经过信号、
类别匹配是否生效及真实运行轨迹。
