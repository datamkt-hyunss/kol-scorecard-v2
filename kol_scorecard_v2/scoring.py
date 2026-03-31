"""
scoring.py — KOL Scorecard v2
가이드 v4 기준 전체 평가 로직
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

# ═══════════════════════════════════════════════════════════
# 1. 컷오프 기준 (가이드 5장 제안값)
# ═══════════════════════════════════════════════════════════
CUTOFFS = {
    # TikTok
    "tiktok": {
        "cpv":   {"E": 12,    "G": 23,    "C": 29,    "lo": True},   # ₩
        "er":    {"E": 3.48,  "G": 1.85,  "C": 1.05,  "lo": False},  # %
        "save":  {"E": 0.490, "G": 0.230, "C": 0.122, "lo": False},  # %
        "share": {"E": 0.058, "G": 0.024, "C": 0.013, "lo": False},  # %
    },
    # Instagram Reels
    "ig_reels": {
        "cpv":     {"E": 14,    "G": 25,    "C": 59,    "lo": True},
        "er":      {"E": 3.66,  "G": 1.91,  "C": 1.43,  "lo": False},
        "comment": {"E": 0.021, "G": 0.008, "C": 0.003, "lo": False},
    },
    # Instagram Feed
    "ig_feed": {
        "cpe": {"E": 1631,   "G": 3465,   "C": 6261,   "lo": True},
        "clr": {"E": 0.0012, "G": 0.0000, "C": 0.0000, "lo": False},
    },
}

# ═══════════════════════════════════════════════════════════
# 2. 가중치 (가이드 3장)
# ═══════════════════════════════════════════════════════════
WEIGHTS = {
    "tiktok":    {"cpv": 0.30, "er": 0.30, "save": 0.25, "share": 0.15},
    "ig_reels":  {"cpv": 0.30, "er": 0.35, "comment": 0.35},
    "ig_feed":   {"cpe": 0.60, "clr": 0.40},
}

# ═══════════════════════════════════════════════════════════
# 3. 등급 정의
# ═══════════════════════════════════════════════════════════
SCORE_MAP = {"◎ 탁월": 10, "○ 양호": 7, "△ 보통": 4, "✕ 저조": 1}

GRADE_META = {
    "◎ 탁월": {
        "label": "◎ 탁월 (Excellent)",
        "color": "#E2EFDA",
        "text_color": "#375623",
        "bg_hex": "E2EFDA",
    },
    "○ 양호": {
        "label": "○ 양호 (Good)",
        "color": "#DDEBF7",
        "text_color": "#1F4E79",
        "bg_hex": "DDEBF7",
    },
    "△ 보통": {
        "label": "△ 보통 (Conditional)",
        "color": "#FFF2CC",
        "text_color": "#7D6608",
        "bg_hex": "FFF2CC",
    },
    "✕ 저조": {
        "label": "✕ 저조 (Hold)",
        "color": "#FCE4D6",
        "text_color": "#843C0C",
        "bg_hex": "FCE4D6",
    },
}

CONCLUSION_META = {
    "채택 ✓": {"color": "#1D6A2D", "text": "채택 ✓", "label": "채택"},
    "검토 △": {"color": "#DCB306", "text": "검토 △", "label": "검토"},
    "제외 ✗": {"color": "#7B0000", "text": "제외 ✗", "label": "제외"},
}


# ═══════════════════════════════════════════════════════════
# 4. 등급 판정 함수
# ═══════════════════════════════════════════════════════════
def get_grade(value: float, cuts: dict) -> str:
    """컷오프 기준으로 4단계 등급 반환"""
    E, G, C, lo = cuts["E"], cuts["G"], cuts["C"], cuts["lo"]
    if lo:   # 낮을수록 좋음 (CPV, CPE)
        if value < E:  return "◎ 탁월"
        if value < G:  return "○ 양호"
        if value < C:  return "△ 보통"
        return "✕ 저조"
    else:    # 높을수록 좋음
        if value >= E: return "◎ 탁월"
        if value >= G: return "○ 양호"
        if value >= C: return "△ 보통"
        return "✕ 저조"


def abs_grade_from_score(score: float) -> str:
    """절대 종합점수 → 등급 텍스트"""
    if score >= 8.0: return "◎ 탁월"
    if score >= 6.0: return "○ 양호"
    if score >= 4.0: return "△ 보통"
    return "✕ 저조"


def stars_from_score(score: float) -> str:
    """절대점수 → 별점 (0~1.9:★ / 2~3.9:★★ / 4~5.9:★★★ / 6~7.9:★★★★ / 8~10:★★★★★)"""
    if score < 2:   return "★"
    if score < 4:   return "★★"
    if score < 6:   return "★★★"
    if score < 8:   return "★★★★"
    return "★★★★★"


# ═══════════════════════════════════════════════════════════
# 5. 절대 종합점수 계산
# ═══════════════════════════════════════════════════════════
def calc_absolute_score(metrics: dict, platform: str) -> tuple[float, dict]:
    """
    metrics: 지표명→값 dict  (예: {"cpv": 15.3, "er": 2.1, "save": 0.35, "share": 0.04})
    Returns: (절대점수, 지표별_등급_dict)
    """
    cuts = CUTOFFS[platform]
    wts  = WEIGHTS[platform]
    grades = {}

    score = 0.0
    for metric, w in wts.items():
        val = metrics.get(metric)
        if val is None:
            grades[metric] = "✕ 저조"
            score += SCORE_MAP["✕ 저조"] * w
        else:
            g = get_grade(float(val), cuts[metric])
            grades[metric] = g
            score += SCORE_MAP[g] * w

    return round(score, 2), grades


# ═══════════════════════════════════════════════════════════
# 6. 상대 종합점수 계산 (그룹 내 백분위)
# ═══════════════════════════════════════════════════════════
def calc_relative_scores(all_metrics: list[dict], platform: str) -> list[float]:
    """
    all_metrics: 각 KOL의 지표 dict 리스트
    Returns: 각 KOL의 상대 종합점수 리스트 (1~10)
    """
    wts = WEIGHTS[platform]
    cuts = CUTOFFS[platform]
    n = len(all_metrics)
    if n == 0:
        return []

    rel_scores = [0.0] * n

    for metric, w in wts.items():
        lo = cuts[metric]["lo"]
        values = [m.get(metric, 0.0) or 0.0 for m in all_metrics]

        for i, val in enumerate(values):
            # 순위 계산 (낮을수록 좋음 → 낮은 값이 높은 순위)
            if lo:
                rank = sum(1 for v in values if v < val) + 1  # 낮을수록 상위
                percentile_score = (n - rank + 1) / n * 10
            else:
                rank = sum(1 for v in values if v > val) + 1  # 높을수록 상위
                percentile_score = (n - rank + 1) / n * 10

            rel_scores[i] += percentile_score * w

    return [round(s, 2) for s in rel_scores]


# ═══════════════════════════════════════════════════════════
# 7. 최종 결론 로직 v4 (가이드 6-3)
# ═══════════════════════════════════════════════════════════
def get_conclusion(abs_score: float, rel_score: float) -> tuple[str, str]:
    """
    Returns: (결론_키, 코멘트)
    결론_키: '채택 ✓' | '검토 △' | '제외 ✗'
    """
    # 1차 필터: 절대점수 < 5.0 → 제외
    if abs_score < 5.0:
        return "제외 ✗", ""

    # 예외 처리: 절대 ≥ 8.0 & 상대 < 4.0 → 검토 + 코멘트
    if abs_score >= 8.0 and rel_score < 4.0:
        return "검토 △", "개별 성과는 우수하나 해당 그룹 내 경쟁력 열위"

    # 2차: 상대점수 고정 임계값
    if rel_score >= 6.0:
        return "채택 ✓", ""
    if rel_score >= 4.0:
        return "검토 △", ""
    return "제외 ✗", ""


# ═══════════════════════════════════════════════════════════
# 8. 원시 데이터 → 지표 변환
# ═══════════════════════════════════════════════════════════
def raw_to_metrics_tiktok(
    cost_jpy: float,
    views: float,
    likes: float,
    comments: float,
    saves: float,
    shares: float,
    rate: float = 9.5,
) -> dict:
    """TikTok 원시 데이터 → CPV·ER%·저장률%·공유율%"""
    if views <= 0:
        return {}
    cost_krw = cost_jpy * rate
    cpv   = cost_krw / views
    er    = (likes + comments + saves + shares) / views * 100
    save  = saves  / views * 100
    share = shares / views * 100
    return {
        "cpv": round(cpv, 2),
        "er":  round(er, 3),
        "save": round(save, 3),
        "share": round(share, 3),
        # 원시값 보존
        "_views": views, "_likes": likes, "_comments": comments,
        "_saves": saves, "_shares": shares, "_cost_krw": cost_krw,
    }


def raw_to_metrics_ig_feed(
    cost_jpy: float,
    likes: float,
    comments: float,
    rate: float = 9.5,
) -> dict:
    """Instagram 피드 원시 데이터 → CPE·CLR"""
    cost_krw = cost_jpy * rate
    total = likes + comments
    if total <= 0:
        return {}
    cpe = cost_krw / total
    clr = comments / likes if likes > 0 else 0.0
    return {
        "cpe": round(cpe, 0),
        "clr": round(clr, 4),
        "_likes": likes, "_comments": comments,
        "_total": total, "_cost_krw": cost_krw,
    }


def raw_to_metrics_ig_reels(
    cost_jpy: float,
    views: float,
    likes: float,
    comments: float,
    rate: float = 9.5,
) -> dict:
    """Instagram 릴스 원시 데이터 → CPV·ER%·댓글%"""
    if views <= 0:
        return {}
    cost_krw = cost_jpy * rate
    cpv     = cost_krw / views
    er      = (likes + comments) / views * 100
    comment = comments / views * 100
    return {
        "cpv": round(cpv, 2),
        "er":  round(er, 3),
        "comment": round(comment, 3),
        "_views": views, "_likes": likes, "_comments": comments,
        "_cost_krw": cost_krw,
    }


# ═══════════════════════════════════════════════════════════
# 9. KOL 평가 데이터클래스
# ═══════════════════════════════════════════════════════════
@dataclass
class KOLResult:
    name: str
    platform: str                     # 'tiktok' | 'ig_reels' | 'ig_feed'
    cost_jpy: float
    metrics: dict                     # 계산된 지표
    grades: dict                      # 지표별 등급
    abs_score: float
    abs_grade: str
    stars: str
    rel_score: float = 0.0
    conclusion: str = ""
    comment: str = ""
    posts_scraped: int = 0
    error: Optional[str] = None

    @property
    def conclusion_color(self) -> str:
        return CONCLUSION_META.get(self.conclusion, {}).get("color", "#888888")

    @property
    def abs_grade_color(self) -> str:
        return GRADE_META.get(self.abs_grade, {}).get("color", "#FFFFFF")


# ═══════════════════════════════════════════════════════════
# 10. 배치 평가 (절대 + 상대 일괄 계산)
# ═══════════════════════════════════════════════════════════
def evaluate_batch(kol_list: list[dict], platform: str) -> list[KOLResult]:
    """
    kol_list: [{"name": str, "cost_jpy": float, **원시지표}, ...]
    platform: 'tiktok' | 'ig_reels' | 'ig_feed'
    """
    results_partial = []
    all_metrics_list = []

    for kol in kol_list:
        name = kol.get("name", "")
        cost = kol.get("cost_jpy", 0.0)
        err  = kol.get("error")

        if platform == "tiktok":
            m = raw_to_metrics_tiktok(
                cost, kol.get("views",0), kol.get("likes",0),
                kol.get("comments",0), kol.get("saves",0), kol.get("shares",0))
        elif platform == "ig_reels":
            m = raw_to_metrics_ig_reels(
                cost, kol.get("views",0), kol.get("likes",0), kol.get("comments",0))
        elif platform == "ig_feed":
            m = raw_to_metrics_ig_feed(
                cost, kol.get("likes",0), kol.get("comments",0))
        else:
            m = {}

        abs_score, grades = calc_absolute_score(m, platform)

        results_partial.append({
            "name": name, "cost_jpy": cost, "metrics": m, "grades": grades,
            "abs_score": abs_score, "posts_scraped": kol.get("posts_scraped",0),
            "error": err,
        })
        all_metrics_list.append(m)

    # 상대점수 일괄 계산
    rel_scores = calc_relative_scores(all_metrics_list, platform)

    results = []
    for i, r in enumerate(results_partial):
        rel = rel_scores[i] if i < len(rel_scores) else 0.0
        conclusion, comment = get_conclusion(r["abs_score"], rel)
        abs_g = abs_grade_from_score(r["abs_score"])
        stars = stars_from_score(r["abs_score"])

        results.append(KOLResult(
            name=r["name"],
            platform=platform,
            cost_jpy=r["cost_jpy"],
            metrics=r["metrics"],
            grades=r["grades"],
            abs_score=r["abs_score"],
            abs_grade=abs_g,
            stars=stars,
            rel_score=rel,
            conclusion=conclusion,
            comment=comment,
            posts_scraped=r["posts_scraped"],
            error=r["error"],
        ))

    return results
