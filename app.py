"""
KOL Scorecard v2 — Streamlit App
가이드 v4 기준 | TikTok 공유수 추가 | 절대/상대점수 이원화
Excel 출력: KOL_스코어_재평가_결과_JP_FIN.xlsx 완전 동일 양식
"""

import subprocess, sys, io
import streamlit as st
import pandas as pd
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from scoring import evaluate_batch, get_grade, stars_from_score

# ── Playwright 자동 설치 ──────────────────────────────────
@st.cache_resource(show_spinner=False)
def _install_playwright_browser():
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True, timeout=180
        )
    except Exception:
        pass

_install_playwright_browser()

# ── 페이지 설정 ───────────────────────────────────────────
st.set_page_config(
    page_title="KOL Scorecard v2",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
* { font-family: 'Noto Sans JP', 'Malgun Gothic', sans-serif !important; }
.section-header {
    background: linear-gradient(135deg,#1F4E79,#2E75B6);
    color:#fff; border-radius:8px; padding:10px 16px;
    font-weight:700; font-size:1.05em; margin:10px 0 6px;
}
</style>
""", unsafe_allow_html=True)

RATE = 9.5

# ═══════════════════════════════════════════════════════════
# Excel 출력: FIN 파일과 완전 동일 양식
# ═══════════════════════════════════════════════════════════
def make_excel(tk_results, ig_results):
    wb = openpyxl.Workbook()

    # ── 공통 스타일 정의 ──────────────────────────────────
    def P(hex_): return PatternFill('solid', fgColor='FF'+hex_ if len(hex_)==6 else hex_)
    def F(bold=False, sz=9, color='000000', italic=False):
        return Font(name='Arial', bold=bold, size=sz, color=color, italic=italic)

    thin  = Side(border_style='thin', color='BFBFBF')
    BALL  = Border(left=thin, right=thin, top=thin, bottom=thin)
    AC    = Alignment(horizontal='center', vertical='center', wrap_text=True)
    AL    = Alignment(horizontal='left',   vertical='center', wrap_text=False)
    ALW   = Alignment(horizontal='left',   vertical='center', wrap_text=True)

    # FIN 파일에서 측정한 정확한 색상값
    FILLS = {
        'hdr_title':  P('1F4E79'),   # 행1 타이틀
        'hdr_blue':   P('2E75B6'),   # 행2 그룹헤더 파란
        'hdr_green':  P('375623'),   # 절대 종합점수
        'hdr_navy':   P('1F4E79'),   # 상대 종합점수
        'hdr_purple': P('4A235A'),   # 최종 평가
        'hdr_light':  P('BDD7EE'),   # 행3 컬럼헤더
        'hdr_grade':  P('C6E0B4'),   # 절대등급 헤더
        'hdr_result': P('D8B4FE'),   # 결론·코멘트 헤더
        'row_odd':    P('F7FBFF'),   # 홀수 데이터행
        'row_even':   P('FFFFFF'),   # 짝수 데이터행
        'rel_score':  P('EEF4FB'),   # 상대점수 배경
        'note_bg':    P('F2F2F2'),   # 주석 배경
        'cmt_bg':     P('FFF2CC'),   # 코멘트(예외) 배경 — FFF2CC
        # 등급
        'E': P('E2EFDA'), 'G': P('DDEBF7'),
        'C': P('FFF2CC'), 'H': P('FCE4D6'),
        # 결론
        'adopt':  P('1D6A2D'),
        'review': P('DCB306'),
        'reject': P('7B0000'),
    }
    GRADE_FONT = {
        '◎ 탁월': F(True,9,'375623'), '○ 양호': F(True,9,'1F4E79'),
        '△ 보통': F(True,9,'7D6608'), '✕ 저조': F(True,9,'843C0C'),
    }
    GRADE_FILL = {
        '◎ 탁월': FILLS['E'], '○ 양호': FILLS['G'],
        '△ 보통': FILLS['C'], '✕ 저조': FILLS['H'],
    }
    CON_FILL = {
        '채택 ✓': FILLS['adopt'],
        '검토 △': FILLS['review'],
        '제외 ✗': FILLS['reject'],
    }

    def cw(ws, col, w): ws.column_dimensions[get_column_letter(col)].width = w
    def rh(ws, row, h): ws.row_dimensions[row].height = h
    def mg(ws, rng):    ws.merge_cells(rng)

    def hcell(ws, r, c, v, fill, font=None, align=AC):
        cc = ws.cell(r, c, v)
        cc.fill = fill
        cc.font = font or F(True, 9, 'FFFFFF')
        cc.alignment = align
        cc.border = BALL

    def dcell(ws, r, c, v, fill, font=None, align=AC, fmt=None):
        cc = ws.cell(r, c, v)
        cc.fill = fill
        cc.font = font or F(False, 9)
        cc.alignment = align
        cc.border = BALL
        if fmt: cc.number_format = fmt

    def grade_cell(ws, r, c, grade):
        cc = ws.cell(r, c, grade)
        cc.fill = GRADE_FILL.get(grade, FILLS['row_even'])
        cc.font = GRADE_FONT.get(grade, F(True, 9))
        cc.alignment = AC
        cc.border = BALL

    def rel_cell(ws, r, c, val):
        cc = ws.cell(r, c, round(val, 2))
        cc.fill = FILLS['rel_score']
        cc.font = F(True, 10)
        cc.alignment = AC
        cc.border = BALL
        cc.number_format = '0.00'

    def con_cell(ws, r, c, con):
        cc = ws.cell(r, c, con)
        cc.fill = CON_FILL.get(con, FILLS['reject'])
        cc.font = F(True, 10, 'FFFFFF')
        cc.alignment = AC
        cc.border = BALL

    def cmt_cell(ws, r, c, cmt, rf):
        cc = ws.cell(r, c, cmt or '')
        cc.fill = FILLS['cmt_bg'] if cmt else rf
        cc.font = F(False, 9) if not cmt else F(False, 9, '7D6608')
        cc.alignment = ALW
        cc.border = BALL

    def note_row(ws, r, c1, c2, text):
        ws.merge_cells(start_row=r, start_column=c1, end_row=r, end_column=c2)
        cc = ws.cell(r, c1, text)
        cc.fill = FILLS['note_bg']
        cc.font = F(False, 8, '595959', italic=True)
        cc.alignment = AL

    # ══════════════════════════════════════════════════════
    # 시트 1: TikTok (FIN 파일 TikTok 시트와 완전 동일)
    # A=No B=KOL명 C=비용(¥) D=조회수 E=좋아요 F=댓글 G=저장 H=공유
    # I=비용(₩) J=CPV(₩) K=ER% L=저장률% M=공유율%
    # N=CPV등급 O=ER등급 P=저장률등급 Q=공유율등급
    # R=절대등급 S=상대점수 T=결론 U=코멘트
    # ══════════════════════════════════════════════════════
    ws_tk = wb.active
    ws_tk.title = 'TikTok'
    ws_tk.sheet_view.showGridLines = False
    ws_tk.freeze_panes = 'A4'

    # FIN 파일 정확한 열 너비
    for col, w in [(1,5),(2,16),(3,10),(4,10),(5,8),(6,6),(7,8),(8,7),
                   (9,9),(10,8),(11,7),(12,8),(13,8),
                   (14,9),(15,9),(16,9),(17,9),
                   (18,9),(19,9),(20,9),(21,30)]:
        cw(ws_tk, col, w)

    # FIN 파일 정확한 행 높이
    rh(ws_tk,1,18); rh(ws_tk,2,30); rh(ws_tk,3,31.9)

    # ── 행1: 타이틀 ──────────────────────────────────────
    mg(ws_tk, 'A1:U1')
    hcell(ws_tk,1,1,
          'TikTok KOL 스코어 평가표  |  기준: KOL 선별 프레임워크 가이드 v4  |  환율: ¥100 = ₩950',
          FILLS['hdr_title'], F(True,11,'FFFFFF'), AL)

    # ── 행2: 그룹 헤더 ───────────────────────────────────
    for rng, label, fill in [
        ('A2:B2', '기본 정보',         FILLS['hdr_blue']),
        ('C2:H2', '원본 데이터 (¥)',    FILLS['hdr_blue']),
        ('I2:M2', '산출 지표 (₩ 환산)', FILLS['hdr_blue']),
        ('N2:Q2', '지표별 등급',        FILLS['hdr_blue']),
        ('R2',    '절대 종합점수',      FILLS['hdr_green']),
        ('S2',    '상대 종합점수',      FILLS['hdr_navy']),
        ('T2:U2', '최종 평가',         FILLS['hdr_purple']),
    ]:
        mg(ws_tk, rng)
        cc = ws_tk[rng.split(':')[0]]
        cc.value = label; cc.fill = fill
        cc.font = F(True,9,'FFFFFF'); cc.alignment = AC

    # ── 행3: 컬럼 헤더 ───────────────────────────────────
    h3 = [
        (1,'No.',       'hdr_light'), (2,'KOL명',      'hdr_light'),
        (3,'비용(¥)',   'hdr_light'), (4,'조회수',     'hdr_light'),
        (5,'좋아요',    'hdr_light'), (6,'댓글',       'hdr_light'),
        (7,'저장',      'hdr_light'), (8,'공유',       'hdr_light'),
        (9,'비용(₩)',   'hdr_light'), (10,'CPV(₩)',    'hdr_light'),
        (11,'ER%',      'hdr_light'), (12,'저장률%',   'hdr_light'),
        (13,'공유율%',  'hdr_light'),
        (14,'CPV\n등급','hdr_light'), (15,'ER\n등급',  'hdr_light'),
        (16,'저장률\n등급','hdr_light'),(17,'공유율\n등급','hdr_light'),
        (18,'절대\n등급','hdr_grade'),
        (19,'상대\n점수','hdr_light'),
        (20,'결론',     'hdr_result'),(21,'코멘트',    'hdr_result'),
    ]
    for col, val, fk in h3:
        hcell(ws_tk, 3, col, val, FILLS[fk], F(True,8,'1F4E79'))

    # ── 데이터 행 ─────────────────────────────────────────
    for idx, r_data in enumerate(tk_results):
        r = idx + 4
        rf = FILLS['row_odd'] if idx % 2 == 0 else FILLS['row_even']
        rh(ws_tk, r, 19.9)
        m = r_data.metrics

        # No (FIN 파일과 동일: 1,2,3... 순번)
        dcell(ws_tk,r,1, idx+1,         rf, F(True,9))
        dcell(ws_tk,r,2, r_data.name,   rf, F(True,9), AL)
        dcell(ws_tk,r,3, int(r_data.cost_jpy), rf, F(False,9), fmt='#,##0')
        dcell(ws_tk,r,4, int(m.get('_views',0)),    rf, F(False,9), fmt='#,##0')
        dcell(ws_tk,r,5, int(m.get('_likes',0)),    rf, F(False,9), fmt='#,##0')
        dcell(ws_tk,r,6, int(m.get('_comments',0)), rf, F(False,9), fmt='#,##0')
        dcell(ws_tk,r,7, int(m.get('_saves',0)),    rf, F(False,9), fmt='#,##0')
        dcell(ws_tk,r,8, int(m.get('_shares',0)),   rf, F(False,9), fmt='#,##0')
        dcell(ws_tk,r,9, int(m.get('_cost_krw', r_data.cost_jpy*RATE)), rf, F(False,9), fmt='#,##0')
        dcell(ws_tk,r,10, round(m.get('cpv',0),1),   rf, F(False,9), fmt='#,##0.0')
        dcell(ws_tk,r,11, round(m.get('er',0),3),    rf, F(False,9), fmt='0.000')
        dcell(ws_tk,r,12, round(m.get('save',0),3),  rf, F(False,9), fmt='0.000')
        dcell(ws_tk,r,13, round(m.get('share',0),3), rf, F(False,9), fmt='0.000')

        grade_cell(ws_tk,r,14, r_data.grades.get('cpv','✕ 저조'))
        grade_cell(ws_tk,r,15, r_data.grades.get('er','✕ 저조'))
        grade_cell(ws_tk,r,16, r_data.grades.get('save','✕ 저조'))
        grade_cell(ws_tk,r,17, r_data.grades.get('share','✕ 저조'))
        grade_cell(ws_tk,r,18, r_data.abs_grade)
        rel_cell(ws_tk,r,19, r_data.rel_score)
        con_cell(ws_tk,r,20, r_data.conclusion)
        cmt_cell(ws_tk,r,21, r_data.comment, rf)

    # ── 주석 행 (FIN 파일과 동일) ─────────────────────────
    nr = len(tk_results) + 5   # 데이터 끝 다음 빈행 건너뜀 → +5
    note_row(ws_tk, nr,   1, 21,
        '【컷오프 기준 (제안값)】  CPV(₩): E<12 / G 12~23 / C 23~29 / H≥29  |  '
        'ER%: E≥3.48% / G 1.85~3.48% / C 1.05~1.85% / H<1.05%  |  '
        '저장률%: E≥0.490% / G 0.230~0.490% / C 0.122~0.230% / H<0.122%  |  '
        '공유율%: E≥0.058% / G 0.024~0.058% / C 0.013~0.024% / H<0.013%')
    note_row(ws_tk, nr+1, 1, 21,
        '【가중치】  CPV 30% / ER 30% / 저장률 25% / 공유율 15%  |  '
        '절대점수: 등급점수(E=10·G=7·C=4·H=1) × 가중치  |  '
        '상대점수: 그룹 내 백분위(1~10점) × 가중치')
    note_row(ws_tk, nr+2, 1, 21,
        '【결론 로직 v4 — 고정 임계값】  1차: 절대점수 < 5.0 → 제외 ✗  |  '
        '예외: 절대≥8.0 & 상대<4.0 → 검토 △ + 코멘트  |  '
        '2차: 상대점수 ≥6.0 → 채택 ✓  /  4.0~5.9 → 검토 △  /  <4.0 → 제외 ✗')

    # ══════════════════════════════════════════════════════
    # 시트 2: Instagram 피드 (FIN 파일 IG 시트와 완전 동일)
    # A=No B=KOL명 C=비용(¥) D=좋아요 E=댓글
    # F=비용(₩) G=총참여수 H=CPE(₩) I=댓글·좋아요비율
    # J=CPE등급 K=댓글좋아요등급 L=절대등급 M=상대점수 N=결론 O=코멘트
    # ══════════════════════════════════════════════════════
    ws_ig = wb.create_sheet('Instagram 피드')
    ws_ig.sheet_view.showGridLines = False
    ws_ig.freeze_panes = 'A4'

    # FIN 파일 정확한 열 너비
    for col, w in [(1,5),(2,16),(3,10),(4,8),(5,6),
                   (6,9),(7,8),(8,10),(9,10),
                   (10,11),(11,12),(12,9),(13,9),(14,9),(15,30)]:
        cw(ws_ig, col, w)

    rh(ws_ig,1,18); rh(ws_ig,2,30); rh(ws_ig,3,31.9)

    # 행1
    mg(ws_ig, 'A1:O1')
    hcell(ws_ig,1,1,
          'Instagram 피드 KOL 스코어 평가표  |  기준: KOL 선별 프레임워크 가이드 v4  |  환율: ¥100 = ₩950',
          FILLS['hdr_title'], F(True,11,'FFFFFF'), AL)

    # 행2
    for rng, label, fill in [
        ('A2:B2', '기본 정보',          FILLS['hdr_blue']),
        ('C2:E2', '원본 데이터 (¥)',     FILLS['hdr_blue']),
        ('F2:I2', '산출 지표 (₩ 환산)', FILLS['hdr_blue']),
        ('J2:K2', '지표별 등급',         FILLS['hdr_blue']),
        ('L2',    '절대 종합점수',       FILLS['hdr_green']),
        ('M2',    '상대 종합점수',       FILLS['hdr_navy']),
        ('N2:O2', '최종 평가',          FILLS['hdr_purple']),
    ]:
        mg(ws_ig, rng)
        cc = ws_ig[rng.split(':')[0]]
        cc.value = label; cc.fill = fill
        cc.font = F(True,9,'FFFFFF'); cc.alignment = AC

    # 행3
    h3_ig = [
        (1,'No.',              'hdr_light'), (2,'KOL명',             'hdr_light'),
        (3,'비용(¥)',          'hdr_light'), (4,'좋아요',            'hdr_light'),
        (5,'댓글',             'hdr_light'), (6,'비용(₩)',           'hdr_light'),
        (7,'총 참여수',         'hdr_light'), (8,'CPE(₩)',            'hdr_light'),
        (9,'댓글·\n좋아요 비율','hdr_light'),
        (10,'CPE\n등급',        'hdr_light'), (11,'댓글·좋아요\n등급', 'hdr_light'),
        (12,'절대\n등급',       'hdr_grade'),
        (13,'상대\n점수',       'hdr_light'),
        (14,'결론',            'hdr_result'), (15,'코멘트',           'hdr_result'),
    ]
    for col, val, fk in h3_ig:
        hcell(ws_ig, 3, col, val, FILLS[fk], F(True,8,'1F4E79'))

    # 데이터 행
    for idx, r_data in enumerate(ig_results):
        r = idx + 4
        rf = FILLS['row_odd'] if idx % 2 == 0 else FILLS['row_even']
        rh(ws_ig, r, 19.9)
        m = r_data.metrics

        dcell(ws_ig,r,1,  idx+1,           rf, F(True,9))
        dcell(ws_ig,r,2,  r_data.name,     rf, F(True,9), AL)
        dcell(ws_ig,r,3,  int(r_data.cost_jpy), rf, F(False,9), fmt='#,##0')
        dcell(ws_ig,r,4,  int(m.get('_likes',0)),    rf, F(False,9), fmt='#,##0')
        dcell(ws_ig,r,5,  int(m.get('_comments',0)), rf, F(False,9), fmt='#,##0')
        dcell(ws_ig,r,6,  int(m.get('_cost_krw', r_data.cost_jpy*RATE)), rf, F(False,9), fmt='#,##0')
        dcell(ws_ig,r,7,  int(m.get('_total',0)),    rf, F(False,9), fmt='#,##0')
        dcell(ws_ig,r,8,  int(m.get('cpe',0)),       rf, F(False,9), fmt='#,##0')
        dcell(ws_ig,r,9,  round(m.get('clr',0),4),   rf, F(False,9), fmt='0.0000')

        grade_cell(ws_ig,r,10, r_data.grades.get('cpe','✕ 저조'))
        grade_cell(ws_ig,r,11, r_data.grades.get('clr','✕ 저조'))
        grade_cell(ws_ig,r,12, r_data.abs_grade)
        rel_cell(ws_ig,r,13, r_data.rel_score)
        con_cell(ws_ig,r,14, r_data.conclusion)
        cmt_cell(ws_ig,r,15, r_data.comment, rf)

    # 주석 행
    ni = len(ig_results) + 5
    note_row(ws_ig, ni,   1, 15,
        '【컷오프 기준 (제안값)】  CPE(₩): E<1,631 / G 1,631~3,465 / C 3,465~6,261 / H≥6,261  |  '
        '댓글·좋아요 비율: E≥0.0042 / G 0.0002~0.0042 / C 0.0000~0.0002 / H<0.0000  |  '
        '가중치: CPE 60% / CLR 40%')
    note_row(ws_ig, ni+1, 1, 15,
        '【절대점수】 등급점수(E=10·G=7·C=4·H=1) × 가중치  |  '
        '【상대점수】 그룹 내 백분위(1~10점) × 가중치')
    note_row(ws_ig, ni+2, 1, 15,
        '【결론 로직 v4 — 고정 임계값】  1차: 절대점수 < 5.0 → 제외 ✗  |  '
        '예외: 절대≥8.0 & 상대<4.0 → 검토 △ + 코멘트  |  '
        '2차: 상대점수 ≥6.0 → 채택 ✓  /  4.0~5.9 → 검토 △  /  <4.0 → 제외 ✗')

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════
# 공통: 결과 표시 함수
# ═══════════════════════════════════════════════════════════
def show_results(tk_results, ig_results):
    if not tk_results and not ig_results:
        return

    st.divider()
    st.markdown('<div class="section-header">📊 평가 결과</div>', unsafe_allow_html=True)

    all_r = tk_results + ig_results
    total = len(all_r)
    adopt  = sum(1 for r in all_r if r.conclusion == '채택 ✓')
    review = sum(1 for r in all_r if r.conclusion == '검토 △')
    reject = sum(1 for r in all_r if r.conclusion == '제외 ✗')

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("전체", f"{total}명")
    c2.metric("채택 ✓", f"{adopt}명",  f"{adopt/total*100:.0f}%" if total else "")
    c3.metric("검토 △", f"{review}명", f"{review/total*100:.0f}%" if total else "")
    c4.metric("제외 ✗", f"{reject}명", f"{reject/total*100:.0f}%" if total else "")

    tab1, tab2, tab3 = st.tabs(["📋 TikTok 결과", "📱 Instagram 피드 결과", "📥 Excel 다운로드"])

    CON_COLOR = {'채택 ✓':'#E8F5E9','검토 △':'#FFFDE7','제외 ✗':'#FFEBEE'}

    def build_df_tk(results):
        rows = []
        for r in sorted(results, key=lambda x: x.rel_score, reverse=True):
            m = r.metrics
            rows.append({
                'KOL명':    r.name,
                '비용(¥)':  f"¥{int(r.cost_jpy):,}",
                'CPV(₩)':  f"{m.get('cpv',0):.1f}",
                'ER%':      f"{m.get('er',0):.3f}",
                '저장률%':  f"{m.get('save',0):.3f}",
                '공유율%★': f"{m.get('share',0):.3f}",
                'CPV등급':  r.grades.get('cpv',''),
                'ER등급':   r.grades.get('er',''),
                '저장등급': r.grades.get('save',''),
                '공유등급': r.grades.get('share',''),
                '절대등급': r.abs_grade,
                '상대점수': f"{r.rel_score:.2f}",
                '결론':     r.conclusion,
                '코멘트':   r.comment or '',
            })
        return pd.DataFrame(rows)

    def build_df_ig(results):
        rows = []
        for r in sorted(results, key=lambda x: x.rel_score, reverse=True):
            m = r.metrics
            rows.append({
                'KOL명':       r.name,
                '비용(¥)':     f"¥{int(r.cost_jpy):,}",
                '평균좋아요':  f"{int(m.get('_likes',0)):,}",
                '평균댓글':    f"{int(m.get('_comments',0)):,}",
                'CPE(₩)':     f"{int(m.get('cpe',0)):,}",
                'CLR':         f"{m.get('clr',0):.4f}",
                'CPE등급':     r.grades.get('cpe',''),
                'CLR등급':     r.grades.get('clr',''),
                '절대등급':    r.abs_grade,
                '상대점수':    f"{r.rel_score:.2f}",
                '결론':        r.conclusion,
                '코멘트':      r.comment or '',
            })
        return pd.DataFrame(rows)

    with tab1:
        if tk_results:
            df = build_df_tk(tk_results)
            def style_tk(row):
                bg = CON_COLOR.get(row['결론'], '#fff')
                return [f'background-color:{bg}']*len(row)
            st.dataframe(df.style.apply(style_tk, axis=1),
                         use_container_width=True, height=min(60+len(df)*36, 480))
        else:
            st.info("TikTok 데이터가 없습니다.")

    with tab2:
        if ig_results:
            df = build_df_ig(ig_results)
            def style_ig(row):
                bg = CON_COLOR.get(row['결론'], '#fff')
                return [f'background-color:{bg}']*len(row)
            st.dataframe(df.style.apply(style_ig, axis=1),
                         use_container_width=True, height=min(60+len(df)*36, 480))
        else:
            st.info("Instagram 피드 데이터가 없습니다.")

    with tab3:
        st.markdown("""
        **📋 출력 양식:** `KOL_스코어_재평가_결과_JP_FIN.xlsx` 와 **완전 동일**합니다.

        | 항목 | 내용 |
        |---|---|
        | 시트 구성 | TikTok + Instagram 피드 2개 시트 |
        | 열 구성 | FIN 파일과 동일 (TikTok 21열 / IG 15열) |
        | 색상 | 등급·결론·행 배경색 모두 동일 |
        | 행 높이·열 너비 | FIN 파일 픽셀 단위 동일 |
        | 주석 행 | 컷오프·가중치·결론 로직 v4 |
        """)
        if tk_results or ig_results:
            xl = make_excel(tk_results, ig_results)
            st.download_button(
                "📥 Excel 다운로드 (FIN 양식)",
                data=xl,
                file_name="KOL_스코어_재평가_결과_v4.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True,
            )
        else:
            st.warning("평가 데이터가 없습니다. 먼저 평가를 실행해주세요.")


# ═══════════════════════════════════════════════════════════
# 사이드바
# ═══════════════════════════════════════════════════════════
with st.sidebar:
    st.title("📊 KOL Scorecard v2")
    st.caption("가이드 v4 기준 | TikTok 공유수 추가")
    st.divider()
    n_posts = st.slider("스크래핑 게시물 수", 5, 15, 10, 1,
                        help="핀 게시물 제외 최근 N개")
    rate = st.number_input("환율 (¥100 = ₩?)", value=950, step=10) / 100
    st.divider()
    st.subheader("📐 결론 로직 v4")
    st.info(
        "**1차 필터:** 절대 < 5.0 → 제외 ✗\n\n"
        "**예외:** 절대 ≥ 8.0 & 상대 < 4.0 → 검토 △\n\n"
        "**2차:** 상대 ≥ 6.0 → 채택 ✓\n"
        "4.0~5.9 → 검토 △ | < 4.0 → 제외 ✗"
    )
    st.divider()
    st.markdown(
        '<span style="background:#E2EFDA;padding:2px 7px;border-radius:3px;font-size:0.8em;font-weight:700;color:#375623">◎ 탁월</span> '
        '<span style="background:#DDEBF7;padding:2px 7px;border-radius:3px;font-size:0.8em;font-weight:700;color:#1F4E79">○ 양호</span> '
        '<span style="background:#FFF2CC;padding:2px 7px;border-radius:3px;font-size:0.8em;font-weight:700;color:#7D6608">△ 보통</span> '
        '<span style="background:#FCE4D6;padding:2px 7px;border-radius:3px;font-size:0.8em;font-weight:700;color:#843C0C">✕ 저조</span>',
        unsafe_allow_html=True
    )
    st.caption(" ")
    st.markdown(
        '<span style="background:#1D6A2D;color:#fff;padding:2px 7px;border-radius:3px;font-size:0.8em;font-weight:700">채택 ✓</span> '
        '<span style="background:#DCB306;color:#fff;padding:2px 7px;border-radius:3px;font-size:0.8em;font-weight:700">검토 △</span> '
        '<span style="background:#7B0000;color:#fff;padding:2px 7px;border-radius:3px;font-size:0.8em;font-weight:700">제외 ✗</span>',
        unsafe_allow_html=True
    )


# ═══════════════════════════════════════════════════════════
# 메인 탭
# ═══════════════════════════════════════════════════════════
tab_manual, tab_scrape, tab_guide = st.tabs(["📝 수동 입력", "🤖 자동 스크래핑", "📖 가이드 v4"])


# ─── TAB 1: 수동 입력 ─────────────────────────────────────
with tab_manual:
    st.markdown('<div class="section-header">KOL 데이터 직접 입력 & 즉시 평가</div>', unsafe_allow_html=True)

    if "tk_kols" not in st.session_state:
        st.session_state.tk_kols = [{"name":"KOL 1","cost":500000}]
    if "ig_kols" not in st.session_state:
        st.session_state.ig_kols = [{"name":"KOL 1","cost":500000}]

    col_l, col_r = st.columns(2)

    # TikTok
    with col_l:
        st.subheader("📱 TikTok")
        b1,b2 = st.columns(2)
        if b1.button("➕ KOL 추가", key="tk_add"):
            n = len(st.session_state.tk_kols)+1
            st.session_state.tk_kols.append({"name":f"KOL {n}","cost":500000})
        if b2.button("🗑️ 초기화", key="tk_clr"):
            st.session_state.tk_kols=[{"name":"KOL 1","cost":500000}]

        tk_inputs=[]
        for idx,kol in enumerate(st.session_state.tk_kols):
            with st.expander(f"**{kol.get('name','KOL')}**", expanded=(idx==0)):
                n_col,c_col = st.columns(2)
                name = n_col.text_input("KOL명", value=kol.get("name",""), key=f"tkn_{idx}")
                cost = c_col.number_input("비용(¥)", 0, value=int(kol.get("cost",500000)), step=10000, key=f"tkc_{idx}")
                st.session_state.tk_kols[idx].update({"name":name,"cost":cost})

                v_col,l_col,cm_col = st.columns(3)
                views    = v_col.number_input("평균 조회수", 0, value=int(kol.get("views",0)),   key=f"tkv_{idx}")
                likes    = l_col.number_input("평균 좋아요", 0, value=int(kol.get("likes",0)),   key=f"tkl_{idx}")
                comments = cm_col.number_input("평균 댓글",  0, value=int(kol.get("cmts",0)),    key=f"tkco_{idx}")
                sv_col,sh_col = st.columns(2)
                saves    = sv_col.number_input("평균 저장",   0, value=int(kol.get("saves",0)),  key=f"tks_{idx}")
                shares   = sh_col.number_input("평균 공유 ★", 0, value=int(kol.get("shares",0)), key=f"tksh_{idx}",
                                               help="v2 신규 — 공유수 반영")
                st.session_state.tk_kols[idx].update(
                    {"views":views,"likes":likes,"cmts":comments,"saves":saves,"shares":shares})
                tk_inputs.append({"name":name,"cost_jpy":cost,
                    "views":views,"likes":likes,"comments":comments,"saves":saves,"shares":shares})

                if len(st.session_state.tk_kols)>1 and st.button("❌ 삭제", key=f"tkdel_{idx}"):
                    st.session_state.tk_kols.pop(idx); st.rerun()

    # Instagram 피드
    with col_r:
        st.subheader("📸 Instagram 피드")
        b3,b4 = st.columns(2)
        if b3.button("➕ KOL 추가", key="ig_add"):
            n = len(st.session_state.ig_kols)+1
            st.session_state.ig_kols.append({"name":f"KOL {n}","cost":500000})
        if b4.button("🗑️ 초기화", key="ig_clr"):
            st.session_state.ig_kols=[{"name":"KOL 1","cost":500000}]

        ig_inputs=[]
        for idx,kol in enumerate(st.session_state.ig_kols):
            with st.expander(f"**{kol.get('name','KOL')}**", expanded=(idx==0)):
                n_col,c_col = st.columns(2)
                name = n_col.text_input("KOL명", value=kol.get("name",""), key=f"ign_{idx}")
                cost = c_col.number_input("비용(¥)", 0, value=int(kol.get("cost",500000)), step=10000, key=f"igc_{idx}")
                st.session_state.ig_kols[idx].update({"name":name,"cost":cost})
                l_col,cm_col = st.columns(2)
                likes    = l_col.number_input("평균 좋아요", 0, value=int(kol.get("likes",0)), key=f"igl_{idx}")
                comments = cm_col.number_input("평균 댓글",  0, value=int(kol.get("cmts",0)),  key=f"igco_{idx}")
                st.session_state.ig_kols[idx].update({"likes":likes,"cmts":comments})
                ig_inputs.append({"name":name,"cost_jpy":cost,"likes":likes,"comments":comments})
                if len(st.session_state.ig_kols)>1 and st.button("❌ 삭제", key=f"igdel_{idx}"):
                    st.session_state.ig_kols.pop(idx); st.rerun()

    if st.button("🔍 평가 실행", type="primary", use_container_width=True):
        tk_v = [k for k in tk_inputs if k["name"] and k["cost_jpy"]>0 and k["views"]>0]
        ig_v = [k for k in ig_inputs if k["name"] and k["cost_jpy"]>0 and (k["likes"]+k["comments"])>0]
        if not tk_v and not ig_v:
            st.warning("유효 데이터를 입력하세요. (조회수·좋아요 모두 0이면 평가 불가)")
        else:
            st.session_state["manual_tk"] = evaluate_batch(tk_v, "tiktok")  if tk_v else []
            st.session_state["manual_ig"] = evaluate_batch(ig_v, "ig_feed") if ig_v else []

    if "manual_tk" in st.session_state or "manual_ig" in st.session_state:
        show_results(
            st.session_state.get("manual_tk", []),
            st.session_state.get("manual_ig", [])
        )


# ─── TAB 2: 자동 스크래핑 ─────────────────────────────────
with tab_scrape:
    st.markdown('<div class="section-header">🤖 자동 스크래핑 (Playwright)</div>', unsafe_allow_html=True)
    st.info("**TikTok v2 신규:** 공유수(shares) 자동 스크래핑 포함 ★")

    st.subheader("📱 TikTok URL 목록")
    tk_urls = st.text_area(
        "KOL명|URL|비용(¥) 형식, 한 줄씩",
        placeholder="가연がよん|https://www.tiktok.com/@kayeon_japan|750000\n深夜のうらら|https://www.tiktok.com/@yamiurarara|260000",
        height=120, key="tk_urls"
    )
    st.subheader("📸 Instagram 피드 URL 목록")
    ig_urls = st.text_area(
        "KOL명|URL|비용(¥) 형식, 한 줄씩",
        placeholder="NoChi🪡🎀|https://www.instagram.com/nochi_official/|460000\nJANE|https://www.instagram.com/jane_official/|230000",
        height=120, key="ig_urls"
    )

    c1,c2 = st.columns([2,1])
    run_btn   = c1.button("🚀 스크래핑 시작", type="primary", use_container_width=True)
    test_mode = c2.checkbox("테스트 모드 (더미 데이터)", value=True)

    def parse_lines(text):
        specs=[]
        for line in text.strip().splitlines():
            if not line.strip(): continue
            parts=[p.strip() for p in line.split("|")]
            if len(parts)>=2:
                specs.append({
                    "name":  parts[0],
                    "url":   parts[1],
                    "cost_jpy": int(parts[2]) if len(parts)>=3 and parts[2].isdigit() else 500000,
                })
        return specs

    if run_btn:
        import random as _r

        tk_specs = parse_lines(tk_urls)
        ig_specs = parse_lines(ig_urls)

        if not tk_specs and not ig_specs:
            st.error("URL을 입력해주세요.")
        else:
            scraped_tk, scraped_ig = [], []
            total_n = len(tk_specs)+len(ig_specs)
            prog = st.progress(0, "스크래핑 준비 중...")
            done = 0

            for spec in tk_specs:
                prog.progress(done/total_n, f"TikTok: {spec['name']}")
                if test_mode:
                    data = {"views":_r.randint(50000,900000),"likes":_r.randint(1000,40000),
                            "comments":_r.randint(20,500),"saves":_r.randint(100,10000),
                            "shares":_r.randint(10,500),"posts_scraped":n_posts,"error":None}
                else:
                    try:
                        from scraper import scrape_tiktok
                        data = scrape_tiktok(spec["url"], n_posts=n_posts)
                    except Exception as e:
                        data = {"views":0,"likes":0,"comments":0,"saves":0,"shares":0,
                                "posts_scraped":0,"error":str(e)}
                scraped_tk.append({"name":spec["name"],"cost_jpy":spec["cost_jpy"],**data})
                done+=1

            for spec in ig_specs:
                prog.progress(done/total_n, f"Instagram: {spec['name']}")
                if test_mode:
                    data = {"likes":_r.randint(500,15000),"comments":_r.randint(5,200),
                            "posts_scraped":n_posts,"error":None}
                else:
                    try:
                        from scraper import scrape_instagram_feed
                        data = scrape_instagram_feed(spec["url"], n_posts=n_posts)
                    except Exception as e:
                        data = {"likes":0,"comments":0,"posts_scraped":0,"error":str(e)}
                scraped_ig.append({"name":spec["name"],"cost_jpy":spec["cost_jpy"],**data})
                done+=1

            prog.progress(1.0, "✅ 완료!")

            for d in scraped_tk+scraped_ig:
                if d.get("error"):
                    st.warning(f"⚠️ {d['name']}: {d['error']}")

            tk_v = [d for d in scraped_tk if not d.get("error") and d.get("views",0)>0]
            ig_v = [d for d in scraped_ig if not d.get("error") and (d.get("likes",0)+d.get("comments",0))>0]

            st.session_state["scrape_tk"] = evaluate_batch(tk_v, "tiktok")  if tk_v else []
            st.session_state["scrape_ig"] = evaluate_batch(ig_v, "ig_feed") if ig_v else []

    if "scrape_tk" in st.session_state or "scrape_ig" in st.session_state:
        show_results(
            st.session_state.get("scrape_tk",[]),
            st.session_state.get("scrape_ig",[])
        )


# ─── TAB 3: 가이드 ────────────────────────────────────────
with tab_guide:
    st.markdown('<div class="section-header">📖 KOL 선별 프레임워크 가이드 v4</div>', unsafe_allow_html=True)
    with st.expander("가중치", expanded=True):
        c1,c2,c3 = st.columns(3)
        c1.markdown("**TikTok**")
        c1.table(pd.DataFrame({"지표":["CPV","ER%","저장률","공유율★"],"가중치":["30%","30%","25%","15%"]}))
        c2.markdown("**IG 릴스**")
        c2.table(pd.DataFrame({"지표":["CPV","ER%","댓글%"],"가중치":["30%","35%","35%"]}))
        c3.markdown("**IG 피드**")
        c3.table(pd.DataFrame({"지표":["CPE","댓글·좋아요비율"],"가중치":["60%","40%"]}))
    with st.expander("TikTok 컷오프 기준"):
        st.table(pd.DataFrame({
            "지표":["CPV(₩)","ER%","저장률%","공유율%★"],
            "◎ 탁월":["<12","≥3.48%","≥0.490%","≥0.058%"],
            "○ 양호":["12~23","1.85~3.48%","0.230~0.490%","0.024~0.058%"],
            "△ 보통":["23~29","1.05~1.85%","0.122~0.230%","0.013~0.024%"],
            "✕ 저조":["≥29","<1.05%","<0.122%","<0.013%"],
        }).set_index("지표"))
    with st.expander("Instagram 피드 컷오프 기준"):
        st.table(pd.DataFrame({
            "지표":["CPE(₩)","댓글·좋아요비율"],
            "◎ 탁월":["<1,631","≥0.0042"],
            "○ 양호":["1,631~3,465","0.0000~0.0042"],
            "△ 보통":["3,465~6,261","~0.0000"],
            "✕ 저조":["≥6,261","<0.0000"],
        }).set_index("지표"))
    with st.expander("결론 로직 v4"):
        st.markdown("""
1. **1차 필터:** 절대점수 < 5.0 → 제외 ✗
2. **예외 처리:** 절대 ≥ 8.0 & 상대 < 4.0 → 검토 △ + 코멘트 자동
3. **2차 결론 (고정 임계값):**
   - 상대 ≥ 6.0 → **채택 ✓**
   - 4.0 ~ 5.9 → **검토 △**
   - < 4.0 → **제외 ✗**
        """)
        cols = st.columns(3)
        cols[0].markdown('<div style="background:#1D6A2D;color:#fff;padding:10px;border-radius:8px;text-align:center;font-weight:700">채택 ✓<br><small>상대 ≥ 6.0</small></div>', unsafe_allow_html=True)
        cols[1].markdown('<div style="background:#DCB306;color:#fff;padding:10px;border-radius:8px;text-align:center;font-weight:700">검토 △<br><small>4.0~5.9</small></div>', unsafe_allow_html=True)
        cols[2].markdown('<div style="background:#7B0000;color:#fff;padding:10px;border-radius:8px;text-align:center;font-weight:700">제외 ✗<br><small>< 4.0</small></div>', unsafe_allow_html=True)
