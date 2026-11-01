# JCCAutoD · 金铲铲商店助手

[![Windows checks](https://github.com/456456bot/JCCAutoD/actions/workflows/ci.yml/badge.svg)](https://github.com/456456bot/JCCAutoD/actions/workflows/ci.yml)

Windows + MuMu 模拟器上的本地商店 OCR 辅助，以及独立的阵容配置工具。
用户手动刷新商店，程序识别目标卡名并发送购买点击；不读取游戏内部 API。

当前版本：**0.1.0**。项目独立开发，与腾讯、Riot Games、MuMu 无隶属关系。

## 功能

- 动态目标列表：新增即开始关注，删除最后一项即停止，F8 清空列表。
- 小键盘 1～5 添加对应商店牌；小键盘 `+` / `-` 从右侧弈子详情读取名称并新增 / 移除。
- 根据商店“即将二星 / 三星”提示发送最后一次购买点击，再移除该目标。
- 阵容头像识别、图中星级读取、赛季切换、手工补录与逐牌追牌目标。
- 配置按赛季自动保存；商店助手通过“赛季 → 配置 → 导入配置”使用，无需选择文件路径。
- 本地 OCR / 模板匹配；触控及裁取坐标使用安卓画面坐标，独立于桌面窗口位置。

## 运行环境

- Windows，64 位 Python **3.12 或更新版本**，包含 Tkinter 和 `py` 启动器。
- MuMu Player；目前在 **v6.8.8、安卓 2048×1536、4:3 底部商店布局**上验证。
- MuMu 安装目录下应有 `nx_main/sdk/external_renderer_ipc.dll`，游戏已启动。
- 首次安装依赖、下载头像库需要联网；运行时识别在本机完成。

其他分辨率按比例换算坐标，但不同宽高比、商店样式或游戏 UI 改版可能需要重新标定。
目前交付为源码启动方式，未提供脱离 Python 环境的独立 EXE。

## 安装与启动

1. 克隆仓库或下载 ZIP 后解压到固定目录。
2. 安装 64 位 Python 3.12+，确保安装 Windows Python launcher。
3. 双击 `setup.bat`：创建 `.venv`、安装依赖并生成两个桌面快捷方式。
4. 首次打开 **金铲铲阵容配置工具**，通过“资源管理…”下载所需头像：
   - S16：**更新 S16 官方头像**，包含原 S16.5 的新增棋子。
   - 其他赛季：**补全全部赛季公开头像**。
5. 打开 **金铲铲商店助手**。启动目标为空，不会自动载入旧名单。

下载的完整头像库、运行配置和日志不随 Git 仓库分发。
本机已有头像库的用户无需重新下载。请保留项目目录及其中的 `.venv`。

备用启动入口：`商店助手.pyw` / `阵容配置工具.pyw`，或 `start.bat` / `lineup_tool.bat`。
重新安装快捷方式可运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install-shortcuts.ps1
```

### MuMu 路径与实例

默认使用 `D:\MuMuPlayer`、实例 `0`。可在启动进程的环境中指定：

```powershell
$env:JCC_MUMU_PATH = 'E:\MuMuPlayer'
$env:JCC_MUMU_INSTANCE = '0'
.\.venv\Scripts\python.exe -m jcc_assistant --gui
```

需要让桌面快捷方式长期使用这些值时，将它们设置为 Windows 用户环境变量。
可选的 `JCC_PORTRAIT_DIR` 用于更改本地头像库目录。
MuMu SDK DLL 由用户自己的模拟器安装提供，本仓库不包含 DLL。

## 创建和导入配置

1. 在配置工具中选择赛季，导入阵容图片或获取 MuMu 截图，点击“识别配置”。
2. 核对名称。头像最高相似度 **大于 60%** 即接受；相似度不是识别正确概率。
3. 工具按头像上方星标生成追牌目标：一星 → 持续购买；二星 → 二星后移除；三星 → 三星后移除。
   星标“未判定”时持续关注，也可选中棋子手动修改目标，支持多选。
4. 填写阵容名称并点击“保存阵容 JSON”，不再选择保存位置。
5. 在商店助手选择赛季、选择配置名称，点击 **导入配置**，非空列表立即生效。

例如 S16 阵容《阵容x》自动保存为：

```text
configurations/
└── S16/
    └── s16_阵容x.json
```

同赛季同名称再次保存时覆盖文件，并保留上一份有效 `.json.bak`。
文件名中的 Windows 非法字符会替换成下划线。选单显示 JSON 中的阵容名称，
而不是文件名。打开选单或点击导入时会更新文件列表；旧版平铺在配置目录下的 JSON 仍可发现。

新建配置结构见 [examples/lineup.json](examples/lineup.json)。
详细补录、星级及配置说明见 [阵容识别与头像录入](docs/阵容识别与头像录入.md)。

## 操作快捷键

| 按键 | 功能 |
| --- | --- |
| F8 | 清空全部目标，禁止后续购买点击 |
| 小键盘 1～5（Num Lock 开启） | 读取对应商店卡名并添加，沿用“手动／1～5 默认”条件 |
| 小键盘 `+` | 打开棋子右侧详情后读取名称，新增目标，默认持续关注 |
| 小键盘 `-` | 从相同详情区域读取名称，删除对应目标 |

重复添加不会创建重复项；详情 `+` 不覆盖已有目标的追牌条件。
主键盘数字、加减号不绑定。F8 注册失败时禁止启用购买，请先关闭占用热键的旧窗口。
未打开详情、名称置信度不足或请求过期时不修改列表。
主窗口及应用弹窗首次出现时居中，之后可以手动移动。

## 行为与边界

- 商店买牌 OCR 要求置信度至少 98%，与配置头像的 60% 阈值分开。
- 普通购买比较五栏 OCR 名称，相同序列不重复处理；新激活目标、升星提示独立处理。
- 不使用固定点击冷却，不统计精确数量，不做购买前后复核。
- 升星提示命中后发送末次点击并删除目标，**不代表已确认购买或合成成功**。
- 不读取实战棋盘/备战区数量，不追踪其他来源获取的棋子，不保证零多买。
- 已发送的触控不能由 F8 撤销；手动刷新和触控仍可能竞争。
- 设备/OCR/触控异常会清空列表。点击记录保存在 `artifacts/purchases/events.jsonl`。
- 公共 TFT 头像不等于金铲铲所有赛季、皮肤和特殊模式均已验证，缺失项按需补录。

## 开发与验证

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试使用独立头像夹具、去除无关玩家区域的截图和模拟设备，不连接模拟器、注册真实热键或点击游戏。
Tk 界面测试需要 Windows 桌面会话。完整下载缓存不参与测试。
固定的本机 Python 3.14 依赖快照见 `requirements-lock.txt`，跨 Python 版本以 `requirements.txt` 为准。

- [架构与识别流程](docs/architecture.md)
- [贡献说明](CONTRIBUTING.md)
- [变更记录](CHANGELOG.md)

## 许可证与素材

原创代码及文档采用 [MIT](LICENSE)。游戏图像、截图、商标、OCR 模型及第三方依赖遵循各自条款，
不属于本项目 MIT 授权范围；来源见 [第三方素材说明](THIRD_PARTY_NOTICES.md)。
