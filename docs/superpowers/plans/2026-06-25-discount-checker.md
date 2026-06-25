# 할인가 자동 체크 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 매주 목요일 오후 9시 풋웨어_소재관리 시트의 UID를 읽어 무신사 상품 할인가를 크롤링하고 변경 여부를 W열에 기재한다.

**Architecture:** `check_discounts.py`가 핵심 로직(시트 읽기 → 크롤링 → 비교 → 시트 쓰기)을 담당하고, `dashboard.py`에 수동 실행 버튼을 추가한다. 스케줄은 Claude Code 루틴으로 매주 목요일 21:00에 자동 실행된다.

**Tech Stack:** Python, gspread(Google Sheets), browser-harness(무신사 크롤링), Streamlit(수동 버튼), Claude Code schedule

## Global Constraints

- 스프레드시트 ID: `1LGnfvS8qyILq_Lu6I_PoZGlwzJVGjKMcw_FLMq-PtwY`
- 시트명: `풋웨어_소재관리`
- U열=UID, V열=기존 할인가, W열=체크 결과
- U열 비어있으면 스킵
- 빨간 배경: `#FF0000`, 노란 배경: `#FFFF00`
- 크롤링 실패 시 재시도 1회
- 무신사 상품 URL: `https://www.musinsa.com/products/{UID}`

---

## 파일 구조

| 파일 | 역할 |
|------|------|
| `check_discounts.py` | 핵심 로직: 시트 읽기 → 크롤링 → 비교 → 시트 쓰기 |
| `dashboard.py` | 기존 파일에 수동 실행 버튼 추가 |

---

## Task 1: 무신사 상품 크롤러 구현

**Files:**
- Create: `check_discounts.py`

**Interfaces:**
- Produces:
  - `scrape_product(uid: str) -> dict` — `{"status": "ok"|"품절"|"실패", "value": "81%"|"300원"|None}`

- [ ] **Step 1: browser-harness 동작 확인**

```powershell
$env:Path = "C:\Users\MADUP\.local\bin;$env:Path"
$py = @"
new_tab("https://www.musinsa.com/products/3609263")
wait_for_load()
print(page_info())
"@
$py | browser-harness
```
예상: 페이지 title에 상품명 포함

- [ ] **Step 2: 할인율/할인가 추출 코드 작성**

`check_discounts.py` 생성:

```python
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
```

- [ ] **Step 3: 수동 테스트**

```python
# check_discounts.py 하단에 임시 추가
if __name__ == "__main__":
    print(scrape_product("3609263"))  # 기존 81% 상품
    print(scrape_product("4226103"))  # 기존 300원 상품
```

```powershell
uv tool run python check_discounts.py
```
예상: `{'status': 'ok', 'value': '81%'}` 형태 출력

- [ ] **Step 4: 임시 테스트 코드 제거 후 커밋**

```bash
git add check_discounts.py
git commit -m "feat: 무신사 상품 크롤러 구현"
```

---

## Task 2: 시트 읽기 / 비교 / 쓰기 구현

**Files:**
- Modify: `check_discounts.py`

**Interfaces:**
- Consumes: `scrape_product(uid) -> dict` (Task 1)
- Produces: `run_check() -> dict` — `{"total": int, "changed": int, "soldout": int, "failed": int}`

- [ ] **Step 1: Google Sheets 읽기 함수 추가**

`check_discounts.py`에 추가:

```python
import os
import json

SPREADSHEET_ID = "1LGnfvS8qyILq_Lu6I_PoZGlwzJVGjKMcw_FLMq-PtwY"
SHEET_NAME = "풋웨어_소재관리"

def read_sheet_rows() -> list[dict]:
    """U열(UID), V열(기존값), 행번호 반환. U열 비어있으면 스킵."""
    import gspread
    gc = gspread.oauth()  # ~/.config/gspread/credentials.json 사용
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
```

- [ ] **Step 2: 비교 함수 추가**

