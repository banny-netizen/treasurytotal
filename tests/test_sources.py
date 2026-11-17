"""파싱·계산 단위 테스트. 자료는 2026-11-17 실제 응답에서 옮겼다(네트워크를 쓰지 않는다)."""
import json
import sys
import unittest
import zlib
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import common  # noqa: E402
import fred  # noqa: E402
import pdftext  # noqa: E402
import src_cbank  # noqa: E402
import src_delinq  # noqa: E402
import src_fedmodel  # noqa: E402
import src_fiscal  # noqa: E402
import src_growth  # noqa: E402
import src_infl  # noqa: E402
import src_macro  # noqa: E402
import src_mm  # noqa: E402
import src_rates  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TODAY = date(2026, 11, 17)


def text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def data(name: str):
    return json.loads(text(name))


class PolicyTest(unittest.TestCase):
    def test_allowlist_blocks_unknown_host(self):
        with self.assertRaises(common.PolicyError):
            common.check_url("https://example.com/data.json")
        with self.assertRaises(common.PolicyError):
            common.check_url("http://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10")
        common.check_url("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10")


class RatesTest(unittest.TestCase):
    def test_nyfed(self):
        effr = src_rates.parse_nyfed(data("nyfed_effr.json"))
        self.assertEqual(effr["rate"][-1], ["2026-11-13", 3.88])
        self.assertEqual(effr["lo"][-1], ["2026-11-13", 3.75])
        self.assertEqual(effr["hi"][-1], ["2026-11-13", 4.0])
        sofr = src_rates.parse_nyfed(data("nyfed_sofr.json"))
        self.assertEqual(sofr["rate"][0], ["2026-11-06", 3.89])
        self.assertEqual(sofr["p75"][-1], ["2026-11-13", 3.95])
        self.assertEqual(sofr["lo"], [])

    def test_ecb(self):
        self.assertEqual(src_rates.parse_ecb(text("ecb_estr.txt"))[-1], ["2026-11-16", 2.44])
        dfr = src_rates.parse_ecb(text("ecb_dfr.txt"))
        self.assertEqual(dfr[-2:], [["2026-06-17", 2.25], ["2026-09-16", 2.5]])

    def test_boj_skips_holidays(self):
        rows = src_rates.parse_boj(data("boj_tona.json"))
        days = [row[0] for row in rows]
        self.assertEqual(rows[0], ["2026-10-01", 1.227])
        self.assertNotIn("2026-10-03", days)          # 토요일
        self.assertEqual(rows[-1], ["2026-11-13", 1.229])

    def test_ecos(self):
        rows = src_rates.parse_ecos(data("ecos_call.json"))
        self.assertEqual(rows[0], ["2026-11-02", 3.041])
        self.assertEqual(src_rates.parse_ecos({"RESULT": {"CODE": "INFO-200", "MESSAGE": "없음"}}), [])
        with self.assertRaises(ValueError):
            src_rates.parse_ecos({"RESULT": {"CODE": "INFO-100", "MESSAGE": "인증키 오류"}})

    def test_clean_drops_jumps(self):
        warnings = []
        old = [["2026-11-10", 3.88], ["2026-11-11", 3.88]]
        new = [["2026-11-12", 3.89], ["2026-11-13", 38.8], ["2026-11-14", 6.2]]
        merged = src_rates.clean("EFFR", old, new, warnings)
        self.assertEqual([row[0] for row in merged], ["2026-11-10", "2026-11-11", "2026-11-12"])
        self.assertEqual(len(warnings), 2)


class FredTest(unittest.TestCase):
    def test_parse(self):
        rows = fred.parse(text("fred_dgs10.txt"), "DGS10")
        self.assertEqual(rows[0], ["2026-10-20", 5.12])
        with self.assertRaises(ValueError):
            fred.parse("observation_date,OTHER\n", "DGS10")

    def test_transform(self):
        rows = [["2025-01-01", 100.0], ["2025-02-01", 101.0], ["2026-01-01", 103.0], ["2026-02-01", 103.02]]
        self.assertEqual(src_macro.transform(rows, "yoy"), [["2026-01-01", 3.0], ["2026-02-01", 2.0]])
        self.assertEqual(src_macro.transform(rows[:2], "diff"), [["2025-02-01", 1.0]])
        self.assertEqual(src_macro.transform(rows[:1], "scale:0.001"), [["2025-01-01", 0.1]])


