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
from collections import deque                 # 그래프용 고정 길이 데이터 저장소

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

# 탭별 페이지 프레임
page_realtime = tk.Frame(root, bg=BG)  # 실시간 모니터 페이지
page_history  = tk.Frame(root, bg=BG)  # 날짜별 기록 페이지

def show_tab(tab):
    """탭 전환 함수 - 선택한 탭 페이지만 보이게 함"""
    if tab == "realtime":
        page_history.pack_forget()
        page_realtime.pack(fill="both", expand=True)
        btn_tab_realtime.config(bg="#185FA5", fg="#ffffff")
        btn_tab_history.config(bg=CARD, fg="#2C2C2A")
    else:
        page_realtime.pack_forget()
        page_history.pack(fill="both", expand=True)
        btn_tab_realtime.config(bg=CARD, fg="#2C2C2A")
        btn_tab_history.config(bg="#185FA5", fg="#ffffff")
        refresh_history_tab()  # 날짜 목록 새로고침

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
btn_tab_history.pack(side="left")

# ════════════════════════════════════════════════════════
# 실시간 모니터 탭
# ════════════════════════════════════════════════════════
page_realtime.pack(fill="both", expand=True)

# ── 상단 타이틀 바 ──────────────────────────────────────
top = tk.Frame(page_realtime, bg=BG, pady=6, padx=16)
top.pack(fill="x")
tk.Label(top, text="소리 감지 모니터", font=FONT_BOLD, bg=BG, fg="#2C2C2A").pack(side="left")
status_lbl = tk.Label(top, text="● 실행 중", font=FONT, bg=BG, fg="#3B6D11")
status_lbl.pack(side="left", padx=12)

def toggle():
    """일시정지/재생 버튼 - running 변수로 애니메이션 제어"""
    global running
    running = not running
    if running:
        btn_toggle.config(text="  일시정지  ", bg="#E6F1FB", fg="#185FA5")
        status_lbl.config(text="● 실행 중", fg="#3B6D11")
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
hist_right = tk.Frame(page_history, bg=BG)   # 날짜 상세 영역
hist_left.pack(side="left", fill="y", padx=(16,6), pady=8)
hist_right.pack(side="left", fill="both", expand=True, padx=(0,16), pady=8)

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
    for w in hist_log_inner.winfo_children(): w.destroy()
    refresh_history_tab()

tk.Button(hist_title_row, text="  선택 날짜 삭제  ", font=FONT, bg="#FCEBEB", fg="#A32D2D",
    relief="flat", bd=0, padx=10, pady=4, cursor="hand2", command=delete_history,
    highlightbackground="#F7C1C1", highlightthickness=1).pack(side="right")

hist_summary_frame = tk.Frame(hist_right, bg=BG)  # 공간별 요약 카드
hist_summary_frame.pack(fill="x", pady=(0,6))

# 막대그래프 영역
hist_chart_card = tk.Frame(hist_right, bg=CARD, padx=14, pady=10,
    highlightbackground=BORDER, highlightthickness=1)
hist_chart_card.pack(fill="x", pady=(0,6))
tk.Label(hist_chart_card, text="공간별 최고 소리값 비교", font=FONT, bg=CARD, fg=GRAY).pack(anchor="w", pady=(0,6))
hist_chart_inner = tk.Frame(hist_chart_card, bg=CARD)
hist_chart_inner.pack(fill="x")

hist_log_card = tk.Frame(hist_right, bg=CARD, padx=14, pady=10,
    highlightbackground=BORDER, highlightthickness=1)
hist_log_card.pack(fill="both", expand=True)
tk.Label(hist_log_card, text="구간별 최고 소리 기록",
    font=FONT, bg=CARD, fg=GRAY).pack(anchor="w", pady=(0,6))
hist_log_inner = tk.Frame(hist_log_card, bg=CARD)
hist_log_inner.pack(fill="both", expand=True)

