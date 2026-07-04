# ================================================================
# 소리 감지 모니터 - 마이크로비트 연동 실시간 소음 측정 앱
# ================================================================

# ── 필요한 라이브러리 불러오기 ──────────────────────────
import tkinter as tk                          # GUI 창 만들기
from tkinter import ttk, simpledialog, messagebox  # 팝업창, 입력창, 경고창
import matplotlib.pyplot as plt               # 그래프 그리기
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # tkinter에 그래프 붙이기
import matplotlib.animation as animation      # 실시간 그래프 애니메이션
import random                                 # 가상 소리 데이터 생성용 난수
import math                                   # 사인파 계산용
import time                                   # 현재 시간 가져오기
import json                                   # 데이터 파일 저장/불러오기
import os                                     # 파일/폴더 경로 관리
import platform                               # 운영체제 확인
from collections import deque                 # 그래프용 고정 길이 데이터 저장소

# ── 한글 폰트 설정 ───────────────────────────────────────
if platform.system() == "Windows":
    plt.rcParams["font.family"] = "Malgun Gothic"   # 윈도우: 맑은 고딕
elif platform.system() == "Darwin":
    plt.rcParams["font.family"] = "AppleGothic"     # 맥: 애플 고딕
else:
    plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["axes.unicode_minus"] = False          # 마이너스 기호 깨짐 방지

# ================================================================
# [수정 1/2] 마이크로비트 연결 시 아래 주석 해제하고 COM 포트 번호 확인
# ================================================================
# import serial                                          # 시리얼 통신 라이브러리
# ser = serial.Serial('COM3', 115200, timeout=1)        # 마이크로비트 포트 연결
# ================================================================

# ── 파일 경로 설정 ──────────────────────────────────────
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))        # 이 파일이 있는 폴더
SAVE_FILE = os.path.join(BASE_DIR, "sound_data.json")         # 당일 데이터 저장 파일
HIST_DIR  = os.path.join(BASE_DIR, "history")                 # 날짜별 기록 폴더
os.makedirs(HIST_DIR, exist_ok=True)                          # history 폴더 없으면 자동 생성

# ── 그래프 설정 ─────────────────────────────────────────
MAX_POINTS = 60  # 그래프에 표시할 최대 데이터 개수 (60개 = 약 12초치)

# ── 소음 단계 정의 (5단계) ──────────────────────────────
# 각 단계별 이름, 색상, 배경색, 글자색 설정
LEVELS = [
    {"name": "매우 조용",     "color": "#1D9E75", "bg": "#E1F5EE", "fg": "#085041"},
    {"name": "조용",          "color": "#378ADD", "bg": "#E6F1FB", "fg": "#0C447C"},
    {"name": "보통",          "color": "#BA7517", "bg": "#FAEEDA", "fg": "#633806"},
    {"name": "시끄러움",      "color": "#D85A30", "bg": "#FAECE7", "fg": "#712B13"},
    {"name": "매우 시끄러움", "color": "#A32D2D", "bg": "#FCEBEB", "fg": "#501313"},
]

# ── 공간별 그래프 색상 (최대 4개 공간) ─────────────────
SPACE_COLORS = ["#185FA5", "#1D9E75", "#D85A30", "#7F77DD"]

# ── 소음 기준값 (이 값을 기준으로 단계 구분) ───────────
thresholds = [50, 100, 150, 200]

def get_level(val):
    """소리값을 받아서 몇 단계인지 반환 (0~4)"""
    for i, t in enumerate(thresholds):
        if val <= t:
            return i
    return 4

def fake_sound(t, offset=0):
    """가상 소리 데이터 생성 (마이크로비트 없을 때 테스트용)
    - 사인파 기반으로 자연스러운 소리 패턴 생성
    - 가끔 큰 소리(스파이크) 발생
    """
    base  = 30 + math.sin((t + offset) * 0.08) * 15  # 기본 소리 파형
    noise = (random.random() - 0.5) * 20              # 랜덤 노이즈
    spike = random.random() * 80 if random.random() < 0.05 else 0  # 5% 확률로 큰 소리
    return max(0, min(255, int(base + noise + spike)))

# ── 오늘 날짜 저장 ──────────────────────────────────────
today_str = time.strftime("%Y-%m-%d")  # 날짜 변경 감지용

# ── 날짜별 히스토리 저장 함수 ───────────────────────────
def save_history():
    """오늘 날짜 파일에 공간별 최고값, 평균, 피크 로그 저장"""
    hist_file = os.path.join(HIST_DIR, f"{today_str}.json")
    hist = {
        "date": today_str,
        "spaces": [
            {
                "name": s["name"],
                "peak": s["peak"],
                "peak_time": s["peak_time"],
                "peaks_log": s["peaks_log"][:50],
                "avg": round(s["total"] / s["count"]) if s["count"] > 0 else 0,
            }
            for s in spaces
        ]
    }
    with open(hist_file, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)

def load_history_list():
    """history 폴더에서 날짜 목록 불러오기 (최신순 정렬)"""
    files = sorted([
        f.replace(".json", "")
        for f in os.listdir(HIST_DIR)
        if f.endswith(".json")
    ], reverse=True)
    return files

def load_history_data(date_str):
    """특정 날짜의 히스토리 데이터 불러오기"""
    hist_file = os.path.join(HIST_DIR, f"{date_str}.json")
    if not os.path.exists(hist_file):
        return None
    with open(hist_file, "r", encoding="utf-8") as f:
        return json.load(f)

