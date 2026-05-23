import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.animation as animation
import random
import math
import time
from collections import deque

MAX_POINTS = 60

LEVELS = [
    {"name": "매우 조용",     "color": "#1D9E75", "bg": "#E1F5EE", "fg": "#085041"},
    {"name": "조용",          "color": "#378ADD", "bg": "#E6F1FB", "fg": "#0C447C"},
    {"name": "보통",          "color": "#BA7517", "bg": "#FAEEDA", "fg": "#633806"},
    {"name": "시끄러움",      "color": "#D85A30", "bg": "#FAECE7", "fg": "#712B13"},
    {"name": "매우 시끄러움", "color": "#A32D2D", "bg": "#FCEBEB", "fg": "#501313"},
]

SPACE_COLORS = ["#185FA5", "#1D9E75", "#D85A30", "#7F77DD"]

thresholds = [50, 100, 150, 200]

def get_level(val):
    for i, t in enumerate(thresholds):
        if val <= t:
            return i
    return 4

def fake_sound(t, offset=0):
    base = 30 + math.sin((t + offset) * 0.08) * 15
    noise = (random.random() - 0.5) * 20
    spike = random.random() * 80 if random.random() < 0.05 else 0
    return max(0, min(255, int(base + noise + spike)))

# ── 공간 데이터 ─────────────────────────────────────────
spaces = [
    {"name": "공간 1", "channel": 1, "data": deque([0]*MAX_POINTS, maxlen=MAX_POINTS),
     "peak": 0, "total": 0, "count": 0, "window_peak": 0, "peaks_log": [], "offset": 0},
]

running = True
tick = 0
start_time = time.time()
selected_space = 0

root = tk.Tk()
root.title("소리 감지 모니터 (마이크로비트)")
root.geometry("1000x750")
root.configure(bg="#f5f5f3")
root.resizable(True, True)

FONT      = ("Helvetica", 11)
FONT_BOLD = ("Helvetica", 12, "bold")
BG        = "#f5f5f3"
CARD      = "#ffffff"
GRAY      = "#888780"
BORDER    = "#D3D1C7"

# ── 상단 타이틀 바 ──────────────────────────────────────
top = tk.Frame(root, bg=BG, pady=8, padx=16)
top.pack(fill="x")
tk.Label(top, text="소리 감지 모니터", font=FONT_BOLD, bg=BG, fg="#2C2C2A").pack(side="left")
status_lbl = tk.Label(top, text="● 실행 중", font=FONT, bg=BG, fg="#3B6D11")
status_lbl.pack(side="left", padx=12)

def toggle():
    global running
    running = not running
    if running:
        btn_toggle.config(text="  일시정지  ", bg="#E6F1FB", fg="#185FA5")
        status_lbl.config(text="● 실행 중", fg="#3B6D11")
    else:
        btn_toggle.config(text="  재  생  ", bg=CARD, fg="#2C2C2A")
        status_lbl.config(text="● 일시정지", fg=GRAY)

def reset_all():
    global tick
    tick = 0
    for s in spaces:
        s["data"].extend([0]*MAX_POINTS)
        s["peak"] = 0; s["total"] = 0; s["count"] = 0
        s["window_peak"] = 0; s["peaks_log"] = []
    refresh_detail()

btn_toggle = tk.Button(top, text="  일시정지  ", font=FONT, bg="#E6F1FB", fg="#185FA5",
                        relief="flat", bd=0, padx=10, pady=4, cursor="hand2", command=toggle,
                        highlightbackground="#B5D4F4", highlightthickness=1)
btn_toggle.pack(side="right", padx=(6,0))
tk.Button(top, text="  초기화  ", font=FONT, bg=CARD, fg="#2C2C2A",
          relief="flat", bd=0, padx=10, pady=4, cursor="hand2", command=reset_all,
          highlightbackground=BORDER, highlightthickness=1).pack(side="right")

# ── 공간 관리 패널 ─────────────────────────────────────
space_mgr = tk.Frame(root, bg=CARD, padx=14, pady=10,
                      highlightbackground=BORDER, highlightthickness=1)
space_mgr.pack(fill="x", padx=16, pady=(4,0))

