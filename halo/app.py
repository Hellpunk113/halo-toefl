from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
import uuid
import wave
import zipfile
import ctypes
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from PIL import Image, ImageTk

try:
    import pygame
except Exception:
    pygame = None
try:
    import sounddevice as sd
except Exception:
    sd = None
try:
    import imageio_ffmpeg
except Exception:
    imageio_ffmpeg = None

from .db import Store, bundle_root, user_root
from .archive import clear_local_records, export_save, import_save
from .reports import attempt_stats, daily_data, export_daily

BLUE, NAVY, BG, INK, MUTED, BORDER = "#1f5e9d", "#153b68", "#f4f6f8", "#17212b", "#596775", "#d7dde4"
UI_FONT = "PingFang TC" if sys.platform == "darwin" else "Microsoft JhengHei UI"
SECTION_SECONDS = {"Reading": 30 * 60, "Listening": 29 * 60, "Writing": 23 * 60, "Speaking": 8 * 60}
ITEM_SECONDS = {
    "Complete the Words": 30, "Read in Daily Life": 60, "Read an Academic Passage": 75,
    "Build a Sentence": 60, "Listening": 35,
    "Listen and Choose a Response": 20, "Listen to a Conversation": 35,
    "Listen to an Announcement": 35, "Listen to an Academic Talk": 40,
}
VISUAL_POOLS = {
    "Listening": ["campus-service.jpg", "conversation-library.jpg", "female-professor.jpg"],
    "Listen and Choose a Response": ["campus-students.jpg", "response-doorway.jpg", "conversation-library.jpg"],
    "Listen to a Conversation": ["campus-service.jpg", "campus-students.jpg", "conversation-library.jpg"],
    "Listen to an Announcement": ["announcement-female.jpg", "announcement-male.jpg", "announcement-coordinator.jpg"],
    "Listen to an Academic Talk": ["female-professor.jpg", "male-professor.jpg", "science-professor.jpg"],
    "Listen and Repeat": ["announcement-male.jpg", "female-professor.jpg", "response-doorway.jpg"],
    "Take an Interview": ["female-interviewer.jpg", "male-interviewer.jpg", "campus-service.jpg"],
}


def open_folder(path: Path):
    """Open a folder with the native file manager on each desktop platform."""
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    elif os.name == "nt":
        os.startfile(str(path))
    else:
        subprocess.Popen(["xdg-open", str(path)])

if os.name == "nt":
    try:
        # Prevent Windows from bitmap-scaling the complete Tk window on HiDPI displays.
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass

ZH = {
    "Home":"首頁", "TOEFL mock exam software":"托福模考軟體", "2026 format · For internal beta distribution within Halo Education Research only":"2026 格式 · 僅在Halo教研企業內測分發",
    "Ready when you are.":"準備好就開始吧。", "Practice with locally stored sources and save every response on this computer.":"使用已安裝的題目練習，作答紀錄將儲存在本機。",
    "Start Full Mock":"開始完整模考", "Practice a Section":"單科練習", "Reports":"學習報告", "Recordings":"口說錄音", "Settings":"設定",
    "Unfinished test found":"發現未完成的測驗", "Resume":"繼續作答", "Discard":"捨棄", "Recent attempts":"最近作答紀錄", "No attempts yet.":"尚無作答紀錄。",
    "Test Library":"題庫", "Installed practice tests":"已安裝的模考題", "Official ETS":"ETS 官方", "Third-party":"第三方", "COMPLETE":"完整", "PARTIAL":"部分",
    "Completion":"完成度", "questions completed":"題已完成", "Exit Test":"退出測驗",
    "Attempt history":"作答紀錄", "Back to Library":"返回題庫", "Attempt":"第", "attempt":"次", "Completed":"已完成", "In progress":"進行中", "Discarded":"已捨棄", "No attempts for this test yet.":"這套題尚無作答紀錄。",
    "Portable save":"跨平台存檔", "Export portable save":"匯出跨平台存檔", "Import portable save":"載入跨平台存檔",
    "Portable save description":"保存每次作答、答案、進度、寫作、口說錄音及雙語解析，可供其他電腦與未來版本載入。",
    "Save exported":"存檔已匯出", "Save imported":"存檔已載入", "attempts exported":"次作答已匯出", "attempts imported":"次作答已載入", "existing attempts skipped":"次既有作答已略過", "Import error":"載入錯誤",
    "Clear local records":"清空本機存檔與作答紀錄", "Clear records warning":"這會永久刪除本機所有作答、答案、計時進度、寫作及口說錄音，且無法復原。",
    "Type ACCESS to continue":"請輸入 ACCESS 以繼續", "ACCESS did not match. Nothing was deleted.":"輸入內容不符，未刪除任何資料。",
    "Final irreversible confirmation":"最後確認：刪除後無法復原。確定要清空本機全部存檔與作答紀錄嗎？", "Local records cleared":"本機存檔與作答紀錄已全部清除。",
    "This is not a valid HALO TOEFL save file.":"這不是有效的 HALO TOEFL 存檔。", "Unsupported HALO TOEFL save format.":"不支援此 HALO TOEFL 存檔版本。",
    "The save file failed its integrity check.":"存檔完整性檢查失敗。", "A recording in the save file failed its integrity check.":"存檔中的口說錄音完整性檢查失敗。", "Unsafe recording path in save file.":"存檔包含不安全的錄音路徑。",
    "Sections available":"可用科目", "None":"無", "Start Full Test":"開始完整測驗", "Reading":"閱讀", "Listening":"聽力", "Writing":"寫作", "Speaking":"口說",
    "Full mock unavailable":"無法開始完整模考", "No imported test has every required Listening and Speaking asset yet. Use section practice for the available source material.":"目前沒有具備全部聽力與口說素材的完整題套，請使用單科練習。",
    "No questions":"沒有題目", "This source could not be converted into questions.":"此來源無法可靠地轉換為題目。", "Audio incomplete":"音訊不完整",
    "This test cannot be run as a full mock until all Listening audio is mapped.":"全部聽力音訊完成配對前，此題套不能進行完整模考。", "Listening is not offered because necessary audio is unavailable.":"缺少必要音訊，無法進行聽力練習。",
    "Time":"時間", "Question":"第", "of":"題，共", "Module":"模組", "Audio plays once during the exam.":"考試中音訊只播放一次。", "Enter the missing letters:":"輸入缺少的字母：",
    "words · saved":"字 · 已儲存", "Microphone check: speak normally and watch the input meter before recording.":"麥克風檢查：請正常說話並查看輸入音量。", "Start Recording":"開始錄音",
    "Play Prompt":"播放題目音訊", "Responses are saved as WAV in your local HALO TOEFL recordings folder.":"回答將以 WAV 格式儲存在本機 HALO TOEFL 錄音資料夾。", "Stop Recording":"停止錄音", "Recorded · Record Again":"已錄音 · 重新錄製",
    "Microphone unavailable":"麥克風無法使用", "The audio recording component is unavailable.":"錄音元件無法使用。", "Microphone error":"麥克風錯誤", "Recording error":"錄音錯誤", "Playback error":"播放錯誤",
    "Back":"上一題", "Next":"下一題", "Finish":"完成", "section":"科", "is about to begin. Your progress is saved automatically.":"即將開始，作答進度會自動儲存。",
    "Mock Test Complete":"模考完成", "estimated":"預估", "Completed":"已完成", "Not completed":"未完成", "answered":"已作答", "Total time":"總時間", "minutes":"分鐘",
    "Review":"檢討", "Export Daily Report":"匯出每日報告", "Back to Home":"返回首頁", "My answer":"我的答案", "Correct answer":"正確答案", "Manual review":"人工評閱", "Replay audio":"重播音訊",
    "Explanation":"解析", "Review locked":"解析尚未開放", "Complete the test before viewing answers and explanations.":"完成整份測驗後才能查看答案與解析。",
    "Explanations are generated from the question, answer key, and source material.":"解析依題目、正解與原始材料生成。",
    "Daily Reports":"每日報告", "Local date":"本地日期", "Total study time":"總學習時間", "Sessions":"練習次數", "Full mocks":"完整模考", "Questions answered":"作答題數", "Accuracy":"正確率", "Speaking prompts":"口說題數", "Writing words":"寫作字數",
    "Export PDF":"匯出 PDF", "Export CSV":"匯出 CSV", "Export JSON":"匯出 JSON", "Export Daily Package":"匯出每日資料包", "Export complete":"匯出完成", "Export error":"匯出錯誤",
    "Saved speaking answers":"已儲存的口說回答", "No recordings yet.":"尚無錄音。", "Open Folder":"開啟資料夾", "Export WAV":"匯出 WAV", "Play":"播放",
    "Export MP3":"匯出 MP3", "Export Attempt Recordings":"匯出本次錄音", "Export Today's Speaking Recordings":"匯出今日口說錄音",
    "Audio input":"音訊輸入", "No microphone device detected":"未偵測到麥克風", "Save microphone selection":"儲存麥克風選擇", "Saved":"已儲存", "Microphone selection saved.":"麥克風選擇已儲存。", "Data folder":"資料資料夾",
    "Language":"介面語言", "Taiwan Traditional Chinese":"台灣正體", "English":"English", "Save language":"儲存語言", "Language saved.":"語言已儲存。",
    "Complete the Words":"完成單字", "Read in Daily Life":"生活情境閱讀", "Read an Academic Passage":"學術文章閱讀",
    "Listen and Choose a Response":"聽音選擇回應", "Listen to a Conversation":"聽對話", "Listen to an Announcement":"聽公告", "Listen to an Academic Talk":"聽學術講座",
    "Build a Sentence":"組成句子", "Write an Email":"撰寫電子郵件", "Write for an Academic Discussion":"學術討論寫作", "Listen and Repeat":"聽後複誦", "Take an Interview":"接受訪談",
    "SYNTHETIC AUDIO — NOT ORIGINAL TEST AUDIO":"合成音訊（非原始測驗音訊）",
    "AI-GENERATED NEURAL AUDIO — NOT ORIGINAL TEST AUDIO":"AI 神經語音（非原始測驗音訊）",
    "IN_PROGRESS":"進行中", "DISCARDED":"已捨棄", "FULL":"完整模考", "SECTION":"單科練習",
    "Test setup":"測驗設定", "Official section times":"官方科目時間", "Use countdown timer":"啟用倒數計時",
    "The timer counts down separately for each section.":"各科將分別依官方時長倒數。", "Start Test":"開始測驗",
    "Countdown off":"倒數計時已關閉", "Time is up":"時間到", "The section time has ended.":"本科作答時間已結束。",
    "Reading passage":"閱讀文章", "Answer area":"作答區", "Type only the missing letters in the blank.":"請直接在文章空格內輸入缺少的字母。",
    "Section time":"科目", "Question time":"本題", "Audio playing":"音訊播放中",
}