class DelinqTest(unittest.TestCase):
    def test_parse(self):
        got = src_delinq.parse(text("household_arrays.txt"))
        self.assertEqual(got["latest"], "2026Q3")
        rate = got["series"]["auto_d90"]["obs"]
        self.assertEqual(len(rate), 91)
        self.assertEqual(rate[0], ["2004Q1", 2.32])
        self.assertEqual(rate[-2:], [["2026Q2", 5.49], ["2026Q3", 5.66]])
        self.assertEqual(got["series"]["auto_bal"]["obs"][-1], ["2026Q3", 1.73])

    def test_length_mismatch(self):
        with self.assertRaises(ValueError):
            src_delinq.parse('const categoriesInput90Day=["2004:Q1"],auto2Input=[1,2],auto1Input=[.5];')


class FiscalTest(unittest.TestCase):
    def test_fiscal(self):
        rows = common.csv_rows(text("fred_fiscal.txt"))
        pick = lambda sid: [[r["observation_date"], float(r[sid])] for r in rows if r[sid]]
        mts = src_fiscal.parse_mts(data("mts_net_interest.json"))
        self.assertAlmostEqual(mts[2024], 881650.995, places=2)
        # 이 자료의 재정수지는 FY2008부터라 최소 연수 조건을 낮춰 계산한다
        fiscal = src_fiscal.build_fiscal(pick("FYFSD"), pick("FYOINT"), pick("FYGDP"), mts, min_years=10)
        self.assertEqual(fiscal["latest"], 2025)
        by = lambda key: dict(fiscal["series"][key])
        # FY2024: 총적자 6.33% − 순이자 3.05% = 기초적자 3.29%
        self.assertAlmostEqual(by("total")[2024], 6.33, places=2)
        self.assertAlmostEqual(by("interest")[2024], 3.05, places=2)
        self.assertAlmostEqual(by("primary")[2024], 3.29, places=2)
        # 순이자를 MTS로 잇기 때문에 2014→2015에 단층이 없어야 한다
        self.assertLess(abs(by("interest")[2015] - by("interest")[2014]), 0.3)
        self.assertEqual(fiscal["series"]["primary"][0][0], 2008)
        self.assertEqual(fiscal["recession"][-1], 2020)
        with self.assertRaises(ValueError):
            src_fiscal.build_fiscal(pick("FYFSD"), pick("FYOINT"), pick("FYGDP"), mts)

    def test_refix(self):
        row = src_fiscal.refix_month(data("mspd1_200903.json"), data("mspd3_200903.json"))
        self.assertEqual(row, ["2009-03-31", 43.0, 32.45])
        self.assertIsNone(src_fiscal.refix_month({"data": []}, {"data": []}))


class GrowthTest(unittest.TestCase):
    def test_cagr_and_quarters(self):
        gdp = [[f"{2020 + i // 4}-{(i % 4) * 3 + 1:02d}-01", 100 * 1.01 ** i] for i in range(14)]
        got = src_growth.gdp_cagr3(gdp)
        self.assertEqual(got[0][0], "2023Q1")
        self.assertAlmostEqual(got[0][1], round((1.01 ** 4 - 1) * 100, 2), places=2)
        monthly = [["2026-01-01", 4.0], ["2026-02-01", 4.2], ["2026-03-01", 4.4], ["2026-04-01", 5.0]]
        self.assertEqual(src_growth.quarterly_average(monthly), [["2026Q1", 4.2]])

    def test_curve(self):
        csv_text = ('Date,"1 Mo","3 Mo","6 Mo","1 Yr","2 Yr","3 Yr","5 Yr","7 Yr","10 Yr","20 Yr","30 Yr"\n'
                    "11/13/2026,4.10,4.32,4.42,4.65,4.88,4.92,4.98,5.05,5.15,5.52,5.47\n"
                    "11/16/2026,4.10,4.34,4.42,4.62,4.83,4.87,4.93,5.01,5.12,5.51,5.46\n")
        curve = src_growth.parse_curve(csv_text)
        self.assertEqual(curve["date"], "2026-11-16")
        self.assertEqual(curve["values"][curve["tenors"].index("10 Yr")], 5.12)


