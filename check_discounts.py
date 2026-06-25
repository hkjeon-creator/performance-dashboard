import subprocess
import re
import time

SPREADSHEET_ID = "1LGnfvS8qyILq_Lu6I_PoZGlwzJVGjKMcw_FLMq-PtwY"
SHEET_NAME = "풋웨어_소재관리"

def scrape_product(uid: str) -> dict:
    """무신사 상품 페이지에서 할인율/할인가/품절 여부 추출."""
    script = f"""
new_tab("https://www.musinsa.com/products/{uid}")
wait_for_load()
import time; time.sleep(3)
result = js(\"\"\"
(() => {{
  // soldout check via button text (charCodes for no encoding issues)
  const soldoutStr = String.fromCharCode(54408,51208);
  const allBtns = document.querySelectorAll('button');
  for (const btn of allBtns) {{
    if (btn.textContent.trim() === soldoutStr) return {{"status": "품절"}};
  }}

  // discount rate: Price__DiscountRate class
  const rateEl = document.querySelector('[class*="Price__DiscountRate"]');
  if (rateEl) {{
    const rate = rateEl.textContent.match(/[0-9]+/);
    if (rate) return {{"status": "ok", "value": rate[0] + "%"}};
  }}

  // final price: Price__CalculatedPrice class
  const priceEl = document.querySelector('[class*="Price__CalculatedPrice"]');
  if (priceEl) {{
    const price = priceEl.textContent.replace(/[^0-9]/g, "");
    if (price) return {{"status": "ok", "value": price + "원"}};
  }}

  return {{"status": "실패"}};
}})()
\"\"\")
print(result)
"""
    for attempt in range(2):
        try:
            proc = subprocess.run(
                ["browser-harness"],
                input=script, capture_output=True, text=True, timeout=30,
                encoding="utf-8", errors="replace",
                env={**__import__("os").environ, "PATH": r"C:\Users\MADUP\.local\bin;" + __import__("os").environ.get("PATH", "")}
            )
            output = proc.stdout.strip()
            # dict 파싱
            match = re.search(r"\{.*\}", output)
            if match:
                import ast
                return ast.literal_eval(match.group())
        except Exception:
            pass
        if attempt == 0:
            time.sleep(3)
    return {"status": "실패", "value": None}


def read_sheet_rows() -> list:
    """U열(UID), V열(기존값), 행번호 반환. U열 비어있으면 스킵."""
    import gspread
    gc = gspread.oauth()
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(SHEET_NAME)
    all_values = ws.get_all_values()

    rows = []
    for i, row in enumerate(all_values, start=1):
        uid = row[20].strip() if len(row) > 20 else ""   # U = index 20
        prev = row[21].strip() if len(row) > 21 else ""  # V = index 21
        if not uid:
            continue
        rows.append({"row": i, "uid": uid, "prev": prev})
    return rows


def normalize(val: str) -> str:
    """공백·콤마 제거 후 소문자 정규화."""
    return val.replace(" ", "").replace(",", "").lower()


def is_changed(prev: str, current: str) -> bool:
    return normalize(prev) != normalize(current)


def write_result(ws, row: int, value: str, style: str):
    """
    style: "none" | "red" | "yellow"
    W열 = 23번째 열 (gspread 1-based)
    """
    ws.update_cell(row, 23, value)

    color_map = {
        "red":    {"red": 1.0, "green": 0.0, "blue": 0.0},
        "yellow": {"red": 1.0, "green": 1.0, "blue": 0.0},
        "none":   {"red": 1.0, "green": 1.0, "blue": 1.0},
    }
    ws.format(f"W{row}", {
        "backgroundColor": color_map[style],
        "textFormat": {"bold": style == "red"},
    })


def run_check() -> dict:
    import gspread
    gc = gspread.oauth()
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(SHEET_NAME)

    rows = read_sheet_rows()
    stats = {"total": len(rows), "changed": 0, "soldout": 0, "failed": 0}

    for item in rows:
        result = scrape_product(item["uid"])

        if result["status"] == "품절":
            write_result(ws, item["row"], "품절", "red")
            stats["soldout"] += 1
        elif result["status"] == "실패":
            write_result(ws, item["row"], "실패", "yellow")
            stats["failed"] += 1
        else:
            value = result["value"]
            if is_changed(item["prev"], value):
                write_result(ws, item["row"], value, "red")
                stats["changed"] += 1
            else:
                write_result(ws, item["row"], value, "none")

    return stats
