# 데이터 품질 규칙

## 불변 조건 (반드시 성립해야 하는 것)

| 조건 | 검증 코드 |
|------|-----------|
| 클릭 ≤ 노출 | `assert (df["클릭"] <= df["노출"]).all()` |
| 구매 ≤ 클릭 | `assert (df["구매"] <= df["클릭"]).all()` |
| 회원가입 ≤ 클릭 | `assert (df["회원가입"] <= df["클릭"]).all()` |
| 비용 > 0 | `assert (df["비용"] > 0).all()` |
| 구매매출 ≥ 0 | `assert (df["구매매출"] >= 0).all()` |
| 날짜 형식 YYYY-MM-DD | `pd.to_datetime(df["일"], errors="raise")` |

불변 조건 위반 시 분석 중단 후 원본 데이터 확인.

---

## 이상치 범위

| 지표 | 낮음 (의심) | 높음 (의심) | 판단 |
|------|-------------|-------------|------|
| CTR | < 0.1% | > 30% | 소재·타겟팅 문제 또는 데이터 오류 |
| CTR (TXT) | < 1% | > 50% | 검색 특성상 높음 — 별도 기준 적용 |
| CVR | < 0.1% | > 20% | 소재·랜딩 문제 또는 데이터 오류 |
| ROAS | < 100% | > 5000% | 적자 또는 소량 집행 의심 |
| CPA | < 100원 | > 500,000원 | 데이터 오류 또는 집행 이상 |

---

## 조인 품질 체크

```python
# appsflyer 매칭률 확인 (80% 미만이면 키 불일치 의심)
match_rate = merged["구매_af"].notna().mean()
assert match_rate >= 0.8, f"AF 매칭률 낮음: {match_rate:.1%}"

# 채널별 수치 차이 확인
diff = merged.copy()
diff["구매_diff"] = (diff["구매"] - diff["구매_af"]).abs()
diff["구매_diff_pct"] = diff["구매_diff"] / diff["구매"] * 100
# 30% 이상 차이 나는 행 경고
flagged = diff[diff["구매_diff_pct"] > 30]
if len(flagged):
    print(f"[경고] 구매 수치 30% 이상 차이 {len(flagged)}행")
```

---

## 일별 파일 체크리스트

새 날짜 데이터 추가 전 확인:

- [ ] `data/channel/YYYY-MM-DD.parquet` 존재
- [ ] `data/appsflyer/YYYY-MM-DD.parquet` 존재
- [ ] 두 파일의 날짜가 동일
- [ ] 컬럼 수 channel=13, appsflyer=9
- [ ] 불변 조건 통과
- [ ] 행 수가 전일 대비 ±50% 이내 (급격한 변화 의심)
