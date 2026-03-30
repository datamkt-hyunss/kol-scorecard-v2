# KOL Scorecard v2

가이드 v4 기준 KOL 평가 시스템 | 새 도메인 독립 배포용

## 주요 변경사항 (v1 → v2)

| 항목 | v1 | v2 |
|---|---|---|
| TikTok 공유수 | ❌ 미수집 | ✅ 자동 스크래핑 추가 |
| 평가 로직 | 단일 점수 | 절대/상대 이원화 (가이드 v4) |
| 결론 임계값 | 상대점수 고정값 | 절대 1차 필터 + 상대 고정 임계값 |
| 별점 표시 | 0.5단위 | ★ ~ ★★★★★ 5구간 |
| 검토 색상 | 황갈 | #DCB306 황금색 |

## 파일 구조

```
kol_scorecard_v2/
├── app.py              # Streamlit 메인 앱
├── scraper.py          # Playwright 스크래퍼 (TikTok + Instagram)
├── scoring.py          # 평가 로직 (가이드 v4)
├── requirements.txt    # Python 패키지
├── packages.txt        # 시스템 패키지 (Playwright용)
└── README.md
```

## Streamlit Cloud 배포 방법

### 1단계: GitHub 레포 생성
```bash
git init
git add .
git commit -m "KOL Scorecard v2 - guide v4 + TikTok shares scraping"
git remote add origin https://github.com/<your-username>/kol-scorecard-v2.git
git push -u origin main
```

### 2단계: Streamlit Cloud 설정
1. https://streamlit.io/cloud 접속
2. "New app" → GitHub 레포 연결
3. Branch: `main`, Main file: `app.py`
4. 앱 이름 설정 (새 도메인: `<your-app-name>.streamlit.app`)
5. Deploy!

> **참고:** Playwright는 처음 실행 시 브라우저를 자동 설치합니다.
> `packages.txt`의 시스템 패키지가 필수입니다.

## 로컬 실행 방법

```bash
# 가상환경 생성 (권장)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 패키지 설치
pip install -r requirements.txt
playwright install chromium

# 앱 실행
streamlit run app.py
```

## 가이드 v4 핵심 로직

### TikTok 지표 (공유율 신규 추가)
| 지표 | 가중치 | 컷오프 탁월 |
|---|---|---|
| CPV(₩) | 30% | < ₩12 |
| ER% | 30% | ≥ 3.48% |
| 저장률% | 25% | ≥ 0.490% |
| **공유율% ★** | **15%** | **≥ 0.058%** |

### 결론 로직 v4
```
절대점수 < 5.0 → 제외 ✗
절대 ≥ 8.0 & 상대 < 4.0 → 검토 △ + 코멘트
상대점수 ≥ 6.0 → 채택 ✓
상대점수 4.0~5.9 → 검토 △
상대점수 < 4.0 → 제외 ✗
```