# ── 당일 데이터 저장/불러오기 ───────────────────────────
def save_data():
    """현재 공간 데이터를 sound_data.json에 저장하고 히스토리도 업데이트"""
    save = {
        "thresholds": thresholds,
        "spaces": [
            {
                "name": s["name"], "channel": s["channel"],
                "peak": s["peak"], "peak_time": s["peak_time"],
                "total": s["total"], "count": s["count"],
                "offset": s["offset"], "peaks_log": s["peaks_log"][:20],
            }
            for s in spaces
        ]
    }
    with open(SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump(save, f, ensure_ascii=False, indent=2)
    save_history()  # 히스토리도 같이 저장

def load_data():
    """앱 시작 시 sound_data.json에서 이전 데이터 불러오기"""
    global thresholds, spaces
    if not os.path.exists(SAVE_FILE):
        return
    try:
        with open(SAVE_FILE, "r", encoding="utf-8") as f:
            save = json.load(f)
        thresholds = save.get("thresholds", [50, 100, 150, 200])
        loaded = save.get("spaces", [])
        if loaded:
            spaces = []
            for s in loaded:
                spaces.append({
                    "name": s["name"], "channel": s["channel"],
                    "data": deque([0]*MAX_POINTS, maxlen=MAX_POINTS),  # 그래프 데이터 (빈 상태로 시작)
                    "peak": s["peak"], "peak_time": s["peak_time"],
                    "total": s["total"], "count": s["count"],
                    "window_peak": 0, "peaks_log": s["peaks_log"],
                    "offset": s["offset"],
                })
    except Exception:
        pass  # 파일 오류 시 무시하고 기본값 사용

# ── 공간 데이터 초기값 ──────────────────────────────────
# 각 공간마다 이름, 채널번호, 그래프데이터, 최고값, 합계, 카운트 등 저장
spaces = [
    {"name": "공간 1", "channel": 1, "data": deque([0]*MAX_POINTS, maxlen=MAX_POINTS),
     "peak": 0, "total": 0, "count": 0, "window_peak": 0, "peaks_log": [], "offset": 0, "peak_time": "—"},
]
load_data()  # 저장된 이전 데이터 불러오기

# ── 전역 변수 ───────────────────────────────────────────
running        = True   # 실행/일시정지 상태
tick           = 0      # 애니메이션 틱 (0.2초마다 1씩 증가)
start_time     = time.time()  # 앱 시작 시각
selected_space = 0      # 현재 선택된 공간 인덱스

# ── 메인 윈도우 생성 ────────────────────────────────────
root = tk.Tk()
root.title("소리 감지 모니터 (마이크로비트)")
root.geometry("1060x780")
root.configure(bg="#f5f5f3")
root.resizable(True, True)

# ── 디자인 상수 ─────────────────────────────────────────
FONT      = ("Helvetica", 11)
FONT_BOLD = ("Helvetica", 12, "bold")
BG        = "#f5f5f3"   # 배경색
CARD      = "#ffffff"   # 카드 배경색
GRAY      = "#888780"   # 보조 텍스트 색
BORDER    = "#D3D1C7"   # 테두리 색

# ── 마이크로비트 개수 입력 팝업 ─────────────────────────
# 앱 시작 시 마이크로비트 총 개수 입력 (수신용 1개 포함)
while True:
    try:
        mb_count = simpledialog.askinteger(
            "마이크로비트 개수",
            "사용할 마이크로비트 총 개수를 입력하세요.\n(수신용 1개 포함, 최소 2개)",
            parent=root, minvalue=1, maxvalue=10)
        if mb_count is None: mb_count = 2; break
        if mb_count < 2:
            messagebox.showwarning("개수 부족",
                "마이크로비트는 최소 2개가 필요해요.\n수신용 1개 + 소리 감지용 1개 이상이어야 해요.\n다시 입력해주세요.")
            continue
        break
    except Exception:
        mb_count = 2; break

MAX_SPACES = mb_count - 1  # 수신용 1개 제외한 최대 공간 수

# ── 탭 버튼 (실시간 모니터 / 날짜별 기록) ──────────────
tab_bar = tk.Frame(root, bg=BG, pady=0)
tab_bar.pack(fill="x", padx=16, pady=(8,0))

page_realtime = tk.Frame(root, bg=BG)  # 실시간 모니터 페이지
page_history  = tk.Frame(root, bg=BG)  # 날짜별 기록 페이지
page_weekly   = tk.Frame(root, bg=BG)  # 주간 통계 페이지
page_monthly  = tk.Frame(root, bg=BG)  # 월간 통계 페이지

def show_tab(tab):
    """탭 전환 함수 - 선택한 탭 페이지만 보이게 함"""
    page_realtime.pack_forget()
    page_history.pack_forget()
    page_weekly.pack_forget()
    page_monthly.pack_forget()
    btn_tab_realtime.config(bg=CARD, fg="#2C2C2A")
    btn_tab_history.config(bg=CARD, fg="#2C2C2A")
    btn_tab_weekly.config(bg=CARD, fg="#2C2C2A")
    btn_tab_monthly.config(bg=CARD, fg="#2C2C2A")

    if tab == "realtime":
        page_realtime.pack(fill="both", expand=True)
        btn_tab_realtime.config(bg="#185FA5", fg="#ffffff")
    elif tab == "history":
        page_history.pack(fill="both", expand=True)
        btn_tab_history.config(bg="#185FA5", fg="#ffffff")
        refresh_history_tab()
    elif tab == "weekly":
        page_weekly.pack(fill="both", expand=True)
        btn_tab_weekly.config(bg="#185FA5", fg="#ffffff")
        refresh_weekly_tab()
    elif tab == "monthly":
        page_monthly.pack(fill="both", expand=True)
        btn_tab_monthly.config(bg="#185FA5", fg="#ffffff")
        refresh_monthly_tab()

# 탭 버튼 생성
btn_tab_realtime = tk.Button(tab_bar, text="  실시간 모니터  ", font=FONT_BOLD,
    bg="#185FA5", fg="#ffffff", relief="flat", bd=0, padx=14, pady=6,
    cursor="hand2", command=lambda: show_tab("realtime"),
    highlightbackground="#185FA5", highlightthickness=1)
btn_tab_realtime.pack(side="left", padx=(0,6))

btn_tab_history = tk.Button(tab_bar, text="  날짜별 기록  ", font=FONT_BOLD,
    bg=CARD, fg="#2C2C2A", relief="flat", bd=0, padx=14, pady=6,
    cursor="hand2", command=lambda: show_tab("history"),
    highlightbackground=BORDER, highlightthickness=1)
btn_tab_history.pack(side="left", padx=(0,6))

btn_tab_weekly = tk.Button(tab_bar, text="  주간 통계  ", font=FONT_BOLD,
    bg=CARD, fg="#2C2C2A", relief="flat", bd=0, padx=14, pady=6,
    cursor="hand2", command=lambda: show_tab("weekly"),
    highlightbackground=BORDER, highlightthickness=1)
btn_tab_weekly.pack(side="left", padx=(0,6))

btn_tab_monthly = tk.Button(tab_bar, text="  월간 통계  ", font=FONT_BOLD,
    bg=CARD, fg="#2C2C2A", relief="flat", bd=0, padx=14, pady=6,
    cursor="hand2", command=lambda: show_tab("monthly"),
    highlightbackground=BORDER, highlightthickness=1)
btn_tab_monthly.pack(side="left")

# ════════════════════════════════════════════════════════
# 실시간 모니터 탭
# ════════════════════════════════════════════════════════
page_realtime.pack(fill="both", expand=True)

# ── 상단 타이틀 바 ──────────────────────────────────────
top = tk.Frame(page_realtime, bg=BG, pady=6, padx=16)
top.pack(fill="x")
tk.Label(top, text="소리 감지 모니터", font=FONT_BOLD, bg=BG, fg="#2C2C2A").pack(side="left")
status_lbl = tk.Label(top, text="● 실행 중", font=("Helvetica", 12, "bold"), bg=BG, fg="#22C55E")
status_lbl.pack(side="left", padx=12)

def toggle():
    """일시정지/재생 버튼 - running 변수로 애니메이션 제어"""
    global running
    running = not running
    if running:
        btn_toggle.config(text="  일시정지  ", bg="#E6F1FB", fg="#185FA5")
        status_lbl.config(text="● 실행 중", fg="#22C55E")
    else:
        btn_toggle.config(text="  재  생  ", bg=CARD, fg="#2C2C2A")
        status_lbl.config(text="● 일시정지", fg=GRAY)

def reset_all():
    """초기화 버튼 - 모든 공간 데이터를 0으로 리셋하고 저장"""
    global tick
    tick = 0
    for s in spaces:
        s["data"].extend([0]*MAX_POINTS)
        s["peak"] = 0; s["total"] = 0; s["count"] = 0
        s["window_peak"] = 0; s["peaks_log"] = []; s["peak_time"] = "—"
    save_data()
    refresh_detail()

btn_toggle = tk.Button(top, text="  일시정지  ", font=FONT, bg="#E6F1FB", fg="#185FA5",
    relief="flat", bd=0, padx=10, pady=4, cursor="hand2", command=toggle,
    highlightbackground="#B5D4F4", highlightthickness=1)
btn_toggle.pack(side="right", padx=(6,0))
tk.Button(top, text="  초기화  ", font=FONT, bg=CARD, fg="#2C2C2A",
    relief="flat", bd=0, padx=10, pady=4, cursor="hand2", command=reset_all,
    highlightbackground=BORDER, highlightthickness=1).pack(side="right")

# ── 공간 관리 패널 ──────────────────────────────────────
space_mgr = tk.Frame(page_realtime, bg=CARD, padx=14, pady=10,
    highlightbackground=BORDER, highlightthickness=1)
space_mgr.pack(fill="x", padx=16, pady=(4,0))
space_top = tk.Frame(space_mgr, bg=CARD)
space_top.pack(fill="x")
tk.Label(space_top, text="공간 관리", font=FONT, bg=CARD, fg=GRAY).pack(side="left")

# 현재 공간 수 / 최대 공간 수 표시 라벨
space_limit_lbl = tk.Label(space_top,
    text=f"현재 {len(spaces)}개 / 최대 {MAX_SPACES}개", font=FONT, bg=CARD, fg=GRAY)
space_limit_lbl.pack(side="left", padx=12)

def update_limit_label():
    """공간 수 표시 라벨 업데이트"""
    space_limit_lbl.config(text=f"현재 {len(spaces)}개 / 최대 {MAX_SPACES}개")

def add_space():
    """공간 추가 - 이름 입력받아 spaces 리스트에 추가"""
    if len(spaces) >= MAX_SPACES:
        messagebox.showwarning(f"최대 {MAX_SPACES}개", f"공간은 최대 {MAX_SPACES}개까지 추가할 수 있어요.")
        return
    name = simpledialog.askstring("공간 추가", "공간 이름 입력:", parent=root)
    if not name: return
    ch = len(spaces) + 1
    spaces.append({
        "name": name, "channel": ch,
        "data": deque([0]*MAX_POINTS, maxlen=MAX_POINTS),
        "peak": 0, "total": 0, "count": 0,
        "window_peak": 0, "peaks_log": [], "offset": random.randint(0,100), "peak_time": "—"
    })
    refresh_space_buttons(); refresh_overview(); update_limit_label()

def delete_space():
    """선택된 공간 삭제 (최소 1개는 유지)"""
    global selected_space
    if len(spaces) <= 1:
        messagebox.showwarning("최소 1개", "공간은 최소 1개 있어야 해요.")
        return
    spaces.pop(selected_space)
    selected_space = min(selected_space, len(spaces)-1)
    refresh_space_buttons(); refresh_overview(); refresh_detail(); update_limit_label()

def rename_space():
    """선택된 공간 이름 변경"""
    name = simpledialog.askstring("공간 이름 변경",
        f"새 이름 입력 (현재: {spaces[selected_space]['name']}):", parent=root)
    if name:
        spaces[selected_space]["name"] = name
        refresh_space_buttons(); refresh_overview()

def change_mb_count():
    """마이크로비트 개수 변경 - MAX_SPACES 업데이트"""
    global MAX_SPACES
    while True:
        new_count = simpledialog.askinteger("마이크로비트 개수 변경",
            f"현재 마이크로비트 총 개수: {MAX_SPACES + 1}개\n새 개수를 입력하세요. (수신용 1개 포함, 최소 2개)",
            parent=root, minvalue=1, maxvalue=10)
        if new_count is None: return
        if new_count < 2:
            messagebox.showwarning("개수 부족",
                "마이크로비트는 최소 2개가 필요해요.\n수신용 1개 + 소리 감지용 1개 이상이어야 해요.\n다시 입력해주세요.")
            continue
        break
    MAX_SPACES = new_count - 1
    update_limit_label()

# 공간 관리 버튼들
tk.Button(space_top, text="+ 공간 추가", font=FONT, bg="#E1F5EE", fg="#085041",
    relief="flat", bd=0, padx=10, pady=3, cursor="hand2", command=add_space,
    highlightbackground="#9FE1CB", highlightthickness=1).pack(side="right", padx=(6,0))
tk.Button(space_top, text="이름 변경", font=FONT, bg=CARD, fg="#2C2C2A",
    relief="flat", bd=0, padx=10, pady=3, cursor="hand2", command=rename_space,
    highlightbackground=BORDER, highlightthickness=1).pack(side="right", padx=(6,0))
tk.Button(space_top, text="공간 삭제", font=FONT, bg="#FCEBEB", fg="#A32D2D",
    relief="flat", bd=0, padx=10, pady=3, cursor="hand2", command=delete_space,
    highlightbackground="#F7C1C1", highlightthickness=1).pack(side="right", padx=(6,0))
tk.Button(space_top, text="마이크로비트 개수 변경", font=FONT, bg=CARD, fg="#2C2C2A",
    relief="flat", bd=0, padx=10, pady=3, cursor="hand2", command=change_mb_count,
    highlightbackground=BORDER, highlightthickness=1).pack(side="right", padx=(6,0))

# ── 공간 선택 탭 버튼들 ─────────────────────────────────
space_btn_frame = tk.Frame(space_mgr, bg=CARD)
space_btn_frame.pack(fill="x", pady=(8,0))
space_btns = []

def select_space(idx):
    """공간 탭 클릭 시 해당 공간 선택 및 상세 정보 업데이트"""
    global selected_space
    selected_space = idx
    refresh_space_buttons(); refresh_detail()

def refresh_space_buttons():
    """공간 탭 버튼 목록 새로 그리기 (선택된 공간 강조 표시)"""
    for w in space_btn_frame.winfo_children(): w.destroy()
    space_btns.clear()
    for i, s in enumerate(spaces):
        color = SPACE_COLORS[i % len(SPACE_COLORS)]
        is_sel = (i == selected_space)
        btn = tk.Button(space_btn_frame, text=s["name"], font=FONT,
            bg=color if is_sel else CARD, fg="#ffffff" if is_sel else "#2C2C2A",
            relief="flat", bd=0, padx=14, pady=4, cursor="hand2",
            command=lambda idx=i: select_space(idx),
            highlightbackground=color, highlightthickness=1)
        btn.pack(side="left", padx=(0,8))
        space_btns.append(btn)

refresh_space_buttons()

# ── 선택 공간 상세 영역 ─────────────────────────────────
detail_frame = tk.Frame(page_realtime, bg=BG)
detail_frame.pack(fill="both", expand=True, padx=16, pady=(6,0))

# 1. 전체 공간 최고 소음 카드
peak_info_card = tk.Frame(detail_frame, bg=CARD, padx=14, pady=12,
    highlightbackground=BORDER, highlightthickness=1)
peak_info_card.pack(fill="x", pady=(0,6))
tk.Label(peak_info_card, text="[ 전체 공간 최고 소음 ]", font=FONT, bg=CARD, fg=GRAY).pack(anchor="w")
peak_info_row1 = tk.Frame(peak_info_card, bg=CARD)
peak_info_row1.pack(fill="x", pady=(4,0))
tk.Label(peak_info_row1, text="가장 시끄러운 공간 : ", font=FONT, bg=CARD, fg=GRAY).pack(side="left")
peak_space_lbl = tk.Label(peak_info_row1, text="—", font=("Helvetica", 13, "bold"), bg=CARD, fg="#185FA5")
peak_space_lbl.pack(side="left")
peak_info_row2 = tk.Frame(peak_info_card, bg=CARD)
peak_info_row2.pack(fill="x", pady=(4,0))
tk.Label(peak_info_row2, text="최고측정소음 시간 : ", font=FONT, bg=CARD, fg=GRAY).pack(side="left")
peak_time_val = tk.Label(peak_info_row2, text="—", font=("Helvetica", 13, "bold"), bg=CARD, fg="#D85A30")
peak_time_val.pack(side="left")
tk.Label(peak_info_row2, text="   소리값 : ", font=FONT, bg=CARD, fg=GRAY).pack(side="left")
peak_val_lbl = tk.Label(peak_info_row2, text="—", font=("Helvetica", 13, "bold"), bg=CARD, fg="#D85A30")
peak_val_lbl.pack(side="left")

# 2. 전체 현황 카드
overview_card = tk.Frame(detail_frame, bg=CARD, padx=14, pady=10,
    highlightbackground=BORDER, highlightthickness=1)
overview_card.pack(fill="x", pady=(0,6))
tk.Label(overview_card, text="전체 현황", font=FONT, bg=CARD, fg=GRAY).pack(anchor="w", pady=(0,6))
overview_inner = tk.Frame(overview_card, bg=CARD)
overview_inner.pack(fill="x")

def refresh_overview():
    """전체 현황 카드 업데이트 - 공간별 현재값과 소음 단계 표시"""
    for w in overview_inner.winfo_children(): w.destroy()
    for i, s in enumerate(spaces):
        col_color = SPACE_COLORS[i % len(SPACE_COLORS)]
        cur = list(s["data"])[-1] if s["count"] > 0 else 0
        lv = get_level(cur)
        info = LEVELS[lv]
        f = tk.Frame(overview_inner, bg=CARD, highlightbackground=col_color, highlightthickness=2)
        f.pack(side="left", padx=(0,10), ipadx=10, ipady=6)
        tk.Label(f, text=s["name"], font=FONT, bg=CARD, fg=col_color).pack(anchor="w", padx=8, pady=(4,0))
        tk.Label(f, text=str(cur), font=("Helvetica", 20, "bold"), bg=CARD, fg=col_color).pack(anchor="w", padx=8)
        tk.Label(f, text=info["name"], font=("Helvetica", 10, "bold"),
            bg=info["bg"], fg=info["fg"], padx=6, pady=2).pack(anchor="w", padx=8, pady=(0,4))

refresh_overview()
stats_frame = tk.Frame(detail_frame, bg=BG)
stats_frame.pack(fill="x", pady=(0,6))
for i in range(3): stats_frame.columnconfigure(i, weight=1)

def make_stat(parent, title, val, color, col):
    """통계 카드 하나 생성 후 라벨 반환"""
    f = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
    tk.Label(f, text=title, font=FONT, bg=CARD, fg=GRAY).pack(anchor="w", padx=12, pady=(8,0))
    lbl = tk.Label(f, text=val, font=("Helvetica", 18, "bold"), bg=CARD, fg=color)
    lbl.pack(anchor="w", padx=12, pady=(0,8))
    f.grid(row=0, column=col, padx=(0 if col==0 else 6, 0), sticky="nsew")
    return lbl

lbl_cur  = make_stat(stats_frame, "현재 소리",  "—", "#2C2C2A", 0)
lbl_time = make_stat(stats_frame, "현재 시간",  "00:00:00", "#2C2C2A", 1)

# 선택 공간 최고 소음 카드
combined_card = tk.Frame(stats_frame, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
combined_card.grid(row=0, column=2, padx=(6,0), sticky="nsew")
tk.Label(combined_card, text="[ 선택 공간 최고 소음 ]", font=FONT, bg=CARD, fg=GRAY).pack(anchor="w", padx=12, pady=(8,2))
lbl_avg = tk.Label(combined_card, text="—", font=("Helvetica", 13, "bold"), bg=CARD, fg="#185FA5")
lbl_avg.pack(anchor="w", padx=12)
combined_row = tk.Frame(combined_card, bg=CARD)
combined_row.pack(anchor="w", padx=12, pady=(2,8))
lbl_peak_time = tk.Label(combined_row, text="—", font=("Helvetica", 12, "bold"), bg=CARD, fg="#D85A30")
lbl_peak_time.pack(side="left")
tk.Label(combined_row, text="  |  ", font=FONT, bg=CARD, fg=GRAY).pack(side="left")
lbl_peak = tk.Label(combined_row, text="—", font=("Helvetica", 12, "bold"), bg=CARD, fg="#D85A30")
lbl_peak.pack(side="left")

# 4. 실시간 그래프
graph_card = tk.Frame(detail_frame, bg=CARD, padx=14, pady=10,
    highlightbackground=BORDER, highlightthickness=1)
graph_card.pack(fill="both", expand=True, pady=(0,6))
graph_lbl = tk.Label(graph_card, text="실시간 소리 레벨", font=FONT, bg=CARD, fg=GRAY)
graph_lbl.pack(anchor="w")

fig, ax = plt.subplots(figsize=(8, 2.0))
fig.patch.set_facecolor("#ffffff")
ax.set_facecolor("#ffffff")
ax.set_ylim(0, 255); ax.set_xlim(0, MAX_POINTS)
ax.tick_params(colors=GRAY, labelsize=9)
for sp in ["top","right"]: ax.spines[sp].set_visible(False)
for sp in ["bottom","left"]: ax.spines[sp].set_color("#E0DED6")
ax.set_ylabel("소리 레벨", fontsize=9, color=GRAY)
ax.set_xticks([])
line_plot, = ax.plot(list(spaces[0]["data"]), color=SPACE_COLORS[0], linewidth=1.5)
hlines = []
time_labels = deque([""] * MAX_POINTS, maxlen=MAX_POINTS)

def draw_hlines():
    """그래프에 기준값 점선 그리기"""
    global hlines
    for h in hlines: h.remove()
    hlines = []
    colors = ["#1D9E75","#378ADD","#BA7517","#D85A30"]
    for i, t in enumerate(thresholds):
        h = ax.axhline(y=t, color=colors[i], linewidth=0.8, linestyle="--", alpha=0.6)
        ax.text(MAX_POINTS-1, t+3, str(t), fontsize=8, color=colors[i], ha="right")
        hlines.append(h)

draw_hlines()
canvas_fig = FigureCanvasTkAgg(fig, master=graph_card)
canvas_fig.get_tk_widget().pack(fill="both", expand=True)

# 실시간 그래프 가로 스크롤바
def rt_scroll(val):
    val = float(val)
    xrange = MAX_POINTS * 0.4
    xmin = val * MAX_POINTS
    ax.set_xlim(xmin, xmin + xrange)
    canvas_fig.draw_idle()

rt_scrollbar = tk.Scale(graph_card, from_=0, to=0.6, resolution=0.01,
    orient="horizontal", command=rt_scroll,
    bg=CARD, fg=GRAY, troughcolor="#E0DED6",
    highlightthickness=0, bd=0, sliderlength=40,
    showvalue=False, length=300)
rt_scrollbar.pack(pady=(2,0))

# ── 기준값 설정 패널 ────────────────────────────────────
thresh_card = tk.Frame(page_realtime, bg=CARD, padx=14, pady=8,
    highlightbackground=BORDER, highlightthickness=1)
thresh_card.pack(fill="x", padx=16, pady=(0,6))
tk.Label(thresh_card, text="기준값 설정 (0~255)", font=FONT, bg=CARD, fg=GRAY).pack(anchor="w", pady=(0,6))
thresh_row = tk.Frame(thresh_card, bg=CARD)
thresh_row.pack(fill="x")
thresh_entries = []
thresh_labels_text = ["매우 조용 ~", "조용 ~", "보통 ~", "시끄러움 ~"]
thresh_colors_list = ["#1D9E75", "#378ADD", "#BA7517", "#D85A30"]
for i in range(4):
    col = tk.Frame(thresh_row, bg=CARD)
    col.pack(side="left", padx=(0,16))
    tk.Label(col, text=thresh_labels_text[i], font=("Helvetica", 10),
        bg=CARD, fg=thresh_colors_list[i]).pack(anchor="w")
    var = tk.StringVar(value=str(thresholds[i]))
    tk.Entry(col, textvariable=var, width=6, font=FONT, justify="center",
        highlightbackground=BORDER, highlightthickness=1, relief="flat").pack(anchor="w")
    thresh_entries.append(var)

def apply_thresholds():
    """입력한 기준값 적용 - 그래프 기준선도 업데이트"""
    global thresholds
    new = []
    for i, v in enumerate(thresh_entries):
        try: val = max(0, min(255, int(v.get()))); new.append(val)
        except ValueError: new.append(thresholds[i])
    new.sort(); thresholds = new
    for i, v in enumerate(thresh_entries): v.set(str(thresholds[i]))
    draw_hlines(); canvas_fig.draw()

def reset_thresholds():
    """기준값을 기본값(50/100/150/200)으로 초기화"""
    global thresholds
    thresholds = [50, 100, 150, 200]
    for i, v in enumerate(thresh_entries): v.set(str(thresholds[i]))
    draw_hlines(); canvas_fig.draw()

tk.Button(thresh_row, text="  적용  ", font=FONT, bg="#E1F5EE", fg="#085041",
    relief="flat", bd=0, padx=10, pady=4, cursor="hand2", command=apply_thresholds,
    highlightbackground="#9FE1CB", highlightthickness=1).pack(side="left", pady=2)
tk.Button(thresh_row, text="  기준값 초기화  ", font=FONT, bg=CARD, fg="#2C2C2A",
    relief="flat", bd=0, padx=10, pady=4, cursor="hand2", command=reset_thresholds,
    highlightbackground=BORDER, highlightthickness=1).pack(side="left", padx=(8,0), pady=2)

def refresh_detail():
    """선택된 공간의 상세 정보(최고값, 평균, 그래프 색상 등) 업데이트"""
    s = spaces[selected_space]
    color = SPACE_COLORS[selected_space % len(SPACE_COLORS)]
    peak_space_lbl.config(text=s["name"])
    peak_time_val.config(text=s["peak_time"] if s["count"] > 0 else "—")
    peak_val_lbl.config(text=str(s["peak"]) if s["count"] > 0 else "—")
    lbl_cur.config(text="—" if s["count"]==0 else str(list(s["data"])[-1]))
    # 위 카드 - 전체 공간 최고 소음
    loudest = max(spaces, key=lambda x: x["peak"])
    if any(sp["count"]>0 for sp in spaces):
        peak_space_lbl.config(text=loudest["name"])
        peak_time_val.config(text=loudest["peak_time"])
        peak_val_lbl.config(text=str(loudest["peak"]))
    else:
        peak_space_lbl.config(text="—")
        peak_time_val.config(text="—")
        peak_val_lbl.config(text="—")
    # 아래 카드 - 선택 공간 최고 소음
    lbl_avg.config(text=s["name"])
    lbl_peak_time.config(text=s["peak_time"] if s["count"] > 0 else "—")
    lbl_peak.config(text=str(s["peak"]) if s["count"] > 0 else "—")
    line_plot.set_color(color)
    graph_lbl.config(text=f"실시간 소리 레벨 — {s['name']}")

# ════════════════════════════════════════════════════════
# 날짜별 기록 탭
# ════════════════════════════════════════════════════════
hist_left  = tk.Frame(page_history, bg=BG)   # 날짜 목록 영역
hist_left.pack(side="left", fill="y", padx=(16,6), pady=8)

# 날짜 상세 영역 - 스크롤 가능
hist_right_outer = tk.Frame(page_history, bg=BG)
hist_right_outer.pack(side="left", fill="both", expand=True, padx=(0,16), pady=(0,8))

hist_right_canvas = tk.Canvas(hist_right_outer, bg=BG, highlightthickness=0)
hist_right_sb = tk.Scrollbar(hist_right_outer, orient="vertical", command=hist_right_canvas.yview)
hist_right_canvas.configure(yscrollcommand=hist_right_sb.set)
hist_right_sb.pack(side="right", fill="y")
hist_right_canvas.pack(side="left", fill="both", expand=True)

hist_right = tk.Frame(hist_right_canvas, bg=BG)
hist_right_canvas.create_window((0,0), window=hist_right, anchor="nw")

def on_hist_right_configure(event):
    hist_right_canvas.configure(scrollregion=hist_right_canvas.bbox("all"))
    hist_right_canvas.itemconfig(1, width=hist_right_canvas.winfo_width())

hist_right.bind("<Configure>", on_hist_right_configure)
hist_right_canvas.bind("<Configure>", lambda e: hist_right_canvas.itemconfig(1, width=e.width))

# 날짜 목록 (스크롤 가능한 리스트)
tk.Label(hist_left, text="날짜 목록", font=FONT_BOLD, bg=BG, fg="#2C2C2A").pack(anchor="w", pady=(0,6))
hist_list_frame = tk.Frame(hist_left, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
hist_list_frame.pack(fill="y", expand=True)
hist_scrollbar = tk.Scrollbar(hist_list_frame)
hist_scrollbar.pack(side="right", fill="y")
hist_listbox = tk.Listbox(hist_list_frame, font=FONT, bg=CARD, fg="#2C2C2A",
    selectbackground="#185FA5", selectforeground="#ffffff",
    relief="flat", bd=0, width=14, yscrollcommand=hist_scrollbar.set)
hist_listbox.pack(fill="both", expand=True)
hist_scrollbar.config(command=hist_listbox.yview)

# 날짜 상세 영역
hist_title_row = tk.Frame(hist_right, bg=BG)
hist_title_row.pack(fill="x", pady=(0,8))

hist_detail_title = tk.Label(hist_title_row, text="날짜를 선택하세요",
    font=FONT_BOLD, bg=BG, fg="#2C2C2A")
hist_detail_title.pack(side="left")

# 날짜 선택 안 했을 때 안내 메시지
hist_no_select_lbl = tk.Label(hist_right, text="날짜를 선택하면 해당 날짜의 통계가 표시됩니다",
    font=FONT, bg=BG, fg=GRAY)
hist_no_select_lbl.pack(anchor="w", pady=(20,0))

compare_dates = []
compare_mode = [False]
first_date = [None]
change_mode = [False]       # 날짜 변경 모드 여부
change_target = [0]         # 변경할 날짜 인덱스 (0=첫번째, 1=두번째)
compared_dates = [None, None]  # 현재 비교 중인 두 날짜 저장
compare_type = [None]       # 비교 유형 저장: "max" / "min" / "normal"

def delete_history():
    """선택된 날짜의 히스토리 파일 삭제"""
    sel = hist_listbox.curselection()
    if not sel:
        messagebox.showwarning("선택 없음", "삭제할 날짜를 먼저 선택해주세요.")
        return
    date_str = hist_listbox.get(sel[0])
    confirm = messagebox.askyesno("삭제 확인", f"{date_str} 기록을 삭제할까요?\n삭제하면 복구할 수 없어요.")
    if not confirm:
        return
    hist_file = os.path.join(HIST_DIR, f"{date_str}.json")
    if os.path.exists(hist_file):
        os.remove(hist_file)
    hist_detail_title.config(text="날짜를 선택하세요")
    for w in hist_summary_frame.winfo_children(): w.destroy()
    for w in hist_compare_frame.winfo_children(): w.destroy()
    refresh_history_tab()

def toggle_compare_mode():
    """날짜 비교 모드 - 날짜 선택 후 버튼 클릭 시 비교"""
    sel = hist_listbox.curselection()

    if not compare_mode[0]:
        # 비교 모드 시작 - 첫번째 날짜 선택 확인
        if not sel:
            messagebox.showwarning("날짜 선택 없음", "먼저 비교할 첫 번째 날짜를 선택해주세요!")
            return
        first_date[0] = hist_listbox.get(sel[0])
        compare_mode[0] = True
        btn_compare.config(text="  비교 실행  ", bg="#1D9E75", fg="#ffffff")
        hist_detail_title.config(text=f"1번째: {first_date[0]}  →  2번째 날짜 클릭 후 비교 실행 버튼 누르세요")
    else:
        # 비교 실행 - 두번째 날짜 선택 확인
        if not sel:
            messagebox.showwarning("날짜 선택 없음", "비교할 두 번째 날짜를 선택해주세요!")
            return
        second_date = hist_listbox.get(sel[0])
        if second_date == first_date[0]:
            messagebox.showwarning("같은 날짜", "서로 다른 날짜를 선택해주세요!")
            return

        # 두 날짜 비교 표시
        hist_detail_title.config(text=f"{first_date[0]}  vs  {second_date}")
        for w in hist_compare_frame.winfo_children(): w.destroy()
        for w in hist_summary_frame.winfo_children(): w.destroy()

        hist_summary_outer.pack_forget()
        hist_compare_frame.pack(fill="both", expand=True)

        show_combined_compare(first_date[0], second_date)

        # 비교한 날짜 저장
        compared_dates[0] = first_date[0]
        compared_dates[1] = second_date
        compare_type[0] = "normal"  # 일반 날짜 비교

        compare_mode[0] = False
        first_date[0] = None
        btn_compare.config(text="  날짜 비교  ", bg="#E6F1FB", fg="#185FA5")

        # 비교 날짜 변경 버튼 표시
        btn_change_compare.pack(side="right", padx=(0,8))
        btn_maxmin.pack_forget()

tk.Button(hist_title_row, text="  선택 날짜 삭제  ", font=FONT, bg="#FCEBEB", fg="#A32D2D",
    relief="flat", bd=0, padx=10, pady=4, cursor="hand2", command=delete_history,
    highlightbackground="#F7C1C1", highlightthickness=1).pack(side="right")

def change_compare():
    """비교 날짜 변경 - 어떤 날짜 변경할지 선택"""
    if compared_dates[0] is None or compared_dates[1] is None:
        return

    popup = tk.Toplevel(root)
    popup.title("날짜 변경")
    popup.geometry("300x140")
    popup.configure(bg=BG)
    popup.resizable(False, False)

    tk.Label(popup, text="변경할 날짜를 선택하세요", font=FONT_BOLD, bg=BG, fg="#2C2C2A").pack(pady=(16,12))

    btn_row = tk.Frame(popup, bg=BG)
    btn_row.pack()

    def select_first():
        change_target[0] = 0
        change_mode[0] = True
        hist_detail_title.config(text=f"첫번째 날짜 변경 중 ({compared_dates[0]}) → 새 날짜를 클릭하세요")
        popup.destroy()

    def select_second():
        change_target[0] = 1
        change_mode[0] = True
        hist_detail_title.config(text=f"두번째 날짜 변경 중 ({compared_dates[1]}) → 새 날짜를 클릭하세요")
        popup.destroy()

    tk.Button(btn_row, text=compared_dates[0], font=FONT, bg="#E6F1FB", fg="#185FA5",
        relief="flat", bd=0, padx=14, pady=6, cursor="hand2", command=select_first,
        highlightbackground="#B5D4F4", highlightthickness=1).pack(side="left", padx=(0,10))
    tk.Button(btn_row, text=compared_dates[1], font=FONT, bg="#E6F1FB", fg="#185FA5",
        relief="flat", bd=0, padx=14, pady=6, cursor="hand2", command=select_second,
        highlightbackground="#B5D4F4", highlightthickness=1).pack(side="left")

btn_change_compare = tk.Button(hist_title_row, text="  비교 날짜 변경  ", font=FONT,
    bg="#E1F5EE", fg="#085041", relief="flat", bd=0, padx=10, pady=4,
    cursor="hand2", command=change_compare,
    highlightbackground="#9FE1CB", highlightthickness=1)
# 초기엔 숨겨둠 (비교 완료 후에만 표시)

maxmin_popup_open = [False]  # 중복 팝업 방지

def compare_max_min():
    """최고/최소 소음 날짜와 비교 - 단일 선택 날짜의 공간 기준"""
    if maxmin_popup_open[0]:
        return
    sel = hist_listbox.curselection()
    if not sel:
        messagebox.showwarning("날짜 선택 없음", "먼저 비교할 날짜를 선택해주세요!")
        return

    current_date = hist_listbox.get(sel[0])
    current_data = load_history_data(current_date)
    if not current_data:
        messagebox.showwarning("데이터 없음", "선택한 날짜의 데이터가 없어요!")
        return

    # 선택 날짜의 공간 목록
    current_spaces = [s["name"] for s in current_data.get("spaces", [])]

    # 다른 날짜들과 공통 공간 찾기
    all_dates = load_history_list()
    other_dates = [d for d in all_dates if d != current_date]
    common_spaces = set(current_spaces)
    for d in other_dates:
        data = load_history_data(d)
        if not data: continue
        other_spaces = set(s["name"] for s in data.get("spaces", []))
        common_spaces = common_spaces & other_spaces

    if not common_spaces:
        messagebox.showwarning("공통 공간 없음",
            "다른 날짜와 동일한 공간이 없어서\n비교할 수 없어요!")
        return

    # 공통 공간만 순서 유지하며 필터링
    filtered_spaces = [s for s in current_spaces if s in common_spaces]

    def find_max_min(space_name=None):
        max_date = max_val = None
        min_date = min_val = None
        for d in all_dates:
            data = load_history_data(d)
            if not data: continue
            spaces_data = data.get("spaces", [])
            if space_name:
                peaks = [s["peak"] for s in spaces_data if s["name"] == space_name and s.get("peak")]
            else:
                peaks = [s["peak"] for s in spaces_data if s["name"] in common_spaces and s.get("peak")]
            if not peaks: continue
            day_max = max(peaks)
            if max_val is None or day_max > max_val:
                max_val = day_max; max_date = d
            if min_val is None or day_max < min_val:
                min_val = day_max; min_date = d
        return max_date, min_date

    def show_maxmin_popup(space_name=None):
        max_date, min_date = find_max_min(space_name)
        if not max_date or not min_date:
            messagebox.showwarning("데이터 없음", "비교할 데이터가 부족해요!")
            return

        popup2 = tk.Toplevel(root)
        popup2.title("최고/최소 소음 날짜")
        popup2.geometry("360x160")
        popup2.configure(bg=BG)
        popup2.resizable(False, False)

        label = f"공간: {space_name}" if space_name else "전체 공통 공간 기준"
        tk.Label(popup2, text=f"기준을 선택하세요 ({label})",
            font=FONT_BOLD, bg=BG, fg="#2C2C2A").pack(pady=(16,12))

        btn_row2 = tk.Frame(popup2, bg=BG)
        btn_row2.pack()

        def compare_with(target_date, label):
            popup2.destroy()
            # 선택 후에 같은 날짜인지 체크
            if current_date == target_date:
                messagebox.showinfo("알림",
                    f"선택한 날짜({current_date})가\n{label}입니다!")
                return

            # 최고/최소 중 어떤 것인지 판별
            is_max = "최고" in label
            value_label = "최고" if is_max else "최소"

            # 어느 날짜가 실선/점선인지 결정
            # 최고 선택 시 더 높은 날짜가 실선, 최소 선택 시 더 낮은 날짜가 실선
            def get_date_value(d, sn):
                data = load_history_data(d)
                if not data: return 0
                spaces_list = data.get("spaces", [])
                if sn:
                    matched = [s for s in spaces_list if s["name"] == sn]
                    peaks = [s["peak"] for s in matched if s.get("peak")]
                else:
                    peaks = [s["peak"] for s in spaces_list if s.get("peak")]
                return max(peaks) if peaks else 0

            val_current = get_date_value(current_date, space_name)
            val_target  = get_date_value(target_date, space_name)

            if is_max:
                solid_date  = current_date if val_current >= val_target else target_date
                dashed_date = target_date  if val_current >= val_target else current_date
            else:
                solid_date  = current_date if val_current <= val_target else target_date
                dashed_date = target_date  if val_current <= val_target else current_date

            dates_ordered = [solid_date, dashed_date]

            hist_detail_title.config(text=f"{current_date}  vs  {target_date} ({label})")
            for w in hist_compare_frame.winfo_children(): w.destroy()
            hist_summary_outer.pack_forget()
            hist_compare_frame.pack(fill="both", expand=True)

            data1 = load_history_data(solid_date)
            data2 = load_history_data(dashed_date)

            if not data1 or not data2:
                return

            # 실선/점선 날짜 안내 표시
            legend_frame = tk.Frame(hist_compare_frame, bg=CARD, padx=14, pady=8,
                highlightbackground=BORDER, highlightthickness=1)
            legend_frame.pack(fill="x", pady=(0,6))
            tk.Label(legend_frame, text=f"공간: {space_name if space_name else '전체'}",
                font=FONT_BOLD, bg=CARD, fg="#2C2C2A").pack(anchor="w", pady=(0,6))
            row1 = tk.Frame(legend_frame, bg=CARD)
            row1.pack(fill="x", pady=2)
            tk.Label(row1, text="━━━━━━", font=("Helvetica", 14, "bold"),
                bg=CARD, fg="#185FA5").pack(side="left")
            tk.Label(row1, text=f"  실선  →  {solid_date}",
                font=("Helvetica", 12, "bold"), bg=CARD, fg="#185FA5").pack(side="left")
            row2 = tk.Frame(legend_frame, bg=CARD)
            row2.pack(fill="x", pady=2)
            tk.Label(row2, text="┅┅┅┅┅┅", font=("Helvetica", 14, "bold"),
                bg=CARD, fg="#D85A30").pack(side="left")
            tk.Label(row2, text=f"  점선  →  {dashed_date}",
                font=("Helvetica", 12, "bold"), bg=CARD, fg="#D85A30").pack(side="left")

            # 한 그래프에 두 날짜 꺾은선 합쳐서 표시
            graph_frame = tk.Frame(hist_compare_frame, bg=CARD, padx=10, pady=8,
                highlightbackground=BORDER, highlightthickness=1)
            graph_frame.pack(fill="x", pady=(0,6))
            tk.Label(graph_frame, text="소리 레벨  (드래그: 좌우이동)",
                font=("Helvetica", 9), bg=CARD, fg=GRAY).pack(anchor="w")

            fig_c, ax_c = plt.subplots(figsize=(7, 2.2))
            fig_c.patch.set_facecolor("#ffffff")
            ax_c.set_facecolor("#ffffff")
            ax_c.set_ylim(0, 270)
            ax_c.tick_params(colors=GRAY, labelsize=8)
            for sp in ["top","right"]: ax_c.spines[sp].set_visible(False)
            for sp in ["bottom","left"]: ax_c.spines[sp].set_color("#E0DED6")
            ax_c.set_ylabel("소음값", fontsize=9, color=GRAY)
            ax_c.set_xlabel("시간", fontsize=9, color=GRAY)

            # 공간별 색상 팔레트 (날짜×공간 조합마다 다른 색)
            space_color_map = {}
            color_pool = ["#185FA5", "#D85A30", "#1D9E75", "#7F77DD",
                          "#BA7517", "#A32D2D", "#085041", "#633806"]
            color_idx = [0]

            def get_space_color(sname):
                if sname not in space_color_map:
                    space_color_map[sname] = color_pool[color_idx[0] % len(color_pool)]
                    color_idx[0] += 1
                return space_color_map[sname]

            all_times = []
            line_objects = {}  # 공간명 → [line, fill] 저장

            for idx, (d, data) in enumerate([(solid_date, data1), (dashed_date, data2)]):
                spaces_list = data.get("spaces", [])
                if space_name:
                    target_spaces = [s for s in spaces_list if s["name"] == space_name]
                else:
                    target_spaces = spaces_list
                for s in target_spaces:
                    logs = sorted(s.get("peaks_log", []), key=lambda x: x["time"])
                    if not logs: continue
                    vals = [l["val"] for l in logs]
                    times = [l["time"] for l in logs]
                    if len(times) > len(all_times): all_times = times
                    s_color = get_space_color(s["name"])
                    line_style = "-" if idx == 0 else (0, (4, 3))
                    marker = "o" if idx == 0 else "s"
                    line, = ax_c.plot(range(len(vals)), vals, color=s_color,
                        linewidth=2.5, linestyle=line_style,
                        label=f"{d} - {s['name']}", marker=marker, markersize=3)
                    fill = ax_c.fill_between(range(len(vals)), vals, alpha=0.05, color=s_color)
                    key = f"{s['name']}_{idx}"
                    line_objects[key] = {"line": line, "fill": fill, "color": s_color}

            def highlight_space(selected_name):
                """선택된 공간 선 강조, 나머지 흐리게"""
                for key, obj in line_objects.items():
                    sn = key.rsplit("_", 1)[0]
                    if selected_name is None or sn == selected_name:
                        obj["line"].set_alpha(1.0)
                        obj["line"].set_linewidth(2.5)
                    else:
                        obj["line"].set_alpha(0.15)
                        obj["line"].set_linewidth(1.0)
                canvas_c.draw_idle()

            if all_times:
                n = len(all_times)
                step = max(1, n // 6)
                tick_pos = list(range(0, n, step))
                ax_c.set_xticks(tick_pos)
                ax_c.set_xticklabels([all_times[j] for j in tick_pos],
                    fontsize=7, color=GRAY, rotation=20)

            thresh_colors_h = ["#1D9E75","#378ADD","#BA7517","#D85A30"]
            for i, t in enumerate(thresholds):
                ax_c.axhline(y=t, color=thresh_colors_h[i], linewidth=0.7, linestyle="--", alpha=0.5)
            ax_c.legend(fontsize=7, loc="upper right")
            fig_c.tight_layout()

            canvas_c = FigureCanvasTkAgg(fig_c, master=graph_frame)
            canvas_c.get_tk_widget().pack(fill="x")
            canvas_c.draw()

            # 스크롤바
            total_pts = max(1, len(all_times))
            view_pts = max(1, int(total_pts * 0.4))
            def c_scroll(val):
                xmin = float(val) * total_pts
                ax_c.set_xlim(xmin, xmin + view_pts)
                canvas_c.draw_idle()
            tk.Scale(graph_frame, from_=0, to=max(0.01, 1 - view_pts/total_pts),
                resolution=0.01, orient="horizontal", command=c_scroll,
                bg=CARD, fg=GRAY, troughcolor="#E0DED6",
                highlightthickness=0, bd=0, sliderlength=40,
                showvalue=False, length=300).pack(pady=(2,0))

            plt.close(fig_c)

            # 수치 표시 - 공간별로 묶어서 표시
            val_frame = tk.Frame(hist_compare_frame, bg=CARD, padx=14, pady=10,
                highlightbackground=BORDER, highlightthickness=1)
            val_frame.pack(fill="x", pady=(0,6))

            # 공간 목록 수집
            all_space_names = []
            for d, data in [(solid_date, data1), (dashed_date, data2)]:
                spaces_list = data.get("spaces", [])
                if space_name:
                    target_spaces = [s for s in spaces_list if s["name"] == space_name]
                else:
                    target_spaces = spaces_list
                for s in target_spaces:
                    if s["name"] not in all_space_names:
                        all_space_names.append(s["name"])

            # 공간 선택 탭 + 접기/펼치기 (가로 스크롤)
            tab_outer = tk.Frame(val_frame, bg=CARD)
            tab_outer.pack(fill="x", pady=(4,6))
            tab_canvas = tk.Canvas(tab_outer, bg=CARD, highlightthickness=0, height=36)
            tab_hscroll = tk.Scrollbar(tab_outer, orient="horizontal", command=tab_canvas.xview)
            tab_canvas.configure(xscrollcommand=tab_hscroll.set)
            tab_frame = tk.Frame(tab_canvas, bg=CARD)
            tab_canvas.create_window((0,0), window=tab_frame, anchor="nw")
            def on_tab_configure(event):
                tab_canvas.configure(scrollregion=tab_canvas.bbox("all"))
            tab_frame.bind("<Configure>", on_tab_configure)
            tab_canvas.pack(fill="x")
            tab_hscroll.pack(fill="x")

            content_frames = {}
            active_space = [None]

            def select_space_tab(sname):
                # 이전 선택 닫기
                if active_space[0] and active_space[0] in content_frames:
                    content_frames[active_space[0]]["frame"].pack_forget()
                    content_frames[active_space[0]]["btn"].config(bg=CARD, fg="#2C2C2A")

                # 같은 탭 다시 누르면 닫기
                if active_space[0] == sname:
                    active_space[0] = None
                    highlight_space(None)  # 모두 동일 색광도
                    return

                # 새 탭 열기
                active_space[0] = sname
                sc = get_space_color(sname)
                content_frames[sname]["btn"].config(bg=sc, fg="#ffffff")
                content_frames[sname]["frame"].pack(fill="x", pady=(0,4))
                highlight_space(sname)  # 선택 공간 강조

            for sname in all_space_names:
                s_color = get_space_color(sname)

                # 탭 버튼
                btn = tk.Button(tab_frame, text=sname, font=FONT,
                    bg=CARD, fg="#2C2C2A", relief="flat", bd=0,
                    padx=12, pady=4, cursor="hand2",
                    command=lambda n=sname: select_space_tab(n),
                    highlightbackground=s_color, highlightthickness=1)
                btn.pack(side="left", padx=(0,6))

                # 해당 공간 수치 프레임 (초기엔 숨김)
                cf = tk.Frame(val_frame, bg=CARD)

                tk.Label(cf, text=f"📍 {sname}",
                    font=FONT_BOLD, bg=CARD, fg=s_color).pack(anchor="w", pady=(4,2))

                for idx, (d, data) in enumerate([(solid_date, data1), (dashed_date, data2)]):
                    spaces_list = data.get("spaces", [])
                    matched = [s for s in spaces_list if s["name"] == sname]
                    if not matched: continue
                    s = matched[0]
                    logs = s.get("peaks_log", [])
                    if not logs: continue
                    vals = [l["val"] for l in logs]
                    val = max(vals) if is_max else min(vals)
                    # 해당 값의 시간 찾기
                    val_time = next((l["time"] for l in logs if l["val"] == val), "—")
                    line_style_txt = "━━━ 실선" if idx == 0 else "┅┅┅ 점선"
                    line_color = "#185FA5" if idx == 0 else "#D85A30"
                    row = tk.Frame(cf, bg=CARD)
                    row.pack(fill="x", pady=2)
                    tk.Label(row, text=line_style_txt,
                        font=("Helvetica", 11, "bold"), bg=CARD, fg=line_color).pack(side="left")
                    tk.Label(row, text=f"  {d}",
                        font=FONT, bg=CARD, fg=GRAY).pack(side="left")
                    tk.Label(row, text=f"  {value_label}: ",
                        font=FONT, bg=CARD, fg=GRAY).pack(side="left")
                    tk.Label(row, text=str(val),
                        font=("Helvetica", 14, "bold"), bg=CARD,
                        fg=s_color).pack(side="left")
                    tk.Label(row, text=f"  시간: {val_time}",
                        font=FONT, bg=CARD, fg=GRAY).pack(side="left")

                tk.Frame(cf, bg="#E0DED6", height=1).pack(fill="x", pady=(4,0))
                content_frames[sname] = {"frame": cf, "btn": btn}

            compared_dates[0] = current_date
            compared_dates[1] = target_date
            compare_type[0] = "max" if is_max else "min"  # 최고/최소 비교 유형 저장
            btn_change_compare.pack(side="right", padx=(0,8))
            btn_maxmin.pack_forget()

        tk.Button(btn_row2, text=f"최고 소음 날짜\n{max_date}",
            font=FONT, bg="#FAECE7", fg="#D85A30",
            relief="flat", bd=0, padx=14, pady=6, cursor="hand2",
            command=lambda: compare_with(max_date, "최고 소음 날짜"),
            highlightbackground="#F7C1C1", highlightthickness=1).pack(side="left", padx=(0,10))

        tk.Button(btn_row2, text=f"최소 소음 날짜\n{min_date}",
            font=FONT, bg="#E6F1FB", fg="#185FA5",
            relief="flat", bd=0, padx=14, pady=6, cursor="hand2",
            command=lambda: compare_with(min_date, "최소 소음 날짜"),
            highlightbackground="#B5D4F4", highlightthickness=1).pack(side="left")

    # 공간 선택 팝업
    maxmin_popup_open[0] = True
    popup1 = tk.Toplevel(root)
    popup1.title("공간 선택")
    popup1.geometry("420x200")
    popup1.configure(bg=BG)
    popup1.resizable(False, False)
    popup1.protocol("WM_DELETE_WINDOW", lambda: [setattr(maxmin_popup_open, '__setitem__', None) or maxmin_popup_open.__setitem__(0, False), popup1.destroy()])

    tk.Label(popup1, text="기준 공간을 선택하세요 (공통 공간만 표시)",
        font=FONT_BOLD, bg=BG, fg="#2C2C2A").pack(pady=(12,6))

    # 검색창
    search_var = tk.StringVar()
    search_entry = tk.Entry(popup1, textvariable=search_var, font=FONT,
        highlightbackground=BORDER, highlightthickness=1, relief="flat")
    search_entry.pack(fill="x", padx=16, pady=(0,8))
    search_entry.insert(0, "🔍 공간 검색...")
    search_entry.bind("<FocusIn>", lambda e: search_entry.delete(0, "end") if search_entry.get().startswith("🔍") else None)

    # 가로 스크롤 버튼 영역
    btn_outer = tk.Frame(popup1, bg=BG)
    btn_outer.pack(fill="x", padx=16, pady=(0,8))
    btn_canvas = tk.Canvas(btn_outer, bg=BG, highlightthickness=0, height=44)
    btn_hscroll = tk.Scrollbar(btn_outer, orient="horizontal", command=btn_canvas.xview)
    btn_canvas.configure(xscrollcommand=btn_hscroll.set)
    btn_row1 = tk.Frame(btn_canvas, bg=BG)
    btn_canvas.create_window((0,0), window=btn_row1, anchor="nw")
    def on_btn_configure(event):
        btn_canvas.configure(scrollregion=btn_canvas.bbox("all"))
    btn_row1.bind("<Configure>", on_btn_configure)
    btn_canvas.pack(fill="x")
    btn_hscroll.pack(fill="x")

    all_space_btns = []

    def select_space(space_name=None):
        maxmin_popup_open[0] = False
        popup1.destroy()
        show_maxmin_popup(space_name)

    def refresh_space_btns(*args):
        for w in btn_row1.winfo_children(): w.destroy()
        keyword = search_var.get().strip()
        if keyword.startswith("🔍"): keyword = ""

        # 전체 버튼
        tk.Button(btn_row1, text="전체", font=FONT, bg=CARD, fg="#2C2C2A",
            relief="flat", bd=0, padx=12, pady=6, cursor="hand2",
            command=lambda: select_space(None),
            highlightbackground=BORDER, highlightthickness=1).pack(side="left", padx=(0,8))

        # 검색 필터링된 공간 버튼
        for i, name in enumerate(filtered_spaces):
            if keyword and keyword.lower() not in name.lower():
                continue
            color = SPACE_COLORS[i % len(SPACE_COLORS)]
            tk.Button(btn_row1, text=name, font=FONT, bg=CARD, fg=color,
                relief="flat", bd=0, padx=12, pady=6, cursor="hand2",
                command=lambda n=name: select_space(n),
                highlightbackground=color, highlightthickness=1).pack(side="left", padx=(0,8))

    search_var.trace("w", refresh_space_btns)
    refresh_space_btns()

btn_maxmin = tk.Button(hist_title_row, text="  최고/최소 소음 날짜와 비교  ", font=FONT,
    bg=CARD, fg="#2C2C2A", relief="flat", bd=0, padx=10, pady=4,
    cursor="hand2", command=compare_max_min,
    highlightbackground=BORDER, highlightthickness=1)
# 초기엔 숨겨둠 (단일 날짜 선택 후에만 표시)

btn_compare = tk.Button(hist_title_row, text="  날짜 비교  ", font=FONT, bg="#E6F1FB", fg="#185FA5",
    relief="flat", bd=0, padx=10, pady=4, cursor="hand2", command=toggle_compare_mode,
    highlightbackground="#B5D4F4", highlightthickness=1)
btn_compare.pack(side="right", padx=(0,8))

# 단일 날짜 카드 영역
hist_summary_outer = tk.Frame(hist_right, bg=BG)
hist_summary_outer.pack(fill="x", pady=(0,6))

hist_summary_canvas = tk.Canvas(hist_summary_outer, bg=BG, highlightthickness=0, height=160)
hist_summary_hscroll = tk.Scrollbar(hist_summary_outer, orient="horizontal",
    command=hist_summary_canvas.xview)
hist_summary_canvas.configure(xscrollcommand=hist_summary_hscroll.set)

hist_summary_frame = tk.Frame(hist_summary_canvas, bg=BG)
hist_summary_canvas.create_window((0,0), window=hist_summary_frame, anchor="nw")

def on_summary_configure(event):
    hist_summary_canvas.configure(scrollregion=hist_summary_canvas.bbox("all"))

hist_summary_frame.bind("<Configure>", on_summary_configure)
hist_summary_canvas.pack(fill="x")
hist_summary_hscroll.pack(fill="x")

# 비교 영역 - 단순 프레임
hist_compare_frame = tk.Frame(hist_right, bg=BG)
hist_compare_frame.pack(fill="both", expand=True)

def show_combined_compare(date1, date2):
    """두 날짜 합쳐진 그래프 + 공간 탭 + 최고값 수치 표시"""
    data1 = load_history_data(date1)
    data2 = load_history_data(date2)
    if not data1 or not data2:
        return

    spaces1 = {s["name"]: s for s in data1.get("spaces", [])}
    spaces2 = {s["name"]: s for s in data2.get("spaces", [])}
    all_snames = list(dict.fromkeys(list(spaces1.keys()) + list(spaces2.keys())))

    # 합쳐진 그래프
    graph_frame2 = tk.Frame(hist_compare_frame, bg=CARD, padx=10, pady=8,
        highlightbackground=BORDER, highlightthickness=1)
    graph_frame2.pack(fill="x", pady=(0,6))
    tk.Label(graph_frame2, text="소리 레벨  (실선: 첫번째 날짜 / 점선: 두번째 날짜)",
        font=("Helvetica", 9), bg=CARD, fg=GRAY).pack(anchor="w")

    fig2, ax2 = plt.subplots(figsize=(7, 2.2))
    fig2.patch.set_facecolor("#ffffff")
    ax2.set_facecolor("#ffffff")
    ax2.set_ylim(0, 270)
    ax2.tick_params(colors=GRAY, labelsize=8)
    for sp in ["top","right"]: ax2.spines[sp].set_visible(False)
    for sp in ["bottom","left"]: ax2.spines[sp].set_color("#E0DED6")
    ax2.set_ylabel("소음값", fontsize=9, color=GRAY)
    ax2.set_xlabel("시간", fontsize=9, color=GRAY)

    all_times2 = []
    line_objects2 = {}
    for i, sname in enumerate(all_snames):
        s_color = SPACE_COLORS[i % len(SPACE_COLORS)]
        for idx, (d, sdict) in enumerate([(date1, spaces1), (date2, spaces2)]):
            if sname not in sdict: continue
            s = sdict[sname]
            logs = sorted(s.get("peaks_log", []), key=lambda x: x["time"])
            if not logs: continue
            vals = [l["val"] for l in logs]
            times = [l["time"] for l in logs]
            if len(times) > len(all_times2): all_times2 = times
            line_style = "-" if idx == 0 else (0, (4, 3))
            marker = "o" if idx == 0 else "s"
            line2, = ax2.plot(range(len(vals)), vals, color=s_color,
                linewidth=2.5, linestyle=line_style,
                label=f"{d} - {sname}", marker=marker, markersize=3)
            ax2.fill_between(range(len(vals)), vals, alpha=0.05, color=s_color)
            line_objects2[f"{sname}_{idx}"] = {"line": line2, "color": s_color}

    def highlight_space2(selected_name):
        for key, obj in line_objects2.items():
            sn = key.rsplit("_", 1)[0]
            if selected_name is None or sn == selected_name:
                obj["line"].set_alpha(1.0)
                obj["line"].set_linewidth(2.5)
            else:
                obj["line"].set_alpha(0.15)
                obj["line"].set_linewidth(1.0)
        canvas2.draw_idle()

    if all_times2:
        n = len(all_times2)
        step = max(1, n // 6)
        tick_pos = list(range(0, n, step))
        ax2.set_xticks(tick_pos)
        ax2.set_xticklabels([all_times2[j] for j in tick_pos], fontsize=7, color=GRAY, rotation=20)

    thresh_colors_h = ["#1D9E75","#378ADD","#BA7517","#D85A30"]
    for i, t in enumerate(thresholds):
        ax2.axhline(y=t, color=thresh_colors_h[i], linewidth=0.7, linestyle="--", alpha=0.5)
    ax2.legend(fontsize=7, loc="upper right")
    fig2.tight_layout()

    canvas2 = FigureCanvasTkAgg(fig2, master=graph_frame2)
    canvas2.get_tk_widget().pack(fill="x")
    canvas2.draw()

    total_pts2 = max(1, len(all_times2))
    view_pts2 = max(1, int(total_pts2 * 0.4))
    def scroll2(val):
        xmin = float(val) * total_pts2
        ax2.set_xlim(xmin, xmin + view_pts2)
        canvas2.draw_idle()
    tk.Scale(graph_frame2, from_=0, to=max(0.01, 1 - view_pts2/total_pts2),
        resolution=0.01, orient="horizontal", command=scroll2,
        bg=CARD, fg=GRAY, troughcolor="#E0DED6",
        highlightthickness=0, bd=0, sliderlength=40,
        showvalue=False, length=300).pack(pady=(2,0))
    plt.close(fig2)

    # 공간 선택 탭 + 최고값 수치
    val_frame2 = tk.Frame(hist_compare_frame, bg=CARD, padx=14, pady=8,
        highlightbackground=BORDER, highlightthickness=1)
    val_frame2.pack(fill="x", pady=(0,6))
    tk.Label(val_frame2, text="공간 선택 (클릭하면 그래프 강조)",
        font=FONT, bg=CARD, fg=GRAY).pack(anchor="w", pady=(0,6))
    tab_canvas2 = tk.Canvas(val_frame2, bg=CARD, highlightthickness=0, height=36)
    tab_hscroll2 = tk.Scrollbar(val_frame2, orient="horizontal", command=tab_canvas2.xview)
    tab_canvas2.configure(xscrollcommand=tab_hscroll2.set)
    tab_btn_frame2 = tk.Frame(tab_canvas2, bg=CARD)
    tab_canvas2.create_window((0,0), window=tab_btn_frame2, anchor="nw")
    def on_tab2_configure(event):
        tab_canvas2.configure(scrollregion=tab_canvas2.bbox("all"))
    tab_btn_frame2.bind("<Configure>", on_tab2_configure)
    tab_canvas2.pack(fill="x")
    tab_hscroll2.pack(fill="x")

    val_content2 = tk.Frame(val_frame2, bg=CARD)
    active2 = [None]
    active_val2 = [None]  # 현재 선택된 최고/최소
    tab_btns2 = {}
    space_val_frames2 = {}

    for i, sname in enumerate(all_snames):
        s_color = SPACE_COLORS[i % len(SPACE_COLORS)]
        cf2 = tk.Frame(val_content2, bg=CARD)
        tk.Label(cf2, text=f"📍 {sname}",
            font=FONT_BOLD, bg=CARD, fg=s_color).pack(anchor="w", pady=(4,2))

        # 최고 / 최소 두 섹션
        maxmin_btns = {}
        maxmin_frames = {}

        for val_type, val_label, val_color in [("max", "최고", "#D85A30"), ("min", "최소", "#185FA5")]:
            # 섹션 버튼
            sec_btn = tk.Button(cf2, text=val_label, font=FONT_BOLD,
                bg=CARD, fg=val_color, relief="flat", bd=0,
                padx=10, pady=3, cursor="hand2",
                highlightbackground=val_color, highlightthickness=1)
            sec_btn.pack(anchor="w", pady=(4,0))

            # 수치 내용 프레임 (초기 숨김)
            sec_frame = tk.Frame(cf2, bg=CARD)

            for idx, (d, sdict) in enumerate([(date1, spaces1), (date2, spaces2)]):
                if sname not in sdict: continue
                s = sdict[sname]
                logs = s.get("peaks_log", [])
                if not logs: continue
                vals = [l["val"] for l in logs]
                val = max(vals) if val_type == "max" else min(vals)
                val_time = next((l["time"] for l in logs if l["val"] == val), "—")
                line_style_txt = "━━━ 실선" if idx == 0 else "┅┅┅ 점선"
                line_color = "#185FA5" if idx == 0 else "#D85A30"
                row = tk.Frame(sec_frame, bg=CARD)
                row.pack(fill="x", pady=2)
                tk.Label(row, text=line_style_txt,
                    font=("Helvetica", 11, "bold"), bg=CARD, fg=line_color).pack(side="left")
                tk.Label(row, text=f"  {d}",
                    font=FONT, bg=CARD, fg=GRAY).pack(side="left")
                tk.Label(row, text=f"  {val_label}: ",
                    font=FONT, bg=CARD, fg=GRAY).pack(side="left")
                tk.Label(row, text=str(val),
                    font=("Helvetica", 14, "bold"), bg=CARD, fg=s_color).pack(side="left")
                tk.Label(row, text=f"  시간: {val_time}",
                    font=FONT, bg=CARD, fg=GRAY).pack(side="left")

            maxmin_btns[val_type] = sec_btn
            maxmin_frames[val_type] = sec_frame

            def make_val_btn(vt=val_type, vc=val_color, sn=sname, sf=sec_frame, mb=maxmin_btns):
                def on_click():
                    # 이전 선택 닫기
                    if active_val2[0]:
                        prev_sn, prev_vt = active_val2[0]
                        if prev_sn in space_val_frames2:
                            prev_frames = space_val_frames2[prev_sn]["maxmin_frames"]
                            prev_btns = space_val_frames2[prev_sn]["maxmin_btns"]
                            if prev_vt in prev_frames:
                                prev_frames[prev_vt].pack_forget()
                            if prev_vt in prev_btns:
                                prev_vt_color = "#D85A30" if prev_vt == "max" else "#185FA5"
                                prev_btns[prev_vt].config(bg=CARD, fg=prev_vt_color)

                    # 같은 버튼 다시 누르면 닫기
                    if active_val2[0] == (sn, vt):
                        active_val2[0] = None
                        highlight_space2(None)
                        return

                    # 새 선택 열기
                    active_val2[0] = (sn, vt)
                    mb[vt].config(bg=vc, fg="#ffffff")
                    sf.pack(fill="x", padx=8, pady=(2,4))

                    # 그래프 업데이트 - 최고/최소 기준으로 실선/점선 결정
                    is_max_sel = (vt == "max")
                    def get_val(d, sn2):
                        data = load_history_data(d)
                        if not data: return 0
                        spaces_list = data.get("spaces", [])
                        matched = [s for s in spaces_list if s["name"] == sn2]
                        logs = matched[0].get("peaks_log", []) if matched else []
                        vals = [l["val"] for l in logs]
                        return max(vals) if vals else 0

                    v1 = get_val(date1, sn)
                    v2 = get_val(date2, sn)
                    if is_max_sel:
                        solid_sn = date1 if v1 >= v2 else date2
                    else:
                        solid_sn = date1 if v1 <= v2 else date2

                    # 그래프 선 스타일 업데이트
                    for key, obj in line_objects2.items():
                        key_sn = key.rsplit("_", 1)[0]
                        key_idx = int(key.rsplit("_", 1)[1])
                        if key_sn == sn:
                            is_solid = (key_idx == 0 and solid_sn == date1) or \
                                       (key_idx == 1 and solid_sn == date2)
                            obj["line"].set_linestyle("-" if is_solid else (0,(4,3)))
                            obj["line"].set_alpha(1.0)
                            obj["line"].set_linewidth(2.5)
                        else:
                            obj["line"].set_alpha(0.15)
                            obj["line"].set_linewidth(1.0)
                    canvas2.draw_idle()
                return on_click

            sec_btn.config(command=make_val_btn())

        tk.Frame(cf2, bg="#E0DED6", height=1).pack(fill="x", pady=(4,0))
        space_val_frames2[sname] = {"frame": cf2, "maxmin_btns": maxmin_btns, "maxmin_frames": maxmin_frames}

        def make_tab(sn=sname, sc=s_color):
            def on_click():
                if active2[0] == sn:
                    active2[0] = None
                    active_val2[0] = None
                    tab_btns2[sn].config(bg=CARD, fg="#2C2C2A")
                    highlight_space2(None)
                    space_val_frames2[sn]["frame"].pack_forget()
                    val_content2.pack_forget()
                else:
                    if active2[0] and active2[0] in tab_btns2:
                        tab_btns2[active2[0]].config(bg=CARD, fg="#2C2C2A")
                        space_val_frames2[active2[0]]["frame"].pack_forget()
                    active2[0] = sn
                    tab_btns2[sn].config(bg=sc, fg="#ffffff")
                    highlight_space2(sn)
                    val_content2.pack(fill="x", pady=(6,0))
                    space_val_frames2[sn]["frame"].pack(fill="x")
            return on_click

        btn2 = tk.Button(tab_btn_frame2, text=sname, font=FONT,
            bg=CARD, fg="#2C2C2A", relief="flat", bd=0,
            padx=12, pady=4, cursor="hand2",
            command=make_tab(),
            highlightbackground=s_color, highlightthickness=1)
        btn2.pack(side="left", padx=(0,6))
        tab_btns2[sname] = btn2


def draw_space_cards(parent, data, date_str):
    """공간별 카드 + 꺾은선 그래프 그리기 (드래그/휠 이동 가능)"""
    tk.Label(parent, text=f"📅 {date_str}", font=FONT_BOLD, bg=BG, fg="#2C2C2A").pack(anchor="w", pady=(6,4))

    # 공간 카드 (가로 스크롤)
    card_outer = tk.Frame(parent, bg=BG)
    card_outer.pack(fill="x", pady=(0,6))
    card_canvas = tk.Canvas(card_outer, bg=BG, highlightthickness=0, height=160)
    card_hscroll = tk.Scrollbar(card_outer, orient="horizontal", command=card_canvas.xview)
    card_canvas.configure(xscrollcommand=card_hscroll.set)
    card_row = tk.Frame(card_canvas, bg=BG)
    card_canvas.create_window((0,0), window=card_row, anchor="nw")
    def on_card_configure(event):
        card_canvas.configure(scrollregion=card_canvas.bbox("all"))
    card_row.bind("<Configure>", on_card_configure)
    card_canvas.pack(fill="x")
    card_hscroll.pack(fill="x")
    for i, s in enumerate(data.get("spaces", [])):
        color = SPACE_COLORS[i % len(SPACE_COLORS)]
        lv = get_level(s["peak"])
        info = LEVELS[lv]
        f = tk.Frame(card_row, bg=CARD, highlightbackground=color, highlightthickness=2)
        f.pack(side="left", padx=(0,10), ipadx=10, ipady=6)
        tk.Label(f, text=s["name"], font=FONT, bg=CARD, fg=color).pack(anchor="w", padx=8, pady=(4,0))
        tk.Label(f, text=f"최고: {s['peak']}", font=("Helvetica", 14, "bold"), bg=CARD, fg=color).pack(anchor="w", padx=8)
        tk.Label(f, text=f"시간: {s['peak_time']}", font=("Helvetica", 10), bg=CARD, fg=GRAY).pack(anchor="w", padx=8)
        tk.Label(f, text=f"평균: {s['avg']}", font=("Helvetica", 10), bg=CARD, fg=GRAY).pack(anchor="w", padx=8)
        tk.Label(f, text=info["name"], font=("Helvetica", 10, "bold"),
            bg=info["bg"], fg=info["fg"], padx=6, pady=2).pack(anchor="w", padx=8, pady=(2,4))

    # 꺾은선 그래프
    spaces_data = data.get("spaces", [])
    if not spaces_data:
        tk.Frame(parent, bg=BORDER, height=2).pack(fill="x", pady=(4,0))
        return

    graph_frame = tk.Frame(parent, bg=CARD, padx=10, pady=8,
        highlightbackground=BORDER, highlightthickness=1)
    graph_frame.pack(fill="x", pady=(0,6))
    tk.Label(graph_frame, text="소리 레벨  (드래그: 좌우이동 / 휠: 확대축소)",
        font=("Helvetica", 9), bg=CARD, fg=GRAY).pack(anchor="w")

    fig_h, ax_h = plt.subplots(figsize=(7, 2.2))
    fig_h.patch.set_facecolor("#ffffff")
    ax_h.set_facecolor("#ffffff")
    ax_h.set_ylim(0, 270)
    ax_h.tick_params(colors=GRAY, labelsize=8)
    for sp in ["top","right"]: ax_h.spines[sp].set_visible(False)
    for sp in ["bottom","left"]: ax_h.spines[sp].set_color("#E0DED6")

    # y축 라벨
    ax_h.set_ylabel("소음값", fontsize=9, color=GRAY)

    # 모든 공간 데이터 수집 및 그리기
    all_times = []
    for i, s in enumerate(spaces_data):
        color = SPACE_COLORS[i % len(SPACE_COLORS)]
        logs = sorted(s.get("peaks_log", []), key=lambda x: x["time"])
        if not logs: continue
        times = [l["time"] for l in logs]
        vals  = [l["val"]  for l in logs]
        all_times = times if len(times) > len(all_times) else all_times
        ax_h.plot(range(len(vals)), vals, color=color, linewidth=1.5, label=s["name"])
        ax_h.fill_between(range(len(vals)), vals, alpha=0.07, color=color)

    # x축 시간 라벨 설정
    if all_times:
        n = len(all_times)
        step = max(1, n // 6)
        tick_pos = list(range(0, n, step))
        ax_h.set_xticks(tick_pos)
        ax_h.set_xticklabels([all_times[j] for j in tick_pos],
            fontsize=7, color=GRAY, rotation=20)
        # x축 끝에 "시간" 라벨
        ax_h.set_xlabel("시간", fontsize=9, color=GRAY)
        ax_h.xaxis.set_label_coords(1.02, -0.15)

    # 기준선
    thresh_colors_h = ["#1D9E75","#378ADD","#BA7517","#D85A30"]
    for i, t in enumerate(thresholds):
        ax_h.axhline(y=t, color=thresh_colors_h[i], linewidth=0.7, linestyle="--", alpha=0.5)

    if len(spaces_data) > 1:
        ax_h.legend(fontsize=8, loc="upper right")

    fig_h.tight_layout()

    canvas_h = FigureCanvasTkAgg(fig_h, master=graph_frame)
    canvas_h.get_tk_widget().pack(fill="x")
    canvas_h.draw()

    # 가로 스크롤바로 시간대 이동
    total_pts = max(len(s.get("peaks_log", [])) for s in spaces_data) if spaces_data else 1
    view_pts = max(1, int(total_pts * 0.4))

    def hist_scroll(val):
        val = float(val)
        xmin = val * total_pts
        ax_h.set_xlim(xmin, xmin + view_pts)
        canvas_h.draw_idle()

    tk.Scale(graph_frame, from_=0, to=max(0.01, 1 - view_pts/total_pts),
        resolution=0.01, orient="horizontal", command=hist_scroll,
        bg=CARD, fg=GRAY, troughcolor="#E0DED6",
        highlightthickness=0, bd=0, sliderlength=40,
        showvalue=False, length=300).pack(pady=(2,0))

    plt.close(fig_h)

    # 구분선
    tk.Frame(parent, bg=BORDER, height=2).pack(fill="x", pady=(4,0))

def show_history_detail(date_str):
    """날짜 클릭 시 단일 보기로 표시 (비교는 버튼으로 처리)"""

    # 날짜 변경 모드
    if change_mode[0]:
        other = compared_dates[1 - change_target[0]]
        if date_str == other:
            messagebox.showwarning("같은 날짜",
                f"선택한 날짜({date_str})가 이미 비교 중인 날짜와 같아요!\n다른 날짜를 선택해주세요.")
            return
        compared_dates[change_target[0]] = date_str
        change_mode[0] = False
        # 변경된 날짜로 다시 비교 표시
        hist_detail_title.config(text=f"{compared_dates[0]}  vs  {compared_dates[1]}")
        for w in hist_compare_frame.winfo_children(): w.destroy()
        hist_compare_frame.pack(fill="both", expand=True)
        hist_summary_outer.pack_forget()

        # 비교 유형에 따라 다른 방식으로 표시
        if compare_type[0] in ("max", "min"):
            # 최고/최소 비교였으면 같은 방식으로 재표시
            is_max_saved = compare_type[0] == "max"
            label_saved = "최고 소음 날짜" if is_max_saved else "최소 소음 날짜"
            # compare_with 재호출 대신 직접 표시
            _d1, _d2 = compared_dates[0], compared_dates[1]
            # 실선/점선 재결정
            def _get_val(d):
                data = load_history_data(d)
                if not data: return 0
                peaks = [s["peak"] for s in data.get("spaces", []) if s.get("peak")]
                return max(peaks) if peaks else 0
            v1, v2 = _get_val(_d1), _get_val(_d2)
            if is_max_saved:
                solid_d  = _d1 if v1 >= v2 else _d2
                dashed_d = _d2 if v1 >= v2 else _d1
            else:
                solid_d  = _d1 if v1 <= v2 else _d2
                dashed_d = _d2 if v1 <= v2 else _d1

            legend_frame = tk.Frame(hist_compare_frame, bg=CARD, padx=14, pady=8,
                highlightbackground=BORDER, highlightthickness=1)
            legend_frame.pack(fill="x", pady=(0,6))
            tk.Label(legend_frame, text=f"비교: {label_saved}",
                font=FONT_BOLD, bg=CARD, fg="#2C2C2A").pack(anchor="w", pady=(0,6))
            row1 = tk.Frame(legend_frame, bg=CARD)
            row1.pack(fill="x", pady=2)
            tk.Label(row1, text="━━━━━━", font=("Helvetica", 14, "bold"),
                bg=CARD, fg="#185FA5").pack(side="left")
            tk.Label(row1, text=f"  실선  →  {solid_d}",
                font=("Helvetica", 12, "bold"), bg=CARD, fg="#185FA5").pack(side="left")
            row2 = tk.Frame(legend_frame, bg=CARD)
            row2.pack(fill="x", pady=2)
            tk.Label(row2, text="┅┅┅┅┅┅", font=("Helvetica", 14, "bold"),
                bg=CARD, fg="#D85A30").pack(side="left")
            tk.Label(row2, text=f"  점선  →  {dashed_d}",
                font=("Helvetica", 12, "bold"), bg=CARD, fg="#D85A30").pack(side="left")
            show_combined_compare(solid_d, dashed_d)
        else:
            show_combined_compare(compared_dates[0], compared_dates[1])
        return

    if compare_mode[0]:
        # 비교 모드일 때는 2번째 날짜 선택만 안내
        hist_detail_title.config(text=f"1번째: {first_date[0]}  →  {date_str} 선택됨, 비교 실행 버튼 누르세요")
        return

    # 단일 보기 모드
    data = load_history_data(date_str)
    if not data:
        hist_detail_title.config(text=f"{date_str} — 데이터 없음")
        return
    hist_detail_title.config(text=f"{date_str} 기록")
    for w in hist_summary_frame.winfo_children(): w.destroy()
    for w in hist_compare_frame.winfo_children(): w.destroy()

    # 이전 그래프/파이차트 카드 제거
    hist_no_select_lbl.pack_forget()  # 안내 메시지 숨기기
    for w in hist_right.winfo_children():
        if w not in [hist_title_row, hist_summary_outer, hist_compare_frame]:
            w.destroy()

    # 단일 보기일 때 summary_frame 보이게, compare_frame 숨기기
    hist_compare_frame.pack_forget()
    hist_summary_outer.pack(fill="x", pady=(0,6))
    btn_change_compare.pack_forget()
    btn_maxmin.pack(side="right", padx=(0,8))

    # 꺾은선 그래프 + 전체 평균선
    graph_card_s = tk.Frame(hist_right, bg=CARD, padx=14, pady=10,
        highlightbackground=BORDER, highlightthickness=1)
    graph_card_s.pack(fill="x", pady=(0,6))
    tk.Label(graph_card_s, text="소리 레벨  (회색: 전체 날짜 평균)  카드 클릭 시 강조",
        font=("Helvetica", 9), bg=CARD, fg=GRAY).pack(anchor="w")

    fig_s, ax_s = plt.subplots(figsize=(7, 2.2))
    fig_s.patch.set_facecolor("#ffffff")
    ax_s.set_facecolor("#ffffff")
    ax_s.set_ylim(0, 270)
    ax_s.tick_params(colors=GRAY, labelsize=8)
    for sp in ["top","right"]: ax_s.spines[sp].set_visible(False)
    for sp in ["bottom","left"]: ax_s.spines[sp].set_color("#E0DED6")
    ax_s.set_ylabel("소음값", fontsize=9, color=GRAY)
    ax_s.set_xlabel("시간", fontsize=9, color=GRAY)

    # 선택 날짜 공간별 꺾은선
    all_times_s = []
    space_lines = {}
    for i, s in enumerate(data.get("spaces", [])):
        color = SPACE_COLORS[i % len(SPACE_COLORS)]
        logs = sorted(s.get("peaks_log", []), key=lambda x: x["time"])
        if not logs: continue
        vals = [l["val"] for l in logs]
        times = [l["time"] for l in logs]
        if len(times) > len(all_times_s): all_times_s = times
        line_s, = ax_s.plot(range(len(vals)), vals, color=color, linewidth=2.0,
            label=s["name"], marker="o", markersize=3)
        ax_s.fill_between(range(len(vals)), vals, alpha=0.06, color=color)
        space_lines[s["name"]] = line_s

    # 전체 날짜 평균선 계산
    all_dates = load_history_list()
    space_avg_map = {}
    for d in all_dates:
        d_data = load_history_data(d)
        if not d_data: continue
        for s in d_data.get("spaces", []):
            sname = s["name"]
            logs = s.get("peaks_log", [])
            if not logs: continue
            vals = [l["val"] for l in logs]
            if sname not in space_avg_map:
                space_avg_map[sname] = []
            space_avg_map[sname].extend(vals)

    avg_lines = {}
    for sname, all_vals in space_avg_map.items():
        if not all_vals: continue
        avg_val = round(sum(all_vals) / len(all_vals))
        avg_line = ax_s.axhline(y=avg_val, color="#AAAAAA", linewidth=1.2,
            linestyle="--", alpha=0.8, label=f"{sname} 전체평균({avg_val})")
        avg_lines[sname] = avg_line

    def highlight_single(sname=None):
        for sn, line in space_lines.items():
            if sname is None or sn == sname:
                line.set_alpha(1.0); line.set_linewidth(2.5)
            else:
                line.set_alpha(0.15); line.set_linewidth(1.0)
        for sn, line in avg_lines.items():
            if sname is None or sn == sname:
                line.set_alpha(0.9); line.set_linewidth(2.0); line.set_color("#555555")
            else:
                line.set_alpha(0.15); line.set_linewidth(0.8); line.set_color("#CCCCCC")
        canvas_s.draw_idle()

    # x축 시간 표시
    if all_times_s:
        n = len(all_times_s)
        step = max(1, n // 6)
        tick_pos = list(range(0, n, step))
        ax_s.set_xticks(tick_pos)
        ax_s.set_xticklabels([all_times_s[j] for j in tick_pos],
            fontsize=7, color=GRAY, rotation=20)

    thresh_colors_h = ["#1D9E75","#378ADD","#BA7517","#D85A30"]
    for i, t in enumerate(thresholds):
        ax_s.axhline(y=t, color=thresh_colors_h[i], linewidth=0.7, linestyle="--", alpha=0.4)

    ax_s.legend(fontsize=7, loc="upper right")
    fig_s.tight_layout()

    canvas_s = FigureCanvasTkAgg(fig_s, master=graph_card_s)
    canvas_s.get_tk_widget().pack(fill="x")
    canvas_s.draw()

    total_pts_s = max(1, len(all_times_s))
    view_pts_s = max(1, int(total_pts_s * 0.4))
    def s_scroll(val):
        xmin = float(val) * total_pts_s
        ax_s.set_xlim(xmin, xmin + view_pts_s)
        canvas_s.draw_idle()
    tk.Scale(graph_card_s, from_=0, to=max(0.01, 1 - view_pts_s/total_pts_s),
        resolution=0.01, orient="horizontal", command=s_scroll,
        bg=CARD, fg=GRAY, troughcolor="#E0DED6",
        highlightthickness=0, bd=0, sliderlength=40,
        showvalue=False, length=300).pack(pady=(2,0))
    plt.close(fig_s)

    # 소음 단계별 비율 파이차트
    pie_card = tk.Frame(hist_right, bg=CARD, padx=14, pady=10,
        highlightbackground=BORDER, highlightthickness=1)
    pie_card.pack(fill="x", pady=(0,6))
    pie_title_lbl = tk.Label(pie_card, text="소음 단계별 비율  (전체 공간)",
        font=FONT, bg=CARD, fg=GRAY)
    pie_title_lbl.pack(anchor="w")
    pie_chart_frame = tk.Frame(pie_card, bg=CARD)
    pie_chart_frame.pack(anchor="w")

    def draw_pie(spaces_data, title="전체 공간"):
        for w in pie_chart_frame.winfo_children():
            w.destroy()
        pie_title_lbl.config(text=f"소음 단계별 비율  ({title})")
        level_counts = [0] * 5
        for s in spaces_data:
            for log in s.get("peaks_log", []):
                lv = get_level(log["val"])
                level_counts[lv] += 1
        total = sum(level_counts)
        if total > 0:
            labels_pie = [LEVELS[i]["name"] for i in range(5) if level_counts[i] > 0]
            sizes_pie  = [level_counts[i] for i in range(5) if level_counts[i] > 0]
            colors_pie = [LEVELS[i]["color"] for i in range(5) if level_counts[i] > 0]
            fig_pie, ax_pie = plt.subplots(figsize=(4, 2.2))
            fig_pie.patch.set_facecolor("#ffffff")
            ax_pie.pie(sizes_pie, labels=labels_pie, colors=colors_pie,
                autopct="%1.1f%%", startangle=90,
                textprops={"fontsize": 8, "color": "#2C2C2A"})
            ax_pie.axis("equal")
            fig_pie.tight_layout()
            canvas_pie = FigureCanvasTkAgg(fig_pie, master=pie_chart_frame)
            canvas_pie.get_tk_widget().pack()
            canvas_pie.draw()
            plt.close(fig_pie)
        else:
            tk.Label(pie_chart_frame, text="측정 데이터가 없어요",
                font=FONT, bg=CARD, fg=GRAY).pack(anchor="w")

    # 초기: 전체 공간 파이차트
    draw_pie(data.get("spaces", []))

    # 공간 카드에 클릭 기능 추가 (그래프 그린 후에 카드 생성)
    active_card = [None]
    for i, s in enumerate(data.get("spaces", [])):
        color = SPACE_COLORS[i % len(SPACE_COLORS)]
        lv = get_level(s["peak"])
        info = LEVELS[lv]
        f = tk.Frame(hist_summary_frame, bg=CARD, highlightbackground=color,
            highlightthickness=2, cursor="hand2")
        f.pack(side="left", padx=(0,10), ipadx=10, ipady=6)
        tk.Label(f, text=s["name"], font=FONT, bg=CARD, fg=color).pack(anchor="w", padx=8, pady=(4,0))
        tk.Label(f, text=f"최고: {s['peak']}", font=("Helvetica", 16, "bold"), bg=CARD, fg=color).pack(anchor="w", padx=8)
        tk.Label(f, text=f"시간: {s['peak_time']}", font=("Helvetica", 10), bg=CARD, fg=GRAY).pack(anchor="w", padx=8)
        tk.Label(f, text=f"평균: {s['avg']}", font=("Helvetica", 10), bg=CARD, fg=GRAY).pack(anchor="w", padx=8)
        tk.Label(f, text=info["name"], font=("Helvetica", 10, "bold"),
            bg=info["bg"], fg=info["fg"], padx=6, pady=2).pack(anchor="w", padx=8, pady=(2,4))

        def make_card_click(sn=s["name"], frame=f, col=color, space_data=s):
            def on_click(event=None):
                if active_card[0] == sn:
                    active_card[0] = None
                    frame.config(highlightthickness=2)
                    highlight_single(None)
                    draw_pie(data.get("spaces", []))  # 전체로 복귀
                else:
                    for w in hist_summary_frame.winfo_children():
                        w.config(highlightthickness=2)
                    active_card[0] = sn
                    frame.config(highlightthickness=4)
                    highlight_single(sn)
                    draw_pie([space_data], sn)  # 선택 공간만
            return on_click

        click_fn = make_card_click()
        f.bind("<Button-1>", click_fn)
        for child in f.winfo_children():
            child.bind("<Button-1>", click_fn)

def on_hist_select(event):
    """날짜 리스트에서 날짜 선택 시 상세 정보 표시"""
    sel = hist_listbox.curselection()
    if sel:
        date_str = hist_listbox.get(sel[0])
        show_history_detail(date_str)

hist_listbox.bind("<<ListboxSelect>>", on_hist_select)

def refresh_history_tab():
    """날짜별 기록 탭 열 때 날짜 목록 새로고침"""
    hist_listbox.delete(0, tk.END)
    for d in load_history_list():
        hist_listbox.insert(tk.END, d)

# ════════════════════════════════════════════════════════
# 주간 통계 탭
# ════════════════════════════════════════════════════════

# 상단 타이틀
weekly_top = tk.Frame(page_weekly, bg=BG, padx=16, pady=8)
weekly_top.pack(fill="x")
weekly_title_lbl = tk.Label(weekly_top, text="이번 주 통계",
    font=FONT_BOLD, bg=BG, fg="#2C2C2A")
weekly_title_lbl.pack(side="left")

weekly_offset = [0]
weekly_compare_offset = [None]  # 비교할 주 offset

def weekly_prev():
    weekly_offset[0] -= 1
    refresh_weekly_tab()

def weekly_next():
    weekly_offset[0] += 1
    refresh_weekly_tab()

def weekly_select_week():
    """주 선택 팝업 - 데이터 있는 날짜 기준"""
    import datetime
    today = datetime.date.today()

    all_dates = load_history_list()
    available_years = sorted(set(d[:4] for d in all_dates), reverse=True)
    if not available_years:
        messagebox.showwarning("데이터 없음", "저장된 기록이 없어요!")
        return

    popup = tk.Toplevel(root)
    popup.title("주 선택")
    popup.geometry("300x180")
    popup.configure(bg=BG)
    popup.resizable(False, False)
    tk.Label(popup, text="년도와 월을 선택하세요", font=FONT_BOLD, bg=BG, fg="#2C2C2A").pack(pady=(14,10))

    sel_frame = tk.Frame(popup, bg=BG)
    sel_frame.pack()

    # 년도 드롭다운 (데이터 있는 년도만)
    tk.Label(sel_frame, text="년도", font=FONT, bg=BG, fg=GRAY).grid(row=0, column=0, padx=(0,4))
    year_var = tk.StringVar(value=str(today.year) if str(today.year) in available_years else available_years[0])
    year_cb = ttk.Combobox(sel_frame, textvariable=year_var, values=available_years,
        width=7, font=FONT, state="readonly")
    year_cb.grid(row=0, column=1, padx=(0,16))

    # 월 드롭다운
    tk.Label(sel_frame, text="월", font=FONT, bg=BG, fg=GRAY).grid(row=0, column=2, padx=(0,4))
    month_var = tk.StringVar(value=str(today.month))
    months = [str(m) for m in range(1, 13)]
    month_cb = ttk.Combobox(sel_frame, textvariable=month_var, values=months,
        width=4, font=FONT, state="readonly")
    month_cb.grid(row=0, column=3)

    def apply():
        try:
            y = int(year_var.get())
            m = int(month_var.get())
            # 해당 년월에 데이터 있는지 확인
            prefix = f"{y}-{m:02d}"
            has_data = any(d.startswith(prefix) for d in all_dates)
            if not has_data:
                messagebox.showwarning("데이터 없음", f"{y}년 {m}월에 저장된 기록이 없어요!")
                return
            # 해당 월의 첫째 날 기준으로 주 offset 계산
            target = datetime.date(y, m, 1)
            monday_this = today - datetime.timedelta(days=today.weekday())
            monday_target = target - datetime.timedelta(days=target.weekday())
            diff_weeks = (monday_target - monday_this).days // 7
            weekly_offset[0] = diff_weeks
            popup.destroy()
            refresh_weekly_tab()
        except ValueError:
            pass

    tk.Button(popup, text="  선택  ", font=FONT_BOLD, bg="#185FA5", fg="#ffffff",
        relief="flat", bd=0, padx=14, pady=6, cursor="hand2", command=apply,
        highlightbackground="#185FA5", highlightthickness=1).pack(pady=(16,0))

def weekly_compare():
    """주 비교 팝업"""
    import datetime
    popup = tk.Toplevel(root)
    popup.title("비교할 주 선택")
    popup.geometry("320x160")
    popup.configure(bg=BG)
    popup.resizable(False, False)
    tk.Label(popup, text="비교할 주를 선택하세요", font=FONT_BOLD, bg=BG, fg="#2C2C2A").pack(pady=(14,10))
    btn_row = tk.Frame(popup, bg=BG)
    btn_row.pack()
    offsets = [("이번 주", 0), ("지난 주", -1), ("2주 전", -2), ("3주 전", -3)]
    for label, offset in offsets:
        if offset == weekly_offset[0]:
            continue  # 현재 보고 있는 주는 제외
        def go(o=offset, l=label):
            weekly_compare_offset[0] = o
            popup.destroy()
            refresh_weekly_tab()
        tk.Button(btn_row, text=label, font=FONT, bg=CARD, fg="#2C2C2A",
            relief="flat", bd=0, padx=10, pady=4, cursor="hand2", command=go,
            highlightbackground=BORDER, highlightthickness=1).pack(side="left", padx=4)

tk.Button(weekly_top, text="◀", font=FONT, bg=CARD, fg="#2C2C2A",
    relief="flat", bd=0, padx=8, pady=3, cursor="hand2", command=weekly_prev,
    highlightbackground=BORDER, highlightthickness=1).pack(side="right", padx=(4,0))
tk.Button(weekly_top, text="주 선택", font=FONT, bg=CARD, fg="#2C2C2A",
    relief="flat", bd=0, padx=8, pady=3, cursor="hand2", command=weekly_select_week,
    highlightbackground=BORDER, highlightthickness=1).pack(side="right", padx=(4,0))
tk.Button(weekly_top, text="▶", font=FONT, bg=CARD, fg="#2C2C2A",
    relief="flat", bd=0, padx=8, pady=3, cursor="hand2", command=weekly_next,
    highlightbackground=BORDER, highlightthickness=1).pack(side="right", padx=(4,0))
tk.Button(weekly_top, text="주간 비교", font=FONT, bg="#E6F1FB", fg="#185FA5",
    relief="flat", bd=0, padx=8, pady=3, cursor="hand2", command=weekly_compare,
    highlightbackground="#B5D4F4", highlightthickness=1).pack(side="right", padx=(4,0))

# 공간 선택 카드 영역 (가로 스크롤)
weekly_search_frame = tk.Frame(page_weekly, bg=BG, padx=16)
weekly_search_frame.pack(fill="x", pady=(0,4))
weekly_search_var = tk.StringVar()
weekly_search_entry = tk.Entry(weekly_search_frame, textvariable=weekly_search_var,
    font=FONT, highlightbackground=BORDER, highlightthickness=1, relief="flat")
weekly_search_entry.pack(fill="x")
weekly_search_entry.insert(0, "🔍 공간 검색...")
weekly_search_entry.bind("<FocusIn>", lambda e: weekly_search_entry.delete(0, "end")
    if weekly_search_entry.get().startswith("🔍") else None)
weekly_search_entry.bind("<FocusOut>", lambda e: weekly_search_entry.insert(0, "🔍 공간 검색...")
    if not weekly_search_entry.get() else None)
weekly_search_var.trace("w", lambda *a: refresh_weekly_tab())

weekly_card_outer = tk.Frame(page_weekly, bg=BG, padx=16)
weekly_card_outer.pack(fill="x", pady=(0,6))
weekly_card_canvas = tk.Canvas(weekly_card_outer, bg=BG, highlightthickness=0, height=100)
weekly_card_hscroll = tk.Scrollbar(weekly_card_outer, orient="horizontal",
    command=weekly_card_canvas.xview)
weekly_card_canvas.configure(xscrollcommand=weekly_card_hscroll.set)
weekly_card_frame = tk.Frame(weekly_card_canvas, bg=BG)
weekly_card_canvas.create_window((0,0), window=weekly_card_frame, anchor="nw")
def on_weekly_card_configure(event):
    weekly_card_canvas.configure(scrollregion=weekly_card_canvas.bbox("all"))
weekly_card_frame.bind("<Configure>", on_weekly_card_configure)
weekly_card_canvas.pack(fill="x")
weekly_card_hscroll.pack(fill="x")

# 그래프 영역
weekly_graph_card = tk.Frame(page_weekly, bg=CARD, padx=14, pady=10,
    highlightbackground=BORDER, highlightthickness=1)
weekly_graph_lbl = tk.Label(weekly_graph_card,
    text="공간을 선택하면 이번 주 통계가 표시됩니다",
    font=FONT, bg=CARD, fg=GRAY)
weekly_graph_lbl.pack(anchor="w")
weekly_graph_inner = tk.Frame(weekly_graph_card, bg=CARD)
weekly_graph_inner.pack(fill="x")

weekly_no_select_lbl = tk.Label(page_weekly,
    text="공간을 선택하면 이번 주 통계가 나타납니다",
    font=FONT, bg=BG, fg=GRAY)
weekly_no_select_lbl.pack(anchor="w", padx=16, pady=(8,0))

weekly_pie_card = tk.Frame(page_weekly, bg=CARD, padx=14, pady=10,
    highlightbackground=BORDER, highlightthickness=1)
weekly_pie_title = tk.Label(weekly_pie_card, text="", font=FONT, bg=CARD, fg=GRAY)
weekly_pie_title.pack(anchor="w")
weekly_pie_frame = tk.Frame(weekly_pie_card, bg=CARD)
weekly_pie_frame.pack(anchor="w")

active_weekly_space = [None]
weekly_fig = [None]
weekly_canvas_widget = [None]

def draw_weekly_graph(sname, color):
    """선택 공간의 해당 주 요일별 최고값 막대그래프"""
    for w in weekly_graph_inner.winfo_children():
        w.destroy()
    if weekly_fig[0]:
        plt.close(weekly_fig[0])

    weekly_graph_lbl.config(text=f"{sname}  요일별 최고 소음값")

    # 해당 주 날짜 계산
    import datetime
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday()) + datetime.timedelta(weeks=weekly_offset[0])
    week_dates = [(monday + datetime.timedelta(days=i)) for i in range(7)]
    day_labels = ["월", "화", "수", "목", "금", "토", "일"]

    # 날짜별 해당 공간 최고값 수집
    vals = []
    for d in week_dates:
        d_str = d.strftime("%Y-%m-%d")
        d_data = load_history_data(d_str)
        if not d_data:
            vals.append(0)
            continue
        matched = [s for s in d_data.get("spaces", []) if s["name"] == sname]
        vals.append(matched[0]["peak"] if matched else 0)

    fig_w, ax_w = plt.subplots(figsize=(7, 2.2))
    fig_w.patch.set_facecolor("#ffffff")
    ax_w.set_facecolor("#ffffff")
    ax_w.set_ylim(0, 270)
    ax_w.tick_params(colors=GRAY, labelsize=9)
    for sp in ["top","right"]: ax_w.spines[sp].set_visible(False)
    for sp in ["bottom","left"]: ax_w.spines[sp].set_color("#E0DED6")
    ax_w.set_ylabel("소음값", fontsize=9, color=GRAY)

    bars = ax_w.bar(day_labels, vals, color=color, width=0.5, alpha=0.85)

    # 오늘 날짜 강조 (이번 주일 때만)
    if weekly_offset[0] == 0:
        today_idx = today.weekday()
        bars[today_idx].set_alpha(1.0)
        bars[today_idx].set_edgecolor("#2C2C2A")
        bars[today_idx].set_linewidth(2)

    # 막대 위에 값 표시
    for bar, val in zip(bars, vals):
        if val > 0:
            ax_w.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 3,
                str(val), ha="center", va="bottom", fontsize=9, color=GRAY)

    # 기준선
    thresh_colors_h = ["#1D9E75","#378ADD","#BA7517","#D85A30"]
    for i, t in enumerate(thresholds):
        ax_w.axhline(y=t, color=thresh_colors_h[i], linewidth=0.7, linestyle="--", alpha=0.5)

    fig_w.tight_layout()
    weekly_fig[0] = fig_w

    canvas_w = FigureCanvasTkAgg(fig_w, master=weekly_graph_inner)
    canvas_w.get_tk_widget().pack(fill="x")
    canvas_w.draw()
    weekly_canvas_widget[0] = canvas_w

    # 파이차트 - 해당 주 선택 공간 소음 단계별 비율
    for w in weekly_pie_frame.winfo_children():
        w.destroy()
    weekly_pie_title.config(text=f"소음 단계별 비율  ({sname})")

    # 해당 주 날짜의 피크 로그 수집
    import datetime
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday()) + datetime.timedelta(weeks=weekly_offset[0])
    week_dates = [(monday + datetime.timedelta(days=i)) for i in range(7)]
    level_counts_w = [0] * 5
    for d in week_dates:
        d_str = d.strftime("%Y-%m-%d")
        d_data = load_history_data(d_str)
        if not d_data: continue
        matched = [s for s in d_data.get("spaces", []) if s["name"] == sname]
        if not matched: continue
        for log in matched[0].get("peaks_log", []):
            lv = get_level(log["val"])
            level_counts_w[lv] += 1

    total_w = sum(level_counts_w)
    if total_w > 0:
        labels_w = [LEVELS[i]["name"] for i in range(5) if level_counts_w[i] > 0]
        sizes_w  = [level_counts_w[i] for i in range(5) if level_counts_w[i] > 0]
        colors_w = [LEVELS[i]["color"] for i in range(5) if level_counts_w[i] > 0]
        fig_wp, ax_wp = plt.subplots(figsize=(4, 2.2))
        fig_wp.patch.set_facecolor("#ffffff")
        ax_wp.pie(sizes_w, labels=labels_w, colors=colors_w,
            autopct="%1.1f%%", startangle=90,
            textprops={"fontsize": 8, "color": "#2C2C2A"})
        ax_wp.axis("equal")
        fig_wp.tight_layout()
        canvas_wp = FigureCanvasTkAgg(fig_wp, master=weekly_pie_frame)
        canvas_wp.get_tk_widget().pack()
        canvas_wp.draw()
        plt.close(fig_wp)
    else:
        tk.Label(weekly_pie_frame, text="측정 데이터가 없어요",
            font=FONT, bg=CARD, fg=GRAY).pack(anchor="w")

def refresh_weekly_tab():
    """주간 통계 탭 열 때 공간 카드 새로고침"""
    import datetime
    prev_space = active_weekly_space[0]  # 이전 선택 공간 기억
    for w in weekly_card_frame.winfo_children():
        w.destroy()
    active_weekly_space[0] = None
    weekly_graph_lbl.config(text="공간을 선택하면 이번 주 통계가 표시됩니다")
    weekly_pie_title.config(text="")
    for w in weekly_graph_inner.winfo_children():
        w.destroy()
    for w in weekly_pie_frame.winfo_children():
        w.destroy()
    weekly_graph_card.pack_forget()
    weekly_pie_card.pack_forget()
    weekly_no_select_lbl.pack(anchor="w", padx=16, pady=(8,0))

    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday()) + datetime.timedelta(weeks=weekly_offset[0])
    sunday = monday + datetime.timedelta(days=6)
    if weekly_offset[0] == 0:
        weekly_title_lbl.config(text=f"이번 주 통계  ({monday.strftime('%m/%d')} ~ {sunday.strftime('%m/%d')})")
    elif weekly_offset[0] == -1:
        weekly_title_lbl.config(text=f"지난 주 통계  ({monday.strftime('%m/%d')} ~ {sunday.strftime('%m/%d')})")
    else:
        weekly_title_lbl.config(text=f"{abs(weekly_offset[0])}주 {'전' if weekly_offset[0] < 0 else '후'} 통계  ({monday.strftime('%m/%d')} ~ {sunday.strftime('%m/%d')})")



    # 전체 날짜에서 공간 목록 수집
    all_snames = []
    for d in load_history_list():
        d_data = load_history_data(d)
        if not d_data: continue
        for s in d_data.get("spaces", []):
            if s["name"] not in all_snames:
                all_snames.append(s["name"])

    # 현재 앱 공간도 포함
    for s in spaces:
        if s["name"] not in all_snames:
            all_snames.append(s["name"])

    if not all_snames:
        tk.Label(weekly_card_frame, text="공간 데이터가 없어요",
            font=FONT, bg=BG, fg=GRAY).pack(anchor="w")
        return

    weekly_btns = {}

    for i, sname in enumerate(all_snames):
        color = SPACE_COLORS[i % len(SPACE_COLORS)]

        # 검색 필터링
        keyword = weekly_search_var.get().strip()
        if keyword and not keyword.startswith("🔍") and keyword.lower() not in sname.lower():
            continue

        def make_click(sn=sname, col=color):
            def on_click(event=None):
                if active_weekly_space[0] == sn:
                    active_weekly_space[0] = None
                    weekly_btns[sn].config(bg=CARD, fg=col, highlightthickness=1)
                    for w in weekly_graph_inner.winfo_children(): w.destroy()
                    weekly_graph_lbl.config(text="공간을 선택하면 이번 주 통계가 표시됩니다")
                    weekly_graph_card.pack_forget()
                    weekly_pie_card.pack_forget()
                    weekly_no_select_lbl.pack(anchor="w", padx=16, pady=(8,0))
                    refresh_weekly_tab()
                    return
                if active_weekly_space[0] and active_weekly_space[0] in weekly_btns:
                    prev = active_weekly_space[0]
                    prev_col = SPACE_COLORS[all_snames.index(prev) % len(SPACE_COLORS)]
                    weekly_btns[prev].config(bg=CARD, fg=prev_col, highlightthickness=1)
                active_weekly_space[0] = sn
                weekly_btns[sn].config(bg=col, fg="#ffffff", highlightthickness=3)
                weekly_no_select_lbl.pack_forget()
                weekly_graph_card.pack(fill="x", padx=16, pady=(0,8))
                weekly_pie_card.pack(fill="x", padx=16, pady=(0,8))
                draw_weekly_graph(sn, col)
            return on_click

        btn_w = tk.Frame(weekly_card_frame, bg=CARD, highlightbackground=color,
            highlightthickness=1, cursor="hand2")
        btn_w.pack(side="left", padx=(0,10), ipadx=12, ipady=8)
        tk.Label(btn_w, text=sname, font=FONT_BOLD, bg=CARD, fg=color).pack(padx=8, pady=(6,2))

        click_fn = make_click()
        btn_w.bind("<Button-1>", click_fn)
        for child in btn_w.winfo_children():
            child.bind("<Button-1>", click_fn)
        weekly_btns[sname] = btn_w

    # 이전에 선택된 공간이 있으면 자동 선택
    if prev_space and prev_space in weekly_btns:
        color = SPACE_COLORS[all_snames.index(prev_space) % len(SPACE_COLORS)]
        active_weekly_space[0] = prev_space
        weekly_btns[prev_space].config(bg=color, fg="#ffffff", highlightthickness=3)
        weekly_no_select_lbl.pack_forget()
        weekly_graph_card.pack(fill="x", padx=16, pady=(0,8))
        weekly_pie_card.pack(fill="x", padx=16, pady=(0,8))
        draw_weekly_graph(prev_space, color)

monthly_top = tk.Frame(page_monthly, bg=BG, padx=16, pady=8)
monthly_top.pack(fill="x")
monthly_title_lbl = tk.Label(monthly_top, text="이번 달 통계",
    font=FONT_BOLD, bg=BG, fg="#2C2C2A")
monthly_title_lbl.pack(side="left")

monthly_offset = [0]
monthly_compare_offset = [None]

def monthly_prev():
    monthly_offset[0] -= 1
    refresh_monthly_tab()

def monthly_next():
    monthly_offset[0] += 1
    refresh_monthly_tab()

def monthly_select_month():
    """월 직접 선택 팝업 - 데이터 있는 년도만 표시"""
    import datetime
    today = datetime.date.today()

    # 저장된 날짜에서 년도 목록 추출
    all_dates = load_history_list()
    available_years = sorted(set(d[:4] for d in all_dates), reverse=True)
    if not available_years:
        messagebox.showwarning("데이터 없음", "저장된 기록이 없어요!")
        return

    popup = tk.Toplevel(root)
    popup.title("월 선택")
    popup.geometry("300x180")
    popup.configure(bg=BG)
    popup.resizable(False, False)
    tk.Label(popup, text="년도와 월을 선택하세요", font=FONT_BOLD, bg=BG, fg="#2C2C2A").pack(pady=(14,10))

    sel_frame = tk.Frame(popup, bg=BG)
    sel_frame.pack()

    # 년도 드롭다운 (데이터 있는 년도만)
    tk.Label(sel_frame, text="년도", font=FONT, bg=BG, fg=GRAY).grid(row=0, column=0, padx=(0,4))
    year_var = tk.StringVar(value=str(today.year) if str(today.year) in available_years else available_years[0])
    year_cb = ttk.Combobox(sel_frame, textvariable=year_var, values=available_years,
        width=7, font=FONT, state="readonly")
    year_cb.grid(row=0, column=1, padx=(0,16))

    # 월 드롭다운
    tk.Label(sel_frame, text="월", font=FONT, bg=BG, fg=GRAY).grid(row=0, column=2, padx=(0,4))
    month_var = tk.StringVar(value=str(today.month))
    months = [str(m) for m in range(1, 13)]
    month_cb = ttk.Combobox(sel_frame, textvariable=month_var, values=months,
        width=4, font=FONT, state="readonly")
    month_cb.grid(row=0, column=3)

    def apply():
        try:
            y = int(year_var.get())
            m = int(month_var.get())
            # 해당 년월에 데이터가 있는지 확인
            prefix = f"{y}-{m:02d}"
            has_data = any(d.startswith(prefix) for d in all_dates)
            if not has_data:
                messagebox.showwarning("데이터 없음", f"{y}년 {m}월에 저장된 기록이 없어요!")
                return
            diff = (y - today.year) * 12 + (m - today.month)
            monthly_offset[0] = diff
            popup.destroy()
            refresh_monthly_tab()
        except ValueError:
            pass

    tk.Button(popup, text="  선택  ", font=FONT_BOLD, bg="#185FA5", fg="#ffffff",
        relief="flat", bd=0, padx=14, pady=6, cursor="hand2", command=apply,
        highlightbackground="#185FA5", highlightthickness=1).pack(pady=(16,0))

def monthly_compare():
    """월 비교 팝업"""
    popup = tk.Toplevel(root)
    popup.title("비교할 월 선택")
    popup.geometry("340x160")
    popup.configure(bg=BG)
    popup.resizable(False, False)
    tk.Label(popup, text="비교할 월을 선택하세요", font=FONT_BOLD, bg=BG, fg="#2C2C2A").pack(pady=(14,10))
    btn_row = tk.Frame(popup, bg=BG)
    btn_row.pack()
    offsets = [("이번 달", 0), ("지난 달", -1), ("2달 전", -2), ("3달 전", -3)]
    for label, offset in offsets:
        if offset == monthly_offset[0]:
            continue
        def go(o=offset):
            monthly_compare_offset[0] = o
            popup.destroy()
            refresh_monthly_tab()
        tk.Button(btn_row, text=label, font=FONT, bg=CARD, fg="#2C2C2A",
            relief="flat", bd=0, padx=10, pady=4, cursor="hand2", command=go,
            highlightbackground=BORDER, highlightthickness=1).pack(side="left", padx=4)

tk.Button(monthly_top, text="◀", font=FONT, bg=CARD, fg="#2C2C2A",
    relief="flat", bd=0, padx=8, pady=3, cursor="hand2", command=monthly_prev,
    highlightbackground=BORDER, highlightthickness=1).pack(side="right", padx=(4,0))
tk.Button(monthly_top, text="월 선택", font=FONT, bg=CARD, fg="#2C2C2A",
    relief="flat", bd=0, padx=8, pady=3, cursor="hand2", command=monthly_select_month,
    highlightbackground=BORDER, highlightthickness=1).pack(side="right", padx=(4,0))
tk.Button(monthly_top, text="▶", font=FONT, bg=CARD, fg="#2C2C2A",
    relief="flat", bd=0, padx=8, pady=3, cursor="hand2", command=monthly_next,
    highlightbackground=BORDER, highlightthickness=1).pack(side="right", padx=(4,0))
tk.Button(monthly_top, text="월간 비교", font=FONT, bg="#E6F1FB", fg="#185FA5",
    relief="flat", bd=0, padx=8, pady=3, cursor="hand2", command=monthly_compare,
    highlightbackground="#B5D4F4", highlightthickness=1).pack(side="right", padx=(4,0))

monthly_search_frame = tk.Frame(page_monthly, bg=BG, padx=16)
monthly_search_frame.pack(fill="x", pady=(0,4))
monthly_search_var = tk.StringVar()
monthly_search_entry = tk.Entry(monthly_search_frame, textvariable=monthly_search_var,
    font=FONT, highlightbackground=BORDER, highlightthickness=1, relief="flat")
monthly_search_entry.pack(fill="x")
monthly_search_entry.insert(0, "🔍 공간 검색...")
monthly_search_entry.bind("<FocusIn>", lambda e: monthly_search_entry.delete(0, "end")
    if monthly_search_entry.get().startswith("🔍") else None)
monthly_search_entry.bind("<FocusOut>", lambda e: monthly_search_entry.insert(0, "🔍 공간 검색...")
    if not monthly_search_entry.get() else None)
monthly_search_var.trace("w", lambda *a: refresh_monthly_tab())

monthly_card_outer = tk.Frame(page_monthly, bg=BG, padx=16)
monthly_card_outer.pack(fill="x", pady=(0,6))
monthly_card_canvas = tk.Canvas(monthly_card_outer, bg=BG, highlightthickness=0, height=100)
monthly_card_hscroll = tk.Scrollbar(monthly_card_outer, orient="horizontal",
    command=monthly_card_canvas.xview)
monthly_card_canvas.configure(xscrollcommand=monthly_card_hscroll.set)
monthly_card_frame = tk.Frame(monthly_card_canvas, bg=BG)
monthly_card_canvas.create_window((0,0), window=monthly_card_frame, anchor="nw")
def on_monthly_card_configure(event):
    monthly_card_canvas.configure(scrollregion=monthly_card_canvas.bbox("all"))
monthly_card_frame.bind("<Configure>", on_monthly_card_configure)
monthly_card_canvas.pack(fill="x")
monthly_card_hscroll.pack(fill="x")

monthly_graph_card = tk.Frame(page_monthly, bg=CARD, padx=14, pady=10,
    highlightbackground=BORDER, highlightthickness=1)
monthly_graph_lbl = tk.Label(monthly_graph_card,
    text="공간을 선택하면 이번 달 통계가 표시됩니다",
    font=FONT, bg=CARD, fg=GRAY)
monthly_graph_lbl.pack(anchor="w")
monthly_graph_inner = tk.Frame(monthly_graph_card, bg=CARD)
monthly_graph_inner.pack(fill="x")

monthly_no_select_lbl = tk.Label(page_monthly,
    text="공간을 선택하면 이번 달 통계가 나타납니다",
    font=FONT, bg=BG, fg=GRAY)
monthly_no_select_lbl.pack(anchor="w", padx=16, pady=(8,0))

monthly_pie_card = tk.Frame(page_monthly, bg=CARD, padx=14, pady=10,
    highlightbackground=BORDER, highlightthickness=1)
monthly_pie_title = tk.Label(monthly_pie_card, text="", font=FONT, bg=CARD, fg=GRAY)
monthly_pie_title.pack(anchor="w")
monthly_pie_frame = tk.Frame(monthly_pie_card, bg=CARD)
monthly_pie_frame.pack(anchor="w")

active_monthly_space = [None]
monthly_fig = [None]

def draw_monthly_graph(sname, color):
    import datetime
    for w in monthly_graph_inner.winfo_children():
        w.destroy()
    if monthly_fig[0]:
        plt.close(monthly_fig[0])
    monthly_graph_lbl.config(text=f"{sname}  주차별 평균 소음값")
    today = datetime.date.today()
    month = today.month + monthly_offset[0]
    year = today.year
    while month < 1:
        month += 12; year -= 1
    while month > 12:
        month -= 12; year += 1
    if month == 12:
        last_day = datetime.date(year+1, 1, 1) - datetime.timedelta(days=1)
    else:
        last_day = datetime.date(year, month+1, 1) - datetime.timedelta(days=1)

    # 실제 주차 수에 맞게 동적으로 생성 (7일 단위)
    week_ranges = []
    week_labels = []
    d = datetime.date(year, month, 1)
    week_num = 1
    while d <= last_day:
        w_end = min(d + datetime.timedelta(days=6), last_day)
        week_ranges.append((d, w_end))
        week_labels.append(f"{week_num}주차")
        d = w_end + datetime.timedelta(days=1)
        week_num += 1

    avgs = []
    for w_start, w_end in week_ranges:
        week_vals = []
        d = w_start
        while d <= w_end:
            d_str = d.strftime("%Y-%m-%d")
            d_data = load_history_data(d_str)
            if d_data:
                matched = [s for s in d_data.get("spaces", []) if s["name"] == sname]
                if matched:
                    logs = matched[0].get("peaks_log", [])
                    vals = [l["val"] for l in logs]
                    if vals:
                        week_vals.extend(vals)
            d += datetime.timedelta(days=1)
        avgs.append(round(sum(week_vals) / len(week_vals)) if week_vals else 0)

    # 현재 주차 계산 (이번 달일 때만)
    current_week_idx = None
    if monthly_offset[0] == 0:
        for i, (w_start, w_end) in enumerate(week_ranges):
            if w_start <= today <= w_end:
                current_week_idx = i
                break

    fig_m, ax_m = plt.subplots(figsize=(7, 2.2))
    fig_m.patch.set_facecolor("#ffffff")
    ax_m.set_facecolor("#ffffff")
    ax_m.set_ylim(0, 270)
    ax_m.tick_params(colors=GRAY, labelsize=9)
    for sp in ["top","right"]: ax_m.spines[sp].set_visible(False)
    for sp in ["bottom","left"]: ax_m.spines[sp].set_color("#E0DED6")
    ax_m.set_ylabel("평균 소음값", fontsize=9, color=GRAY)
    bars = ax_m.bar(week_labels, avgs, color=color, width=0.5, alpha=0.85)
    if current_week_idx is not None:
        bars[current_week_idx].set_alpha(1.0)
        bars[current_week_idx].set_edgecolor("#2C2C2A")
        bars[current_week_idx].set_linewidth(2)
    for bar, avg in zip(bars, avgs):
        if avg > 0:
            ax_m.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 3,
                str(avg), ha="center", va="bottom", fontsize=9, color=GRAY)
    thresh_colors_h = ["#1D9E75","#378ADD","#BA7517","#D85A30"]
    for i, t in enumerate(thresholds):
        ax_m.axhline(y=t, color=thresh_colors_h[i], linewidth=0.7, linestyle="--", alpha=0.5)
    fig_m.tight_layout()
    monthly_fig[0] = fig_m
    canvas_m = FigureCanvasTkAgg(fig_m, master=monthly_graph_inner)
    canvas_m.get_tk_widget().pack(fill="x")
    canvas_m.draw()

    # 파이차트 - 해당 월 선택 공간 소음 단계별 비율
    for w in monthly_pie_frame.winfo_children():
        w.destroy()
    monthly_pie_title.config(text=f"소음 단계별 비율  ({sname})")

    import datetime
    today = datetime.date.today()
    month2 = today.month + monthly_offset[0]
    year2 = today.year
    while month2 < 1: month2 += 12; year2 -= 1
    while month2 > 12: month2 -= 12; year2 += 1
    if month2 == 12:
        last_day2 = datetime.date(year2+1, 1, 1) - datetime.timedelta(days=1)
    else:
        last_day2 = datetime.date(year2, month2+1, 1) - datetime.timedelta(days=1)

    level_counts_m = [0] * 5
    d = datetime.date(year2, month2, 1)
    while d <= last_day2:
        d_str = d.strftime("%Y-%m-%d")
        d_data = load_history_data(d_str)
        if d_data:
            matched = [s for s in d_data.get("spaces", []) if s["name"] == sname]
            if matched:
                for log in matched[0].get("peaks_log", []):
                    lv = get_level(log["val"])
                    level_counts_m[lv] += 1
        d += datetime.timedelta(days=1)

    total_m = sum(level_counts_m)
    if total_m > 0:
        labels_m2 = [LEVELS[i]["name"] for i in range(5) if level_counts_m[i] > 0]
        sizes_m2  = [level_counts_m[i] for i in range(5) if level_counts_m[i] > 0]
        colors_m2 = [LEVELS[i]["color"] for i in range(5) if level_counts_m[i] > 0]
        fig_mp, ax_mp = plt.subplots(figsize=(4, 2.2))
        fig_mp.patch.set_facecolor("#ffffff")
        ax_mp.pie(sizes_m2, labels=labels_m2, colors=colors_m2,
            autopct="%1.1f%%", startangle=90,
            textprops={"fontsize": 8, "color": "#2C2C2A"})
        ax_mp.axis("equal")
        fig_mp.tight_layout()
        canvas_mp = FigureCanvasTkAgg(fig_mp, master=monthly_pie_frame)
        canvas_mp.get_tk_widget().pack()
        canvas_mp.draw()
        plt.close(fig_mp)
    else:
        tk.Label(monthly_pie_frame, text="측정 데이터가 없어요",
            font=FONT, bg=CARD, fg=GRAY).pack(anchor="w")

def refresh_monthly_tab():
    import datetime
    prev_space = active_monthly_space[0]  # 이전 선택 공간 기억
    for w in monthly_card_frame.winfo_children():
        w.destroy()
    active_monthly_space[0] = None
    monthly_graph_lbl.config(text="공간을 선택하면 이번 달 통계가 표시됩니다")
    monthly_pie_title.config(text="")
    for w in monthly_graph_inner.winfo_children():
        w.destroy()
    for w in monthly_pie_frame.winfo_children():
        w.destroy()
    monthly_graph_card.pack_forget()
    monthly_pie_card.pack_forget()
    monthly_no_select_lbl.pack(anchor="w", padx=16, pady=(8,0))
    today = datetime.date.today()
    month = today.month + monthly_offset[0]
    year = today.year
    while month < 1:
        month += 12; year -= 1
    while month > 12:
        month -= 12; year += 1
    monthly_title_lbl.config(text=f"{year}년 {month}월 통계")


    all_snames = []
    for d in load_history_list():
        d_data = load_history_data(d)
        if not d_data: continue
        for s in d_data.get("spaces", []):
            if s["name"] not in all_snames:
                all_snames.append(s["name"])
    for s in spaces:
        if s["name"] not in all_snames:
            all_snames.append(s["name"])
    if not all_snames:
        tk.Label(monthly_card_frame, text="공간 데이터가 없어요",
            font=FONT, bg=BG, fg=GRAY).pack(anchor="w")
        return
    monthly_btns = {}
    for i, sname in enumerate(all_snames):
        color = SPACE_COLORS[i % len(SPACE_COLORS)]

        # 검색 필터링
        keyword = monthly_search_var.get().strip()
        if keyword and not keyword.startswith("🔍") and keyword.lower() not in sname.lower():
            continue

        def make_click(sn=sname, col=color):
            def on_click(event=None):
                if active_monthly_space[0] == sn:
                    active_monthly_space[0] = None
                    monthly_btns[sn].config(highlightthickness=1)
                    for w in monthly_graph_inner.winfo_children(): w.destroy()
                    monthly_graph_lbl.config(text="공간을 선택하면 이번 달 통계가 표시됩니다")
                    monthly_graph_card.pack_forget()
                    monthly_pie_card.pack_forget()
                    monthly_no_select_lbl.pack(anchor="w", padx=16, pady=(8,0))
                    refresh_monthly_tab()
                    return
                if active_monthly_space[0] and active_monthly_space[0] in monthly_btns:
                    monthly_btns[active_monthly_space[0]].config(highlightthickness=1)
                active_monthly_space[0] = sn
                monthly_btns[sn].config(highlightthickness=3)
                monthly_no_select_lbl.pack_forget()
                monthly_graph_card.pack(fill="x", padx=16, pady=(0,8))
                monthly_pie_card.pack(fill="x", padx=16, pady=(0,8))
                draw_monthly_graph(sn, col)
            return on_click
        btn_m = tk.Frame(monthly_card_frame, bg=CARD, highlightbackground=color,
            highlightthickness=1, cursor="hand2")
        btn_m.pack(side="left", padx=(0,10), ipadx=12, ipady=8)
        tk.Label(btn_m, text=sname, font=FONT_BOLD, bg=CARD, fg=color).pack(padx=8, pady=(6,2))
        click_fn = make_click()
        btn_m.bind("<Button-1>", click_fn)
        for child in btn_m.winfo_children():
            child.bind("<Button-1>", click_fn)
        monthly_btns[sname] = btn_m

    # 이전에 선택된 공간이 있으면 자동 선택
    if prev_space and prev_space in monthly_btns:
        color = SPACE_COLORS[all_snames.index(prev_space) % len(SPACE_COLORS)]
        active_monthly_space[0] = prev_space
        monthly_btns[prev_space].config(highlightthickness=3)
        monthly_no_select_lbl.pack_forget()
        monthly_graph_card.pack(fill="x", padx=16, pady=(0,8))
        monthly_pie_card.pack(fill="x", padx=16, pady=(0,8))
        draw_monthly_graph(prev_space, color)
def animate(frame):
    """0.2초마다 실행 - 소리값 받아서 그래프/카드 업데이트"""
    global tick
    if not running:
        return line_plot,

    tick += 1

    # ================================================================
    # [수정 2/2] 마이크로비트 연결 시 아래 try 블록 주석 해제하고
    #            가상 데이터 for 블록 전체 주석처리
    # ================================================================
    # try:
    #     line = ser.readline().decode('utf-8').strip()  # 마이크로비트에서 "채널:값" 형식으로 수신
    #     channel, val = line.split(":")                 # 채널번호와 소리값 분리
    #     channel = int(channel) - 1                     # 0부터 시작하도록 변환
    #     val = int(val)
    #     if 0 <= channel < len(spaces):                 # 해당 채널 공간에 데이터 저장
    #         s = spaces[channel]
    #         s["data"].append(val)
    #         if channel == 0: time_labels.append(time.strftime("%H:%M:%S"))
    #         s["total"] += val; s["count"] += 1
    #         if val > s["peak"]: s["peak"] = val; s["peak_time"] = time.strftime("%H:%M:%S")
    #         if val > s["window_peak"]: s["window_peak"] = val
    #         if tick % 10 == 0 and s["window_peak"] > 0:
    #             s["peaks_log"].insert(0, {"time": time.strftime("%H:%M:%S"), "val": s["window_peak"]})
    #             s["window_peak"] = 0
    # except Exception:
    #     pass
    # ================================================================

    # 가상 데이터 (마이크로비트 연결 시 아래 for 블록 전체 주석처리)
    for i, s in enumerate(spaces):
        val = fake_sound(tick, s["offset"])            # 가상 소리값 생성
        s["data"].append(val)                          # 그래프 데이터에 추가
        if i == 0: time_labels.append(time.strftime("%H:%M:%S"))  # x축 시간 저장
        s["total"] += val; s["count"] += 1            # 평균 계산용 누적
        if val > s["peak"]:                            # 최고값 갱신
            s["peak"] = val
            s["peak_time"] = time.strftime("%H:%M:%S")
        if val > s["window_peak"]: s["window_peak"] = val
        if tick % 10 == 0 and s["window_peak"] > 0:   # 10틱마다 구간 피크 기록
            s["peaks_log"].insert(0, {"time": time.strftime("%H:%M:%S"), "val": s["window_peak"]})
            s["window_peak"] = 0

    # 전체 현황 카드 업데이트
    refresh_overview()

    # 선택 공간 상세 업데이트
    s = spaces[selected_space]
    lv = get_level(list(s["data"])[-1])
    info = LEVELS[lv]
    color = SPACE_COLORS[selected_space % len(SPACE_COLORS)]

    peak_space_lbl.config(text=s["name"])
    peak_time_val.config(text=s["peak_time"] if s["count"] > 0 else "—")
    peak_val_lbl.config(text=str(s["peak"]) if s["count"] > 0 else "—")
    lbl_cur.config(text=str(list(s["data"])[-1]), fg=info["color"])
    # 위 카드 - 전체 공간 최고 소음
    loudest = max(spaces, key=lambda x: x["peak"])
    if any(sp["count"]>0 for sp in spaces):
        peak_space_lbl.config(text=loudest["name"])
        peak_time_val.config(text=loudest["peak_time"])
        peak_val_lbl.config(text=str(loudest["peak"]))
    # 아래 카드 - 선택 공간 최고 소음
    lbl_avg.config(text=s["name"])
    lbl_peak_time.config(text=s["peak_time"] if s["count"] > 0 else "—")
    lbl_peak.config(text=str(s["peak"]) if s["count"] > 0 else "—")
    lbl_time.config(text=time.strftime("%H:%M:%S"))

    # 그래프 업데이트
    y = list(s["data"])
    tl = list(time_labels)
    line_plot.set_ydata(y)
    line_plot.set_color(color)
    tick_positions = list(range(0, MAX_POINTS, 10))
    ax.set_xticks(tick_positions)
    ax.set_xticklabels([tl[p] if tl[p] else "" for p in tick_positions],
        fontsize=7, color=GRAY, rotation=15)
    for coll in ax.collections: coll.remove()
    ax.fill_between(range(MAX_POINTS), y, alpha=0.08, color=color)
    canvas_fig.draw()

    return line_plot,

# ── 애니메이션 시작 ─────────────────────────────────────
ani = animation.FuncAnimation(fig, animate, interval=200, blit=False)
refresh_detail()

def auto_save():
    """10초마다 자동 저장 (당일 데이터 + 히스토리)"""
    save_data()
    root.after(10000, auto_save)

def check_new_day():
    """1분마다 날짜 확인 - 자정이 지나면 데이터 자동 리셋"""
    global today_str, tick
    new_today = time.strftime("%Y-%m-%d")
    if new_today != today_str:
        save_history()   # 하루치 데이터 히스토리에 저장
        today_str = new_today
        tick = 0
        for s in spaces:
            s["data"].extend([0]*MAX_POINTS)
            s["peak"] = 0; s["total"] = 0; s["count"] = 0
            s["window_peak"] = 0; s["peaks_log"] = []; s["peak_time"] = "—"
        # 전체 공간 최고 소음 카드 초기화
        peak_space_lbl.config(text="—")
        peak_time_val.config(text="—")
        peak_val_lbl.config(text="—")
        refresh_detail()
        # 주간/월간 탭도 새로고침
        refresh_weekly_tab()
        refresh_monthly_tab()
    root.after(60000, check_new_day)

root.after(10000, auto_save)       # 10초 후 첫 자동저장 시작
root.after(60000, check_new_day)   # 1분 후 첫 날짜 확인 시작
root.mainloop()                    # 앱 실행 (이 줄이 실행되는 동안 앱이 켜져 있음)