```python
def normalize(val: str) -> str:
    """공백·콤마 제거 후 소문자 정규화."""
    return val.replace(" ", "").replace(",", "").lower()

def is_changed(prev: str, current: str) -> bool:
    return normalize(prev) != normalize(current)
```

- [ ] **Step 3: 시트 쓰기 함수 추가**

```python
def write_result(ws, row: int, value: str, style: str):
    """
    style: "none" | "red" | "yellow"
    W열 = 23번째 열 (index 22, gspread는 1-based → col=23)
    """
    import gspread
    cell = ws.cell(row, 23)
    cell.value = value
    ws.update_cell(row, 23, value)

    color_map = {
        "red":    {"red": 1.0, "green": 0.0, "blue": 0.0},
        "yellow": {"red": 1.0, "green": 1.0, "blue": 0.0},
        "none":   {"red": 1.0, "green": 1.0, "blue": 1.0},
    }
    fmt = gspread.models.Cell(row, 23)
    ws.format(f"W{row}", {
        "backgroundColor": color_map[style],
        "textFormat": {"bold": style == "red"},
    })
```

- [ ] **Step 4: 메인 실행 함수 추가**

```python
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
```

- [ ] **Step 5: gspread 설치 확인**

```powershell
uv tool run --with gspread python -c "import gspread; print('ok')"
```
예상: `ok`

- [ ] **Step 6: requirements.txt에 gspread 추가**

```
streamlit>=1.58.0
pandas
plotly
pyarrow
gspread
```

- [ ] **Step 7: 커밋**

```bash
git add check_discounts.py requirements.txt
git commit -m "feat: 시트 읽기/비교/쓰기 구현"
```

---

## Task 3: Streamlit 수동 실행 버튼 추가

**Files:**
- Modify: `dashboard.py`

**Interfaces:**
- Consumes: `run_check() -> dict` from `check_discounts.py`

- [ ] **Step 1: dashboard.py 사이드바에 버튼 추가**

`dashboard.py`의 사이드바 섹션 하단(새로고침 버튼 아래)에 추가:

```python
st.divider()
st.header("🔍 할인가 체크")
if st.button("할인가 체크 실행", type="primary"):
    with st.spinner("무신사 상품 크롤링 중..."):
        import sys, os
        sys.path.insert(0, str(DATA_DIR))
        from check_discounts import run_check
        stats = run_check()
    st.success(
        f"완료! 총 {stats['total']}개 | "
        f"변경 {stats['changed']}건 | "
        f"품절 {stats['soldout']}건 | "
        f"실패 {stats['failed']}건"
    )
```

- [ ] **Step 2: 로컬 실행 확인**

```powershell
uv tool run --with plotly --with gspread streamlit run dashboard.py
```
- 사이드바 하단 "🔍 할인가 체크" 섹션 확인
- 버튼 클릭 → 스피너 → 완료 메시지 확인

- [ ] **Step 3: 커밋 및 푸시**

```bash
git add dashboard.py
git commit -m "feat: 대시보드 수동 할인가 체크 버튼 추가"
git push
```

---

## Task 4: 자동 스케줄 등록 (매주 목요일 21:00)

**Files:**
- Claude Code schedule 설정

- [ ] **Step 1: 스케줄 등록**

Claude Code에서:
```
/schedule 매주 목요일 오후 9시에 check_discounts.py의 run_check()를 실행해줘
```

또는 `anthropic-skills:schedule` 스킬로:
- 시간: `0 21 * * 4` (목요일 21:00 cron)
- 작업: `check_discounts.py` 실행

- [ ] **Step 2: 다음 목요일 실행 확인**

실행 후 풋웨어_소재관리 시트 W열 확인:
- 값이 기재됐는지
- 변경된 항목은 빨간 배경인지
- 실패 항목은 노란 배경인지

- [ ] **Step 3: 최종 커밋**

```bash
git add .
git commit -m "feat: 목요일 자동 스케줄 등록 완료"
git push
```
