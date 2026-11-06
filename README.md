# Python 旅游信息整理项目

把自己填写的目的地、出发日期、预算和景点清单整理成 CSV 与 Markdown 行程摘要。适合练习 Python 的数据类型、函数、文件读写、输入校验和单元测试。

项目只读取本地 JSON 文件，不联网，不调用付费 API，不预订、不付款。预算来自你的输入；项目不收集价格，因此会明确标记“价格未提供，待核实”，不估算旅行总花费或预算余额。景点按填写顺序列出，不自动推断路线、开放时间或每日安排。

## 1. 准备环境

需要 **Python 3.10 或更新版本**。下载或克隆项目后，在终端中进入包含本 README 和 `travel_summary.py` 的项目根目录。下面的命令均在该目录执行。

全部功能和测试都使用 Python 标准库。`requirements.txt` 中只有说明注释，无需安装第三方包。这样可以先专注 Python 基础，避免 API 密钥、依赖版本和网络设置增加学习负担。

推荐创建虚拟环境，保持项目运行环境独立。下列步骤直接使用虚拟环境中的 Python，无需激活环境。

### Windows（PowerShell）

```powershell
py -3 --version
py -3 -m venv .venv
Copy-Item examples/trip.json my_trip.json
```

用文本编辑器修改 `my_trip.json`，保存为 UTF-8，然后运行：

