import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import pathlib
import glob

st.set_page_config(page_title="광고 성과 대시보드", layout="wide", page_icon="📊")

BLUE_PALETTE = ["#2C6FAC", "#5B9FD4", "#89C3E0", "#3A7EB8", "#6AAFCC", "#9DCFDF", "#B8DDE8"]
CHANNEL_COLORS = {
    "구글": "#2C6FAC",
    "메타": "#4BA8C8",
    "네이버": "#85C17E",
}
FUNNEL_MAP = {
    "상단": ["GGL_CMP_01_플러스가입", "META_CMP_01_신규유저", "META_CMP_02_룩얼라이크", "NVR_CMP_02_일반KW"],
    "중단": ["GGL_CMP_02_리타겟팅", "GGL_CMP_03_첫구매"],
    "하단": ["META_CMP_03_재구매", "NVR_CMP_01_브랜드KW", "NVR_CMP_03_재구매"],
}
FUNNEL_KPI = {
    "상단": "CPA (회원가입 기준), 회원가입률",
    "중단": "CPA (구매 기준), CVR",
    "하단": "ROAS, 구매매출",
}
DATA_DIR = Path(__file__).parent
MEDIA_SOURCE_MAP = {
    "구글": "googleadwords_int",
    "메타": "Facebook Ads",
    "네이버": "naver_search",
}


# ── 데이터 로드 ───────────────────────────────────────────────────────────────

def load_file(path):
    p = pathlib.Path(path)
    return pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p)

def read_uploaded(files):
    frames = []
    for f in files:
        if f.name.endswith(".parquet"):
            frames.append(pd.read_parquet(f))
        else:
            frames.append(pd.read_csv(f))
    return pd.concat(frames, ignore_index=True) if frames else None

def load_data(uploaded_ch=None, uploaded_af=None):
    # 업로드 파일 우선, 없으면 로컬 폴더
    if uploaded_ch:
        ch = read_uploaded(uploaded_ch)
    else:
        ch_files = sorted(
            glob.glob(str(DATA_DIR / "data" / "channel" / "*.parquet")) or
            glob.glob(str(DATA_DIR / "data" / "channel" / "*.csv"))
        )
        if not ch_files:
            return None
        ch = pd.concat([load_file(f) for f in ch_files], ignore_index=True)

    if uploaded_af:
        af = read_uploaded(uploaded_af)
    else:
        af_files = sorted(
            glob.glob(str(DATA_DIR / "data" / "appsflyer" / "*.parquet")) or
            glob.glob(str(DATA_DIR / "data" / "appsflyer" / "*.csv"))
        )
        if not af_files:
            return None
        af = pd.concat([load_file(f) for f in af_files], ignore_index=True)

    ch = ch.rename(columns={"일": "날짜"})
    af = af.rename(columns={"일": "날짜", "미디어소스": "미디어소스_af"})
    ch["미디어소스_af"] = ch["채널"].map(MEDIA_SOURCE_MAP)

    af_r = af.rename(columns={
        "클릭": "클릭_af", "회원가입": "회원가입_af",
        "구매": "구매_af", "구매매출": "구매매출_af",
    })
    join_keys = ["날짜", "미디어소스_af", "캠페인", "그룹", "소재"]
    merged = pd.merge(ch, af_r[join_keys + ["클릭_af", "회원가입_af", "구매_af", "구매매출_af"]],
                      on=join_keys, how="left")

    merged["날짜"] = pd.to_datetime(merged["날짜"])
    merged["CTR"]  = (merged["클릭"] / merged["노출"] * 100).round(2)
    merged["CVR"]  = (merged["구매"] / merged["클릭"] * 100).round(2)
    merged["CPC"]  = (merged["비용"] / merged["클릭"]).round(0)
    merged["CPA"]  = (merged["비용"] / merged["구매"].replace(0, pd.NA)).round(0)
    merged["ROAS"] = (merged["구매매출"] / merged["비용"] * 100).round(1)

    # 소재 파생 컬럼
    merged["소재타입"] = merged["소재"].str.split("_").str[0]
    merged["AB그룹"]  = merged["소재"].str.extract(r"_([AB])_")
    merged["소재베이스"] = merged["소재"].str.replace(r"_[AB]_", "_X_", regex=True)

    return merged