space_top = tk.Frame(space_mgr, bg=CARD)
space_top.pack(fill="x")
tk.Label(space_top, text="공간 관리", font=FONT, bg=CARD, fg=GRAY).pack(side="left")

def add_space():
    if len(spaces) >= 4:
        messagebox.showwarning("최대 4개", "공간은 최대 4개까지 추가할 수 있어요.")
        return
    name = simpledialog.askstring("공간 추가", "공간 이름 입력:", parent=root)
    if not name:
        return
    ch = len(spaces) + 1
    spaces.append({
        "name": name, "channel": ch,
        "data": deque([0]*MAX_POINTS, maxlen=MAX_POINTS),
        "peak": 0, "total": 0, "count": 0,
        "window_peak": 0, "peaks_log": [], "offset": random.randint(0, 100)
    })
    refresh_space_buttons()
    refresh_overview()

def delete_space():
    global selected_space
    if len(spaces) <= 1:
        messagebox.showwarning("최소 1개", "공간은 최소 1개 있어야 해요.")
        return
    spaces.pop(selected_space)
    selected_space = min(selected_space, len(spaces)-1)
    refresh_space_buttons()
    refresh_overview()
    refresh_detail()

def rename_space():
    name = simpledialog.askstring("공간 이름 변경",
                                   f"새 이름 입력 (현재: {spaces[selected_space]['name']}):",
                                   parent=root)
    if name:
        spaces[selected_space]["name"] = name
        refresh_space_buttons()
        refresh_overview()

tk.Button(space_top, text="+ 공간 추가", font=FONT, bg="#E1F5EE", fg="#085041",
          relief="flat", bd=0, padx=10, pady=3, cursor="hand2", command=add_space,
          highlightbackground="#9FE1CB", highlightthickness=1).pack(side="right", padx=(6,0))
tk.Button(space_top, text="이름 변경", font=FONT, bg=CARD, fg="#2C2C2A",
          relief="flat", bd=0, padx=10, pady=3, cursor="hand2", command=rename_space,
          highlightbackground=BORDER, highlightthickness=1).pack(side="right", padx=(6,0))
tk.Button(space_top, text="공간 삭제", font=FONT, bg="#FCEBEB", fg="#A32D2D",
          relief="flat", bd=0, padx=10, pady=3, cursor="hand2", command=delete_space,
          highlightbackground="#F7C1C1", highlightthickness=1).pack(side="right", padx=(6,0))

space_btn_frame = tk.Frame(space_mgr, bg=CARD)
space_btn_frame.pack(fill="x", pady=(8,0))
space_btns = []

def select_space(idx):
    global selected_space
    selected_space = idx
    refresh_space_buttons()
    refresh_detail()

def refresh_space_buttons():
    for w in space_btn_frame.winfo_children():
        w.destroy()
    space_btns.clear()
    for i, s in enumerate(spaces):
        color = SPACE_COLORS[i % len(SPACE_COLORS)]
        is_sel = (i == selected_space)
        btn = tk.Button(space_btn_frame, text=s["name"], font=FONT,
                        bg=color if is_sel else CARD,
                        fg="#ffffff" if is_sel else "#2C2C2A",
                        relief="flat", bd=0, padx=14, pady=4, cursor="hand2",
                        command=lambda idx=i: select_space(idx),
                        highlightbackground=color, highlightthickness=1)
        btn.pack(side="left", padx=(0,8))
        space_btns.append(btn)

refresh_space_buttons()

# ── 전체 현황 (overview) ───────────────────────────────
overview_card = tk.Frame(root, bg=CARD, padx=14, pady=10,
                          highlightbackground=BORDER, highlightthickness=1)
overview_card.pack(fill="x", padx=16, pady=(6,0))
tk.Label(overview_card, text="전체 현황", font=FONT, bg=CARD, fg=GRAY).pack(anchor="w", pady=(0,6))
overview_inner = tk.Frame(overview_card, bg=CARD)
overview_inner.pack(fill="x")