class HaloApp(tk.Tk):
    def __init__(self):
        super().__init__()
        try:
            self.tk.call("tk", "scaling", self.winfo_fpixels("1i") / 72.0)
            import tkinter.font as tkfont
            for name,size in {"TkDefaultFont":11,"TkTextFont":12,"TkMenuFont":10,"TkHeadingFont":12,"TkCaptionFont":11}.items():
                tkfont.nametofont(name).configure(family=UI_FONT,size=size)
        except Exception:
            pass
        self.title("HALO TOEFL")
        if os.name == "nt":
            try:
                self.iconbitmap(default=str(bundle_root() / "artwork" / "HALO-TOEFL.ico"))
                self._app_icon = ImageTk.PhotoImage(Image.open(bundle_root() / "artwork" / "HALO-TOEFL-icon.png"))
                self.iconphoto(True, self._app_icon)
            except Exception:
                pass
        self.dpi_scale = max(1.0, self.winfo_fpixels("1i") / 96.0)
        self.geometry(f"{round(1180*self.dpi_scale)}x{round(760*self.dpi_scale)}")
        self.minsize(round(980*self.dpi_scale), round(650*self.dpi_scale))
        self.configure(bg=BG)
        self.store = Store()
        self.lang = self.store.setting("language", "zh-TW")
        self.current_attempt = None
        self.exam_questions = []
        self.exam_index = 0
        self.exam_started = 0
        self.recording = None
        self.record_started = 0
        self.audio_played = set()
        self.timer_generation = 0
        self.countdown_enabled = True
        self.timer_section = None
        self.timer_remaining = 0
        self.timer_ticks = 0
        self.timer_timeout_handled = False
        self.timer_question = None
        self.question_remaining = 0
        self.question_timeout_handled = False
        self.current_visual = None
        self.cloze_prefix = ""
        self.cloze_store_whole = False
        self.protocol("WM_DELETE_WINDOW", self.close)
        if pygame:
            try: pygame.mixer.init()
            except Exception: pass
        self.show_home()

    def tr(self, text):
        return ZH.get(text, text) if self.lang == "zh-TW" else text

    def section_name(self, text):
        return self.tr(text)

    def status_name(self, text):
        return self.tr(text)

    def close(self):
        self.save_progress()
        if pygame:
            try: pygame.mixer.quit()
            except Exception: pass
        self.destroy()

    def clear(self):
        self.timer_generation += 1
        self.unbind_all("<MouseWheel>")
        for child in self.winfo_children(): child.destroy()

    def header(self, title, subtitle="", show_home_button=True):
        frame = tk.Frame(self, bg=NAVY, height=86)
        frame.pack(fill="x")
        tk.Label(frame, text="HALO TOEFL", font=(UI_FONT, 18, "bold"), bg=NAVY, fg="white").pack(side="left", padx=30, pady=20)
        text = title + ("\n" + subtitle if subtitle else "")
        tk.Label(frame, text=text, font=(UI_FONT, 10, "bold"), bg=NAVY, fg="white", justify="left").pack(side="left", padx=18)
        if show_home_button:
            tk.Button(frame, text=self.tr("Home"), command=self.show_home, bg="#ffffff", fg=NAVY, relief="flat", padx=14).pack(side="right", padx=18)

    def button(self, parent, text, command, primary=True, **kw):
        return tk.Button(parent, text=text, command=command, font=(UI_FONT, 10, "bold"),
                         bg=BLUE if primary else "white", fg="white" if primary else NAVY,
                         activebackground="#174d82", activeforeground="white", relief="solid", bd=1,
                         padx=16, pady=9, **kw)

    def card(self, parent):
        return tk.Frame(parent, bg="white", highlightbackground=BORDER, highlightthickness=1)

    def show_home(self):
        self.current_attempt = None
        self.clear()
        self.header(self.tr("TOEFL mock exam software"), self.tr("2026 format · For internal beta distribution within Halo Education Research only"), show_home_button=False)
        body = tk.Frame(self, bg=BG); body.pack(fill="both", expand=True, padx=54, pady=35)
        tk.Label(body, text=self.tr("Ready when you are."), font=(UI_FONT, 28, "bold"), bg=BG, fg=INK).pack(anchor="w")
        tk.Label(body, text=self.tr("Practice with locally stored sources and save every response on this computer."), font=(UI_FONT, 12), bg=BG, fg=MUTED).pack(anchor="w", pady=(5,25))
        actions = tk.Frame(body, bg=BG); actions.pack(anchor="w")
        self.button(actions, self.tr("Start Full Mock"), self.start_full_mock).grid(row=0,column=0,padx=(0,10))
        self.button(actions, self.tr("Practice a Section"), self.show_library, False).grid(row=0,column=1,padx=10)
        self.button(actions, self.tr("Reports"), self.show_reports, False).grid(row=0,column=2,padx=10)
        self.button(actions, self.tr("Recordings"), self.show_recordings, False).grid(row=0,column=3,padx=10)
        self.button(actions, self.tr("Settings"), self.show_settings, False).grid(row=0,column=4,padx=10)
        unfinished = self.store.unfinished()
        if unfinished:
            resume = self.card(body); resume.pack(fill="x", pady=(28,12))
            tk.Label(resume, text=self.tr("Unfinished test found"), font=(UI_FONT, 13, "bold"), bg="white", fg=INK).pack(side="left", padx=18, pady=14)
            self.button(resume, self.tr("Resume"), lambda: self.resume_attempt(unfinished["id"])).pack(side="right", padx=12, pady=8)
            self.button(resume, self.tr("Discard"), lambda: (self.store.finish(unfinished["id"], "DISCARDED"), self.show_home()), False).pack(side="right", padx=4, pady=8)
        recent = self.card(body); recent.pack(fill="both", expand=True, pady=(20,0))
        tk.Label(recent, text=self.tr("Recent attempts"), font=(UI_FONT, 14, "bold"), bg="white", fg=INK).pack(anchor="w", padx=20, pady=(18,10))
        rows = self.store.db.execute("SELECT a.*,t.name FROM attempts a JOIN tests t ON a.test_id=t.id ORDER BY a.started DESC LIMIT 8").fetchall()
        if not rows: tk.Label(recent, text=self.tr("No attempts yet."), bg="white", fg=MUTED).pack(anchor="w", padx=20, pady=14)
        for r in rows:
            line = tk.Frame(recent, bg="white"); line.pack(fill="x", padx=20, pady=5)
            tk.Label(line, text=f"{r['name']}  ·  {self.tr(r['mode'])}  ·  {self.tr(r['status'])}", bg="white", fg=INK, font=(UI_FONT,10)).pack(side="left")
            tk.Label(line, text=r["started"][:19].replace("T"," "), bg="white", fg=MUTED).pack(side="right")

    def start_full_mock(self):
        choices = [t for t in self.store.tests() if t["status"] == "COMPLETE"]
        if not choices:
            messagebox.showinfo(self.tr("Full mock unavailable"), self.tr("No imported test has every required Listening and Speaking asset yet. Use section practice for the available source material."))
            self.show_library(); return
        self.start_attempt(choices[0]["id"], "FULL", ["Reading","Listening","Writing","Speaking"])

    def show_library(self):
        self.clear(); self.header(self.tr("Test Library"), self.tr("Installed practice tests"))
        shell=tk.Frame(self,bg=BG);shell.pack(fill="both",expand=True,padx=32,pady=18)
        canvas=tk.Canvas(shell,bg=BG,highlightthickness=0)
        scrollbar=ttk.Scrollbar(shell,orient="vertical",command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right",fill="y");canvas.pack(side="left",fill="both",expand=True)
        body=tk.Frame(canvas,bg=BG);window=canvas.create_window((0,0),window=body,anchor="nw")
        body.bind("<Configure>",lambda _e:canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",lambda e:canvas.itemconfigure(window,width=e.width))
        def wheel(event):
            if canvas.winfo_exists():canvas.yview_scroll(-1 if event.delta>0 else 1,"units")
        self.bind_all("<MouseWheel>",wheel)
        for test in self.store.tests():
            c=self.card(body); c.pack(fill="x",pady=7)
            top=tk.Frame(c,bg="white"); top.pack(fill="x",padx=18,pady=(14,4))
            tk.Label(top,text=test["name"],font=(UI_FONT,13,"bold"),bg="white",fg=INK).pack(side="left")
            tk.Label(top,text=self.tr("Official ETS" if test["category"]=="OFFICIAL_ETS" else "Third-party")+" · "+self.status_name(test["status"]),bg="white",fg=BLUE).pack(side="right")
            sections=[r["name"] for r in self.store.db.execute("SELECT name FROM sections WHERE test_id=?",(test["id"],))]
            tk.Label(c,text=f"{test['provider']}  ·  {self.tr('Sections available')}: {', '.join(self.section_name(s) for s in sections) or self.tr('None')}",bg="white",fg=MUTED).pack(anchor="w",padx=18,pady=4)
            answered,total,percent=self.store.test_completion(test["id"])
            attempt_count=self.store.db.execute("SELECT COUNT(*) FROM attempts WHERE test_id=?",(test["id"],)).fetchone()[0]
            progress=tk.Frame(c,bg="white");progress.pack(fill="x",padx=18,pady=(5,4))
            tk.Label(progress,text=f"{self.tr('Completion')} {percent}%  ·  {answered}/{total} {self.tr('questions completed')}",font=(UI_FONT,10,"bold"),bg="white",fg=BLUE).pack(side="left")
            self.button(progress,f"{self.tr('Attempt history')} ({attempt_count})",lambda x=test["id"]:self.show_test_history(x),False).pack(side="right",padx=(18,0))
            ttk.Progressbar(c,maximum=100,value=percent).pack(fill="x",padx=18,pady=(0,5))
            if test["audio_notice"]:
                tk.Label(c,text=self.tr(test["audio_notice"]),bg="white",fg="#9a5b13",font=(UI_FONT,9,"bold")).pack(anchor="w",padx=18,pady=(0,4))
            bar=tk.Frame(c,bg="white");bar.pack(anchor="w",padx=18,pady=(4,14))
            unfinished=self.store.db.execute("SELECT id FROM attempts WHERE test_id=? AND status='IN_PROGRESS' ORDER BY started DESC LIMIT 1",(test["id"],)).fetchone()
            if unfinished:self.button(bar,self.tr("Resume"),lambda x=unfinished["id"]:self.resume_attempt(x)).pack(side="left",padx=(0,7))
            if test["status"]=="COMPLETE": self.button(bar,self.tr("Start Full Test"),lambda x=test["id"]:self.start_attempt(x,"FULL",["Reading","Listening","Writing","Speaking"])).pack(side="left",padx=(0,7))
            for section in sections:
                self.button(bar,self.section_name(section),lambda x=test["id"],s=section:self.start_attempt(x,"SECTION",[s]),False).pack(side="left",padx=3)

    def start_attempt(self, test_id, mode, sections):
        questions=self.store.questions(test_id,sections)
        if not questions: messagebox.showwarning(self.tr("No questions"), self.tr("This source could not be converted into questions.")); return
        if "Listening" in sections and not self.store.audio_ok(test_id,"Listening"):
            if mode=="FULL": messagebox.showwarning(self.tr("Audio incomplete"), self.tr("This test cannot be run as a full mock until all Listening audio is mapped.")); return
            messagebox.showwarning(self.tr("Audio incomplete"), self.tr("Listening is not offered because necessary audio is unavailable.")); return
        self.show_start_options(test_id, mode, sections, questions)

    def show_test_history(self,test_id):
        test=self.store.db.execute("SELECT * FROM tests WHERE id=?",(test_id,)).fetchone()
        if not test:self.show_library();return
        self.clear();self.header(self.tr("Attempt history"),test["name"])
        shell=tk.Frame(self,bg=BG);shell.pack(fill="both",expand=True,padx=48,pady=20)
        actions=tk.Frame(shell,bg=BG);actions.pack(fill="x",pady=(0,10))
        self.button(actions,self.tr("Back to Library"),self.show_library,False).pack(side="left")
        canvas=tk.Canvas(shell,bg=BG,highlightthickness=0);scroll=ttk.Scrollbar(shell,orient="vertical",command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set);scroll.pack(side="right",fill="y");canvas.pack(side="left",fill="both",expand=True)
        body=tk.Frame(canvas,bg=BG);window=canvas.create_window((0,0),window=body,anchor="nw")
        body.bind("<Configure>",lambda _e:canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",lambda e:canvas.itemconfigure(window,width=e.width))
        self.bind_all("<MouseWheel>",lambda e:canvas.yview_scroll(-1 if e.delta>0 else 1,"units"))
        rows=self.store.db.execute("SELECT * FROM attempts WHERE test_id=? ORDER BY started",(test_id,)).fetchall()
        if not rows:
            tk.Label(body,text=self.tr("No attempts for this test yet."),font=(UI_FONT,13),bg=BG,fg=MUTED).pack(anchor="w",pady=20);return
        numbers={row["id"]:index for index,row in enumerate(rows,1)}
        for row in reversed(rows):
            answered,total,percent=self.store.attempt_completion(row["id"])
            status={"COMPLETE":self.tr("Completed"),"IN_PROGRESS":self.tr("In progress"),"DISCARDED":self.tr("Discarded")}.get(row["status"],row["status"])
            number=f"第 {numbers[row['id']]} 次" if self.lang=="zh-TW" else f"Attempt {numbers[row['id']]}"
            sections=("、" if self.lang=="zh-TW" else ", ").join(self.section_name(s) for s in json.loads(row["sections"]))
            card=self.card(body);card.pack(fill="x",pady=7)
            top=tk.Frame(card,bg="white");top.pack(fill="x",padx=18,pady=(14,5))
            tk.Label(top,text=f"{number}  ·  {self.tr(row['mode'])}",font=(UI_FONT,13,"bold"),bg="white",fg=INK).pack(side="left")
            tk.Label(top,text=status,font=(UI_FONT,10,"bold"),bg="white",fg=BLUE).pack(side="right")
            tk.Label(card,text=f"{row['started'][:19].replace('T',' ')}  ·  {sections}",bg="white",fg=MUTED).pack(anchor="w",padx=18,pady=3)
            tk.Label(card,text=f"{self.tr('Completion')} {percent}%  ·  {answered}/{total} {self.tr('questions completed')}",bg="white",fg=INK).pack(anchor="w",padx=18,pady=3)
            ttk.Progressbar(card,maximum=100,value=percent).pack(fill="x",padx=18,pady=(2,8))
            row_actions=tk.Frame(card,bg="white");row_actions.pack(fill="x",padx=18,pady=(0,12))
            if row["status"]=="IN_PROGRESS":self.button(row_actions,self.tr("Resume"),lambda x=row["id"]:self.resume_attempt(x)).pack(side="left")
            elif row["status"]=="COMPLETE":self.button(row_actions,self.tr("Review"),lambda x=row["id"]:self.show_review(x),False).pack(side="left")

    def show_start_options(self, test_id, mode, sections, questions):
        self.clear(); self.header(self.tr("Test setup"), self.tr("Official section times"))
        body=tk.Frame(self,bg=BG);body.pack(fill="both",expand=True,padx=120,pady=55)
        card=self.card(body);card.pack(fill="x")
        tk.Label(card,text=self.tr("Official section times"),font=(UI_FONT,18,"bold"),bg="white",fg=INK).pack(anchor="w",padx=28,pady=(26,14))
        for section in sections:
            minutes=SECTION_SECONDS[section]//60
            tk.Label(card,text=f"{self.section_name(section)}   {minutes} {self.tr('minutes')}",font=(UI_FONT,12),bg="white",fg=INK).pack(anchor="w",padx=32,pady=5)
        enabled=self.store.setting("countdown_enabled","1") != "0"
        self.countdown_choice=tk.BooleanVar(value=enabled)
        tk.Checkbutton(card,text=self.tr("Use countdown timer"),variable=self.countdown_choice,font=(UI_FONT,14,"bold"),bg="white",fg=NAVY,activebackground="white",selectcolor="#dcecff",padx=8,pady=5).pack(anchor="w",padx=28,pady=(22,4))
        tk.Label(card,text=self.tr("The timer counts down separately for each section."),bg="white",fg=MUTED).pack(anchor="w",padx=32,pady=(0,24))
        actions=tk.Frame(body,bg=BG);actions.pack(fill="x",pady=18)
        self.button(actions,self.tr("Back"),self.show_library,False).pack(side="left")
        self.button(actions,self.tr("Start Test"),lambda:self.begin_attempt(test_id,mode,sections,questions,self.countdown_choice.get())).pack(side="right")

    def begin_attempt(self, test_id, mode, sections, questions, countdown_enabled):
        aid=uuid.uuid4().hex
        self.store.set_setting("countdown_enabled","1" if countdown_enabled else "0")
        self.store.make_attempt(aid,test_id,mode,sections,countdown_enabled,SECTION_SECONDS)
        self.current_attempt=aid;self.exam_questions=questions;self.exam_index=0;self.exam_started=time.time();self.audio_played=set()
        self.countdown_enabled=bool(countdown_enabled);self.timer_section=None;self.timer_timeout_handled=False
        self.timer_question=None;self.question_timeout_handled=False
        self.show_exam()

    def resume_attempt(self, attempt_id):
        attempt=self.store.db.execute("SELECT * FROM attempts WHERE id=?",(attempt_id,)).fetchone()
        self.current_attempt=attempt_id; self.exam_questions=self.store.questions(attempt["test_id"], __import__("json").loads(attempt["sections"]))
        self.exam_index=min(attempt["index_position"],len(self.exam_questions)-1);self.exam_started=time.time()-attempt["elapsed_seconds"];self.audio_played=set()
        self.countdown_enabled=bool(attempt["countdown_enabled"]);self.timer_section=None;self.timer_timeout_handled=False
        self.timer_question=None;self.question_timeout_handled=False
        self.show_exam()

    def save_progress(self):
        if self.current_attempt:
            self.store.progress(self.current_attempt,self.exam_index,int(time.time()-self.exam_started))
            if self.countdown_enabled and self.timer_section:
                self.store.set_section_time(self.current_attempt,self.timer_section,self.timer_remaining)
            if self.countdown_enabled and self.timer_question:
                self.store.set_question_time(self.current_attempt,self.timer_question,self.question_remaining)

    def show_exam(self):
        self.clear(); q=self.exam_questions[self.exam_index]; total=len(self.exam_questions)
        self.activate_section_timer(q["section"])
        self.activate_question_timer(q)
        self.configure(bg="white")
        top=tk.Frame(self,bg=NAVY);top.pack(fill="x")
        tk.Label(top,text=f"{self.section_name(q['section'])}  ·  {self.tr(q['type'])}",bg=NAVY,fg="white",font=(UI_FONT,13,"bold")).pack(side="left",padx=26,pady=15)
        tk.Button(top,text=self.tr("Exit Test"),command=self.exit_exam,font=(UI_FONT,10,"bold"),bg="white",fg=NAVY,activebackground="#e7f1fb",relief="flat",padx=14,pady=6).pack(side="right",padx=(8,20),pady=9)
        self.timer_label=tk.Label(top,text="",bg=NAVY,fg="white",font=(UI_FONT,12));self.timer_label.pack(side="right",padx=25)
        generation=self.timer_generation
        self.tick_timer(generation)
        prog=tk.Frame(self,bg="#e8eef4");prog.pack(fill="x")
        progress=(f"第 {self.exam_index+1} 題，共 {total} 題  ·  模組 {q['module']}" if self.lang=="zh-TW" else f"Question {self.exam_index+1} of {total}  ·  Module {q['module']}")
        tk.Label(prog,text=progress,bg="#e8eef4",fg=INK).pack(anchor="w",padx=28,pady=9)
        content=tk.Frame(self,bg="white");content.pack(fill="both",expand=True,padx=28,pady=20)
        if q["section"]=="Listening": self.play_question_audio(q, auto=True)
        split_reading=q["section"]=="Reading" and bool(q["stimulus"])
        if split_reading:
            panes=tk.PanedWindow(content,orient="horizontal",sashwidth=7,sashrelief="flat",bg=BORDER,bd=0)
            panes.pack(fill="both",expand=True)
            left=tk.Frame(panes,bg="#f7f9fb",highlightbackground=BORDER,highlightthickness=1)
            right=tk.Frame(panes,bg="white",padx=28,pady=10)
            panes.add(left,stretch="always",minsize=390);panes.add(right,stretch="always",minsize=390)
            def center_sash(event):
                def place():
                    if panes.winfo_exists() and panes.winfo_width()>800:
                        panes.sash_place(0,panes.winfo_width()//2,1)
                panes.after_idle(place)
            panes.bind("<Configure>",center_sash)
            tk.Label(left,text=self.tr("Reading passage"),font=(UI_FONT,10,"bold"),bg="#e8eef4",fg=NAVY,padx=14,pady=9).pack(fill="x")
            if q["type"]=="Complete the Words": self.show_cloze_passage(left,q)
            else: self.show_stimulus(left,q["stimulus"])
            question_parent=right
            tk.Label(right,text=self.tr("Answer area"),font=(UI_FONT,10,"bold"),bg="white",fg=BLUE).pack(anchor="w",pady=(0,12))
        elif q["section"] in ("Listening","Speaking") and q["type"] in VISUAL_POOLS:
            panes=tk.PanedWindow(content,orient="horizontal",sashwidth=7,sashrelief="flat",bg=BORDER,bd=0)
            panes.pack(fill="both",expand=True)
            visual=tk.Frame(panes,bg="#edf2f7",highlightbackground=BORDER,highlightthickness=1)
            right=tk.Frame(panes,bg="white",padx=30,pady=8)
            panes.add(visual,stretch="always",minsize=360);panes.add(right,stretch="always",minsize=430)
            panes.bind("<Configure>",lambda _e,p=panes:p.after_idle(lambda:p.sash_place(0,p.winfo_width()//2,1) if p.winfo_exists() and p.winfo_width()>800 else None))
            self.show_task_visual(visual,q)
            question_parent=right
        else:
            question_parent=content
            if q["stimulus"]: self.show_stimulus(content,q["stimulus"],height=10)
        if q["section"]=="Listening":
            tk.Label(question_parent,text=self.tr("Audio plays once during the exam."),bg="white",fg=MUTED).pack(anchor="w",pady=(0,10))
        prompt = self.tr("Type only the missing letters in the blank.") if q["type"]=="Complete the Words" else q["prompt"]
        tk.Label(question_parent,text=prompt,font=(UI_FONT,17,"bold"),bg="white",fg=INK,wraplength=520 if split_reading else 920,justify="left").pack(anchor="w",pady=(4,20))
        if q["section"]=="Writing": self.show_writing(question_parent,q)
        elif q["section"]=="Speaking": self.show_speaking(question_parent,q)
        elif q["type"]!="Complete the Words": self.show_choices(question_parent,q)
        footer=tk.Frame(self,bg="white");footer.pack(fill="x",padx=35,pady=(0,22))
        if self.exam_index>0 and not (q["section"]=="Listening") and self.exam_questions[self.exam_index-1]["section"]==q["section"]:
            self.button(footer,self.tr("Back"),self.back,False).pack(side="left")
        next_text=self.tr("Finish") if self.exam_index==total-1 else self.tr("Next")
        self.button(footer,next_text,self.next).pack(side="right")

    def activate_section_timer(self, section):
        if not self.countdown_enabled:
            self.timer_section=section;return
        if self.timer_section != section:
            if self.timer_section and self.current_attempt:
                self.store.set_section_time(self.current_attempt,self.timer_section,self.timer_remaining)
            self.timer_section=section
            self.timer_remaining=self.store.section_time(self.current_attempt,section,SECTION_SECONDS[section])
            self.timer_timeout_handled=False

    def activate_question_timer(self, question):
        timed = self.countdown_enabled and question["type"] in ITEM_SECONDS
        question_id = question["id"] if timed else None
        if self.timer_question != question_id:
            if self.timer_question and self.current_attempt:
                self.store.set_question_time(self.current_attempt,self.timer_question,self.question_remaining)
            self.timer_question=question_id
            if question_id:
                self.question_remaining=self.store.question_time(self.current_attempt,question_id,ITEM_SECONDS[question["type"]])
            self.question_timeout_handled=False

    def tick_timer(self, generation):
        if generation != self.timer_generation or not self.current_attempt or not hasattr(self,"timer_label"): return
        if not self.countdown_enabled:
            self.timer_label.configure(text=self.tr("Countdown off"))
        else:
            secs=max(0,int(self.timer_remaining))
            section_text=f"{self.tr('Section time')} {secs//3600:02d}:{secs%3600//60:02d}:{secs%60:02d}"
            question_text=""
            q=self.exam_questions[self.exam_index]
            audio_busy=bool(q["section"]=="Listening" and pygame and q.get("audio") and q["id"] in self.audio_played and pygame.mixer.music.get_busy())
            if self.timer_question:
                qsecs=max(0,int(self.question_remaining))
                question_text=f"  ·  {self.tr('Question time')} " + (self.tr("Audio playing") if audio_busy else f"{qsecs//60:02d}:{qsecs%60:02d}")
            self.timer_label.configure(text=section_text+question_text)
            if secs == 0:
                if not self.timer_timeout_handled:
                    self.timer_timeout_handled=True
                    self.after(10,lambda:self.handle_timeout(self.timer_section))
                return
            self.timer_remaining-=1;self.timer_ticks+=1
            if self.timer_question and not audio_busy:
                if self.question_remaining<=0:
                    if not self.question_timeout_handled:
                        self.question_timeout_handled=True
                        current=self.timer_question
                        self.after(10,lambda:self.handle_question_timeout(current))
                    return
                self.question_remaining-=1
            if self.timer_ticks % 5 == 0:
                self.store.set_section_time(self.current_attempt,self.timer_section,self.timer_remaining)
                if self.timer_question:
                    self.store.set_question_time(self.current_attempt,self.timer_question,self.question_remaining)
        self.after(1000,lambda:self.tick_timer(generation))

    def handle_timeout(self, section):
        if not self.current_attempt or self.exam_questions[self.exam_index]["section"] != section:return
        self.save_current_answer();self.save_progress()
        messagebox.showinfo(self.tr("Time is up"),self.tr("The section time has ended."))
        next_index=next((i for i in range(self.exam_index+1,len(self.exam_questions)) if self.exam_questions[i]["section"]!=section),None)
        if next_index is None:self.finish_attempt();return
        self.exam_index=next_index;self.instructions(self.exam_questions[next_index]["section"]);self.show_exam()

    def handle_question_timeout(self, question_id):
        if not self.current_attempt or self.exam_questions[self.exam_index]["id"]!=question_id:return
        self.next()

    def show_task_visual(self,parent,q):
        names=VISUAL_POOLS[q["type"]]
        attempt=self.store.db.execute("SELECT test_id FROM attempts WHERE id=?",(self.current_attempt,)).fetchone()
        seed=f"{attempt[0] if attempt else ''}:{q['type']}:{q['id']}".encode()
        name=names[int.from_bytes(hashlib.sha256(seed).digest()[:4],"big")%len(names)]
        path=bundle_root()/"resources"/"images"/"people"/name
        image=Image.open(path).convert("RGB")
        size=(round(350*self.dpi_scale),round(263*self.dpi_scale))
        image.thumbnail(size,Image.Resampling.LANCZOS)
        self.current_visual=ImageTk.PhotoImage(image)
        holder=tk.Frame(parent,bg="#edf2f7");holder.pack(fill="both",expand=True,padx=18,pady=18)
        tk.Label(holder,image=self.current_visual,bg="#edf2f7",bd=0).pack(expand=True)

    def show_stimulus(self,parent,text,height=None):
        box=tk.Frame(parent,bg="#f7f9fb");box.pack(fill="both",expand=True,padx=12,pady=12)
        stim=tk.Text(box,height=height,wrap="word",font=(UI_FONT,14),bg="#f7f9fb",fg=INK,relief="flat",padx=12,pady=10,spacing2=3)
        scroll=ttk.Scrollbar(box,orient="vertical",command=stim.yview);stim.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right",fill="y");stim.pack(side="left",fill="both",expand=True)
        stim.insert("1.0",text);stim.configure(state="disabled")

    def show_cloze_passage(self,parent,q):
        box=tk.Frame(parent,bg="#f7f9fb");box.pack(fill="both",expand=True,padx=12,pady=12)
        text=tk.Text(box,wrap="word",font=(UI_FONT,14),bg="#f7f9fb",fg=INK,relief="flat",padx=12,pady=10,spacing2=4)
        scroll=ttk.Scrollbar(box,orient="vertical",command=text.yview);text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right",fill="y");text.pack(side="left",fill="both",expand=True)
        pattern=re.compile(r"(?P<prefix>[A-Za-z]+)(?P<between>[ \t\r\n]*)(?P<gap>_+(?:[ \t]*_+)*|-+(?:[ \t\r\n]*-+)*(?![ \t\r\n]*[A-Za-z]))(?P<label>\d{1,2})?")
        matches=list(pattern.finditer(q["stimulus"]))
        blank=int((re.search(r"blank\s+(\d+)",q["prompt"],re.I) or [None,"1"])[1])
        target=next((m for m in matches if m.group("label") and int(m.group("label"))==blank),None)
        correct=q.get("correct","")
        if target is None and correct:
            whole_matches=[m for m in matches if correct.lower().startswith(m.group("prefix").lower()) and len(correct)>len(m.group("prefix"))]
            if whole_matches: target=max(whole_matches,key=lambda m:len(m.group("prefix")))
        if target is None and 0 < blank <= len(matches):target=matches[blank-1]
        self.answer_var=tk.StringVar(value="")
        self.cloze_prefix="";self.cloze_store_whole=False
        cursor=0
        for match in matches:
            if match.end() <= cursor:
                continue
            text.insert("end",q["stimulus"][cursor:match.start("gap")])
            count=sum(match.group("gap").count(char) for char in "_-")
            if match is target:
                prefix=match.group("prefix")
                self.cloze_prefix=prefix
                self.cloze_store_whole=bool(correct.lower().startswith(prefix.lower()) and len(correct)>count)
                skip_end=match.end()
                if correct.lower().startswith(prefix.lower()) and len(correct)>len(prefix):
                    count=len(correct)-len(prefix)
                    self.cloze_store_whole=True
                    residue=re.match(r"(?:[ \t]*[A-Za-z]?[ \t]*[_-]+)*",q["stimulus"][skip_end:])
                    if residue:skip_end+=residue.end()
                stored=self.store.answer(self.current_attempt,q["id"])
                if self.cloze_store_whole and stored.lower().startswith(prefix.lower()):stored=stored[len(prefix):]
                self.answer_var.set(stored[:count])
                validate=(self.register(lambda value,n=count: value=="" or (len(value)<=n and value.isalpha())),"%P")
                entry=tk.Entry(text,textvariable=self.answer_var,width=max(2,count+1),font=(UI_FONT,14,"bold"),justify="center",validate="key",validatecommand=validate,relief="solid",bd=2)
                text.window_create("end",window=entry,padx=2)
                self.after(80,entry.focus_set)
                cursor=skip_end
            else:
                text.insert("end","_"*count)
                cursor=match.end()
        text.insert("end",q["stimulus"][cursor:])
        text.configure(state="disabled")

    def show_choices(self,parent,q):
        self.answer_var=tk.StringVar(value=self.store.answer(self.current_attempt,q["id"]))
        option_cards=[]
        def choose(key):
            self.answer_var.set(key)
            refresh()
        def refresh(*_args):
            selected=self.answer_var.get()
            for key,card,marker,label in option_cards:
                active=key==selected
                color="#e7f1fb" if active else "white"
                card.configure(bg=color,highlightbackground=BLUE if active else "#c9d3dc",highlightcolor=BLUE)
                marker.configure(text="●" if active else "○",bg=color,fg=BLUE if active else "#52677a")
                label.configure(bg=color,fg=INK)
        for key,value in q["choices"].items():
            card=tk.Frame(parent,bg="white",cursor="hand2",highlightthickness=2,highlightbackground="#c9d3dc",highlightcolor=BLUE,takefocus=True)
            card.pack(fill="x",anchor="w",pady=5)
            marker=tk.Label(card,text="○",font=(UI_FONT,22,"bold"),width=2,bg="white",fg="#52677a",cursor="hand2")
            marker.pack(side="left",padx=(12,4),pady=10)
            label=tk.Label(card,text=f"{key}.  {value}",font=(UI_FONT,15),bg="white",fg=INK,anchor="w",justify="left",wraplength=710,cursor="hand2")
            label.pack(side="left",fill="x",expand=True,padx=(0,14),pady=12)
            for widget in (card,marker,label):
                widget.bind("<Button-1>",lambda _event,k=key:choose(k))
            card.bind("<Return>",lambda _event,k=key:choose(k))
            card.bind("<space>",lambda _event,k=key:choose(k))
            option_cards.append((key,card,marker,label))
        refresh()
        if not q["choices"]:
            tk.Label(parent,text=self.tr("Enter the missing letters:"),bg="white",fg=INK).pack(anchor="w")
            tk.Entry(parent,textvariable=self.answer_var,font=(UI_FONT,16),width=24).pack(anchor="w",pady=8)

    def show_writing(self,parent,q):
        self.editor=tk.Text(parent,height=16,wrap="word",font=(UI_FONT,14),undo=True,bg="#fbfcfd",relief="solid",bd=1)
        self.editor.insert("1.0",self.store.answer(self.current_attempt,q["id"]))
        self.editor.pack(fill="both",expand=True)
        self.word_count=tk.Label(parent,bg="white",fg=MUTED);self.word_count.pack(anchor="e",pady=5)
        attempt_id=self.current_attempt;editor=self.editor;counter=self.word_count
        def autosave(_=None):
            if self.current_attempt!=attempt_id or not editor.winfo_exists():return
            text=editor.get("1.0","end-1c");self.store.save_writing(attempt_id,q["id"],text);counter.configure(text=f"{len(text.split())} {self.tr('words · saved')}")
            self.after(3000,autosave)
        autosave()

    def show_speaking(self,parent,q):
        tk.Label(parent,text=self.tr("Microphone check: speak normally and watch the input meter before recording."),bg="white",fg=MUTED).pack(anchor="w")
        self.meter=ttk.Progressbar(parent,maximum=100,length=430);self.meter.pack(anchor="w",pady=10)
        self.monitor_meter()
        self.record_button=self.button(parent,self.tr("Start Recording"),lambda:self.toggle_recording(q));self.record_button.pack(anchor="w",pady=8)
        if q["audio"]: self.button(parent,self.tr("Play Prompt"),lambda:self.play_question_audio(q,False),False).pack(anchor="w")
        tk.Label(parent,text=self.tr("Responses are saved as WAV in your local HALO TOEFL recordings folder."),bg="white",fg=MUTED).pack(anchor="w",pady=10)

    def monitor_meter(self):
        if not self.current_attempt or not hasattr(self,"meter"): return
        try:
            if sd:
                import numpy as np
                selected=self.store.setting("microphone","")
                device=int(selected.split(":",1)[0]) if selected.split(":",1)[0].isdigit() else None
                level=float(np.abs(sd.rec(512,samplerate=16000,channels=1,blocking=True,device=device)).mean())*900
                self.meter["value"]=min(100,level)
        except Exception: pass
        self.after(500,self.monitor_meter)

    def toggle_recording(self,q):
        if self.recording is not None: self.stop_recording(q); return
        if not sd: messagebox.showerror(self.tr("Microphone unavailable"),self.tr("The audio recording component is unavailable."));return
        try:
            selected=self.store.setting("microphone","")
            device=int(selected.split(":",1)[0]) if selected.split(":",1)[0].isdigit() else None
            self.record_started=time.time(); self.recording=sd.rec(480000,samplerate=16000,channels=1,dtype="int16",device=device)
            self.record_button.configure(text=self.tr("Stop Recording"))
            self.after((q["duration"] or 45)*1000,lambda:self.stop_recording(q) if self.recording is not None else None)
        except Exception as e: messagebox.showerror(self.tr("Microphone error"),str(e))

    def stop_recording(self,q):
        if self.recording is None:return
        try:
            sd.stop(); data=self.recording;duration=time.time()-self.record_started
            today=date.today().isoformat();attempt=self.current_attempt
            test_id=self.store.db.execute("SELECT test_id FROM attempts WHERE id=?", (attempt,)).fetchone()[0]
            target=user_root()/"recordings"/today/test_id/attempt
            target.mkdir(parents=True,exist_ok=True);path=target/f"{today}_{q['id']}.wav"
            with wave.open(str(path),"wb") as out: out.setnchannels(1);out.setsampwidth(2);out.setframerate(16000);out.writeframes(data.tobytes())
            self.store.save_recording(attempt,q["id"],path,duration)
            self.record_button.configure(text=self.tr("Recorded · Record Again"))
        except Exception as e: messagebox.showerror(self.tr("Recording error"),str(e))
        self.recording=None

    def play_question_audio(self,q,auto=False):
        if not q["audio"] or not pygame:return
        if auto and q["id"] in self.audio_played:return
        path=bundle_root()/q["audio"]
        try: pygame.mixer.music.load(str(path));pygame.mixer.music.play();self.audio_played.add(q["id"])
        except Exception as e:
            if not auto: messagebox.showerror(self.tr("Playback error"),str(e))

    def next(self):
        q=self.exam_questions[self.exam_index]
        self.save_current_answer()
        if self.exam_index==len(self.exam_questions)-1: self.finish_attempt();return
        if self.exam_questions[self.exam_index+1]["section"]!=q["section"]: self.instructions(self.exam_questions[self.exam_index+1]["section"])
        self.exam_index+=1;self.save_progress();self.show_exam()

    def back(self):
        self.save_current_answer();self.exam_index=max(0,self.exam_index-1);self.save_progress();self.show_exam()

    def exit_exam(self):
        if not self.current_attempt:return
        self.save_current_answer();self.save_progress()
        if pygame:
            try:pygame.mixer.music.stop()
            except Exception:pass
        self.current_attempt=None;self.exam_questions=[];self.show_library()

    def save_current_answer(self):
        if not self.current_attempt or not self.exam_questions:return
        q=self.exam_questions[self.exam_index]
        if q["section"]=="Writing" and hasattr(self,"editor"):
            self.store.save_writing(self.current_attempt,q["id"],self.editor.get("1.0","end-1c"))
        elif q["section"]!="Speaking" and hasattr(self,"answer_var"):
            answer=self.answer_var.get()
            if q["type"]=="Complete the Words" and self.cloze_store_whole:
                answer=self.cloze_prefix+answer
            self.store.save_answer(self.current_attempt,q["id"],answer)

    def instructions(self,section):
        if self.lang == "zh-TW":
            messagebox.showinfo(f"{self.section_name(section)}科",f"{self.section_name(section)}科即將開始，作答進度會自動儲存。")
        else:
            messagebox.showinfo(f"{section} section",f"The {section} section is about to begin. Your progress is saved automatically.")

    def finish_attempt(self):
        self.save_progress();self.store.finish(self.current_attempt);aid=self.current_attempt;self.current_attempt=None;self.show_results(aid)

    def show_results(self,attempt_id):
        result=attempt_stats(self.store,attempt_id);self.clear();self.header(self.tr("Mock Test Complete"))
        body=tk.Frame(self,bg=BG);body.pack(fill="both",expand=True,padx=90,pady=45)
        c=self.card(body);c.pack(fill="x")
        tk.Label(c,text=result["test"],font=(UI_FONT,19,"bold"),bg="white",fg=INK).pack(anchor="w",padx=25,pady=(24,12))
        for section,stat in result["stats"].items():
            if stat["questions"]:
                score=f"{stat['estimated_score']}/6 {self.tr('estimated')}" if stat["estimated_score"] is not None else (self.tr("Completed") if stat["answered"] else self.tr("Not completed"))
                tk.Label(c,text=f"{self.section_name(section):<12} {score}     {stat['answered']}/{stat['questions']} {self.tr('answered')}",font=(UI_FONT,12),bg="white",fg=INK).pack(anchor="w",padx=30,pady=6)
        tk.Label(c,text=f"{self.tr('Total time')}: {result['attempt']['elapsed_seconds']//60} {self.tr('minutes')}",bg="white",fg=MUTED).pack(anchor="w",padx=30,pady=(10,24))
        actions=tk.Frame(body,bg=BG);actions.pack(pady=20)
        self.button(actions,self.tr("Review"),lambda:self.show_review(attempt_id)).pack(side="left",padx=5)
        self.button(actions,self.tr("Export Daily Report"),lambda:self.export_today("PDF"),False).pack(side="left",padx=5)
        self.button(actions,self.tr("Back to Home"),self.show_home,False).pack(side="left",padx=5)

    def show_review(self,attempt_id):
        attempt=self.store.db.execute("SELECT * FROM attempts WHERE id=?",(attempt_id,)).fetchone()
        if not attempt or attempt["status"]!="COMPLETE":
            messagebox.showinfo(self.tr("Review locked"),self.tr("Complete the test before viewing answers and explanations."));return
        result=attempt_stats(self.store,attempt_id);self.clear();self.header(self.tr("Review"),result["test"])
        outer=tk.Frame(self,bg=BG);outer.pack(fill="both",expand=True)
        canvas=tk.Canvas(outer,bg=BG,highlightthickness=0);bar=ttk.Scrollbar(outer,orient="vertical",command=canvas.yview);inner=tk.Frame(canvas,bg=BG)
        inner.bind("<Configure>",lambda e:canvas.configure(scrollregion=canvas.bbox("all")));review_window=canvas.create_window((0,0),window=inner,anchor="nw");canvas.bind("<Configure>",lambda e:canvas.itemconfigure(review_window,width=e.width));canvas.configure(yscrollcommand=bar.set);canvas.pack(side="left",fill="both",expand=True);bar.pack(side="right",fill="y")
        tk.Label(inner,text=self.tr("Explanations are generated from the question, answer key, and source material."),font=(UI_FONT,10),bg=BG,fg=MUTED).pack(anchor="w",padx=45,pady=(16,4))
        for q in result["questions"]:
            c=self.card(inner);c.pack(fill="x",padx=45,pady=8)
            answer=result["answers"].get(q["id"],"—")
            correct=f"{q['correct']}. {q['choices'][q['correct']]}" if q["choices"] and q["correct"] in q["choices"] else (q["correct"] or self.tr("Manual review"))
            explanation=self.store.explanation(result["attempt"]["test_id"],q["id"],self.lang)
            tk.Label(c,text=f"{self.section_name(q['section'])} · {q['id']} · {self.tr(q['type'])}",bg="white",fg=BLUE,font=(UI_FONT,10,"bold")).pack(anchor="w",padx=15,pady=(10,3))
            tk.Label(c,text=q["prompt"],bg="white",fg=INK,wraplength=900,justify="left").pack(anchor="w",padx=15)
            tk.Label(c,text=f"{self.tr('My answer')}: {answer}\n{self.tr('Correct answer')}: {correct}",bg="white",fg=INK,justify="left",wraplength=1050).pack(anchor="w",padx=15,pady=(5,7))
            tk.Label(c,text=f"{self.tr('Explanation')}: {explanation}",bg="#f3f7fb",fg=INK,font=(UI_FONT,11),justify="left",anchor="w",wraplength=1050,padx=12,pady=10).pack(fill="x",padx=15,pady=(0,10))
            if q["section"]=="Listening" and q["audio"]: self.button(c,self.tr("Replay audio"),lambda x=q:self.play_question_audio(x,False),False).pack(anchor="w",padx=15,pady=(0,10))

    def show_reports(self):
        self.clear();self.header(self.tr("Daily Reports"),self.tr("Local date"))
        body=tk.Frame(self,bg=BG);body.pack(fill="both",expand=True,padx=70,pady=35);report=daily_data(self.store)
        c=self.card(body);c.pack(fill="x");tk.Label(c,text=datetime.fromisoformat(report["date"]).strftime("%B %d, %Y"),font=(UI_FONT,18,"bold"),bg="white",fg=INK).pack(anchor="w",padx=20,pady=(20,12))
        metrics=[("Total study time",f"{report['total_study_seconds']//60} {self.tr('minutes')}"),("Sessions",report["sessions"]),("Full mocks",report["full_mocks_completed"]),("Questions answered",report["questions_answered"]),("Accuracy",str(report["objective_accuracy"])+"%" if report["objective_accuracy"] is not None else "N/A"),("Speaking prompts",report["speaking_prompts_completed"]),("Writing words",report["writing_words"])]
        for label,value in metrics:tk.Label(c,text=f"{self.tr(label):<26} {value}",font=(UI_FONT,11),bg="white",fg=INK).pack(anchor="w",padx=28,pady=3)
        actions=tk.Frame(body,bg=BG);actions.pack(pady=25)
        for fmt in ("PDF","CSV","JSON","ZIP"):self.button(actions,self.tr("Export Daily Package" if fmt=="ZIP" else "Export "+fmt),lambda x=fmt:self.export_today(x),fmt in ("PDF","ZIP")).pack(side="left",padx=5)

    def export_today(self,fmt):
        day=date.today().isoformat();default=f"HALO-TOEFL-{'Daily-Report-' if fmt!='ZIP' else ''}{day}.{fmt.lower()}"
        path=filedialog.asksaveasfilename(defaultextension="."+fmt.lower(),initialfile=default,filetypes=[(fmt, "*."+fmt.lower())])
        if path:
            try:export_daily(self.store,day,fmt,path);messagebox.showinfo(self.tr("Export complete"),path)
            except Exception as e:messagebox.showerror(self.tr("Export error"),str(e))

    def show_recordings(self):
        self.clear();self.header(self.tr("Recordings"),self.tr("Saved speaking answers"))
        body=tk.Frame(self,bg=BG);body.pack(fill="both",expand=True,padx=45,pady=25)
        rows=self.store.db.execute("SELECT r.*,a.test_id FROM speaking_recordings r JOIN attempts a ON r.attempt_id=a.id ORDER BY r.created DESC").fetchall()
        if not rows:tk.Label(body,text=self.tr("No recordings yet."),bg=BG,fg=MUTED,font=(UI_FONT,13)).pack(anchor="w");return
        actions=tk.Frame(body,bg=BG);actions.pack(fill="x",pady=(0,10))
        self.button(actions,self.tr("Export Today's Speaking Recordings"),lambda:self.export_recordings_zip(today_only=True)).pack(side="left")
        for r in rows:
            c=self.card(body);c.pack(fill="x",pady=5);tk.Label(c,text=f"{r['created'][:10]} · {r['test_id']} · {r['question_id']} · {r['duration']:.1f}s",bg="white",fg=INK).pack(side="left",padx=15,pady=12)
            self.button(c,self.tr("Open Folder"),lambda x=Path(r['path']):open_folder(x.parent),False).pack(side="right",padx=5,pady=6)
            self.button(c,self.tr("Export Attempt Recordings"),lambda x=r['attempt_id']:self.export_recordings_zip(attempt_id=x),False).pack(side="right",padx=5,pady=6)
            self.button(c,self.tr("Export MP3"),lambda x=Path(r['path']):self.export_recording_mp3(x),False).pack(side="right",padx=5,pady=6)
            self.button(c,self.tr("Export WAV"),lambda x=Path(r['path']):self.copy_recording(x),False).pack(side="right",padx=5,pady=6)
            self.button(c,self.tr("Play"),lambda x=Path(r['path']):self.play_file(x),False).pack(side="right",padx=5,pady=6)

    def play_file(self,path):
        try: pygame.mixer.music.load(str(path));pygame.mixer.music.play()
        except Exception as e:messagebox.showerror(self.tr("Playback error"),str(e))

    def copy_recording(self,path):
        destination=filedialog.asksaveasfilename(defaultextension=".wav",initialfile=path.name,filetypes=[("WAV","*.wav")])
        if destination:shutil.copy2(path,destination);messagebox.showinfo(self.tr("Export complete"),destination)

    def export_recording_mp3(self,path):
        destination=filedialog.asksaveasfilename(defaultextension=".mp3",initialfile=path.with_suffix(".mp3").name,filetypes=[("MP3","*.mp3")])
        if not destination:return
        try:
            if not imageio_ffmpeg: raise RuntimeError("FFmpeg component unavailable")
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),"-y","-loglevel","error","-i",str(path),
                            "-codec:a","libmp3lame","-q:a","3",destination],check=True,timeout=90)
            messagebox.showinfo(self.tr("Export complete"),destination)
        except Exception as e:messagebox.showerror(self.tr("Export error"),self.tr(str(e)))

    def export_recordings_zip(self,attempt_id=None,today_only=False):
        if attempt_id:
            rows=self.store.db.execute("SELECT * FROM speaking_recordings WHERE attempt_id=? ORDER BY question_id",(attempt_id,)).fetchall()
            default=f"HALO-TOEFL-{attempt_id[:8]}-Speaking.zip"
        else:
            today=date.today().isoformat()
            rows=self.store.db.execute("SELECT * FROM speaking_recordings WHERE substr(created,1,10)=? ORDER BY created",(today,)).fetchall()
            default=f"HALO-TOEFL-{today}-Speaking.zip"
        destination=filedialog.asksaveasfilename(defaultextension=".zip",initialfile=default,filetypes=[("ZIP","*.zip")])
        if not destination:return
        try:
            with zipfile.ZipFile(destination,"w",zipfile.ZIP_DEFLATED) as archive:
                for row in rows:
                    path=Path(row["path"])
                    if path.exists(): archive.write(path,path.name)
            messagebox.showinfo(self.tr("Export complete"),destination)
        except Exception as e:messagebox.showerror(self.tr("Export error"),str(e))

    def show_settings(self):
        self.clear();self.header(self.tr("Settings"))
        shell=tk.Frame(self,bg=BG);shell.pack(fill="both",expand=True,padx=65,pady=25)
        canvas=tk.Canvas(shell,bg=BG,highlightthickness=0);scroll=ttk.Scrollbar(shell,orient="vertical",command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set);scroll.pack(side="right",fill="y");canvas.pack(side="left",fill="both",expand=True)
        body=tk.Frame(canvas,bg=BG);window=canvas.create_window((0,0),window=body,anchor="nw")
        body.bind("<Configure>",lambda _e:canvas.configure(scrollregion=canvas.bbox("all")));canvas.bind("<Configure>",lambda e:canvas.itemconfigure(window,width=e.width))
        self.bind_all("<MouseWheel>",lambda e:canvas.yview_scroll(-1 if e.delta>0 else 1,"units"))
        c=self.card(body);c.pack(fill="x",pady=(0,12))
        tk.Label(c,text=self.tr("Language"),font=(UI_FONT,14,"bold"),bg="white",fg=INK).pack(anchor="w",padx=20,pady=(18,8))
        display_language=tk.StringVar(value=self.tr("Taiwan Traditional Chinese") if self.lang=="zh-TW" else "English")
        language_combo=ttk.Combobox(c,textvariable=display_language,values=["台灣正體","English"],state="readonly",width=28);language_combo.pack(anchor="w",padx=20,pady=8)
        def save_language():
            self.lang="zh-TW" if display_language.get()=="台灣正體" else "en"
            self.store.set_setting("language",self.lang)
            messagebox.showinfo(self.tr("Saved"),self.tr("Language saved."));self.show_settings()
        self.button(c,self.tr("Save language"),save_language).pack(anchor="w",padx=20,pady=(4,18))

        portable=self.card(body);portable.pack(fill="x",pady=12)
        tk.Label(portable,text=self.tr("Portable save"),font=(UI_FONT,14,"bold"),bg="white",fg=INK).pack(anchor="w",padx=20,pady=(18,6))
        tk.Label(portable,text=self.tr("Portable save description"),font=(UI_FONT,10),bg="white",fg=MUTED,wraplength=900,justify="left").pack(anchor="w",padx=20,pady=(0,12))
        portable_actions=tk.Frame(portable,bg="white");portable_actions.pack(anchor="w",padx=20,pady=(0,18))
        self.button(portable_actions,self.tr("Export portable save"),self.export_portable_save).pack(side="left",padx=(0,8))
        self.button(portable_actions,self.tr("Import portable save"),self.import_portable_save,False).pack(side="left")

        audio=self.card(body);audio.pack(fill="x",pady=12)
        tk.Label(audio,text=self.tr("Audio input"),font=(UI_FONT,14,"bold"),bg="white",fg=INK).pack(anchor="w",padx=20,pady=(18,8))
        devices=[]
        try:devices=[f"{i}: {d['name']}" for i,d in enumerate(sd.query_devices()) if d['max_input_channels']>0]
        except Exception:devices=[self.tr("No microphone device detected")]
        value=tk.StringVar(value=self.store.setting("microphone",devices[0] if devices else ""));combo=ttk.Combobox(audio,textvariable=value,values=devices,state="readonly",width=70);combo.pack(anchor="w",padx=20,pady=8)
        self.button(audio,self.tr("Save microphone selection"),lambda:(self.store.set_setting("microphone",value.get()),messagebox.showinfo(self.tr("Saved"),self.tr("Microphone selection saved.")))).pack(anchor="w",padx=20,pady=(4,18))
        tk.Label(audio,text=f"{self.tr('Data folder')}: {user_root()}",bg="white",fg=MUTED,justify="left").pack(anchor="w",padx=20,pady=(0,18))

        danger=self.card(body);danger.pack(fill="x",pady=12)
        tk.Label(danger,text=self.tr("Clear local records"),font=(UI_FONT,14,"bold"),bg="white",fg="#a32626").pack(anchor="w",padx=20,pady=(18,6))
        tk.Label(danger,text=self.tr("Clear records warning"),font=(UI_FONT,10,"bold"),bg="white",fg="#a32626",wraplength=900,justify="left").pack(anchor="w",padx=20,pady=(0,12))
        tk.Button(danger,text=self.tr("Clear local records"),command=self.clear_local_data,font=(UI_FONT,10,"bold"),bg="#a32626",fg="white",activebackground="#7d1f1f",activeforeground="white",relief="flat",padx=16,pady=9).pack(anchor="w",padx=20,pady=(0,20))

    def export_portable_save(self):
        destination=filedialog.asksaveasfilename(defaultextension=".halo-save",initialfile=f"HALO-TOEFL-Save-{date.today().isoformat()}.halo-save",filetypes=[("HALO TOEFL portable save","*.halo-save")])
        if not destination:return
        try:
            result=export_save(self.store,destination)
            messagebox.showinfo(self.tr("Save exported"),f"{destination}\n\n{result['attempt_count']} {self.tr('attempts exported')}")
        except Exception as e:messagebox.showerror(self.tr("Export error"),self.tr(str(e)))

    def import_portable_save(self):
        source=filedialog.askopenfilename(filetypes=[("HALO TOEFL portable save","*.halo-save"),("All files","*.*")])
        if not source:return
        try:
            result=import_save(self.store,source)
            messagebox.showinfo(self.tr("Save imported"),f"{result['imported']} {self.tr('attempts imported')}\n{result['skipped']} {self.tr('existing attempts skipped')}")
            self.show_settings()
        except Exception as e:messagebox.showerror(self.tr("Import error"),self.tr(str(e)))

    def clear_local_data(self):
        typed=simpledialog.askstring(self.tr("Clear local records"),self.tr("Clear records warning")+"\n\n"+self.tr("Type ACCESS to continue"),parent=self)
        if typed is None:return
        if typed!="ACCESS":
            messagebox.showwarning(self.tr("Clear local records"),self.tr("ACCESS did not match. Nothing was deleted."));return
        if not messagebox.askyesno(self.tr("Clear local records"),self.tr("Final irreversible confirmation"),icon="warning",parent=self):return
        clear_local_records(self.store);self.current_attempt=None;self.exam_questions=[]
        messagebox.showinfo(self.tr("Clear local records"),self.tr("Local records cleared"));self.show_settings()


def main():
    HaloApp().mainloop()

if __name__ == "__main__": main()
