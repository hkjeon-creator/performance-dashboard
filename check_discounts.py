import subprocess
import re
import time

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
