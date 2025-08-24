import sys, time, re, threading, datetime, sqlite3
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QListWidget, QTextEdit, QFileDialog
import pyautogui, pygetwindow as gw, win32gui

# 默认配置（启动时为空，点按钮选择）
LOG_FILE = ""
DB_FILE = ""
CAR_TYPE = "BPC_Dirtbike"
CAR_LIFETIME = 7200  # 2 小时
SUMMON_LIMIT = 5

summon_counts = {}
active_cars = {}

def log_msg(text, gui=None):
    print(text)
    if gui:
        gui.debug.append(text)
        gui.debug.ensureCursorVisible()

def focus_scum_window():
    windows = gw.getWindowsWithTitle("SCUM")
    if not windows:
        return False
    scum_window = windows[0]
    win32gui.SetForegroundWindow(scum_window._hWnd)
    time.sleep(0.3)
    return True

def send_scum_command(cmd, gui=None):
    if focus_scum_window():
        pyautogui.press("t")
        pyautogui.typewrite(cmd)
        pyautogui.press("enter")
        log_msg(f"[执行] {cmd}", gui)
    else:
        log_msg("❌ 未找到 SCUM 窗口", gui)

def get_latest_vehicle():
    if not DB_FILE:
        return None
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    try:
        cur.execute("SELECT vehicle_entity_id, vehicle_asset_id FROM vehicle_spawner ORDER BY rowid DESC LIMIT 1;")
        row = cur.fetchone()
        log_msg(f"[DEBUG] 最新车辆数据: {row}", None)
        return row
    except Exception as e:
        log_msg(f"[ERROR] 查询车辆失败: {e}", None)
        return None
    finally:
        conn.close()

def destroy_vehicle(vehicle_id, gui=None):
    log_msg(f"[DEBUG] 定时器触发，准备删除车辆 ID={vehicle_id}", gui)
    send_scum_command(f"#DestroyVehicle {vehicle_id}", gui)
    if vehicle_id in active_cars:
        del active_cars[vehicle_id]
    log_msg(f"[销毁] 已执行删除车辆 ID={vehicle_id}", gui)

def spawn_car(steamid, player_name, gui=None):
    today = datetime.date.today().isoformat()
    record = summon_counts.get(steamid, {"count": 0, "last_date": today})

    if record["last_date"] != today:
        record = {"count": 0, "last_date": today}

    if record["count"] >= SUMMON_LIMIT:
        send_scum_command(f"@{player_name} Limit reached ({SUMMON_LIMIT}/day)", gui)
        log_msg(f"[限制] 玩家 {player_name} (SteamID {steamid}) 已召唤满 {SUMMON_LIMIT} 辆", gui)
        return

    send_scum_command(f"#SpawnVehicle {CAR_TYPE} 1 Location {steamid}", gui)
    time.sleep(1)

    vehicle = get_latest_vehicle()
    if not vehicle:
        return
    vid, vtype = vehicle

    record["count"] += 1
    record["last_date"] = today
    summon_counts[steamid] = record

    active_cars[vid] = {"player": steamid, "spawn_time": time.time()}
    log_msg(f"[生成] {player_name} 第 {record['count']} 辆车 (ID={vid})", gui)

    if gui:
        gui.add_car(player_name, vid)

    threading.Timer(CAR_LIFETIME, lambda: destroy_vehicle(vid, gui)).start()

def listen_log(gui=None):
    if not LOG_FILE:
        log_msg("[ERROR] 日志路径未设置", gui)
        return
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            f.seek(0, 2)
            while gui and gui.running:
                line = f.readline()
                if not line:
                    time.sleep(0.2)
                    continue
                log_msg(f"[DEBUG] 新日志: {line.strip()}", gui)
                match = re.search(r"'(\d+):(.+?)\(\d+\)'\s+Command:\s+'(.+?)'", line)
                if match:
                    steamid, player_name, cmd = match.groups()
                    log_msg(f"[DEBUG] 匹配到玩家 {player_name} (SteamID {steamid}) 输入命令: {cmd}", gui)
                    if cmd == "getcar":
                        spawn_car(steamid, player_name, gui)
    except Exception as e:
        log_msg(f"[ERROR] 无法打开日志文件: {e}", gui)

class DidiCarBot(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SCUM 滴滴车机器人")
        self.resize(600, 550)

        layout = QVBoxLayout()

        self.status_label = QLabel("机器人状态：未运行")
        layout.addWidget(self.status_label)

        self.start_btn = QPushButton("启动机器人")
        self.start_btn.clicked.connect(self.start_bot)
        layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("停止机器人")
        self.stop_btn.clicked.connect(self.stop_bot)
        layout.addWidget(self.stop_btn)

        self.log_btn = QPushButton("选择日志文件")
        self.log_btn.clicked.connect(self.select_log_file)
        layout.addWidget(self.log_btn)

        self.db_btn = QPushButton("选择数据库文件")
        self.db_btn.clicked.connect(self.select_db_file)
        layout.addWidget(self.db_btn)

        layout.addWidget(QLabel("已召唤车辆："))
        self.car_list = QListWidget()
        layout.addWidget(self.car_list)

        self.life_label = QLabel("车辆存活时间 (小时)：2 固定")
        layout.addWidget(self.life_label)

        layout.addWidget(QLabel("实时调试日志："))
        self.debug = QTextEdit()
        self.debug.setReadOnly(True)
        layout.addWidget(self.debug)

        self.setLayout(layout)
        self.running = False
        self.thread = None

    def select_log_file(self):
        global LOG_FILE
        path, _ = QFileDialog.getOpenFileName(self, "选择 SCUM 日志文件", "", "Log Files (*.log);;All Files (*)")
        if path:
            LOG_FILE = path
            log_msg(f"[设置] 日志文件路径: {LOG_FILE}", self)

    def select_db_file(self):
        global DB_FILE
        path, _ = QFileDialog.getOpenFileName(self, "选择 SCUM 数据库文件", "", "Database Files (*.db);;All Files (*)")
        if path:
            DB_FILE = path
            log_msg(f"[设置] 数据库文件路径: {DB_FILE}", self)

    def start_bot(self):
        self.running = True
        self.status_label.setText("机器人状态：运行中")
        self.thread = threading.Thread(target=listen_log, args=(self,), daemon=True)
        self.thread.start()
        log_msg("[启动] 机器人已启动", self)

    def stop_bot(self):
        self.running = False
        self.status_label.setText("机器人状态：已停止")
        log_msg("[停止] 机器人已停止", self)

    def add_car(self, player, vid):
        self.car_list.addItem(f"{player} - 车辆ID:{vid} - {time.strftime('%H:%M:%S')}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = DidiCarBot()
    win.show()
    sys.exit(app.exec())
