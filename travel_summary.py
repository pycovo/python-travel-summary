"""读取本地 JSON，将用户填写的旅行信息整理为 CSV 和 Markdown。"""

import argparse
import csv
import html
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path


PRICE_NOTE = "未提供价格及来源，待自行核实"
CSV_FIELDS = ["目的地", "出发日期", "预算", "币种", "景点序号", "景点名称", "价格说明"]


class TripInputError(ValueError):
    """输入内容不符合要求；命令行会把它显示为可读的中文提示。"""


@dataclass
class Trip:
    """校验后的旅行数据；预算只代表用户设定的金额。"""

    destination: str
    departure_date: date
    budget: Decimal
    attractions: list[str]
    currency: str = "CNY"


def _read_text(value: object, field: str) -> str:
    """统一检查文本，让每个字段都遵循相同规则。"""
    if not isinstance(value, str) or not value.strip():
        raise TripInputError(f"{field} 必须是非空文本。")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise TripInputError(f"{field} 不能包含换行、制表符等控制字符。")
    try:
        value.encode("utf-8")
    except UnicodeError as error:
        raise TripInputError(f"{field} 包含无法保存为 UTF-8 的无效字符。") from error
    return value.strip()


def _read_budget(value: object) -> Decimal:
    """用 Decimal 处理金额，避免浮点数的小数误差。"""
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise TripInputError("budget 必须是非负金额，例如字符串 \"1500.00\"。")
    try:
        amount = Decimal(str(value).strip())
        if not amount.is_finite() or amount < 0:
            raise TripInputError("budget 必须是有限的非负金额。")
        rounded = amount.quantize(Decimal("0.01"))
        if rounded != amount:
            raise TripInputError("budget 最多保留两位小数，不会自动舍入。")
    except InvalidOperation as error:
        raise TripInputError("budget 不是有效金额，或金额过大。") from error
    return rounded.copy_abs()  # 将 -0.00 统一显示为 0.00。


def parse_trip(data: object) -> Trip:
    """先校验所有输入，再创建数据对象，避免把错误带到导出步骤。"""
    if not isinstance(data, dict):
        raise TripInputError("JSON 最外层必须是对象（使用花括号）。")
    required = {"destination", "departure_date", "budget", "attractions"}
    missing = required - data.keys()
    if missing:
        raise TripInputError("缺少必填字段：" + ", ".join(sorted(missing)))
    unknown = data.keys() - required - {"currency"}
    if unknown:
        raise TripInputError("未知字段：" + ", ".join(sorted(map(str, unknown))))

    destination = _read_text(data["destination"], "destination")
    date_text = _read_text(data["departure_date"], "departure_date")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_text):
        raise TripInputError("departure_date 必须使用 YYYY-MM-DD 格式。")
    try:
        departure_date = date.fromisoformat(date_text)
    except ValueError as error:
        raise TripInputError("departure_date 必须是有效日期，例如 2027-05-01。") from error

    budget = _read_budget(data["budget"])
    currency = _read_text(data.get("currency", "CNY"), "currency")
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise TripInputError("currency 必须是三位大写字母，例如 CNY；不进行汇率换算。")
    if not isinstance(data["attractions"], list):
        raise TripInputError("attractions 必须是景点文本列表，也可以是空列表 []。")
    attractions = [
        _read_text(name, f"attractions 第 {index} 项")
        for index, name in enumerate(data["attractions"], start=1)
    ]
    return Trip(destination, departure_date, budget, attractions, currency)


def load_trip(path: Path) -> Trip:
    """兼容普通 UTF-8 和带 BOM 的 JSON 文件。"""
    try:
        with Path(path).open(encoding="utf-8-sig") as file:
            # JSON 小数直接读成 Decimal，避免先经过二进制浮点数。
            data = json.load(file, parse_float=Decimal)
    except json.JSONDecodeError as error:
        raise TripInputError(
            f"JSON 格式错误：第 {error.lineno} 行，第 {error.colno} 列。"
        ) from error
    except UnicodeError as error:
        raise TripInputError("输入文件必须使用 UTF-8 编码保存。") from error
    except (ValueError, InvalidOperation) as error:
        raise TripInputError("JSON 中的数字超出可处理范围，请检查金额。") from error
    return parse_trip(data)


def _csv_text(value: str) -> str:
    """避免用户文本被电子表格当作公式执行。"""
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def write_csv(trip: Trip, path: Path) -> None:
    """每个景点占一行；空清单也保留旅行基础信息。"""
    with Path(path).open("x", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(CSV_FIELDS)
        names = trip.attractions or [""]
        for index, name in enumerate(names, start=1):
            writer.writerow([
                _csv_text(trip.destination),
                trip.departure_date.isoformat(),
                f"{trip.budget:.2f}",
                trip.currency,
                index if trip.attractions else "",
                _csv_text(name),
                PRICE_NOTE,
            ])


def _markdown_text(value: str) -> str:
    """把输入作为普通文本展示，保留字符本身而不执行 HTML 或 Markdown。"""
    value = html.escape(value, quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", value)


def write_markdown(trip: Trip, path: Path) -> None:
    """用简单的标题和列表生成可直接阅读的摘要。"""
    lines = [
        "# 行程摘要",
        "",
        f"- 目的地：{_markdown_text(trip.destination)}",
        f"- 出发日期：{trip.departure_date.isoformat()}",
        f"- 用户设定预算：{trip.budget:.2f} {trip.currency}",
        f"- 景点数量：{len(trip.attractions)}",
        "",
        "## 景点清单",
        "",
    ]
    if trip.attractions:
        lines.extend(
            f"{index}. {_markdown_text(name)}"
            for index, name in enumerate(trip.attractions, start=1)
        )
    else:
        lines.append("尚未填写景点。")
    lines.extend([
        "",
        "## 数据说明",
        "",
        "- 数据来源：用户填写的本地 JSON 文件。",
        f"- 价格：{PRICE_NOTE}。",
        "- 预算是用户设定的计划金额，不是报价；未估算总花费或预算余额。",
        "- 景点按输入顺序展示；未核实营业信息，未规划路线或分配游览日期。",
        "- 本工具离线运行，不调用 API，不进行预订或付款。",
        "",
    ])
    with Path(path).open("x", encoding="utf-8") as file:
        file.write("\n".join(lines))


def generate_summary(input_path: Path, output_dir: Path) -> tuple[Path, Path]:
    """先完成校验和文件检查，再创建目录并导出两种格式。"""
    trip = load_trip(input_path)
    output_dir = Path(output_dir)
    csv_path = output_dir / "itinerary.csv"
    markdown_path = output_dir / "itinerary.md"
    for path in (csv_path, markdown_path):
        if path.exists() or path.is_symlink():
            raise FileExistsError(f"输出已存在：{path}。请换一个 --output-dir。")
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(trip, csv_path)
    write_markdown(trip, markdown_path)
    return csv_path, markdown_path


def main(argv: list[str] | None = None) -> int:
    """命令行入口；返回状态码，方便终端和测试判断结果。"""
    parser = argparse.ArgumentParser(description="离线整理旅行信息，生成 CSV 和 Markdown 摘要。")
    parser.add_argument("input", type=Path, help="用户填写的 UTF-8 JSON 文件")
    parser.add_argument("--output-dir", type=Path, default=Path("output"), help="输出目录（默认：output）")
    args = parser.parse_args(argv)
    try:
        csv_path, markdown_path = generate_summary(args.input, args.output_dir)
    except (TripInputError, OSError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 1
    print(f"已生成 CSV：{csv_path}")
    print(f"已生成 Markdown：{markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
