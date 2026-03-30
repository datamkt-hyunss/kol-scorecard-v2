"""
KOL Scorecard v2 — Streamlit App
가이드 v4 기준 | TikTok 공유수 추가 | 절대/상대점수 이원화
"""

import streamlit as st
import pandas as pd
import json
import time
from typing import Optional

from scoring import (
    evaluate_batch, GRADE_META, CONCLUSION_META, CUTOFFS, WEIGHTS,
    SCORE_MAP, get_grade, stars_from_score,
)

# ── 페이지 설정 ───────────────────────────────────────────
st.set_page_config(
    page_title="KOL Scorecard v2",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────
st.markdown("""
<style>
/* 전체 폰트 */
* { font-family: 'Noto Sans JP', 'Malgun Gothic', sans-serif !important; }

/* 카드 */
.kol-card {
    border: 1px solid #e0e0e0;
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 12px;
    background: #fff;
}
/* 결론 배지 */
.badge-adopt  { background:#1D6A2D; color:#fff; border-radius:6px; padding:3px 10px; font-weight:700; }
.badge-review { background:#DCB306; color:#fff; border-radius:6px; padding:3px 10px; font-weight:700; }
.badge-reject { background:#7B0000; color:#fff; border-radius:6px; padding:3px 10px; font-weight:700; }

/* 등급 배지 */
.g-e { background:#E2EFDA; color:#375623; border-radius:4px; padding:2px 7px; font-size:0.85em; font-weight:700; }
.g-g { background:#DDEBF7; color:#1F4E79; border-radius:4px; padding:2px 7px; font-size:0.85em; font-weight:700; }
.g-c { background:#FFF2CC; color:#7D6608; border-radius:4px; padding:2px 7px; font-size:0.85em; font-weight:700; }
.g-h { background:#FCE4D6; color:#843C0C; border-radius:4px; padding:2px 7px; font-size:0.85em; font-weight:700; }

/* 테이블 헤더 */
.score-table th { background:#1F4E79; color:#fff; text-align:center; padding:8px; }
.score-table td { text-align:center; padding:6px 10px; border-bottom:1px solid #f0f0f0; }

/* 섹션 헤더 */
.section-header {
    background: linear-gradient(135deg,#1F4E79,#2E75B6);
    color:#fff; border-radius:8px; padding:10px 16px;
    font-weight:700; font-size:1.1em; margin:12px 0 8px;
}
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# 유틸 함수
# ═══════════════════════════════════════════════════════════
def grade_badge(grade: str) -> str:
    cls = {"◎ 탁월":"g-e","○ 양호":"g-g","△ 보통":"g-c","✕ 저조":"g-h"}.get(grade,"g-h")
    return f'<span class="{cls}">{grade}</span>'


def conclusion_badge(conclusion: str) -> str:
    cls = {"채택 ✓":"badge-adopt","검토 △":"badge-review","제외 ✗":"badge-reject"}.get(conclusion,"badge-reject")
    return f'<span class="{cls}">{conclusion}</span>'


def format_num(v, fmt=".1f") -> str:
    if v is None: return "-"
    try:
        return f"{v:{fmt}}"
    except Exception:
        return str(v)


# ═══════════════════════════════════════════════════════════
# 사이드바 — 플랫폼 & 공통 설정
# ═══════════════════════════════════════════════════════════
with st.sidebar:
    st.image("https://raw.githubusercontent.com/streamlit/streamlit/master/docs/_static/favicon.png", width=40)
    st.title("KOL Scorecard v2")
    st.caption("가이드 v4 기준 | 절대/상대점수 이원화")
    st.divider()

    platform_label = st.selectbox(
        "📱 평가 플랫폼",
        ["TikTok", "Instagram 피드", "Instagram 릴스"],
    )
    PLATFORM_MAP = {
        "TikTok": "tiktok",
        "Instagram 피드": "ig_feed",
        "Instagram 릴스": "ig_reels",
    }
    platform = PLATFORM_MAP[platform_label]

    st.divider()
    n_posts = st.slider("스크래핑 게시물 수", 5, 15, 10, 1,
                        help="핀 게시물 제외 최근 N개 기준")
    rate = st.number_input("환율 (¥100 = ₩?)", value=950, step=10,
                           help="¥100 기준 KRW 환율") / 100

    st.divider()
    st.subheader("📐 컷오프 기준")
    with st.expander("현재 적용 컷오프 보기"):
        cuts = CUTOFFS[platform]
        rows = []
        for metric, c in cuts.items():
            rows.append({
                "지표": metric.upper(),
                "탁월(E)": f"{'<' if c['lo'] else '≥'}{c['E']}",
                "양호(G)": f"{c['G']}~{c['E']}" if c['lo'] else f"{c['G']}~{c['E']}",
                "보통(C)": f"{c['C']}~{c['G']}" if c['lo'] else f"{c['C']}~{c['G']}",
                "저조(H)": f"≥{c['C']}" if c['lo'] else f"<{c['C']}",
            })
        st.dataframe(pd.DataFrame(rows).set_index("지표"), use_container_width=True)

    with st.expander("가중치 보기"):
        wts = WEIGHTS[platform]
        for m, w in wts.items():
            st.progress(w, text=f"{m.upper()}: {int(w*100)}%")

    st.divider()
    st.subheader("⚙️ 결론 로직 v4")
    st.info(
        "**1차 필터:** 절대점수 < 5.0 → 제외 ✗\n\n"
        "**예외:** 절대 ≥ 8.0 & 상대 < 4.0 → 검토 △ + 코멘트\n\n"
        "**2차:** 상대점수 ≥ 6.0 → 채택 ✓\n"
        "4.0 ~ 5.9 → 검토 △\n"
        "< 4.0 → 제외 ✗"
    )


# ═══════════════════════════════════════════════════════════
# 메인 탭
# ═══════════════════════════════════════════════════════════
tab_manual, tab_scrape, tab_guide = st.tabs([
    "📝 수동 입력 평가", "🤖 자동 스크래핑", "📖 가이드 v4"
])


# ───────────────────────────────────────────────────────────
# TAB 1: 수동 입력
# ───────────────────────────────────────────────────────────
with tab_manual:
    st.markdown('<div class="section-header">KOL 수동 데이터 입력 & 즉시 평가</div>',
                unsafe_allow_html=True)

    # ── KOL 추가 / 삭제 관리 ──────────────────────────────
    if "manual_kols" not in st.session_state:
        st.session_state.manual_kols = [{"name": "KOL 1"}]

    col_add, col_clear, _ = st.columns([1, 1, 6])
    with col_add:
        if st.button("➕ KOL 추가"):
            n = len(st.session_state.manual_kols) + 1
            st.session_state.manual_kols.append({"name": f"KOL {n}"})
    with col_clear:
        if st.button("🗑️ 전체 초기화"):
            st.session_state.manual_kols = [{"name": "KOL 1"}]

    st.divider()

    # ── 각 KOL 입력 폼 ───────────────────────────────────
    kol_inputs = []
    for idx, kol_state in enumerate(st.session_state.manual_kols):
        with st.expander(f"**{kol_state.get('name','KOL')}**", expanded=(idx == 0)):
            cols = st.columns([2, 2, 6])
            name = cols[0].text_input("KOL명", value=kol_state.get("name",""), key=f"name_{idx}")
            cost = cols[1].number_input("비용 (¥)", min_value=0, value=int(kol_state.get("cost",500000)),
                                        step=10000, key=f"cost_{idx}")
            st.session_state.manual_kols[idx]["name"] = name
            st.session_state.manual_kols[idx]["cost"] = cost

            # 플랫폼별 입력 필드
            if platform == "tiktok":
                c1,c2,c3,c4,c5 = st.columns(5)
                views    = c1.number_input("평균 조회수", 0, value=int(kol_state.get("views",0)), key=f"v_{idx}")
                likes    = c2.number_input("평균 좋아요", 0, value=int(kol_state.get("likes",0)), key=f"l_{idx}")
                comments = c3.number_input("평균 댓글",   0, value=int(kol_state.get("cmts",0)),  key=f"c_{idx}")
                saves    = c4.number_input("평균 저장",   0, value=int(kol_state.get("saves",0)), key=f"s_{idx}")
                shares   = c5.number_input("평균 공유 ★", 0, value=int(kol_state.get("shares",0)),key=f"sh_{idx}",
                                           help="v2 신규 — TikTok 공유수")
                st.session_state.manual_kols[idx].update(
                    {"views":views,"likes":likes,"cmts":comments,"saves":saves,"shares":shares})
                kol_inputs.append({
                    "name": name, "cost_jpy": cost,
                    "views":views, "likes":likes, "comments":comments,
                    "saves":saves, "shares":shares,
                })

            elif platform == "ig_feed":
                c1,c2 = st.columns(2)
                likes    = c1.number_input("평균 좋아요", 0, value=int(kol_state.get("likes",0)), key=f"l_{idx}")
                comments = c2.number_input("평균 댓글",   0, value=int(kol_state.get("cmts",0)),  key=f"c_{idx}")
                st.session_state.manual_kols[idx].update({"likes":likes,"cmts":comments})
                kol_inputs.append({"name":name,"cost_jpy":cost,"likes":likes,"comments":comments})

            elif platform == "ig_reels":
                c1,c2,c3 = st.columns(3)
                views    = c1.number_input("평균 조회수", 0, value=int(kol_state.get("views",0)), key=f"v_{idx}")
                likes    = c2.number_input("평균 좋아요", 0, value=int(kol_state.get("likes",0)), key=f"l_{idx}")
                comments = c3.number_input("평균 댓글",   0, value=int(kol_state.get("cmts",0)),  key=f"c_{idx}")
                st.session_state.manual_kols[idx].update({"views":views,"likes":likes,"cmts":comments})
                kol_inputs.append({"name":name,"cost_jpy":cost,"views":views,
                                   "likes":likes,"comments":comments})

            # 삭제 버튼
            if st.button("❌ 이 KOL 삭제", key=f"del_{idx}") and len(st.session_state.manual_kols) > 1:
                st.session_state.manual_kols.pop(idx)
                st.rerun()

    st.divider()

    # ── 평가 실행 ─────────────────────────────────────────
    if st.button("🔍 평가 실행", type="primary", use_container_width=True):
        valid = [k for k in kol_inputs if k.get("name") and k.get("cost_jpy",0) > 0]
        if not valid:
            st.warning("KOL명과 비용을 입력해주세요.")
        else:
            results = evaluate_batch(valid, platform)
            st.session_state["results"] = results
            st.session_state["results_platform"] = platform

    # ── 결과 표시 ─────────────────────────────────────────
    if "results" in st.session_state and st.session_state.get("results_platform") == platform:
        _show_results(st.session_state["results"], platform, rate)


def _show_results(results, platform, rate):
    st.markdown('<div class="section-header">📊 평가 결과</div>', unsafe_allow_html=True)

    # 요약 카드
    c1,c2,c3 = st.columns(3)
    adopt_n  = sum(1 for r in results if r.conclusion == "채택 ✓")
    review_n = sum(1 for r in results if r.conclusion == "검토 △")
    reject_n = sum(1 for r in results if r.conclusion == "제외 ✗")
    c1.metric("채택 ✓", f"{adopt_n}명", f"{adopt_n/len(results)*100:.0f}%")
    c2.metric("검토 △", f"{review_n}명", f"{review_n/len(results)*100:.0f}%")
    c3.metric("제외 ✗", f"{reject_n}명", f"{reject_n/len(results)*100:.0f}%")

    st.divider()

    # 상세 결과 테이블
    rows = []
    for r in sorted(results, key=lambda x: x.rel_score, reverse=True):
        row = {
            "KOL명": r.name,
            "절대 점수": r.stars + f" ({r.abs_score:.1f})",
            "절대 등급": r.abs_grade,
            "상대 점수": f"{r.rel_score:.2f}",
            "결론": r.conclusion,
        }

        if platform == "tiktok":
            m = r.metrics
            row.update({
                "CPV(₩)":   format_num(m.get("cpv"), ".1f"),
                "ER%":       format_num(m.get("er"),  ".3f"),
                "저장률%":   format_num(m.get("save"),".3f"),
                "공유율%★":  format_num(m.get("share"),".3f"),
                "CPV등급":   r.grades.get("cpv",""),
                "ER등급":    r.grades.get("er",""),
                "저장등급":  r.grades.get("save",""),
                "공유등급★": r.grades.get("share",""),
            })
        elif platform == "ig_feed":
            m = r.metrics
            row.update({
                "CPE(₩)": format_num(m.get("cpe"),".0f"),
                "CLR":     format_num(m.get("clr"),".4f"),
                "CPE등급": r.grades.get("cpe",""),
                "CLR등급": r.grades.get("clr",""),
            })
        elif platform == "ig_reels":
            m = r.metrics
            row.update({
                "CPV(₩)": format_num(m.get("cpv"),".1f"),
                "ER%":     format_num(m.get("er"), ".3f"),
                "댓글%":   format_num(m.get("comment"),".3f"),
                "CPV등급": r.grades.get("cpv",""),
                "ER등급":  r.grades.get("er",""),
                "댓글등급": r.grades.get("comment",""),
            })

        if r.comment:
            row["코멘트"] = r.comment
        rows.append(row)

    df = pd.DataFrame(rows)

    # 결론 색상 적용
    def color_conclusion(val):
        c = {"채택 ✓":"#E8F5E9","검토 △":"#FFF9C4","제외 ✗":"#FFEBEE"}
        return f"background-color: {c.get(val,'#fff')}"

    styled = df.style.applymap(color_conclusion, subset=["결론"])
    st.dataframe(styled, use_container_width=True, height=400)

    # 개별 카드
    st.markdown("### 📋 KOL별 상세")
    for r in sorted(results, key=lambda x: x.rel_score, reverse=True):
        bg = {"채택 ✓":"#E8F5E9","검토 △":"#FFFDE7","제외 ✗":"#FFEBEE"}.get(r.conclusion,"#fff")
        st.markdown(f"""
        <div class="kol-card" style="border-left:5px solid {r.conclusion_color}; background:{bg}">
        <div style="display:flex; justify-content:space-between; align-items:center">
          <div>
            <strong style="font-size:1.1em">{r.name}</strong>
            <span style="margin-left:12px; font-size:1.4em">{r.stars}</span>
          </div>
          <div>{conclusion_badge(r.conclusion)}</div>
        </div>
        <div style="margin-top:8px; color:#555; font-size:0.9em">
          절대점수: <strong>{r.abs_score:.2f}</strong> ({r.abs_grade}) &nbsp;|&nbsp;
          상대점수: <strong>{r.rel_score:.2f}</strong>
          {'&nbsp;&nbsp;<em style="color:#7D6608">💬 ' + r.comment + '</em>' if r.comment else ''}
        </div>
        </div>
        """, unsafe_allow_html=True)

    # Excel 다운로드
    import io
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    st.download_button(
        "📥 결과 Excel 다운로드",
        data=buf.getvalue(),
        file_name=f"KOL_평가결과_{platform}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

# _show_results를 탭 밖에서도 쓰기 위해 전역으로 정의
import inspect
# (이미 위에서 정의됨)


# ───────────────────────────────────────────────────────────
# TAB 2: 자동 스크래핑
# ───────────────────────────────────────────────────────────
with tab_scrape:
    st.markdown('<div class="section-header">🤖 자동 스크래핑 (Playwright)</div>',
                unsafe_allow_html=True)

    st.info(
        "계정 URL을 입력하면 Playwright로 자동 스크래핑합니다.\n\n"
        "**TikTok v2 신규:** 공유수(shares) 자동 수집 추가됨 ★"
    )

    if platform == "ig_reels":
        st.warning("릴스는 Instagram 릴스 탭 URL 기준 스크래핑. 피드 게시물과 구분하세요.")

    # URL 입력
    urls_text = st.text_area(
        "계정 URL (한 줄에 하나씩, 형식: KOL명|URL|비용¥)",
        placeholder=(
            "예시:\n"
            "가연がよん|https://www.tiktok.com/@kayeon_japan|750000\n"
            "深夜のうらら|https://www.tiktok.com/@yamiurarara|260000"
        ),
        height=160,
    )

    col_run, col_test = st.columns([2, 1])
    run_scrape = col_run.button("🚀 스크래핑 시작", type="primary", use_container_width=True)
    test_mode  = col_test.checkbox("테스트 모드 (더미 데이터)", value=True,
                                    help="실제 스크래핑 대신 더미 데이터로 로직 테스트")

    if run_scrape and urls_text.strip():
        lines = [l.strip() for l in urls_text.strip().splitlines() if l.strip()]
        kol_specs = []
        for line in lines:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2:
                name = parts[0]
                url  = parts[1]
                cost = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 500000
                kol_specs.append({"name": name, "url": url, "cost_jpy": cost})

        if not kol_specs:
            st.error("URL 형식이 잘못됐습니다. '이름|URL|비용' 형식으로 입력하세요.")
        else:
            progress_bar = st.progress(0, text="스크래핑 준비 중...")
            scraped_data = []

            for i, spec in enumerate(kol_specs):
                progress_bar.progress(
                    (i + 0.5) / len(kol_specs),
                    text=f"스크래핑 중: {spec['name']} ({i+1}/{len(kol_specs)})"
                )

                if test_mode:
                    # 더미 데이터
                    import random as _r
                    if platform == "tiktok":
                        data = {
                            "views":    _r.randint(50000, 900000),
                            "likes":    _r.randint(1000, 40000),
                            "comments": _r.randint(20, 500),
                            "saves":    _r.randint(100, 10000),
                            "shares":   _r.randint(10, 500),   # ★ 공유수
                            "posts_scraped": n_posts,
                            "error": None,
                        }
                    elif platform == "ig_feed":
                        data = {
                            "likes":    _r.randint(500, 15000),
                            "comments": _r.randint(5, 200),
                            "posts_scraped": n_posts,
                            "error": None,
                        }
                    else:  # ig_reels
                        data = {
                            "views":    _r.randint(30000, 500000),
                            "likes":    _r.randint(500, 20000),
                            "comments": _r.randint(10, 300),
                            "posts_scraped": n_posts,
                            "error": None,
                        }
                else:
                    # 실제 스크래핑
                    try:
                        from scraper import scrape_tiktok, scrape_instagram_feed
                        if platform == "tiktok":
                            data = scrape_tiktok(spec["url"], n_posts=n_posts)
                        elif platform in ("ig_feed", "ig_reels"):
                            data = scrape_instagram_feed(spec["url"], n_posts=n_posts)
                        else:
                            data = {"error": "미지원 플랫폼"}
                    except Exception as e:
                        data = {"error": str(e), "posts_scraped": 0}

                scraped_data.append({
                    "name": spec["name"],
                    "cost_jpy": spec["cost_jpy"],
                    **data,
                })

                progress_bar.progress(
                    (i + 1) / len(kol_specs),
                    text=f"완료: {spec['name']}"
                )
                time.sleep(0.3)

            progress_bar.progress(1.0, text="✅ 스크래핑 완료!")

            # 에러 체크
            errors = [(d["name"], d.get("error")) for d in scraped_data if d.get("error")]
            if errors:
                for name, err in errors:
                    st.warning(f"⚠️ {name}: {err}")

            # 수집 결과 미리보기
            with st.expander("📋 수집 데이터 미리보기"):
                preview_rows = []
                for d in scraped_data:
                    row = {"KOL명": d["name"], "비용(¥)": f"¥{d['cost_jpy']:,}",
                           "수집게시물": d.get("posts_scraped", 0)}
                    if platform == "tiktok":
                        row.update({
                            "평균조회수": f"{d.get('views',0):,.0f}",
                            "평균좋아요": f"{d.get('likes',0):,.0f}",
                            "평균댓글":   f"{d.get('comments',0):,.0f}",
                            "평균저장":   f"{d.get('saves',0):,.0f}",
                            "평균공유★":  f"{d.get('shares',0):,.0f}",
                        })
                    elif platform == "ig_feed":
                        row.update({
                            "평균좋아요": f"{d.get('likes',0):,.0f}",
                            "평균댓글":   f"{d.get('comments',0):,.0f}",
                        })
                    preview_rows.append(row)
                st.dataframe(pd.DataFrame(preview_rows), use_container_width=True)

            # 평가 실행
            results = evaluate_batch(scraped_data, platform)
            st.session_state["scrape_results"] = results
            st.session_state["scrape_platform"] = platform

    if "scrape_results" in st.session_state and st.session_state.get("scrape_platform") == platform:
        _show_results(st.session_state["scrape_results"], platform, rate)


# ───────────────────────────────────────────────────────────
# TAB 3: 가이드 v4
# ───────────────────────────────────────────────────────────
with tab_guide:
    st.markdown('<div class="section-header">📖 KOL 선별 프레임워크 가이드 v4</div>',
                unsafe_allow_html=True)

    st.markdown("""
    > **CPV × Engagement Efficiency Framework**
    > 2025–2026 | 일본 시장 기준 (JP Only) | v4
    """)

    with st.expander("1️⃣ 플랫폼별 가중치", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**TikTok (숏폼)**")
            st.table(pd.DataFrame({
                "지표": ["CPV", "ER%", "저장률", "공유율★"],
                "가중치": ["30%", "30%", "25%", "15%"],
            }))
            st.caption("★ v2 신규: 공유율 스크래핑 추가")
        with col2:
            st.markdown("**Instagram 릴스**")
            st.table(pd.DataFrame({
                "지표": ["CPV", "ER%", "댓글%"],
                "가중치": ["30%", "35%", "35%"],
            }))
        with col3:
            st.markdown("**Instagram 피드**")
            st.table(pd.DataFrame({
                "지표": ["CPE", "댓글·좋아요비율"],
                "가중치": ["60%", "40%"],
            }))

    with st.expander("2️⃣ 등급 컷오프 (TikTok 제안값)"):
        tk_df = pd.DataFrame({
            "지표": ["CPV(₩)", "ER%", "저장률%", "공유율%★"],
            "◎ 탁월": ["<12", "≥3.48%", "≥0.490%", "≥0.058%"],
            "○ 양호": ["12~23", "1.85~3.48%", "0.230~0.490%", "0.024~0.058%"],
            "△ 보통": ["23~29", "1.05~1.85%", "0.122~0.230%", "0.013~0.024%"],
            "✕ 저조": ["≥29", "<1.05%", "<0.122%", "<0.013%"],
        })
        st.dataframe(tk_df.set_index("지표"), use_container_width=True)

    with st.expander("3️⃣ 등급 컷오프 (Instagram)"):
        ig_reels_df = pd.DataFrame({
            "지표 (릴스)": ["CPV(₩)", "ER%", "댓글%"],
            "◎ 탁월": ["<14", "≥3.66%", "≥0.021%"],
            "○ 양호": ["14~25", "1.91~3.66%", "0.008~0.021%"],
            "△ 보통": ["25~59", "1.43~1.91%", "0.003~0.008%"],
            "✕ 저조": ["≥59", "<1.43%", "<0.003%"],
        })
        st.dataframe(ig_reels_df.set_index("지표 (릴스)"), use_container_width=True)

        ig_feed_df = pd.DataFrame({
            "지표 (피드)": ["CPE(₩)", "댓글·좋아요비율"],
            "◎ 탁월": ["<1,631", "≥0.0012"],
            "○ 양호": ["1,631~3,465", "0.0000~0.0012"],
            "△ 보통": ["3,465~6,261", "~0.0000"],
            "✕ 저조": ["≥6,261", "<0.0000"],
        })
        st.dataframe(ig_feed_df.set_index("지표 (피드)"), use_container_width=True)

    with st.expander("4️⃣ 점수 산출 방식 v4"):
        st.markdown("""
        **절대 종합점수** (Absolute Score)
        - 등급점수 × 가중치 합산
        - ◎탁월=10 / ○양호=7 / △보통=4 / ✕저조=1
        - 리스트 구성 변경에 무관하게 고정

        **상대 종합점수** (Relative Score)
        - 그룹 내 백분위 순위 → 1~10점 변환 후 × 가중치 합산
        - 공식: `(n − rank + 1) / n × 10`

        **절대점수 → 별점**
        | 점수 | 별점 |
        |---|---|
        | 8~10 | ★★★★★ |
        | 6~7.9 | ★★★★ |
        | 4~5.9 | ★★★ |
        | 2~3.9 | ★★ |
        | 0~1.9 | ★ |
        """)

    with st.expander("5️⃣ 결론 로직 v4"):
        st.markdown("""
        1. **1차 필터:** 절대점수 < 5.0 → **제외 ✗**
        2. **예외 처리:** 절대 ≥ 8.0 & 상대 < 4.0 → **검토 △** + 코멘트
        3. **2차 결론 (고정 임계값):**
           - 상대점수 ≥ 6.0 → **채택 ✓** 🟢
           - 4.0 ~ 5.9 → **검토 △** 🟡
           - < 4.0 → **제외 ✗** 🔴

        > 고정 임계값 사용 이유: 새 KOL 추가 시에도 기존 결론 불변 보장
        """)

        cols = st.columns(3)
        cols[0].markdown(
            '<div style="background:#1D6A2D;color:#fff;padding:12px;border-radius:8px;text-align:center;font-weight:700;font-size:1.1em">채택 ✓<br><small>상대점수 ≥ 6.0</small></div>',
            unsafe_allow_html=True)
        cols[1].markdown(
            '<div style="background:#DCB306;color:#fff;padding:12px;border-radius:8px;text-align:center;font-weight:700;font-size:1.1em">검토 △<br><small>상대점수 4.0~5.9</small></div>',
            unsafe_allow_html=True)
        cols[2].markdown(
            '<div style="background:#7B0000;color:#fff;padding:12px;border-radius:8px;text-align:center;font-weight:700;font-size:1.1em">제외 ✗<br><small>상대점수 < 4.0</small></div>',
            unsafe_allow_html=True)