class FedModelTest(unittest.TestCase):
    LINES = ["The forward 12", "-", "month P/E ratio for the S&P 500 is", "1", "8", ".", "3",
             ". This P/E ratio is", "below", "the 5", "-", "year average (", "19", ".", "9", ")",
             "and", "below the 10", "-", "year average (", "18", ".", "8", ").",
             "The forward 12", "-", "month P/E ratio is", "1", "8", ".", "3", "."]

    def test_read_report(self):
        got = src_fedmodel.read_report("\n".join(self.LINES))
        self.assertEqual(got["per"], 18.3)
        self.assertEqual(got["mentions"], 2)
        self.assertEqual((got["a5"], got["a10"]), (19.9, 18.8))
        self.assertIsNone(src_fedmodel.read_report("Earnings season update with no valuation sentence."))

    def test_pdf_text(self):
        content = (b"BT /F1 11 Tf 72 700 Td [(The f)3(orward 12)-2(-month P/E ratio for the S&P 500 is 2)1(1.9.)] TJ ET\n"
                   b"BT 72 680 Td (This P/E ratio is above the 5-year average \\(19.8\\)) Tj ET")
        packed = zlib.compress(content)
        pdf = (b"%PDF-1.7\n1 0 obj\n<< /Length " + str(len(packed)).encode() + b" /Filter /FlateDecode >>\nstream\n"
               + packed + b"\nendstream\nendobj\n%%EOF")
        got = src_fedmodel.read_report(pdftext.extract(pdf))
        self.assertEqual((got["per"], got["a5"]), (21.9, 19.8))

    def test_pdf_escapes(self):
        # 역슬래시 뒤 숫자가 8진수가 아닌 경우(\\9)에도 멈추지 않아야 한다
        self.assertEqual(pdftext._unescape(b"a\\9b\\050c\\)"), b"a9b(c)")

    def test_candidates_and_pairing(self):
        days = src_fedmodel.candidates(date(2026, 10, 30), date(2026, 11, 17))
        self.assertEqual([d.isoformat() for d in days], ["2026-11-06", "2026-11-13"])
        self.assertEqual(src_fedmodel.tag_of(date(2026, 11, 13)), "111326")
        self.assertEqual(src_fedmodel.day_of("061826"), date(2026, 6, 18))
        yields = {"2026-11-10": 5.05, "2026-11-12": 5.10}
        self.assertEqual(src_fedmodel.pair_yield(date(2026, 11, 11), yields), ("2026-11-10", 5.05))


class InflTest(unittest.TestCase):
    def test_pce(self):
        price = src_infl.dbn_lines(data("dbn_t20804.json"))
        nominal = src_infl.dbn_lines(data("dbn_t20805.json"))
        self.assertEqual(price[1]["2026-09"], 132.257)
        release = src_infl.pce_releases(price, nominal)[0]
        self.assertEqual(release["id"], "PCE-2026-09")
        head = release["items"][0]
        self.assertEqual((head["n"], head["mom"]), ("전체", 0.49))
        drivers = [item for item in release["items"] if item.get("drv")]
        self.assertEqual(len(drivers), 16)
        self.assertAlmostEqual(sum(item["w"] for item in drivers), 100.0, delta=0.2)
        # 겹치지 않는 16개 항목의 기여도 합 = 전체 전월비
        self.assertAlmostEqual(sum(item["c"] for item in drivers), 0.49, delta=0.02)

    def test_cpi(self):
        levels = {"CPIAUCSL": {"2025-10": 326.0, "2026-08": 334.131, "2026-09": 336.298, "2026-10": 337.476},
                  "CPIAUCNS": {"2025-10": 325.0, "2026-10": 338.0}}
        release = src_infl.cpi_releases(levels)[0]
        self.assertEqual(release["id"], "CPI-2026-10")
        head = release["items"][0]
        self.assertEqual(head["mom"], 0.35)
        self.assertEqual(head["pmom"], 0.65)
        self.assertEqual(head["yoy"], 4.0)           # 비계절조정 지수 기준

    def test_month_before(self):
        self.assertEqual(src_infl.month_before("2026-01"), "2025-12")
        self.assertEqual(src_infl.month_before("2026-10", 12), "2025-10")