@st.cache_data(ttl=300)
def get_data():
    return load_data()

@st.cache_data(ttl=3600)
def get_uploaded_data(ch_key, af_key):
    # 업로드 파일은 session_state에서 직접 읽음 (캐시 키만 사용)
    return load_data(
        uploaded_ch=st.session_state.get("uploaded_ch"),
        uploaded_af=st.session_state.get("uploaded_af"),
    )


# ── 헬퍼 함수 ─────────────────────────────────────────────────────────────────

def fmt_number(n, prefix="", suffix=""):
    if pd.isna(n):
        return "-"
    if n >= 100_000_000:
        return f"{prefix}{n/100_000_000:.1f}억{suffix}"
    if n >= 10_000:
        return f"{prefix}{n/10_000:.1f}만{suffix}"
    return f"{prefix}{int(n):,}{suffix}"

def calc_delta(curr, prev):
    if prev == 0 or pd.isna(prev):
        return None
    return round((curr - prev) / prev * 100, 1)

def agg_kpis(d):
    imp  = d["노출"].sum()
    clk  = d["클릭"].sum()
    cost = d["비용"].sum()
    sig  = d["회원가입"].sum()
    pur  = d["구매"].sum()
    rev  = d["구매매출"].sum()
    return {
        "노출": imp, "클릭": clk, "비용": cost,
        "회원가입": sig, "구매": pur, "구매매출": rev,
        "ROAS": rev / cost * 100 if cost else 0,
        "CPA":  cost / pur if pur else 0,
        "CTR":  clk / imp * 100 if imp else 0,
    }

def flag_anomalies(d):
    rows = []
    for _, r in d.iterrows():
        flags = []
        ctr = r["클릭"] / r["노출"] * 100 if r["노출"] else 0
        cvr = r["구매"] / r["클릭"] * 100 if r["클릭"] else 0
        roas = r["구매매출"] / r["비용"] * 100 if r["비용"] else 0
        if ctr < 0.1:
            flags.append(f"CTR {ctr:.2f}% (<0.1%)")
        if cvr > 20:
            flags.append(f"CVR {cvr:.1f}% (>20%)")
        if roas < 100:
            flags.append(f"ROAS {roas:.0f}% (적자)")
        if 0 < roas > 5000:
            flags.append(f"ROAS {roas:.0f}% (>5000%)")
        if flags:
            rows.append({
                "채널": r["채널"], "캠페인": r["캠페인"],
                "소재": r["소재"], "이상 항목": " / ".join(flags),
            })
    return pd.DataFrame(rows)

def chart_layout(fig, height=400):
    fig.update_layout(
        plot_bgcolor="#F7FBFF", paper_bgcolor="white", height=height,
        yaxis=dict(gridcolor="#DDE8F0"), xaxis=dict(gridcolor="#DDE8F0"),
    )
    return fig


# ── 앱 시작 ───────────────────────────────────────────────────────────────────

st.title("📊 광고 성과 대시보드")

if st.session_state.get("uploaded_ch") or st.session_state.get("uploaded_af"):
    ch_key = str([f.name for f in st.session_state.get("uploaded_ch", [])])
    af_key = str([f.name for f in st.session_state.get("uploaded_af", [])])
    df = get_uploaded_data(ch_key, af_key)
else:
    df = get_data()

if df is None:
    st.info("👈 왼쪽 사이드바에서 채널/앱스플라이어 데이터를 업로드하세요.")
    st.stop()

