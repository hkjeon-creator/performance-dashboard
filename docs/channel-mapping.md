# 채널 매핑

## 채널 ↔ 미디어소스 매핑

channel 데이터의 `채널` 컬럼과 appsflyer 데이터의 `미디어소스` 컬럼은 값이 달라
조인 전 반드시 매핑 변환 필요.

| 채널 (channel) | 미디어소스 (appsflyer) | 채널분류 |
|----------------|----------------------|----------|
| 구글 | googleadwords_int | 외부 |
| 메타 | Facebook Ads | 외부 |
| 네이버 | naver_search | 자체 |

---

## 조인 키

```
날짜 + 미디어소스(매핑 후) + 캠페인 + 그룹 + 소재
```

조인 방식: LEFT JOIN (channel 기준). appsflyer에 없는 행은 _af 컬럼이 NaN.

---

## 파이썬 조인 코드

```python
MEDIA_MAP = {
    "구글": "googleadwords_int",
    "메타": "Facebook Ads",
    "네이버": "naver_search",
}

ch["미디어소스_af"] = ch["채널"].map(MEDIA_MAP)

af_renamed = af.rename(columns={
    "클릭": "클릭_af",
    "회원가입": "회원가입_af",
    "구매": "구매_af",
    "구매매출": "구매매출_af",
})

merged = ch.merge(
    af_renamed[["날짜", "미디어소스_af", "캠페인", "그룹", "소재",
                "클릭_af", "회원가입_af", "구매_af", "구매매출_af"]],
    on=["날짜", "미디어소스_af", "캠페인", "그룹", "소재"],
    how="left",
)
```

---

## 채널 특성 요약

| 채널 | 과금 방식 | 주요 강점 | 주요 소재 타입 |
|------|-----------|-----------|----------------|
| 구글 | CPC / CPM | 검색 의도 + 디스플레이 리타겟 | VID, IMG, CRS |
| 메타 | CPM | 정밀 타겟팅, 룩얼라이크 | VID, IMG, CRS |
| 네이버 | CPC | 국내 검색 점유율, 브랜드 방어 | TXT, IMG |

> 채널 간 CTR·CVR 직접 비교 시 광고 형식 차이를 반드시 감안할 것.