def show_history_detail(date_str):
    """날짜 클릭 시 해당 날짜의 공간별 요약 카드와 피크 로그 표시"""
    data = load_history_data(date_str)
    if not data:
        hist_detail_title.config(text=f"{date_str} — 데이터 없음")
        return

    hist_detail_title.config(text=f"{date_str} 기록")

    # 공간별 요약 카드 (최고값, 시각, 평균, 소음 단계)
    for w in hist_summary_frame.winfo_children(): w.destroy()
    for i, s in enumerate(data.get("spaces", [])):
        color = SPACE_COLORS[i % len(SPACE_COLORS)]
        lv = get_level(s["peak"])
        info = LEVELS[lv]
        f = tk.Frame(hist_summary_frame, bg=CARD, highlightbackground=color, highlightthickness=2)
        f.pack(side="left", padx=(0,10), ipadx=10, ipady=6)
        tk.Label(f, text=s["name"], font=FONT, bg=CARD, fg=color).pack(anchor="w", padx=8, pady=(4,0))
        tk.Label(f, text=f"최고: {s['peak']}", font=("Helvetica", 16, "bold"), bg=CARD, fg=color).pack(anchor="w", padx=8)
        tk.Label(f, text=f"시간: {s['peak_time']}", font=("Helvetica", 10), bg=CARD, fg=GRAY).pack(anchor="w", padx=8)
        tk.Label(f, text=f"평균: {s['avg']}", font=("Helvetica", 10), bg=CARD, fg=GRAY).pack(anchor="w", padx=8)
        tk.Label(f, text=info["name"], font=("Helvetica", 10, "bold"),
            bg=info["bg"], fg=info["fg"], padx=6, pady=2).pack(anchor="w", padx=8, pady=(2,4))

    # 막대그래프 그리기
    for w in hist_chart_inner.winfo_children(): w.destroy()
    spaces_data = data.get("spaces", [])
    if spaces_data:
        fig_h, ax_h = plt.subplots(figsize=(6, 1.8))
        fig_h.patch.set_facecolor("#ffffff")
        ax_h.set_facecolor("#ffffff")
        names  = [s["name"] for s in spaces_data]
        peaks  = [s["peak"] for s in spaces_data]
        colors = [SPACE_COLORS[i % len(SPACE_COLORS)] for i in range(len(spaces_data))]
        bars = ax_h.bar(names, peaks, color=colors, width=0.5)
        ax_h.set_ylim(0, 255)
        ax_h.set_ylabel("최고값", fontsize=9, color=GRAY)
        ax_h.tick_params(colors=GRAY, labelsize=9)
        for sp in ["top","right"]: ax_h.spines[sp].set_visible(False)
        for sp in ["bottom","left"]: ax_h.spines[sp].set_color("#E0DED6")
        # 막대 위에 값 표시
        for bar, peak in zip(bars, peaks):
            ax_h.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 4,
                str(peak), ha="center", va="bottom", fontsize=9, color=GRAY)
        # 기준선 표시
        thresh_colors_h = ["#1D9E75","#378ADD","#BA7517","#D85A30"]
        for i, t in enumerate(thresholds):
            ax_h.axhline(y=t, color=thresh_colors_h[i], linewidth=0.7, linestyle="--", alpha=0.5)
        fig_h.tight_layout()
        canvas_h = FigureCanvasTkAgg(fig_h, master=hist_chart_inner)
        canvas_h.get_tk_widget().pack(fill="x")
        canvas_h.draw()
        plt.close(fig_h)

    # 구간별 피크 로그 (모든 공간 합쳐서 시간순 정렬)
    for w in hist_log_inner.winfo_children(): w.destroy()
    all_logs = []
    for i, s in enumerate(data.get("spaces", [])):
        for log in s.get("peaks_log", []):
            all_logs.append({"space": s["name"], "time": log["time"], "val": log["val"], "idx": i})
    all_logs.sort(key=lambda x: x["time"], reverse=True)

    if not all_logs:
        tk.Label(hist_log_inner, text="기록 없음", font=FONT, bg=CARD, fg=GRAY).pack(anchor="w")
        return

    for log in all_logs[:20]:
        color = SPACE_COLORS[log["idx"] % len(SPACE_COLORS)]
        lv = get_level(log["val"])
        info = LEVELS[lv]
        row = tk.Frame(hist_log_inner, bg=CARD)
        row.pack(fill="x", pady=1)
        tk.Label(row, text=log["time"], font=FONT, bg=CARD, fg=GRAY).pack(side="left")
        tk.Label(row, text=f"  {log['space']}  ", font=FONT, bg=CARD, fg=color).pack(side="left")
        tk.Label(row, text=str(log["val"]), font=("Helvetica", 11, "bold"), bg=CARD, fg="#2C2C2A").pack(side="left")
        tk.Label(row, text=info["name"], font=("Helvetica", 10, "bold"),
            bg=info["bg"], fg=info["fg"], padx=6, pady=1).pack(side="right")
        tk.Frame(hist_log_inner, bg="#E0DED6", height=1).pack(fill="x")

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

# ── 실시간 애니메이션 함수 ──────────────────────────────
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
        refresh_detail()
    root.after(60000, check_new_day)

root.after(10000, auto_save)       # 10초 후 첫 자동저장 시작
root.after(60000, check_new_day)   # 1분 후 첫 날짜 확인 시작
root.mainloop()                    # 앱 실행 (이 줄이 실행되는 동안 앱이 켜져 있음)