date_min, date_max = df["날짜"].min(), df["날짜"].max()
yesterday = date_max


# ── 사이드바 ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("📂 데이터 업로드")
    up_ch = st.file_uploader(
        "채널 데이터 (CSV/Parquet, 복수 가능)",
        type=["csv", "parquet"], accept_multiple_files=True, key="upload_ch"
    )
    up_af = st.file_uploader(
        "앱스플라이어 데이터 (CSV/Parquet, 복수 가능)",
        type=["csv", "parquet"], accept_multiple_files=True, key="upload_af"
    )
    if up_ch:
        st.session_state["uploaded_ch"] = up_ch
    if up_af:
        st.session_state["uploaded_af"] = up_af

    using_upload = bool(st.session_state.get("uploaded_ch") or st.session_state.get("uploaded_af"))
    if using_upload:
        st.success("✅ 업로드 데이터 사용 중")
        if st.button("🗑️ 업로드 초기화"):
            st.session_state.pop("uploaded_ch", None)
            st.session_state.pop("uploaded_af", None)
            st.rerun()

    st.divider()
    st.header("필터")

    compare_mode = st.radio("비교 기준 (Daily 탭)", ["전일 대비", "전주 동요일 대비"])

    date_range = st.date_input("기간 (채널·캠페인·소재 탭)",
                               value=(date_min, date_max),
                               min_value=date_min, max_value=date_max)
    channels  = st.multiselect("채널", sorted(df["채널"].unique()),
                                default=sorted(df["채널"].unique()))
    campaigns = st.multiselect("캠페인", sorted(df["캠페인"].unique()),
                                default=sorted(df["캠페인"].unique()))

    st.caption(f"데이터: {date_min.date()} ~ {date_max.date()}")
    if st.button("🔄 새로고침"):
        st.cache_data.clear()
        st.rerun()

# 전체 필터 데이터
if len(date_range) == 2:
    start, end = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
    filtered = df[(df["날짜"] >= start) & (df["날짜"] <= end)]
else:
    filtered = df.copy()
filtered = filtered[filtered["채널"].isin(channels) & filtered["캠페인"].isin(campaigns)]


# ── 탭 ────────────────────────────────────────────────────────────────────────

tab_daily, tab_ch, tab_cr, tab_raw = st.tabs([
    "📋 Daily 요약", "📊 채널·캠페인", "🎨 소재 분석", "🔍 원본 데이터"
])


# ════════════════════════════════════════════════════════════════════════════
# 탭 1 — Daily 요약
# ════════════════════════════════════════════════════════════════════════════

