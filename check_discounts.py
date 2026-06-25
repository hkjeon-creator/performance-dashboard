import subprocess
import re
import time

def scrape_product(uid: str) -> dict:
    """무신사 상품 페이지에서 할인율/할인가/품절 여부 추출."""
    script = f"""
new_tab("https://www.musinsa.com/products/{uid}")
wait_for_load()
import time; time.sleep(2)
result = js(\"\"\"
(() => {{
  // 품절 체크
  const soldOut = document.querySelector('[class*="soldout"], [class*="sold-out"]');
  const btnText = document.querySelector('[class*="purchase"] button, [class*="buy"] button');
  if (soldOut || (btnText && btnText.disabled)) return {{"status": "품절"}};

  // 할인율 추출
  const rateEl = document.querySelector('[class*="discount-rate"], [class*="sale-rate"], [class*="discountRate"]');
  if (rateEl) {{
    const rate = rateEl.textContent.match(/\\d+/);
    if (rate) return {{"status": "ok", "value": rate[0] + "%"}};
  }}

  // 할인가 추출 (최종가)
  const priceEl = document.querySelector('[class*="final-price"], [class*="sale-price"], [class*="finalPrice"]');
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
