"""使用标准库 unittest 验证输入校验、文件导出和命令行行为。"""

import csv
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from travel_summary import TripInputError, generate_summary, load_trip, parse_trip


PROJECT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_DIR / "travel_summary.py"
CSV_COLUMNS = ["目的地", "出发日期", "预算", "币种", "景点序号", "景点名称", "价格说明"]


def trip_data(**changes):
    """每次返回独立的输入，避免一个测试影响另一个测试。"""
    data = {
        "destination": "杭州",
        "departure_date": "2027-05-01",
        "budget": "1500.00",
        "attractions": ["西湖", "浙江省博物馆", "京杭大运河"],
    }
    data.update(changes)
    return data


class InputTests(unittest.TestCase):
    def test_valid_input_and_default_currency(self):
        trip = parse_trip(trip_data())
        self.assertEqual(trip.destination, "杭州")
        self.assertEqual(trip.departure_date, date(2027, 5, 1))
        self.assertEqual(trip.budget, Decimal("1500.00"))
        self.assertEqual(trip.currency, "CNY")
        self.assertEqual(trip.attractions, ["西湖", "浙江省博物馆", "京杭大运河"])

    def test_text_is_trimmed_and_attraction_order_is_preserved(self):
        trip = parse_trip(trip_data(destination=" 杭州 ", attractions=[" 西湖 ", " 运河 "]))
        self.assertEqual(trip.destination, "杭州")
        self.assertEqual(trip.attractions, ["西湖", "运河"])

    def test_empty_attractions_and_zero_budget_are_valid(self):
        trip = parse_trip(trip_data(attractions=[], budget=0))
        self.assertEqual(trip.attractions, [])
        self.assertEqual(trip.budget, Decimal("0"))

    def test_money_accepts_numeric_values_and_extra_trailing_zeros(self):
        for budget in (1500, Decimal("0.10"), "1500.000", " 12.50 "):
            with self.subTest(budget=budget):
                self.assertEqual(parse_trip(trip_data(budget=budget)).budget, Decimal(str(budget)))

    def test_optional_currency_is_preserved(self):
        self.assertEqual(parse_trip(trip_data(currency="USD")).currency, "USD")

    def test_each_required_field_is_checked(self):
        for field in ("destination", "departure_date", "budget", "attractions"):
            with self.subTest(field=field):
                data = trip_data()
                del data[field]
                with self.assertRaises(TripInputError):
                    parse_trip(data)

    def test_unknown_fields_are_rejected_instead_of_silently_ignored(self):
        with self.assertRaises(TripInputError):
            parse_trip(trip_data(price=50))

    def test_invalid_root_types_are_rejected(self):
        for data in (None, [], "杭州", 1):
            with self.subTest(data=data):
                with self.assertRaises(TripInputError):
                    parse_trip(data)

    def test_invalid_destinations_are_rejected(self):
        for destination in (None, 123, "", "  ", "杭\n州", "杭\t州", "杭\x00州"):
            with self.subTest(destination=destination):
                with self.assertRaises(TripInputError):
                    parse_trip(trip_data(destination=destination))

    def test_dates_must_be_real_dates_in_exact_iso_format(self):
        invalid_dates = (
            "2027-02-29", "2027-13-01", "2027-2-01", "20270501",
            "2027-W17-6", "2027/05/01", "2027-05-01T10:00:00", None, 20270501,
        )
        for departure_date in invalid_dates:
            with self.subTest(departure_date=departure_date):
                with self.assertRaises(TripInputError):
                    parse_trip(trip_data(departure_date=departure_date))
        self.assertEqual(parse_trip(trip_data(departure_date="2028-02-29")).departure_date,
                         date(2028, 2, 29))

    def test_invalid_budgets_are_rejected_without_rounding_or_inventing_values(self):
        invalid_budgets = (
            -1, "-0.01", "12.345", True, False, None, "", "很多", [], {},
            "NaN", "Infinity", "-Infinity", Decimal("NaN"), Decimal("Infinity"),
        )
        for budget in invalid_budgets:
            with self.subTest(budget=budget):
                with self.assertRaises(TripInputError):
                    parse_trip(trip_data(budget=budget))

    def test_attractions_must_be_a_list_of_nonempty_plain_text(self):
        for attractions in (None, "西湖", {}, [123], [""], ["  "], ["西\n湖"]):
            with self.subTest(attractions=attractions):
                with self.assertRaises(TripInputError):
                    parse_trip(trip_data(attractions=attractions))

    def test_currency_must_be_three_uppercase_letters(self):
        for currency in (None, "", "cny", "人民币", "US", "USDD", 123):
            with self.subTest(currency=currency):
                with self.assertRaises(TripInputError):
                    parse_trip(trip_data(currency=currency))

    def test_loads_utf8_bom_and_preserves_decimal_precision(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "旅行.json"
            content = json.dumps(trip_data(budget=0.1), ensure_ascii=False)
            path.write_text(content, encoding="utf-8-sig")
            self.assertEqual(load_trip(path).budget, Decimal("0.1"))

    def test_malformed_json_and_wrong_encoding_have_friendly_input_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            for content in (b'{"destination":', b'\xff\xfe\x00'):
                with self.subTest(content=content):
                    path.write_bytes(content)
                    with self.assertRaises(TripInputError):
                        load_trip(path)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.input_path = self.root / "trip.json"
        self.output_dir = self.root / "结果" / "旅行摘要"

    def write_input(self, **changes):
        self.input_path.write_text(json.dumps(trip_data(**changes), ensure_ascii=False),
                                   encoding="utf-8")

    def read_csv(self, path):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            self.assertEqual(reader.fieldnames, CSV_COLUMNS)
            return list(reader)

    def test_generates_both_formats_with_user_data_and_no_price_estimates(self):
        self.write_input()
        csv_path, markdown_path = generate_summary(self.input_path, self.output_dir)
        self.assertEqual(csv_path, self.output_dir / "itinerary.csv")
        self.assertEqual(markdown_path, self.output_dir / "itinerary.md")
        self.assertTrue(csv_path.read_bytes().startswith(b"\xef\xbb\xbf"))
        rows = self.read_csv(csv_path)
        self.assertEqual([row["景点名称"] for row in rows], ["西湖", "浙江省博物馆", "京杭大运河"])
        self.assertEqual([row["景点序号"] for row in rows], ["1", "2", "3"])
        for row in rows:
            self.assertEqual(row["目的地"], "杭州")
            self.assertEqual(row["出发日期"], "2027-05-01")
            self.assertEqual(row["预算"], "1500.00")
            self.assertEqual(row["币种"], "CNY")
            self.assertIn("未提供", row["价格说明"])
            self.assertIn("核实", row["价格说明"])
        markdown = markdown_path.read_text(encoding="utf-8")
        for value in ("杭州", "2027-05-01", "1500.00", "CNY", "预算", "价格", "核实"):
            self.assertIn(value, markdown)
        self.assertLess(markdown.index("西湖"), markdown.index("浙江省博物馆"))
        self.assertLess(markdown.index("浙江省博物馆"), markdown.index("京杭大运河"))

    def test_empty_attractions_keep_trip_information_in_both_formats(self):
        self.write_input(attractions=[])
        csv_path, markdown_path = generate_summary(self.input_path, self.output_dir)
        rows = self.read_csv(csv_path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["目的地"], "杭州")
        self.assertEqual(rows[0]["预算"], "1500.00")
        self.assertEqual(rows[0]["景点序号"], "")
        self.assertEqual(rows[0]["景点名称"], "")
        self.assertIn("尚未填写景点", markdown_path.read_text(encoding="utf-8"))

    def test_csv_quotes_commas_and_double_quotes_without_losing_chinese_text(self):
        name = '博物馆, "特别展"'
        self.write_input(destination='杭州, "中国"', attractions=[name])
        csv_path, _ = generate_summary(self.input_path, self.output_dir)
        row = self.read_csv(csv_path)[0]
        self.assertEqual(row["目的地"], '杭州, "中国"')
        self.assertEqual(row["景点名称"], name)

    def test_csv_text_cannot_start_a_spreadsheet_formula(self):
        self.write_input(destination="=1+1", attractions=[" +1+1", "-1+1", "@SUM(1,2)"])
        csv_path, _ = generate_summary(self.input_path, self.output_dir)
        rows = self.read_csv(csv_path)
        self.assertEqual(rows[0]["目的地"], "'=1+1")
        self.assertEqual([row["景点名称"] for row in rows],
                         ["'+1+1", "'-1+1", "'@SUM(1,2)"])

    def test_markdown_escapes_html_and_link_syntax(self):
        self.write_input(destination="<script>alert(1)</script>",
                         attractions=["[景点](https://example.com)", "*特别展*"])
        _, markdown_path = generate_summary(self.input_path, self.output_dir)
        markdown = markdown_path.read_text(encoding="utf-8")
        self.assertNotIn("<script>", markdown)
        self.assertIn("&lt;script&gt;", markdown)
        self.assertNotIn("[景点](https://example.com)", markdown)
        self.assertIn(r"\[景点\]", markdown)
        self.assertIn(r"\*特别展\*", markdown)

    def test_existing_either_output_is_preserved_and_no_other_output_is_created(self):
        self.write_input()
        self.output_dir.mkdir(parents=True)
        for filename, other in (("itinerary.csv", "itinerary.md"),
                                ("itinerary.md", "itinerary.csv")):
            with self.subTest(filename=filename):
                existing = self.output_dir / filename
                existing.write_text("用户已有内容", encoding="utf-8")
                with self.assertRaises(FileExistsError):
                    generate_summary(self.input_path, self.output_dir)
                self.assertEqual(existing.read_text(encoding="utf-8"), "用户已有内容")
                self.assertFalse((self.output_dir / other).exists())
                existing.unlink()

    def test_invalid_input_produces_no_summary_files(self):
        self.write_input(budget="未知")
        with self.assertRaises(TripInputError):
            generate_summary(self.input_path, self.output_dir)
        self.assertFalse((self.output_dir / "itinerary.csv").exists())
        self.assertFalse((self.output_dir / "itinerary.md").exists())

    def test_unpaired_unicode_surrogates_are_rejected_before_export(self):
        for changes in ({"destination": "\ud800"}, {"attractions": ["\ud800"]}):
            with self.subTest(field=next(iter(changes))):
                data = trip_data(**changes)
                with self.assertRaises(TripInputError):
                    parse_trip(data)
                # JSON 转义可保留非法代理字符，供读取及校验步骤检查。
                self.input_path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(TripInputError):
                    generate_summary(self.input_path, self.output_dir)
                self.assertFalse((self.output_dir / "itinerary.csv").exists())
                self.assertFalse((self.output_dir / "itinerary.md").exists())


class CommandLineTests(unittest.TestCase):
    def run_cli(self, *arguments):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, arguments)],
                              cwd=PROJECT_DIR, capture_output=True, text=True,
                              encoding="utf-8", check=False)

    def test_cli_success_creates_files(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "trip.json"
            output_dir = Path(directory) / "output"
            input_path.write_text(json.dumps(trip_data(), ensure_ascii=False), encoding="utf-8")
            result = self.run_cli(input_path, "--output-dir", output_dir)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((output_dir / "itinerary.csv").is_file())
            self.assertTrue((output_dir / "itinerary.md").is_file())

    def test_cli_bad_input_and_missing_file_return_friendly_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "trip.json"
            input_path.write_text("{", encoding="utf-8")
            for path in (input_path, Path(directory) / "missing.json"):
                with self.subTest(path=path):
                    result = self.run_cli(path, "--output-dir", Path(directory) / "output")
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("错误", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)

    def test_extreme_json_numbers_have_friendly_errors_without_output(self):
        cases = (
            ("large_exponent", "1e9999999999999999999"),
            ("long_integer", "1" * 4301),
        )
        with tempfile.TemporaryDirectory() as directory:
            for name, number in cases:
                with self.subTest(case=name):
                    input_path = Path(directory) / (name + ".json")
                    output_dir = Path(directory) / name
                    content = json.dumps(trip_data()).replace('"1500.00"', number)
                    input_path.write_text(content, encoding="utf-8")
                    with self.assertRaises(TripInputError):
                        load_trip(input_path)
                    result = self.run_cli(input_path, "--output-dir", output_dir)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("错误", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertFalse((output_dir / "itinerary.csv").exists())
                    self.assertFalse((output_dir / "itinerary.md").exists())

    def test_cli_missing_arguments_show_usage(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage:", result.stderr)


if __name__ == "__main__":
    unittest.main()