def refresh_overview():
    for w in overview_inner.winfo_children():
        w.destroy()
    for i, s in enumerate(spaces):
        col_color = SPACE_COLORS[i % len(SPACE_COLORS)]
        lv = get_level(s["peak"]) if s["count"] > 0 else 0
        info = LEVELS[lv]
        f = tk.Frame(overview_inner, bg=CARD, highlightbackground=col_color, highlightthickness=2)
        f.pack(side="left", padx=(0,10), ipadx=10, ipady=6)
        tk.Label(f, text=s["name"], font=FONT, bg=CARD, fg=col_color).pack(anchor="w", padx=8, pady=(4,0))
        cur = list(s["data"])[-1] if s["count"] > 0 else 0
        tk.Label(f, text=str(cur), font=("Helvetica", 20, "bold"), bg=CARD, fg=col_color).pack(anchor="w", padx=8)
        tk.Label(f, text=info["name"], font=("Helvetica", 10, "bold"),
                 bg=info["bg"], fg=info["fg"], padx=6, pady=2).pack(anchor="w", padx=8, pady=(0,4))

refresh_overview()

# ── 선택 공간 상세 ─────────────────────────────────────
detail_frame = tk.Frame(root, bg=BG)
detail_frame.pack(fill="both", expand=True, padx=16, pady=(6,0))

level_card = tk.Frame(detail_frame, bg=CARD, padx=14, pady=10,
                       highlightbackground=BORDER, highlightthickness=1)
level_card.pack(fill="x", pady=(0,6))
level_name_lbl = tk.Label(level_card, text="공간 1", font=FONT, bg=CARD, fg=GRAY)
level_name_lbl.pack(anchor="w")
level_lbl = tk.Label(level_card, text="—", font=("Helvetica", 28, "bold"), bg=CARD, fg=GRAY)
level_lbl.pack(anchor="w")

stats_frame = tk.Frame(detail_frame, bg=BG)
stats_frame.pack(fill="x", pady=(0,6))
for i in range(4):
    stats_frame.columnconfigure(i, weight=1)

def make_stat(parent, title, val, color, col):
    f = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
    tk.Label(f, text=title, font=FONT, bg=CARD, fg=GRAY).pack(anchor="w", padx=12, pady=(8,0))
    lbl = tk.Label(f, text=val, font=("Helvetica", 18, "bold"), bg=CARD, fg=color)
    lbl.pack(anchor="w", padx=12, pady=(0,8))
    f.grid(row=0, column=col, padx=(0 if col==0 else 6, 0), sticky="nsew")
    return lbl

lbl_cur  = make_stat(stats_frame, "현재 소리",     "—", "#2C2C2A", 0)
lbl_peak = make_stat(stats_frame, "최고값 (피크)", "—", "#D85A30", 1)
lbl_avg  = make_stat(stats_frame, "평균값",         "—", "#185FA5", 2)
lbl_time = make_stat(stats_frame, "경과 시간",      "0s","#2C2C2A", 3)

graph_card = tk.Frame(detail_frame, bg=CARD, padx=14, pady=10,
                       highlightbackground=BORDER, highlightthickness=1)
graph_card.pack(fill="both", expand=True, pady=(0,6))
graph_lbl = tk.Label(graph_card, text="실시간 소리 레벨", font=FONT, bg=CARD, fg=GRAY)
graph_lbl.pack(anchor="w")

fig, ax = plt.subplots(figsize=(8, 2.0))
fig.patch.set_facecolor("#ffffff")
ax.set_facecolor("#ffffff")
ax.set_ylim(0, 255)
ax.set_xlim(0, MAX_POINTS)
ax.tick_params(colors=GRAY, labelsize=9)
for sp in ["top","right"]: ax.spines[sp].set_visible(False)
for sp in ["bottom","left"]: ax.spines[sp].set_color("#E0DED6")
ax.set_ylabel("소리 레벨", fontsize=9, color=GRAY)
ax.set_xticks([])
line_plot, = ax.plot(list(spaces[0]["data"]), color=SPACE_COLORS[0], linewidth=1.5)
hlines = []

def draw_hlines():
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

# ── 기준값 설정 ────────────────────────────────────────
thresh_card = tk.Frame(root, bg=CARD, padx=14, pady=8,
                        highlightbackground=BORDER, highlightthickness=1)
