"""Local desktop exercise of the firmware workflow. Never opens a serial port."""
import argparse
import ctypes
import json
from pathlib import Path
import time
from build_robot_sim import ROOT, build_library, run_tests

class Simulator:
    def __init__(self):
        self.lib = ctypes.CDLL(str(build_library()))
        self.lib.Sim_Init.argtypes = []
        self.lib.Sim_Init.restype = None
        self.lib.Sim_Command.argtypes = [ctypes.c_char_p, ctypes.c_uint32]
        self.lib.Sim_Command.restype = ctypes.c_int
        self.lib.Sim_Poll.argtypes = [ctypes.c_uint32]
        self.lib.Sim_Poll.restype = None
        for name in ('Sim_Status', 'Sim_NextLog'):
            getattr(self.lib, name).argtypes = []
            getattr(self.lib, name).restype = ctypes.c_char_p
        self.lib.Sim_Init()

    def command(self, text, now):
        return self.lib.Sim_Command(text.encode('ascii'), now & 0xffffffff)

    def poll(self, now):
        self.lib.Sim_Poll(now & 0xffffffff)

    def status(self):
        return json.loads(self.lib.Sim_Status().decode('ascii'))

    def logs(self):
        while True:
            item = self.lib.Sim_NextLog()
            if item is None:
                break
            yield item.decode('ascii').rstrip()

def demo():
    """Deterministic demonstration; tests the real DLL API without a GUI/board."""
    sim = Simulator()
    lines = ['MSPM0G3507 desktop dry-run transcript', 'No hardware or serial connection.']
    def flush():
        lines.extend(sim.logs())
    flush()
    for color, expected_bin in [('RED','LEFT'), ('GREEN','CENTER'), ('BLUE','RIGHT')]:
        sim.command('RESET', 0)
        sim.command('START ' + color, 0)
        flush()
        for step in range(1,8):
            sim.poll(step * 1000)
            flush()
        state = sim.status()
        assert state['state'] == 'DONE' and state['bin'] == expected_bin
    sim.command('RESET', 0)
    sim.command('START RED', 0)
    sim.command('PAUSE', 400)
    sim.poll(10000)
    assert sim.status()['elapsed_ms'] == 400
    sim.command('RESUME', 10000)
    sim.poll(10600)
    assert sim.status()['step'] == 1
    sim.command('STOP', 10600)
    assert sim.status()['state'] == 'ABORTED'
    flush()
    sim.command('RESET', 0)
    sim.command('START BLUE', 0)
    sim.command('SIM STALL', 0)
    sim.poll(3000)
    assert sim.status()['fault'] == 'TIMEOUT'
    flush()
    sim.command('RESET', 0)
    sim.command('JOINTS', 0)
    sim.command('POSES', 0)
    flush()
    output = ROOT / 'docs/testing/无舵机演练日志.txt'
    output.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('PASS: shared DLL demo (all colors, pause/resume/stop, timeout and configuration)')
    print('Transcript:', output)