with tab_daily:
    today_df = df[df["날짜"] == yesterday]

    offset = pd.Timedelta(days=1) if compare_mode == "전일 대비" else pd.Timedelta(days=7)
    compare_date = yesterday - offset
    compare_df = df[df["날짜"] == compare_date]
    compare_label = "전일" if compare_mode == "전일 대비" else "전주 동요일"

    curr = agg_kpis(today_df)
    prev = agg_kpis(compare_df) if len(compare_df) else {}

    st.caption(f"기준일: {yesterday.date()} | 비교: {compare_label} ({compare_date.date()})")

    # ROAS 강조 배너
    roas_color = "#2E6DA4" if curr["ROAS"] >= 300 else "#E07B3A"
    st.markdown(
        f"""<div style="background:#EBF3FB;border-left:6px solid {roas_color};
        border-radius:6px;padding:14px 22px;margin:4px 0 12px 0;">
        <span style="font-size:12px;color:#666;">어제 전체 ROAS</span><br>
        <span style="font-size:34px;font-weight:700;color:{roas_color};">{curr['ROAS']:.0f}%</span>
        <span style="font-size:13px;color:#888;margin-left:12px;">
        매출 {fmt_number(curr['구매매출'], '₩')} / 광고비 {fmt_number(curr['비용'], '₩')}</span>
        </div>""",
        unsafe_allow_html=True,
    )

    # KPI 카드
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    def delta_str(key, fmt=lambda x: x):
        if not prev:
            return None
        d = calc_delta(curr[key], prev.get(key, 0))
        return f"{d:+.1f}%" if d is not None else None

    k1.metric("노출",    fmt_number(curr["노출"]),          delta=delta_str("노출"))
    k2.metric("클릭",    fmt_number(curr["클릭"]),          delta=delta_str("클릭"))
    k3.metric("비용",    fmt_number(curr["비용"], "₩"),     delta=delta_str("비용"))
    k4.metric("ROAS",   f"{curr['ROAS']:.0f}%",            delta=delta_str("ROAS"))
    k5.metric("구매",    fmt_number(curr["구매"]),          delta=delta_str("구매"))
    k6.metric("CPA",    fmt_number(curr["CPA"], "₩"),      delta=delta_str("CPA"))

    st.divider()

    # 채널별 ROAS 순위
    by_ch_today = today_df.groupby("채널").agg(
        비용=("비용", "sum"), 구매매출=("구매매출", "sum")
    ).reset_index()
    by_ch_today["ROAS"] = (by_ch_today["구매매출"] / by_ch_today["비용"] * 100).round(1)
    by_ch_today = by_ch_today.sort_values("ROAS", ascending=True)

    fig = px.bar(by_ch_today, x="ROAS", y="채널", orientation="h",
                 color="채널", color_discrete_map=CHANNEL_COLORS,
                 title=f"채널별 ROAS — {yesterday.date()}", text_auto=True)
    fig.add_vline(x=by_ch_today["ROAS"].mean(), line_dash="dot", line_color="#9DC3D4",
                  annotation_text=f"평균 {by_ch_today['ROAS'].mean():.0f}%")
    chart_layout(fig, height=280)
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # 이상치 플래그
    st.markdown("#### ⚠️ 이상 수치 체크")
    anomalies = flag_anomalies(today_df)
    if anomalies.empty:
        st.success("✅ 전날 이상 수치 없음")
    else:
        st.warning(f"{len(anomalies)}개 항목에서 이상 수치 감지됨")
        st.dataframe(anomalies, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════════════════
# 탭 2 — 채널·캠페인
# ════════════════════════════════════════════════════════════════════════════

with tab_ch:
    # 퍼널 필터
    funnel_sel = st.selectbox("퍼널 단계 필터", ["전체", "상단", "중단", "하단"])
    if funnel_sel != "전체":
        funnel_cmp = FUNNEL_MAP[funnel_sel]
        fdata = filtered[filtered["캠페인"].isin(funnel_cmp)]
        st.info(f"**{funnel_sel} 퍼널** 주요 KPI: {FUNNEL_KPI[funnel_sel]}")
    else:
        fdata = filtered

    # 채널별 집계
    by_ch = fdata.groupby("채널").agg(
        노출=("노출","sum"), 클릭=("클릭","sum"), 비용=("비용","sum"),
        회원가입=("회원가입","sum"), 구매=("구매","sum"), 구매매출=("구매매출","sum"),
    ).reset_index()
    by_ch["CTR"]  = (by_ch["클릭"] / by_ch["노출"] * 100).round(2)
    by_ch["CVR"]  = (by_ch["구매"] / by_ch["클릭"] * 100).round(2)
    by_ch["ROAS"] = (by_ch["구매매출"] / by_ch["비용"] * 100).round(1)
    by_ch["CPA"]  = (by_ch["비용"] / by_ch["구매"]).round(0)

    # 캠페인별 집계
    by_cmp = fdata.groupby(["채널","캠페인","캠페인목적"]).agg(
        노출=("노출","sum"), 클릭=("클릭","sum"), 비용=("비용","sum"),
        회원가입=("회원가입","sum"), 구매=("구매","sum"), 구매매출=("구매매출","sum"),
    ).reset_index()
    by_cmp["CTR"]  = (by_cmp["클릭"] / by_cmp["노출"] * 100).round(2)
    by_cmp["ROAS"] = (by_cmp["구매매출"] / by_cmp["비용"] * 100).round(1)
    by_cmp["CPA"]  = (by_cmp["비용"] / by_cmp["구매"]).round(0)

    # 광고비 vs ROAS 버블
    st.markdown("#### 📈 광고비 vs ROAS")
    fig = px.scatter(by_cmp, x="비용", y="ROAS", size="구매매출", color="채널",
                     hover_name="캠페인",
                     hover_data={"비용":":,","ROAS":":.1f","구매매출":":,"},
                     color_discrete_map=CHANNEL_COLORS, size_max=55)
    fig.add_hline(y=by_cmp["ROAS"].mean(), line_dash="dot", line_color="#9DC3D4",
                  annotation_text=f"평균 {by_cmp['ROAS'].mean():.0f}%",
                  annotation_position="bottom right")
    chart_layout(fig, height=420)
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(by_ch, x="채널", y="비용", color="채널",
                     title="채널별 광고비", text_auto=True,
                     color_discrete_map=CHANNEL_COLORS)
        chart_layout(fig, 320)
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = px.bar(by_ch, x="채널", y="ROAS", color="채널",
                     title="채널별 ROAS (%)", text_auto=True,
                     color_discrete_map=CHANNEL_COLORS)
        chart_layout(fig, 320)
        st.plotly_chart(fig, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        fig = px.pie(by_ch, values="구매매출", names="채널",
                     title="채널별 구매매출 비중",
                     color_discrete_map=CHANNEL_COLORS)
        st.plotly_chart(fig, use_container_width=True)
    with c4:
        fig = px.bar(by_ch, x="채널", y=["회원가입","구매"],
                     title="채널별 전환", barmode="group",
                     color_discrete_map=CHANNEL_COLORS)
        chart_layout(fig, 320)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("##### 캠페인별 집계")
    st.dataframe(by_cmp.style.format({
        "비용":"{:,.0f}","노출":"{:,.0f}","클릭":"{:,.0f}",
        "구매매출":"{:,.0f}","CTR":"{:.2f}%","ROAS":"{:.1f}%","CPA":"{:,.0f}",
    }), use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# 탭 3 — 소재 분석
# ════════════════════════════════════════════════════════════════════════════

with tab_cr:
    by_cr = filtered.groupby(["채널","캠페인","그룹","소재","소재타입","AB그룹","소재베이스"]).agg(
        노출=("노출","sum"), 클릭=("클릭","sum"), 비용=("비용","sum"),
        회원가입=("회원가입","sum"), 구매=("구매","sum"), 구매매출=("구매매출","sum"),
    ).reset_index()
    by_cr["CTR"]  = (by_cr["클릭"] / by_cr["노출"] * 100).round(2)
    by_cr["CVR"]  = (by_cr["구매"] / by_cr["클릭"] * 100).round(2)
    by_cr["ROAS"] = (by_cr["구매매출"] / by_cr["비용"] * 100).round(1)
    by_cr["CPA"]  = (by_cr["비용"] / by_cr["구매"]).round(0)

    sec1, sec2, sec3 = st.tabs(["🆚 AB 비교", "📈 소재 추이", "🔻 하위 소재"])

    # ── AB 비교 ──────────────────────────────────────────────────────────────
    with sec1:
        ab = by_cr[by_cr["AB그룹"].notna()].copy()
        if ab.empty:
            st.info("현재 필터 기간에 AB 테스트 소재가 없습니다.")
        else:
            pairs = ab.groupby(["채널","캠페인","그룹","소재베이스"])
            for (ch_name, cmp, grp, base), group in pairs:
                if len(group) < 2:
                    continue
                st.markdown(f"**{ch_name} / {cmp} / {grp}**")
                disp = group[["AB그룹","소재","노출","클릭","비용","구매","구매매출","CTR","CVR","ROAS","CPA"]].copy()
                disp = disp.sort_values("AB그룹").reset_index(drop=True)
                winner_idx = disp["ROAS"].idxmax()

                def highlight_winner(row):
                    return ["background-color:#EBF3FB;font-weight:bold"
                            if row.name == winner_idx else "" for _ in row]

                st.dataframe(
                    disp.style
                        .apply(highlight_winner, axis=1)
                        .format({"비용":"{:,.0f}","구매매출":"{:,.0f}",
                                 "CTR":"{:.2f}%","CVR":"{:.2f}%",
                                 "ROAS":"{:.1f}%","CPA":"{:,.0f}"}),
                    use_container_width=True, hide_index=True,
                )
                st.caption(f"승자(ROAS 기준): {disp.loc[winner_idx,'소재']} — ROAS {disp.loc[winner_idx,'ROAS']:.0f}%")
                st.markdown("---")

    # ── 소재 추이 ─────────────────────────────────────────────────────────────
    with sec2:
        all_creatives = sorted(filtered["소재"].unique())
        selected_cr = st.multiselect("소재 선택 (복수 선택 가능)", all_creatives,
                                     default=all_creatives[:3] if len(all_creatives) >= 3 else all_creatives)
        if selected_cr:
            trend_df = (
                filtered[filtered["소재"].isin(selected_cr)]
                .groupby(["날짜","소재"])
                .agg(비용=("비용","sum"), 구매매출=("구매매출","sum"))
                .reset_index()
            )
            trend_df["ROAS"] = (trend_df["구매매출"] / trend_df["비용"] * 100).round(1)

            unique_dates = trend_df["날짜"].nunique()
            if unique_dates < 2:
                st.info("날짜가 1일치뿐입니다. 데이터가 더 쌓이면 추이를 볼 수 있습니다.")
                st.dataframe(trend_df[["소재","ROAS","비용","구매매출"]].style.format({
                    "ROAS":"{:.1f}%","비용":"{:,.0f}","구매매출":"{:,.0f}"
                }), use_container_width=True, hide_index=True)
            else:
                fig = px.line(trend_df, x="날짜", y="ROAS", color="소재",
                              title="소재별 일별 ROAS 추이", markers=True,
                              color_discrete_sequence=BLUE_PALETTE)
                chart_layout(fig, 420)
                st.plotly_chart(fig, use_container_width=True)

    # ── 하위 소재 ─────────────────────────────────────────────────────────────
    with sec3:
        n = st.slider("하위 소재 N개", 5, 20, 10)
        avg_roas = by_cr["ROAS"].mean()
        bottom = by_cr.nsmallest(n, "ROAS")[
            ["채널","캠페인","소재","비용","구매매출","ROAS","CVR","CPA"]
        ].reset_index(drop=True)

        def highlight_bottom(row):
            color = "#FEE2E2" if row["ROAS"] < avg_roas * 0.5 else ""
            return [f"background-color:{color}" for _ in row]

        st.caption(f"전체 평균 ROAS: {avg_roas:.0f}% | 빨간 행 = 평균의 50% 미만")
        st.dataframe(
            bottom.style
                .apply(highlight_bottom, axis=1)
                .format({"비용":"{:,.0f}","구매매출":"{:,.0f}",
                         "ROAS":"{:.1f}%","CVR":"{:.2f}%","CPA":"{:,.0f}"}),
            use_container_width=True, hide_index=True,
        )


# ════════════════════════════════════════════════════════════════════════════
# 탭 4 — 원본 데이터
# ════════════════════════════════════════════════════════════════════════════

with tab_raw:
    st.caption(f"총 {len(filtered):,}행 | {DATA_DIR}")
    st.dataframe(filtered, use_container_width=True)