```powershell
.\.venv\Scripts\python.exe travel_summary.py my_trip.json --output-dir output
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

如果系统没有 `py` 命令，请使用已安装的 Python 3.10+ 对应的 `python` 命令创建虚拟环境。

### macOS / Linux

```sh
python3 --version
python3 -m venv .venv
cp examples/trip.json my_trip.json
```

用文本编辑器修改 `my_trip.json`，保存为 UTF-8，然后运行：

```sh
.venv/bin/python travel_summary.py my_trip.json --output-dir output
.venv/bin/python -m unittest discover -s tests -v
```

如果 Linux 提示缺少 `venv` 模块，需要通过系统的软件包管理器安装对应的 Python venv 组件；也可以直接使用系统的 Python 3.10+ 运行本项目。

### 不使用虚拟环境时

如果终端中的 `python` 已指向 Python 3.10+，最短运行步骤是：

```sh
python travel_summary.py examples/trip.json --output-dir output
python -m unittest discover -s tests -v
```

查看命令帮助：

```sh
python travel_summary.py --help
```

## 2. 填写输入

`examples/trip.json` 是可直接运行的示例：

```json
{
  "destination": "成都",
  "departure_date": "2027-05-01",
  "budget": "1500.00",
  "currency": "CNY",
  "attractions": [
    "四川博物院",
    "人民公园",
    "宽窄巷子"
  ]
}
```

这里的 `1500.00` 是演示用的个人计划预算，**不是任何门票、交通或住宿的报价**。景点名称仅演示清单输入，不表示已核实其开放情况。

| 字段 | 是否必填 | 规则 |
| --- | --- | --- |
| `destination` | 是 | 非空字符串，例如 `"成都"` |
| `departure_date` | 是 | 有效日期，严格使用 `YYYY-MM-DD`，例如 `"2027-05-01"` |
| `budget` | 是 | 非负、有限的金额，最多两位有效小数；推荐写成 `"1500.00"`，也接受 JSON 数字 |
| `currency` | 否 | 三位大写英文字母，省略时为 `CNY`；仅作币种标签，不做汇率转换 |
| `attractions` | 是 | 字符串列表，元素不得为空；暂未决定景点时填写 `[]` |

文本两端的空白会被去除，文本中的控制字符会被拒绝。`true`、`null`、负数、`NaN` 和 `Infinity` 都不是有效预算；`"12.345"` 也会报错，`"12.340"` 可作为 `12.34` 使用。

JSON 的键和字符串使用双引号，不允许注释或末尾多余的逗号。项目拒绝未知字段，避免拼错字段名，或误以为额外的价格数据已被处理。当前版本没有价格和价格来源字段。

使用 JSON 是因为它能直接表达字符串、数字和列表，也能让你在编辑器中反复修改同一份输入，观察导出结果如何变化。

## 3. 查看输出

运行后会生成：

```text
output/
├── itinerary.csv
└── itinerary.md
```

- **CSV**：可用电子表格软件打开。列为“目的地、出发日期、预算、币种、景点序号、景点名称、价格说明”。每个景点占一行，行内重复基本信息，便于筛选。使用带 BOM 的 UTF-8（`utf-8-sig`），方便常见电子表格软件识别中文。
- **Markdown**：可用文本编辑器或 Markdown 阅读器打开，适合阅读和保存。使用 UTF-8，展示基本信息和有序景点清单。

两个文件都只整理输入信息，明确说明价格未提供。空景点清单也可以生成摘要：CSV 保留一行基本信息，Markdown 提示“尚未填写景点”。可运行 `examples/empty_trip.json` 查看这一情况，并选择不同的输出目录：

```sh
python travel_summary.py examples/empty_trip.json --output-dir output-empty
```

如果任意目标输出文件已经存在，程序会报错并保留已有文件。请换一个 `--output-dir`，或确认不再需要后自行删除旧文件再运行。这个设计便于比较多次练习结果，也能避免不小心覆盖已整理的行程。

CSV 中可能被电子表格识别为公式的文本会增加前置单引号；Markdown 中的特殊字符和 HTML 会转义。这样，用户填写的内容可以作为文字显示。

## 4. 理解代码与测试

项目使用一个主程序文件，便于初学者按顺序阅读：

```text
travel_summary.py        # 数据模型、校验、导出和命令行入口
requirements.txt         # 无第三方依赖的说明
examples/trip.json        # 正常景点清单
examples/empty_trip.json  # 空景点清单
tests/test_travel_summary.py
```

建议按以下顺序学习：

1. `Trip` 数据类集中保存一次行程的数据，减少函数间传递零散变量。
2. `parse_trip` 校验字段和数据类型；`load_trip` 负责读取 JSON。先校验再生成，错误输入不会被当成有效行程。
3. `write_csv` 和 `write_markdown` 分别负责一种输出格式，方便单独阅读和修改。
4. `generate_summary` 组合读取和导出步骤；`main` 接收命令行参数，并将错误显示为可读信息。

预算使用标准库 `Decimal`，避免普通浮点数在十进制金额中产生不直观的精度误差。输出固定保留两位小数，只表示输入预算的展示格式。

单元测试使用标准库 `unittest`，并在临时目录中写文件。测试覆盖正常输入、错误输入、中文和特殊字符、空清单、命令行运行和已有输出保护等行为。临时文件不会改动你自己的行程文件。

## 5. 常见问题

| 现象 | 处理方法 |
| --- | --- |
| 找不到输入文件 | 检查当前目录与文件路径；路径含空格时用引号括住 |
| JSON 格式错误 | 检查双引号、逗号和括号；不要添加注释 |
| 日期或预算错误 | 按输入字段表修改，例如使用 `"2027-05-01"` 和 `"1500.00"` |
| 输出文件已经存在 | 改用新的输出目录，或自行移除确认不用的旧输出 |

成功运行返回状态码 `0`；输入或文件读写错误会在标准错误输出显示中文提示，并返回 `1`；命令行参数用法错误返回 `2`。

## 6. 在分支上练习修改

使用 Git 时，先创建自己的开发分支，再修改代码和运行测试：

```sh
git switch -c feature/my-change
python -m unittest discover -s tests -v
git add travel_summary.py tests README.md
git commit -m "Describe my change"
```

`.gitignore` 忽略 `my_trip.json`、生成的摘要、输出目录和虚拟环境，避免把个人行程与本地运行文件误提交到仓库。其他自己命名的私人输入文件也应加入 `.gitignore`。