def gui():
    import tkinter as tk
    from tkinter import ttk
    from tkinter.scrolledtext import ScrolledText

    root = tk.Tk()
    root.title('机械臂无舵机演练 — MSPM0G3507')
    root.geometry('1080x800')
    root.minsize(940, 740)
    root.configure(bg='#eef2f7')
    root.option_add('*Font', ('Microsoft YaHei UI', 10))
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('TFrame', background='#eef2f7')
    style.configure('TLabel', background='#eef2f7', foreground='#24334b')
    style.configure('TButton', padding=(12, 7))
    style.configure('Treeview', rowheight=30, font=('Microsoft YaHei UI', 10))
    style.configure('Treeview.Heading', font=('Microsoft YaHei UI', 10, 'bold'))
    style.configure('TNotebook.Tab', padding=(18, 9))
    style.configure('Horizontal.TProgressbar', background='#2563eb', troughcolor='#dfe7f2')

    banner = tk.Frame(root, bg='#14243e', padx=24, pady=17)
    banner.pack(fill='x')
    tk.Label(banner, text='机械臂 · 无舵机演练', font=('Microsoft YaHei UI', 20, 'bold'),
             fg='white', bg='#14243e').pack(anchor='w')
    tk.Label(banner, text='与 Keil 固件共用 C 流程代码  /  本机模拟  /  无串口连接',
             fg='#b9cce7', bg='#14243e').pack(anchor='w', pady=(5,0))

    body = ttk.Frame(root, padding=18)
    body.pack(fill='both', expand=True)
    tabs = ttk.Notebook(body)
    tabs.pack(fill='both', expand=True)
    exercise, calibration = ttk.Frame(tabs, padding=15), ttk.Frame(tabs, padding=15)
    tabs.add(exercise, text='动作演练')
    tabs.add(calibration, text='关节与位置')
    status_label = ttk.Label(exercise, text='正在加载 C 流程…', font=('Microsoft YaHei UI', 15, 'bold'))
    status_label.pack(anchor='w')
    details = ttk.Label(exercise, text='')
    details.pack(anchor='w', pady=(4,10))
    starts = ttk.Frame(exercise)
    starts.pack(fill='x')
    action_buttons = {}
    def button(parent, label, command, key):
        b = ttk.Button(parent, text=label, command=lambda: send(command))
        b.pack(side='left', padx=(0,7), pady=3)
        action_buttons[key] = b
        return b
    for label, color in [('红色 → 左区','RED'), ('绿色 → 中区','GREEN'), ('蓝色 → 右区','BLUE')]:
        button(starts, '开始：' + label, 'START ' + color, color)
    mode = tk.StringVar(value='自动演练')
    mode_select = ttk.Combobox(starts, state='readonly', textvariable=mode,
                              values=['自动演练','手动确认'], width=11)
    mode_select.pack(side='right')
    mode_select.bind('<<ComboboxSelected>>', lambda event: send('SIM AUTO' if mode.get()=='自动演练' else 'SIM MANUAL'))
    controls = ttk.Frame(exercise)
    controls.pack(fill='x', pady=(4,7))
    for label, command in [('暂停','PAUSE'),('继续','RESUME'),('中止','STOP'),('复位','RESET')]:
        button(controls,label,command,command)
    ack = ttk.Button(controls, text='确认本步完成（模拟）', command=lambda: send('ACK '+str(sim.status()['ticket'])))
    ack.pack(side='left', padx=(5,0))
    progress = ttk.Progressbar(exercise, maximum=7)
    progress.pack(fill='x', pady=(0,12))

    split = ttk.Panedwindow(exercise, orient='horizontal')
    split.pack(fill='both', expand=True)
    phases = ttk.Frame(split, padding=(0,0,12,0))
    logging = ttk.Frame(split)
    split.add(phases, weight=2)
    split.add(logging, weight=3)
    step_names = ['准备','靠近目标','夹紧','抬起','移到放置区','松夹','返回准备位置']
    subtitles = ['准备姿态和夹爪状态','等待未来填入的抓取姿态','仅模拟夹爪动作完成',
                 '仅模拟离开抓取位置','红左 · 绿中 · 蓝右','仅模拟松开夹爪','完成后等待下一次复位']
    step_labels = []
    for index, (name, subtitle) in enumerate(zip(step_names,subtitles)):
        row = tk.Frame(phases, bg='#f8fafc', padx=12, pady=7)
        row.pack(fill='x', pady=(0,5))
        title = tk.Label(row, text=f'{index+1:02}  {name}', anchor='w', bg='#f8fafc',
                         fg='#44516a', font=('Microsoft YaHei UI',11,'bold'))
        title.pack(fill='x')
        tk.Label(row, text=subtitle, anchor='w', bg='#f8fafc',fg='#69788f',font=('Microsoft YaHei UI',9)).pack(fill='x')
        step_labels.append(title)
    ttk.Label(logging,text='流程日志（SIM_ACK 是模拟回执）').pack(anchor='w',pady=(0,5))
    log = ScrolledText(logging, state='disabled', wrap='word', height=15, width=53,
                       font=('Consolas',9), bg='#14243e', fg='#d9e6f8', insertbackground='white',relief='flat',padx=10,pady=10)
    log.pack(fill='both',expand=True)
    faults = ttk.Frame(logging)
    faults.pack(fill='x',pady=(6,0))
    button(faults,'模拟超时','SIM STALL','STALL')
    button(faults,'模拟失败','SIM FAIL','FAIL')
    command_row = ttk.Frame(exercise)
    command_row.pack(fill='x',pady=(10,0))
    ttk.Label(command_row,text='调试命令').pack(side='left')
    command_text = tk.StringVar()
    command_entry = ttk.Entry(command_row,textvariable=command_text)
    command_entry.pack(side='left',fill='x',expand=True,padx=8)
    def submit():
        text=command_text.get().strip()
        if text:
            send(text)
            command_text.set('')
    command_entry.bind('<Return>',lambda event: submit())
    ttk.Button(command_row,text='发送',command=submit).pack(side='right')

    ttk.Label(calibration,text='参数尚未标定',font=('Microsoft YaHei UI',15,'bold')).pack(anchor='w')
    ttk.Label(calibration,text='ID 1–4 是拟定分配；方向、零位、限位、速度与动作位置都没有猜测值。',
              wraplength=930).pack(anchor='w',pady=(7,14))
    joint_tree = ttk.Treeview(calibration, columns=('joint','id','direction','zero','limits','speed','state'),
                             show='headings',height=4)
    for key, title, width in [('joint','关节',130),('id','拟定 ID',75),('direction','方向',90),
                              ('zero','零位',90),('limits','限位',110),('speed','速度上限',110),('state','状态',120)]:
        joint_tree.heading(key,text=title); joint_tree.column(key,width=width,anchor='center')
    joint_tree.pack(fill='x')
    ttk.Label(calibration,text='动作姿态表',font=('Microsoft YaHei UI',12,'bold')).pack(anchor='w',pady=(20,8))
    pose_tree=ttk.Treeview(calibration,columns=('name','joints','position','time'),show='headings',height=8)
    for key,title,width in [('name','姿态',160),('joints','参与关节',220),('position','原始位置',260),('time','运动时间',100)]:
        pose_tree.heading(key,text=title); pose_tree.column(key,width=width,anchor='center')
    pose_tree.pack(fill='both',expand=True)
    ttk.Label(calibration,text='到货后修改 firmware/src/robot_config.c，再重建演练程序与 Keil 工程。\n'
              '本窗口只查看配置，不修改设备 ID、不保存假零位；自动演练的 1 秒计时不是真实运动时间。',
              wraplength=930).pack(anchor='w',pady=(14,0))
    ttk.Label(body,text='仅验证流程逻辑。位置、碰撞、夹持是否成功和真实舵机到位，需要实物标定与反馈。',
              wraplength=1000).pack(anchor='w',pady=(10,0))

    sim = Simulator()
    joint_names = {'BASE':'底座','SHOULDER':'肩关节','ELBOW':'肘关节','GRIPPER':'夹爪'}
    pose_names = {'READY':'准备','APPROACH':'靠近','GRIP':'夹紧','LIFT':'抬起',
                  'PLACE_RED':'红色放置','PLACE_GREEN':'绿色放置','PLACE_BLUE':'蓝色放置','RELEASE':'松夹'}
    sim.command('JOINTS',0)
    sim.command('POSES',0)
    initial_logs = list(sim.logs())
    for line in initial_logs:
        if line.startswith('JOINT '):
            parts=line.split(); p=dict(x.split('=',1) for x in parts[2:])
            def known(value, unknown): return '待标定' if value==unknown else value
            joint_tree.insert('', 'end', values=(joint_names[parts[1]],p['id'],known(p['dir'],'0'),
                known(p['zero'],'-1'),known(p['min'],'-1')+' / '+known(p['max'],'-1'),
                known(p['max_speed'],'0'),'待确认' if p['calibrated']=='0' else '已配置'))
        if line.startswith('POSE '):
            parts=line.split(); p=dict(x.split('=',1) for x in parts[2:])
            mask=int(p['mask'])
            joints='、'.join(name for i,name in enumerate(joint_names.values()) if mask&(1<<i))
            pose_tree.insert('','end',values=(pose_names[parts[1]],joints,
                '待标定' if p['calibrated']=='0' else p['raw'],'待标定' if p['move_ms']=='0' else p['move_ms']+' ms'))

    state_names={'IDLE':'等待开始','RUNNING':'正在演练','PAUSED':'已暂停','DONE':'演练完成',
                 'ABORTED':'已中止','FAULT':'演练故障'}
    color_names={'NONE':'未选择','RED':'红色','GREEN':'绿色','BLUE':'蓝色'}
    bin_names={'NONE':'—','LEFT':'左区','CENTER':'中区','RIGHT':'右区'}
    def now(): return int(time.monotonic()*1000)&0xffffffff
    def append(line):
        log.configure(state='normal')
        log.insert('end',line+'\n')
        if int(log.index('end-1c').split('.')[0])>800:
            log.delete('1.0','101.0')
        log.see('end'); log.configure(state='disabled')
    def refresh():
        for line in sim.logs(): append(line)
        s=sim.status(); state=s['state']; busy=state in ('RUNNING','PAUSED')
        status_label.configure(text=f"{state_names[state]}  ·  {color_names[s['color']]} → {bin_names[s['bin']]}")
        extra='请复位后再次开始' if state in ('DONE','ABORTED','FAULT') else '只演练逻辑，不输出舵机信号'
        details.configure(text=f"当前步骤 {s['step']+1}/7  ·  活动计时 {s['elapsed_ms']} ms / 3000 ms  ·  {extra}")
        if s['fault']!='NONE': details.configure(text='故障：'+('模拟动作超时' if s['fault']=='TIMEOUT' else '模拟动作失败')+'。复位不会移动机械臂。')
        progress['value']=7 if state=='DONE' else (0 if state=='IDLE' else s['step']+min(s['elapsed_ms']/1000,0.99))
        for i,label in enumerate(step_labels):
            mark='✓' if state=='DONE' or (state!='IDLE' and i<s['step']) else ('▶' if state!='IDLE' and i==s['step'] else f'{i+1:02}')
            label.configure(text=f'{mark}  {step_names[i]}',fg='#2563eb' if busy and i==s['step'] else '#44516a')
        for color in ('RED','GREEN','BLUE'): action_buttons[color].configure(state='normal' if state=='IDLE' else 'disabled')
        for key,enabled in [('PAUSE',state=='RUNNING'),('RESUME',state=='PAUSED'),('STOP',busy),
                            ('RESET',not busy),('STALL',state=='RUNNING' and s['mode']=='AUTO'),('FAIL',busy)]:
            action_buttons[key].configure(state='normal' if enabled else 'disabled')
        ack.configure(state='normal' if state=='RUNNING' and s['mode']=='MANUAL' else 'disabled')
        mode_select.configure(state='readonly' if state=='IDLE' else 'disabled')
        mode.set('自动演练' if s['mode']=='AUTO' else '手动确认')
    def send(text):
        append('> '+text)
        try: sim.command(text,now())
        except UnicodeEncodeError: append('命令使用英文；也可以直接点击上方按钮。')
        refresh()
    def tick():
        sim.poll(now()); refresh(); root.after(50,tick)
    append('准备就绪：选择颜色开始；所有完成回执均由模拟器产生。')
    append('硬件参数未标定，默认没有任何设备连接。')
    tick()
    root.mainloop()

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--demo',action='store_true',help='Run deterministic demonstration without a window')
    p.add_argument('--test',action='store_true',help='Build and run firmware workflow tests')
    a=p.parse_args()
    try:
        if a.test: print(run_tests())
        if a.demo: demo()
        if not a.test and not a.demo: gui()
    except Exception as exc:
        if a.test or a.demo: raise
        from tkinter import messagebox
        messagebox.showerror('演练程序启动失败',str(exc))
        raise