class CentralBankTest(unittest.TestCase):
    def test_fomc(self):
        meetings = src_cbank.parse_fomc(text("fomc_calendar.html"))
        y2026 = [m for m in meetings if m["date"].startswith("2026")]
        self.assertEqual(len(y2026), 8)
        self.assertEqual(y2026[0], {"start": "2026-01-27", "date": "2026-01-28", "sep": False})
        self.assertEqual([m["date"] for m in y2026 if m["sep"]],
                         ["2026-03-18", "2026-06-17", "2026-09-16", "2026-12-09"])

    def test_fed_results(self):
        meetings = [{"start": "2026-09-15", "date": "2026-09-16", "sep": True},
                    {"start": "2026-10-27", "date": "2026-10-28", "sep": False},
                    {"start": "2026-12-08", "date": "2026-12-09", "sep": True}]
        upper = [["2026-09-01", 3.75], ["2026-09-16", 3.75], ["2026-09-17", 4.0], ["2026-11-16", 4.0]]
        lower = [[day, value - 0.25] for day, value in upper]
        src_cbank.fed_results(meetings, upper, lower, TODAY)
        self.assertEqual((meetings[0]["result"], meetings[0]["chg_bp"], meetings[0]["rate"]), ("인상", 25, "3.75~4.00%"))
        self.assertEqual((meetings[1]["result"], meetings[1]["chg_bp"]), ("동결", 0))
        self.assertNotIn("result", meetings[2])

    def test_ecb(self):
        meetings = src_cbank.parse_ecb(text("ecb_calendar.html"))
        self.assertEqual(meetings[0]["date"], "2026-12-17")
        self.assertIn("2027-02-04", [m["date"] for m in meetings])
        self.assertNotIn("2027-02-24", [m["date"] for m in meetings])       # 비통화정책 회의
        past = [{"start": "2026-09-09", "date": "2026-09-10"}, {"start": "2026-10-28", "date": "2026-10-29"}]
        src_cbank.ecb_results(past, [["2026-06-17", 2.25], ["2026-09-16", 2.5]], TODAY)
        self.assertEqual((past[0]["result"], past[0]["chg_bp"], past[0]["rate"]), ("인상", 25, "2.50%"))
        self.assertEqual(past[1]["result"], "동결")

    def test_boj(self):
        meetings = src_cbank.parse_boj(text("boj_schedule.html"))
        self.assertEqual(meetings[0], {"start": "2026-01-22", "date": "2026-01-23"})
        self.assertIn({"start": "2026-12-17", "date": "2026-12-18"}, meetings)
        self.assertIn({"start": "2027-01-21", "date": "2027-01-22"}, meetings)
        self.assertEqual(len(meetings), 16)

    def test_bok_year_by_weekday(self):
        meetings = src_cbank.parse_bok(text("bok_schedule.html"), TODAY)
        days = [m["date"] for m in meetings]
        self.assertIn("2026-01-15", days)
        self.assertIn("2026-11-26", days)
        self.assertIn("2025-02-25", days)

    def test_sep(self):
        sep = src_cbank.parse_sep(text("sep_20260916.html"))
        self.assertEqual(sep["years"], ["2026", "2027", "2028", "2029", "장기"])
        self.assertEqual(sep["medians"], [4.1, 4.1, 3.9, 3.6, 3.2])
        self.assertEqual(sep["ct"][0], "4.1~4.4")
        self.assertEqual(sep["participants"], [18, 18, 17, 17, 18])
        self.assertEqual(sep["bins"][0], [4.375, [4, 8, 0, 0, 0]])
        self.assertEqual(sep["bins"][-1], [2.875, [0, 0, 0, 1, 1]])

    def test_merge_keeps_past(self):
        old = [{"start": "2026-02-04", "date": "2026-02-05", "result": "동결"}]
        new = [{"start": "2026-12-16", "date": "2026-12-17"}]
        merged = src_cbank.merge_meetings(old, new, TODAY)
        self.assertEqual([m["date"] for m in merged], ["2026-02-05", "2026-12-17"])
        self.assertEqual(merged[0]["result"], "동결")


class MoneyMarketTest(unittest.TestCase):
    def test_board(self):
        reports = src_mm.parse(text("tradition_board.html"))
        self.assertEqual(len(reports), 10)
        self.assertEqual(reports[0]["date"], "2026-11-17")
        self.assertTrue(reports[0]["url"].startswith("https://www.traditionkorea.com/data/files/"))

    def test_other_host_is_dropped(self):
        html = ('<table><tr><td>Daily Report (20261117)</td>'
                '<td><a href="https://example.com/x.pdf">View</a></td></tr></table>')
        self.assertEqual(src_mm.parse(html), [])


if __name__ == "__main__":
    unittest.main()
