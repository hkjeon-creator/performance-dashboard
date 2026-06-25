# 구현 플랜 — 대시보드 재설계

스펙: `2026-06-25-dashboard-redesign.md`

---

## 단계 요약

| 단계 | 작업 | 예상 범위 |
|------|------|-----------|
| 1 | 데이터 헬퍼 함수 분리 | dashboard.py 상단 |
| 2 | Daily 요약 탭 | 전일/전주 토글, KPI 카드, 이상치 플래그 |
| 3 | 채널·캠페인 탭 | 퍼널 필터 + 기존 차트 통합 |
| 4 | 소재 분석 탭 | AB 자동 페어링, 추이 차트, 하위 목록 |
| 5 | 원본 데이터 탭 | 현재 유지 |
| 6 | 탭 순서 재조립 | 최종 통합 |

---

## 단계별 상세

### 단계 1 — 데이터 헬퍼 분리

**목적:** 각 탭에서 중복 집계 코드 없애기

추가할 함수:
```python
def get_yesterday(df) -> pd.DataFrame
    # df에서 가장 최신 날짜 1일치만 반환

def get_comparison_day(df, mode: str) -> pd.DataFrame
    # mode="전일": 최신 날짜 -1일
    # mode="전주": 최신 날짜 -7일

def calc_change_rate(current, previous) -> float
    # (current - previous) / previous * 100

def flag_anomalies(df) -> pd.DataFrame
    # data-quality-rules.md 기준 적용
    # CTR<0.1%, CVR>20%, ROAS<100%, ROAS>5000%
    # 이상 행 + 사유 컬럼 반환
```

---

### 단계 2 — Daily 요약 탭

1. 사이드바에 비교 기준 토글 추가
   ```python
   compare_mode = st.sidebar.radio("비교 기준", ["전일 대비", "전주 동요일 대비"])
   ```

2. KPI 카드 6개 — `st.metric(delta=)` 활용
   - 노출, 클릭, 비용, ROAS, 구매, CPA
   - delta: 변화율(%) + 방향

3. ROAS 강조 배너 — 현재 코드 유지, Daily 탭으로 이동

4. 채널별 ROAS 순위 가로 바차트
   - 어제 기준, 채널색 적용

5. 이상치 플래그 테이블
   - `flag_anomalies()` 결과
   - 없으면 `st.success("✅ 전날 이상 수치 없음")`

---

### 단계 3 — 채널·캠페인 탭

1. 퍼널 단계 필터 추가
   ```python
   FUNNEL_MAP = {
       "상단": ["GGL_CMP_01", "META_CMP_01", "META_CMP_02", "NVR_CMP_02"],
       "중단": ["GGL_CMP_02", "GGL_CMP_03"],
       "하단": ["META_CMP_03", "NVR_CMP_01", "NVR_CMP_03"],
   }
   funnel = st.selectbox("퍼널 단계", ["전체", "상단", "중단", "하단"])
   ```
   - 전체 외 선택 시 안내 문구: "퍼널 단계가 다른 캠페인과 ROAS를 직접 비교하지 마세요"

2. 기존 탭1(채널별) + 탭2(캠페인별) 차트 통합
   - 채널별 광고비·ROAS 바차트
   - 광고비 vs ROAS 버블차트 (평균 기준선 포함)
   - 캠페인 집계 테이블

---

### 단계 4 — 소재 분석 탭

**서브섹션 1: AB 비교**

```python
# 소재명에서 AB 페어 자동 추출
df["AB그룹"] = df["소재"].str.extract(r"_([AB])_")
df["소재베이스"] = df["소재"].str.replace(r"_[AB]_", "_", regex=True)

# 페어가 있는 소재만 필터
ab_pairs = df[df["AB그룹"].notna()]
```

- 캠페인+그룹별로 A/B 나란히 비교 테이블
- ROAS 높은 쪽 배경 강조

**서브섹션 2: 소재 추이**

```python
selected = st.multiselect("소재 선택", sorted(df["소재"].unique()))
trend = df[df["소재"].isin(selected)].groupby(["날짜","소재"])["ROAS"].mean()
```

- 일별 ROAS 라인차트 (plotly)
- 데이터가 1일치뿐이면 "날짜별 추이를 보려면 데이터를 더 추가하세요" 안내

**서브섹션 3: 하위 소재**

```python
n = st.slider("하위 N개", 5, 20, 10)
bottom = by_cr.nsmallest(n, "ROAS")
```

- ROAS 기준 하위 N개
- ROAS < 전체 평균 50% 행은 빨간 배경

---

### 단계 5 — 원본 데이터 탭

변경 없음. 현재 코드 그대로.

---

### 단계 6 — 최종 통합

탭 순서 재조립:
```python
tab1, tab2, tab3, tab4 = st.tabs([
    "📋 Daily 요약",
    "📊 채널·캠페인",
    "🎨 소재 분석",
    "🔍 원본 데이터",
])
```

---

## 체크리스트

- [ ] 단계 1: 헬퍼 함수 작성 및 기존 코드 리팩터
- [ ] 단계 2: Daily 요약 탭 구현
- [ ] 단계 3: 채널·캠페인 탭 구현
- [ ] 단계 4-A: 소재 AB 비교 구현
- [ ] 단계 4-B: 소재 추이 차트 구현
- [ ] 단계 4-C: 하위 소재 목록 구현
- [ ] 단계 5: 원본 탭 유지 확인
- [ ] 단계 6: 탭 통합, 실행 확인