thresh_card.pack(fill="x", padx=16, pady=(0,6))
tk.Label(thresh_card, text="기준값 설정 (0~255)", font=FONT, bg=CARD, fg=GRAY).pack(anchor="w", pady=(0,6))
thresh_row = tk.Frame(thresh_card, bg=CARD)
thresh_row.pack(fill="x")

thresh_entries = []
thresh_labels_text = ["매우 조용 ~", "조용 ~", "보통 ~", "시끄러움 ~"]
thresh_colors = ["#1D9E75", "#378ADD", "#BA7517", "#D85A30"]
for i in range(4):
    col = tk.Frame(thresh_row, bg=CARD)
    col.pack(side="left", padx=(0,16))
    tk.Label(col, text=thresh_labels_text[i], font=("Helvetica", 10), bg=CARD, fg=thresh_colors[i]).pack(anchor="w")
    var = tk.StringVar(value=str(thresholds[i]))
    tk.Entry(col, textvariable=var, width=6, font=FONT, justify="center",
             highlightbackground=BORDER, highlightthickness=1, relief="flat").pack(anchor="w")
    thresh_entries.append(var)

def apply_thresholds():
    global thresholds
    new = []
    for i, v in enumerate(thresh_entries):
        try:
            val = max(0, min(255, int(v.get())))
            new.append(val)
        except ValueError:
            new.append(thresholds[i])
    new.sort()
    thresholds = new
    for i, v in enumerate(thresh_entries): v.set(str(thresholds[i]))
    draw_hlines(); canvas_fig.draw()

def reset_thresholds():
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
    s = spaces[selected_space]
    color = SPACE_COLORS[selected_space % len(SPACE_COLORS)]
    level_name_lbl.config(text=s["name"])
    lbl_cur.config(text="—" if s["count"]==0 else str(list(s["data"])[-1]))
    lbl_peak.config(text="—" if s["count"]==0 else str(s["peak"]))
    lbl_avg.config(text="—" if s["count"]==0 else str(round(s["total"]/s["count"])))
    line_plot.set_color(color)
    graph_lbl.config(text=f"실시간 소리 레벨 — {s['name']}")

# ── 애니메이션 ─────────────────────────────────────────
def animate(frame):
    global tick
    if not running:
        return line_plot,

    tick += 1

    for i, s in enumerate(spaces):
        val = fake_sound(tick, s["offset"])
        # ── 실제 마이크로비트 연결 시 채널별로 값 받아오기 ──
        # val = int(ser.readline().decode('utf-8').strip())  # 채널 i+1
        # ────────────────────────────────────────────────────

        s["data"].append(val)
        s["total"] += val
        s["count"] += 1
        if val > s["peak"]: s["peak"] = val
        if val > s["window_peak"]: s["window_peak"] = val

        if tick % 10 == 0 and s["window_peak"] > 0:
            s["peaks_log"].insert(0, {"time": f"{tick}s", "val": s["window_peak"]})
            s["window_peak"] = 0

    # 전체 현황 업데이트
    refresh_overview()

    # 선택 공간 상세 업데이트
    s = spaces[selected_space]
    lv = get_level(list(s["data"])[-1])
    info = LEVELS[lv]
    color = SPACE_COLORS[selected_space % len(SPACE_COLORS)]

    level_lbl.config(text=info["name"], fg=info["color"])
    level_card.config(bg=info["bg"])
    level_lbl.config(bg=info["bg"])
    for w in level_card.winfo_children(): w.config(bg=info["bg"])

    lbl_cur.config(text=str(list(s["data"])[-1]), fg=info["color"])
    lbl_peak.config(text=str(s["peak"]))
    lbl_avg.config(text=str(round(s["total"]/s["count"])) if s["count"] > 0 else "—")
    lbl_time.config(text=f"{int(time.time()-start_time)}s")

    y = list(s["data"])
    line_plot.set_ydata(y)
    line_plot.set_color(color)
    for coll in ax.collections: coll.remove()
    ax.fill_between(range(MAX_POINTS), y, alpha=0.08, color=color)
    canvas_fig.draw()

    return line_plot,

ani = animation.FuncAnimation(fig, animate, interval=200, blit=False)
refresh_detail()
root.mainloop()