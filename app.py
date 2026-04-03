"""
VaultSystemFx — Trading Bot
Interfaccia HTML/CSS premium con pywebview.
"""

import os
import sys
import json
import time
import threading
import logging
import base64
from pathlib import Path
from datetime import datetime

# Fix DPI Windows
try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    BASE_DIR  = Path(sys.executable).parent
    _INTERNAL = Path(sys._MEIPASS)
else:
    BASE_DIR  = Path(__file__).parent
    _INTERNAL = BASE_DIR

CONFIG_FILE = BASE_DIR / "user_config.json"
LOG_FILE    = BASE_DIR / "lw_bot.log"
LOGO_FILE   = _INTERNAL / "logo.png"
ICON_FILE   = _INTERNAL / "icon.ico"

# ─────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8")]
)
log = logging.getLogger("VaultSystemFx")

# ─────────────────────────────────────────────────────────────────
# DEFAULT CONFIG
# ─────────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "mt5_path": "",
    "mt5_login": "",
    "mt5_password": "",
    "mt5_server": "",
    "symbols": [
        {"symbol": "EURUSD-P", "lot": 0.07, "enabled": False},
        {"symbol": "USDCAD-P", "lot": 0.07, "enabled": False},
        {"symbol": "GBPUSD-P", "lot": 0.07, "enabled": False},
        {"symbol": "XAUUSD-P", "lot": 0.02, "enabled": False},
        {"symbol": "GBPJPY-P", "lot": 0.07, "enabled": False},
        {"symbol": "EURGBP-P", "lot": 0.07, "enabled": False},
        {"symbol": "USDJPY-P", "lot": 0.07, "enabled": False},
        {"symbol": "EURJPY-P", "lot": 0.07, "enabled": False},
        {"symbol": "EURNZD-P", "lot": 0.07, "enabled": True},
        {"symbol": "EURCHF-P", "lot": 0.07, "enabled": True},
        {"symbol": "USDCHF-P", "lot": 0.07, "enabled": True},
    ],
    "donchian_period": 96,
    "lwti_period": 25,
    "lwti_threshold": 20.0,
    "volume_ma_period": 30,
    "atr_period": 14,
    "consolidation_mult": 0.5,
    "min_body_ratio": 0.65,
    "use_engulfing": True,
    "cooldown_bars": 0,
    "rr_ratio": 2.0,
    "sl_buffer_points": 5,
    "max_spread_pts": 30,
    "deviation": 20,
    "magic_number": 202501,
    "use_session_filter": True,
    "session_start_hour": 7,
    "session_end_hour": 19.5,  # 19:30 (usa decimali: .5 = 30 min)
}

_STRATEGY_KEYS = {
    "donchian_period", "lwti_period", "lwti_threshold", "volume_ma_period",
    "atr_period", "consolidation_mult", "min_body_ratio", "use_engulfing",
    "cooldown_bars", "rr_ratio", "sl_buffer_points", "max_spread_pts",
    "deviation", "magic_number", "use_session_filter",
}

# ─────────────────────────────────────────────────────────────────
# LICENSE CHECK - Sistema chiavi univoche legate all'hardware
# ─────────────────────────────────────────────────────────────────
GIST_URL = "https://gist.githubusercontent.com/matteosani05-blip/787332a9bd6531ce63414606ae059f96/raw/licenses.json"
LICENSE_FILE = BASE_DIR / "license.key"

def _get_hardware_id():
    """Genera un ID hardware univoco basato su CPU, disco e MAC address."""
    import hashlib
    import subprocess
    import uuid

    components = []

    # CPU ID
    try:
        result = subprocess.run(
            ['wmic', 'cpu', 'get', 'ProcessorId'],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        cpu_id = result.stdout.strip().split('\n')[-1].strip()
        if cpu_id and cpu_id != "ProcessorId":
            components.append(cpu_id)
    except:
        pass

    # Disk Serial
    try:
        result = subprocess.run(
            ['wmic', 'diskdrive', 'get', 'SerialNumber'],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip() and l.strip() != "SerialNumber"]
        if lines:
            components.append(lines[0])
    except:
        pass

    # MAC Address
    try:
        mac = ':'.join(['{:02x}'.format((uuid.getnode() >> i) & 0xff) for i in range(0, 48, 8)][::-1])
        components.append(mac)
    except:
        pass

    # Motherboard Serial
    try:
        result = subprocess.run(
            ['wmic', 'baseboard', 'get', 'SerialNumber'],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        mb_serial = result.stdout.strip().split('\n')[-1].strip()
        if mb_serial and mb_serial != "SerialNumber" and mb_serial != "To be filled by O.E.M.":
            components.append(mb_serial)
    except:
        pass

    if not components:
        components.append(str(uuid.getnode()))

    combined = "|".join(components)
    return hashlib.sha256(combined.encode()).hexdigest()[:32].upper()

def _load_local_license():
    """Carica la licenza salvata localmente."""
    if LICENSE_FILE.exists():
        try:
            with open(LICENSE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("key", ""), data.get("hardware_id", "")
        except:
            pass
    return "", ""

def _save_local_license(key, hardware_id):
    """Salva la licenza attivata localmente."""
    try:
        with open(LICENSE_FILE, "w", encoding="utf-8") as f:
            json.dump({"key": key, "hardware_id": hardware_id}, f)
        return True
    except:
        return False

def _notify_activation(key, hardware_id, client_name):
    """Notifica l'attivazione via Telegram."""
    import requests
    try:
        # Telegram bot per notifiche admin
        ADMIN_TG_TOKEN = "7555446841:AAFJ4ehYejHlK2D3AujAhZS0zfyHyBcl_jI"
        ADMIN_CHAT_ID = "5aborcode-licenze"  # Sostituisci con il tuo chat ID

        message = f"""🔑 *NUOVA ATTIVAZIONE LICENZA*

📋 *Chiave:* `{key}`
👤 *Cliente:* {client_name or 'Non specificato'}
🖥️ *Hardware ID:* `{hardware_id}`
📅 *Data:* {datetime.now().strftime('%Y-%m-%d %H:%M')}

⚠️ Aggiorna il Gist con questo hardware_id!"""

        requests.post(
            f"https://api.telegram.org/bot{ADMIN_TG_TOKEN}/sendMessage",
            json={"chat_id": ADMIN_CHAT_ID, "text": message, "parse_mode": "Markdown"},
            timeout=5
        )
    except:
        pass  # Non bloccare se la notifica fallisce

def _activate_license(key):
    """Attiva una licenza con il server remoto."""
    import requests

    key = key.strip().upper()
    hardware_id = _get_hardware_id()

    try:
        r = requests.get(GIST_URL, timeout=10)
        if r.status_code != 200:
            return False, "Errore connessione al server licenze."

        data = r.json()
        licenses = data.get("licenses", {})

        if key not in licenses:
            return False, "Chiave licenza non valida."

        license_info = licenses[key]

        # Controlla se la licenza è già attivata su un altro PC
        activated_hwid = license_info.get("hardware_id", "")

        if activated_hwid and activated_hwid != hardware_id:
            return False, "Questa licenza è già attivata su un altro PC.\nContatta il supporto per trasferirla."

        # Licenza valida - salva localmente
        _save_local_license(key, hardware_id)

        client_name = license_info.get("name", "")

        # Notifica attivazione (solo se è una nuova attivazione)
        if not activated_hwid:
            _notify_activation(key, hardware_id, client_name)

        return True, f"Licenza attivata con successo!" + (f"\nBenvenuto, {client_name}!" if client_name else "")

    except Exception as e:
        return False, f"Errore attivazione: {e}"

def _check_license():
    """Verifica la licenza all'avvio."""
    import requests

    saved_key, saved_hwid = _load_local_license()
    current_hwid = _get_hardware_id()

    # Se non c'è licenza salvata, richiedi attivazione
    if not saved_key:
        return False, "NEED_ACTIVATION"

    # Verifica che l'hardware ID corrisponda
    if saved_hwid != current_hwid:
        return False, "L'hardware del PC è cambiato.\nRiattiva la licenza."

    # Verifica online
    try:
        r = requests.get(GIST_URL, timeout=10)
        if r.status_code != 200:
            # Offline mode: accetta se la licenza locale è presente
            return True, "Licenza valida (offline)"

        data = r.json()
        licenses = data.get("licenses", {})

        if saved_key not in licenses:
            return False, "Licenza revocata o non valida."

        license_info = licenses[saved_key]
        activated_hwid = license_info.get("hardware_id", "")

        # Verifica binding hardware
        if activated_hwid and activated_hwid != current_hwid:
            return False, "Licenza trasferita ad un altro PC.\nContatta il supporto."

        client_name = license_info.get("name", "")
        return True, f"Licenza valida" + (f" — {client_name}" if client_name else "")

    except Exception:
        # Errore rete: accetta licenza locale
        return True, "Licenza valida (offline)"

def _show_activation_dialog():
    """Mostra dialog per inserire la chiave licenza."""
    import tkinter as tk
    from tkinter import ttk, messagebox

    result = {"key": None, "success": False}

    def on_activate():
        key = entry.get().strip().upper()
        if not key:
            messagebox.showerror("Errore", "Inserisci una chiave licenza valida.")
            return

        btn_activate.config(state="disabled", text="Attivazione...")
        root.update()

        success, msg = _activate_license(key)

        if success:
            result["key"] = key
            result["success"] = True
            messagebox.showinfo("Successo", msg)
            root.destroy()
        else:
            btn_activate.config(state="normal", text="Attiva Licenza")
            messagebox.showerror("Errore", msg)

    def on_close():
        root.destroy()

    root = tk.Tk()
    root.title("VaultSystemFx - Attivazione")
    root.geometry("450x280")
    root.resizable(False, False)
    root.configure(bg="#0a0d14")

    # Centra la finestra
    root.update_idletasks()
    x = (root.winfo_screenwidth() - 450) // 2
    y = (root.winfo_screenheight() - 280) // 2
    root.geometry(f"+{x}+{y}")

    # Stile
    style = ttk.Style()
    style.theme_use('clam')
    style.configure("TLabel", background="#0a0d14", foreground="#ffffff", font=("Segoe UI", 10))
    style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"), foreground="#818cf8")
    style.configure("TEntry", fieldbackground="#1a1f2e", foreground="#ffffff", font=("Consolas", 12))
    style.configure("TButton", font=("Segoe UI", 11, "bold"), padding=10)

    # Titolo
    title = ttk.Label(root, text="VaultSystemFx", style="Title.TLabel")
    title.pack(pady=(30, 5))

    subtitle = ttk.Label(root, text="Inserisci la tua chiave licenza per attivare il bot")
    subtitle.pack(pady=(0, 25))

    # Entry
    entry_frame = tk.Frame(root, bg="#0a0d14")
    entry_frame.pack(fill="x", padx=50)

    entry = tk.Entry(entry_frame, font=("Consolas", 14), bg="#1a1f2e", fg="#ffffff",
                    insertbackground="#818cf8", relief="flat", justify="center")
    entry.pack(fill="x", ipady=12)
    entry.focus()

    # Hardware ID info
    hwid = _get_hardware_id()
    hwid_label = ttk.Label(root, text=f"Hardware ID: {hwid[:16]}...", font=("Consolas", 8), foreground="#64748b")
    hwid_label.pack(pady=(10, 0))

    # Bottone
    btn_activate = tk.Button(root, text="Attiva Licenza", font=("Segoe UI", 11, "bold"),
                            bg="#6366f1", fg="#ffffff", relief="flat", cursor="hand2",
                            activebackground="#4f46e5", activeforeground="#ffffff",
                            command=on_activate)
    btn_activate.pack(pady=25, ipadx=30, ipady=8)

    # Enter key
    entry.bind("<Return>", lambda e: on_activate())

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()

    return result["success"]

# ─────────────────────────────────────────────────────────────────
# AUTO-UPDATE
# ─────────────────────────────────────────────────────────────────
CURRENT_VERSION = "1.1.0"

def _check_update():
    import requests
    try:
        r = requests.get(GIST_URL, timeout=8)
        if r.status_code != 200:
            return None
        data = r.json()
        latest  = data.get("latest_version", "")
        url     = data.get("download_url", "")
        note    = data.get("update_note", "")
        if not latest or not url:
            return None
        def ver(s):
            try: return [int(x) for x in s.split(".")]
            except: return [0]
        if ver(latest) > ver(CURRENT_VERSION):
            return {"version": latest, "url": url, "note": note}
        return None
    except Exception:
        return None

# ─────────────────────────────────────────────────────────────────
# SISTEMA LICENZE CON CHIAVI (commentato - attivare quando serve)
# ─────────────────────────────────────────────────────────────────
# def _check_update_with_license():
#     """
#     Check update che verifica anche la validità della licenza.
#     Solo chi ha una chiave valida può ricevere aggiornamenti.
#
#     Struttura Gist attesa:
#     {
#         "latest_version": "1.0.3",
#         "download_url": "https://...",
#         "licenses": {
#             "ABC123-DEF456": {"name": "Cliente1", "hardware_id": "", "active": true},
#             "XYZ789-GHI012": {"name": "Cliente2", "hardware_id": "", "active": true}
#         }
#     }
#     """
#     import requests
#     try:
#         # Carica chiave locale
#         saved_key, saved_hwid = _load_local_license()
#         if not saved_key:
#             return None  # Nessuna licenza = nessun update
#
#         r = requests.get(GIST_URL, timeout=8)
#         if r.status_code != 200:
#             return None
#         data = r.json()
#
#         # Verifica licenza valida
#         licenses = data.get("licenses", {})
#         if saved_key not in licenses:
#             return None  # Chiave non trovata = nessun update
#
#         license_info = licenses[saved_key]
#         if not license_info.get("active", False):
#             return None  # Licenza disattivata = nessun update
#
#         # Licenza valida - controlla versione
#         latest = data.get("latest_version", "")
#         url = data.get("download_url", "")
#         note = data.get("update_note", "")
#
#         if not latest or not url:
#             return None
#
#         def ver(s):
#             try: return [int(x) for x in s.split(".")]
#             except: return [0]
#
#         if ver(latest) > ver(CURRENT_VERSION):
#             return {"version": latest, "url": url, "note": note}
#         return None
#     except Exception:
#         return None
#
# # Per attivare: sostituire _check_update() con _check_update_with_license()
# # nella classe Api metodo check_update() (circa riga 1335)

def _download_and_install(url):
    import requests, subprocess
    try:
        log.info(f"[UPDATE] Inizio download da: {url}")
        exe_path = Path(sys.executable) if getattr(sys, 'frozen', False) else None
        if not exe_path:
            log.error("[UPDATE] Non è un exe compilato")
            return "error:Solo per .exe compilato"

        log.info(f"[UPDATE] exe_path: {exe_path}")
        tmp_path = exe_path.parent / "VaultSystemFx_new.exe"
        log.info(f"[UPDATE] tmp_path: {tmp_path}")

        # Download
        log.info("[UPDATE] Avvio requests.get...")
        r = requests.get(url, stream=True, timeout=300, allow_redirects=True)
        log.info(f"[UPDATE] Status code: {r.status_code}")
        if r.status_code != 200:
            log.error(f"[UPDATE] Download fallito HTTP {r.status_code}")
            return f"error:Download fallito HTTP {r.status_code}"
        log.info("[UPDATE] Scrittura file...")
        with open(tmp_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        log.info(f"[UPDATE] File scaricato: {tmp_path.exists()}, size: {tmp_path.stat().st_size if tmp_path.exists() else 0}")

        # BAT che aspetta, sostituisce e riavvia
        bat_path = exe_path.parent / "_update.bat"
        vbs_path = exe_path.parent / "_update.vbs"

        bat_content = f"""@echo off
timeout /t 2 /nobreak >nul
taskkill /f /im "{exe_path.name}" >nul 2>&1
timeout /t 3 /nobreak >nul
del "{exe_path}" >nul 2>&1
timeout /t 1 /nobreak >nul
move /y "{tmp_path}" "{exe_path}"
timeout /t 2 /nobreak >nul
start "" "{exe_path}"
del "{vbs_path}"
del "%~f0"
"""
        with open(bat_path, "w") as f:
            f.write(bat_content)

        # VBS per lanciare il bat in modo completamente nascosto
        vbs_content = f'CreateObject("Wscript.Shell").Run """{bat_path}""", 0, False'
        with open(vbs_path, "w") as f:
            f.write(vbs_content)

        # Lancia il vbs (nascosto) che lancia il bat
        subprocess.Popen(
            ["wscript", str(vbs_path)],
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
        )
        
        # Chiudi il bot dopo 1 secondo
        import threading
        def _exit():
            import time
            time.sleep(1)
            import webview
            for w in webview.windows:
                w.destroy()
            sys.exit(0)
        threading.Thread(target=_exit, daemon=True).start()
        
        log.info("[UPDATE] Completato con successo")
        return "ok"
    except Exception as e:
        log.error(f"[UPDATE] Errore: {type(e).__name__}: {e}")
        import traceback
        log.error(traceback.format_exc())
        return f"error:{e}"
    
def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            merged = {**DEFAULT_CONFIG, **saved}
            for key in _STRATEGY_KEYS:
                merged[key] = DEFAULT_CONFIG[key]
            return merged
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

DEFAULT_TG_TOKEN = "7555446841:AAFJ4ehYejHlK2D3AujAhZS0zfyHyBcl_jI"

def _send_telegram(chat_id, token, message):
    import requests
    try:
        tok = token.strip() if token.strip() else DEFAULT_TG_TOKEN
        if not tok or not chat_id:
            return "error:token o chat_id mancante"
        url = f"https://api.telegram.org/bot{tok}/sendMessage"
        r = requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }, timeout=8)
        if r.status_code == 200:
            return "ok"
        return f"error:HTTP {r.status_code} — {r.text}"
    except Exception as e:
        return f"error:{e}"

# ─────────────────────────────────────────────────────────────────
# BOT ENGINE
# ─────────────────────────────────────────────────────────────────
class BotEngine:
    def __init__(self, cfg, log_callback=None, status_callback=None):
        self.cfg = cfg
        self.running = False
        self.thread = None
        self.log_cb = log_callback
        self.status_cb = status_callback
        self.total_trades = 0
        self.last_signal_bar = {}
        self._rma_atr = {}
        # Daily loss limit tracking
        self._daily_start_balance = None
        self._daily_date = None
        self._daily_loss_triggered = False

    def _tg(self, msg):
        chat_id = self.cfg.get("tg_chat_id", "").strip()
        token   = self.cfg.get("tg_token", "").strip()
        if chat_id:
            threading.Thread(
                target=_send_telegram,
                args=(chat_id, token, msg),
                daemon=True
            ).start()

    def _log(self, msg, level="INFO"):
        log.info(msg)
        if self.log_cb:
            self.log_cb(f"[{level}] {msg}")

    def _status(self, text):
        if self.status_cb:
            self.status_cb(text)

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self._status("Fermato")
        self._log("Bot fermato dall'utente")
        if self.cfg.get("tg_notify_start", True):
            self._tg("⛔ <b>VaultSystemFx fermato</b>")

    # ── Coerenza valutaria (proporzionalità inversa) ──

    def _extract_currencies(self, symbol):
        """Estrae base e quote: 'EURUSD-P' -> ('EUR', 'USD')."""
        clean = symbol.split("-")[0].split(".")[0]
        if len(clean) >= 6:
            return clean[:3].upper(), clean[3:6].upper()
        return None

    # Simboli soggetti al filtro correlazione (solo questi si bloccano a vicenda)
    CORRELATED_SYMBOLS = {"EURUSD", "USDCAD"}

    def _is_correlated_symbol(self, symbol):
        """Controlla se il simbolo è nella lista dei correlati."""
        clean = symbol.split("-")[0].split(".")[0].upper()
        return clean in self.CORRELATED_SYMBOLS

    def _check_daily_loss_limit(self, mt5):
        """
        Controlla se la perdita giornaliera ha raggiunto il 3% del capitale.
        Ritorna True se il trading deve essere bloccato.
        """
        if not self.cfg.get("daily_loss_enabled", False):
            return False

        today = datetime.now().date()

        # Reset a nuovo giorno
        if self._daily_date != today:
            self._daily_date = today
            self._daily_loss_triggered = False
            account_info = mt5.account_info()
            if account_info:
                self._daily_start_balance = account_info.balance
                self._log(f"📊 Nuovo giorno — Balance iniziale: ${self._daily_start_balance:.2f}")
            else:
                self._daily_start_balance = None
                return False

        # Se già triggerato oggi, blocca
        if self._daily_loss_triggered:
            return True

        # Controlla perdita attuale
        if self._daily_start_balance is None:
            return False

        account_info = mt5.account_info()
        if not account_info:
            return False

        current_balance = account_info.balance
        loss = self._daily_start_balance - current_balance

        limit_amount = self.cfg.get("daily_loss_amount", 300)
        if loss >= limit_amount:
            self._daily_loss_triggered = True
            self._log(f"🛑 STOP GIORNALIERO: Perdita -€{loss:.2f} (limite €{limit_amount} raggiunto)", "WARN")
            self._status(f"⛔ Stop giornaliero -€{limit_amount} attivo")
            if self.cfg.get("tg_notify_error", True):
                self._tg(
                    f"🛑 <b>Stop Giornaliero Attivato</b>\n"
                    f"Perdita: <b>-€{loss:.2f}</b>\n"
                    f"Limite: €{limit_amount}\n"
                    f"Nessun nuovo trade fino a domani."
                )
            return True

        return False

    def _check_currency_correlation(self, mt5, pending_signals):
        """
        Filtra segnali in base a posizioni aperte e correlazione valutaria.
        Attivo SOLO per EURUSD e USDCAD (gli altri simboli sono indipendenti).
        Posizione in PROFITTO:
          - Valuta DEBOLE (venduta) → blocca se DAVANTI (base): WEAK___
          - Valuta FORTE (comprata) → blocca se DOPO (quote): ___STRONG
        Posizione in PERDITA < 1 giorno → blocca correlati.
        Posizione in PERDITA > 1 giorno → lascia passare.
        """
        magic = self.cfg.get("magic_number", 202501)
        one_day = 86400  # secondi in un giorno

        blocked_bases = set()
        blocked_quotes = set()

        open_positions = mt5.positions_get()
        if open_positions:
            for pos in open_positions:
                if pos.magic != magic:
                    continue
                # Solo posizioni su simboli correlati generano blocchi
                if not self._is_correlated_symbol(pos.symbol):
                    continue
                currencies = self._extract_currencies(pos.symbol)
                if not currencies:
                    continue
                base, quote = currencies
                is_long = pos.type == 0

                if pos.profit > 0:
                    if is_long:
                        blocked_bases.add(quote)
                        blocked_quotes.add(base)
                    else:
                        blocked_bases.add(base)
                        blocked_quotes.add(quote)
                elif pos.profit < 0:
                    open_duration = time.time() - pos.time
                    if open_duration < one_day:
                        if is_long:
                            blocked_bases.add(quote)
                            blocked_quotes.add(base)
                        else:
                            blocked_bases.add(base)
                            blocked_quotes.add(quote)

        # Filtra segnali — solo simboli correlati possono essere bloccati
        valid = []
        for sig in pending_signals:
            # Simboli non correlati passano sempre
            if not self._is_correlated_symbol(sig["symbol"]):
                valid.append(sig)
                continue

            currencies = self._extract_currencies(sig["symbol"])
            if not currencies:
                valid.append(sig)
                continue

            base, quote = currencies
            d_str = "BUY" if sig["direction"] == "buy" else "SELL"

            if base in blocked_bases:
                self._log(
                    f"⚠️ {sig['symbol']} {d_str} bloccato: "
                    f"{base} davanti e debole (correlazione profitto)",
                    "WARN",
                )
                continue

            if quote in blocked_quotes:
                self._log(
                    f"⚠️ {sig['symbol']} {d_str} bloccato: "
                    f"{quote} dopo e forte (correlazione profitto)",
                    "WARN",
                )
                continue

            valid.append(sig)

        return valid

    def _check_eurusd_eurgbp_correlation(self, mt5, pending_signals):
        """
        Filtro correlazione EURUSD-EURGBP:
        - Se EURUSD è LONG → blocca SELL su EURGBP
        - Se EURUSD è SHORT → blocca BUY su EURGBP
        """
        magic = self.cfg.get("magic_number", 202501)
        eurusd_direction = None  # None, "long", "short"

        # Cerca posizione aperta su EURUSD
        open_positions = mt5.positions_get()
        if open_positions:
            for pos in open_positions:
                if pos.magic != magic:
                    continue
                clean_sym = pos.symbol.split("-")[0].split(".")[0].upper()
                if clean_sym == "EURUSD":
                    eurusd_direction = "long" if pos.type == 0 else "short"
                    break

        # Se non c'è posizione EURUSD, nessun filtro
        if eurusd_direction is None:
            return pending_signals

        # Filtra segnali EURGBP
        valid = []
        for sig in pending_signals:
            clean_sym = sig["symbol"].split("-")[0].split(".")[0].upper()

            if clean_sym == "EURGBP":
                # EURUSD LONG → blocca SELL su EURGBP
                if eurusd_direction == "long" and sig["direction"] == "sell":
                    self._log(
                        f"⚠️ EURGBP SELL bloccato: EURUSD è LONG (correlazione EUR)",
                        "WARN",
                    )
                    continue
                # EURUSD SHORT → blocca BUY su EURGBP
                if eurusd_direction == "short" and sig["direction"] == "buy":
                    self._log(
                        f"⚠️ EURGBP BUY bloccato: EURUSD è SHORT (correlazione EUR)",
                        "WARN",
                    )
                    continue

            valid.append(sig)

        return valid

    def _run(self):
        import MetaTrader5 as mt5
        import numpy as np

        self._log("Avvio bot...")
        self._status("Connessione a MT5...")

        init_args = {}
        if self.cfg.get("mt5_path"):
            init_args["path"] = self.cfg["mt5_path"]

        # Chiudi eventuali connessioni pendenti prima di inizializzare
        try:
            mt5.shutdown()
        except Exception:
            pass

        # Retry initialize con delay
        max_retries = 3
        connected = False
        for attempt in range(max_retries):
            if mt5.initialize(**init_args):
                connected = True
                break
            err = mt5.last_error()
            self._log(f"MT5 initialize tentativo {attempt+1}/{max_retries} fallito: {err}", "WARN")
            if attempt < max_retries - 1:
                time.sleep(2)

        if not connected:
            self._log(f"MT5 initialize fallito: {mt5.last_error()}", "ERROR")
            self._status("Errore connessione MT5")
            if self.cfg.get("tg_notify_error", True):
                self._tg(f"❌ <b>Errore connessione MT5</b>\n{mt5.last_error()}")
            self.running = False
            return

        login = self.cfg.get("mt5_login", "")
        password = self.cfg.get("mt5_password", "")
        server = self.cfg.get("mt5_server", "")

        if login and password and server:
            if not mt5.login(int(login), password, server):
                self._log(f"MT5 login fallito: {mt5.last_error()}", "ERROR")
                self._status("Errore login MT5")
                self.running = False
                return

        account_info = mt5.account_info()
        if account_info and login and int(login) != account_info.login:
            self._log(f"⚠️ Account connesso ({account_info.login}) diverso da quello inserito ({login})!", "ERROR")
            self._status(f"Errore: account sbagliato ({account_info.login})")
            mt5.shutdown()
            self.running = False
            return

        info = mt5.terminal_info()
        self._log(f"MT5 connesso | Build={info.build}")
        self._status("Connesso")
        if self.cfg.get("tg_notify_start", True):
            syms = [s["symbol"] for s in self.cfg.get("symbols", []) if s.get("enabled", True)]
            self._tg(
                f"🚀 <b>VaultSystemFx avviato</b>\n"
                f"📊 Simboli: <b>{', '.join(syms)}</b>\n"
                f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

        active_symbols = [s for s in self.cfg.get("symbols", []) if s.get("enabled", True)]
        symbol_names = [s["symbol"] for s in active_symbols]
        self._log(f"Simboli attivi: {symbol_names}")

        while self.running:
            try:
                now = time.time()
                bar_sec = 5 * 60
                elapsed = now % bar_sec
                sleep_time = bar_sec - elapsed + 2
                self._status(f"Attesa candela M5... ({int(sleep_time)}s)")

                start = time.time()
                be_check_time = 0
                while self.running and (time.time() - start) < sleep_time:
                    time.sleep(0.5)
                    # Controlla BE ogni 5 secondi
                    if time.time() - be_check_time >= 5:
                        try:
                            self._manage_breakeven(mt5)
                        except Exception:
                            pass
                        be_check_time = time.time()

                if not self.running:
                    break

                if mt5.terminal_info() is None:
                    self._log("MT5 disconnesso — riconnessione...", "WARN")
                    self._status("Riconnessione...")
                    if not mt5.initialize(**init_args):
                        continue
                    if login and password and server:
                        mt5.login(int(login), password, server)

                self._status("Analisi in corso...")
                self._log(f"--- Analisi M5 | {datetime.now().strftime('%H:%M:%S')} ---")

                # Controllo daily loss limit
                if self._check_daily_loss_limit(mt5):
                    limit_amount = self.cfg.get("daily_loss_amount", 300)
                    self._status(f"⛔ Stop giornaliero -€{limit_amount} | No trade")
                    continue

                # Fase 1: raccolta segnali
                pending_signals = []
                for sym_cfg in active_symbols:
                    if not self.running:
                        break
                    signal = self._compute_signal(mt5, np, sym_cfg)
                    if signal:
                        pending_signals.append(signal)

                # Fase 2: filtro coerenza valutaria (profitto/perdita + proporzionalità)
                if pending_signals:
                    valid = self._check_currency_correlation(mt5, pending_signals)
                    valid = self._check_eurusd_eurgbp_correlation(mt5, valid)
                    for sig in valid:
                        self._execute_order(mt5, sig)

                self._status(f"Attivo | Trade: {self.total_trades}")

            except Exception as e:
                self._log(f"Errore: {e}", "ERROR")
                time.sleep(10)

        mt5.shutdown()

    def _manage_breakeven(self, mt5):
        """Sposta SL a BE+3 pips quando profit >= soglia (20 pips Forex, 200 pips XAUUSD)."""
        if not self.cfg.get("be_enabled", False):
            return

        magic = self.cfg.get("magic_number", 202501)
        positions = mt5.positions_get()
        if not positions:
            return

        for pos in positions:
            if pos.magic != magic:
                continue

            symbol = pos.symbol
            sym_upper = symbol.upper()
            is_gold = "XAU" in sym_upper or "GOLD" in sym_upper

            info_sym = mt5.symbol_info(symbol)
            if not info_sym:
                continue

            point = info_sym.point
            digits = info_sym.digits

            # Calcola pips: per JPY pairs (digits=3) 1 pip = 10 points, altrimenti 1 pip = 10 points (5 digits)
            if digits == 3 or digits == 2:
                pip_value = point * 10
            else:
                pip_value = point * 10

            entry_price = pos.price_open
            current_sl = pos.sl

            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                continue

            # Calcola profit in pips
            if pos.type == 0:  # BUY
                current_price = tick.bid
                profit_pips = (current_price - entry_price) / pip_value
                be_sl = round(entry_price + (3 * pip_value), digits)  # BE + 3 pips
                # Verifica se SL attuale è già >= BE
                if current_sl >= be_sl:
                    continue
            else:  # SELL
                current_price = tick.ask
                profit_pips = (entry_price - current_price) / pip_value
                be_sl = round(entry_price - (3 * pip_value), digits)  # BE - 3 pips
                # Verifica se SL attuale è già <= BE
                if current_sl > 0 and current_sl <= be_sl:
                    continue

            # Soglia BE: 200 pips per XAUUSD, 20 pips per Forex
            be_threshold = 200 if is_gold else 20
            if profit_pips >= be_threshold:
                req = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": pos.ticket,
                    "symbol": symbol,
                    "sl": be_sl,
                    "tp": pos.tp,
                }
                result = mt5.order_send(req)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    direction = "BUY" if pos.type == 0 else "SELL"
                    self._log(f"🔒 BE attivato {symbol} {direction} | SL spostato a {be_sl} (+3 pips)")
                    if self.cfg.get("tg_notify_trade", True):
                        self._tg(f"🔒 <b>Break Even</b> — {symbol}\nSL spostato a <b>{be_sl}</b> (+3 pips di profit garantiti)")

    def _compute_signal(self, mt5, np, sym_cfg):
        symbol   = sym_cfg["symbol"]
        lot_mode = sym_cfg.get("lot_mode", "fixed")
        lot_size = sym_cfg.get("lot", 0.07)
        risk_pct = sym_cfg.get("risk_pct", 1.0)
        cfg      = self.cfg

        # ── Filtro sessione: orario e giorno ──
        if cfg.get("use_session_filter", False):
            now = datetime.now()
            # Lunedì=0, Venerdì=4 → solo lun-ven
            if now.weekday() > 4:
                return
            # Ora corrente come decimale (es. 19:30 = 19.5)
            current_hour = now.hour + now.minute / 60.0
            start_hour = cfg.get("session_start_hour", 7)
            end_hour = cfg.get("session_end_hour", 19.5)
            # Gestisce range che attraversano la mezzanotte (es. 23:00 -> 06:00)
            if start_hour < end_hour:
                # Range normale (es. 7:00 -> 19:30)
                if current_hour < start_hour or current_hour >= end_hour:
                    return
            else:
                # Range attraversa mezzanotte (es. 23:00 -> 06:00)
                if current_hour < start_hour and current_hour >= end_hour:
                    return

        donch_period  = cfg.get("donchian_period", 96)
        lwti_period   = cfg.get("lwti_period", 25)
        lwti_thresh   = cfg.get("lwti_threshold", 20.0)
        vol_period    = cfg.get("volume_ma_period", 30)
        atr_period    = cfg.get("atr_period", 14)
        consol_mult   = cfg.get("consolidation_mult", 0.5)
        min_body      = cfg.get("min_body_ratio", 0.65)
        use_engulf    = cfg.get("use_engulfing", True)
        rr            = cfg.get("rr_ratio", 2.0)
        sl_buffer_pts = cfg.get("sl_buffer_points", 5)
        max_spread    = cfg.get("max_spread_pts", 30)
        cooldown      = cfg.get("cooldown_bars", 0)
        magic         = cfg.get("magic_number", 202501)
        deviation     = cfg.get("deviation", 20)

        needed = max(donch_period, lwti_period, vol_period, atr_period) + 10
        rates  = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 1, needed)
        if rates is None or len(rates) < needed:
            return

        highs   = rates["high"]
        lows    = rates["low"]
        closes  = rates["close"]
        opens   = rates["open"]
        volumes = rates["tick_volume"].astype(float)

        i      = len(rates) - 1
        i_prev = i - 1

        if cooldown > 0:
            last = self.last_signal_bar.get(symbol, -9999)
            if (i - last) < cooldown:
                return

        def _donch(h, l, period, idx):
            s = idx - period + 1
            if s < 0: return None, None, None
            return np.max(h[s:idx+1]), np.min(l[s:idx+1]), (np.max(h[s:idx+1]) + np.min(l[s:idx+1])) / 2.0

        upper, lower, middle = _donch(highs, lows, donch_period, i_prev)
        upper_p, lower_p, _ = _donch(highs, lows, donch_period, i_prev - 1)
        if upper is None or upper_p is None:
            return

        bw      = upper - lower
        bw_prev = upper_p - lower_p

        if i < atr_period:
            return

        # ── FIX BUG 1: ATR con RMA (Wilder's Smoothing) ──
        # Pine: ta.atr(period) = ta.rma(ta.tr, period)
        # RMA: rma_t = (rma_{t-1} * (period-1) + value_t) / period
        tr_current = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        prev_rma = self._rma_atr.get(symbol)
        if prev_rma is None:
            trs = []
            for j in range(i - atr_period + 1, i + 1):
                tr = max(highs[j]-lows[j], abs(highs[j]-closes[j-1]), abs(lows[j]-closes[j-1]))
                trs.append(tr)
            atr_val = float(np.mean(trs))
        else:
            atr_val = (prev_rma * (atr_period - 1) + tr_current) / atr_period
        self._rma_atr[symbol] = atr_val

        if atr_val <= 0:
            return

        is_consol = bw < atr_val * consol_mult
        expanding = bw > bw_prev

        def _lwti(h, l, c, period, idx):
            s = idx - period + 1
            if s < 0: return 0.0
            hh, ll = np.max(h[s:idx+1]), np.min(l[s:idx+1])
            rng = hh - ll
            return (2.0 * (c[idx] - ll) / rng - 1.0) * 100.0 if rng > 0 else 0.0

        lwti_cur  = _lwti(highs, lows, closes, lwti_period, i)
        lwti_prev = _lwti(highs, lows, closes, lwti_period, i_prev)

        vs      = i - vol_period + 1
        vol_cur = volumes[i]
        vol_ma  = np.mean(volumes[vs:i+1]) if vs >= 0 else 0

        close_ = closes[i]; open_ = opens[i]
        high_  = highs[i];  low_  = lows[i]
        candle_range = high_ - low_
        candle_body  = abs(close_ - open_)
        strong   = (candle_body / candle_range >= min_body) if candle_range > 0 else False
        bullish  = close_ > open_
        bearish  = close_ < open_
        engulf_l = close_ > highs[i_prev] if use_engulf else True
        engulf_s = close_ < lows[i_prev]  if use_engulf else True

        long_sig  = (close_ > upper and lwti_cur > lwti_thresh and lwti_cur > lwti_prev
                     and vol_cur > vol_ma and bullish and strong and engulf_l
                     and expanding and not is_consol)
        short_sig = (close_ < lower and lwti_cur < -lwti_thresh and lwti_cur < lwti_prev
                     and vol_cur > vol_ma and bearish and strong and engulf_s
                     and expanding and not is_consol)

        if not long_sig and not short_sig:
            return

        info_sym = mt5.symbol_info(symbol)
        if not info_sym:
            return

        point     = info_sym.point
        sl_buffer = sl_buffer_pts * point

        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            return
        spread = (tick.ask - tick.bid) / point if point > 0 else 0
        if spread > max_spread:
            self._log(f"Spread alto {symbol}: {spread:.0f} pts — skip", "WARN")
            return

        positions = mt5.positions_get(symbol=symbol)
        if positions and any(p.magic == magic for p in positions):
            return

        # Prepara segnale (esecuzione dopo filtro correlazione)
        mt5.symbol_select(symbol, True)
        digits = info_sym.digits

        if long_sig:
            action = "buy"
            price  = round(tick.ask, digits)
            sl     = round(middle - sl_buffer, digits)
            tp     = round(close_ + (close_ - sl) * rr, digits)
        else:
            action = "sell"
            price  = round(tick.bid, digits)
            sl     = round(middle + sl_buffer, digits)
            tp     = round(close_ - (sl - close_) * rr, digits)

        filling = mt5.ORDER_FILLING_FOK
        if not (info_sym.filling_mode & 1):
            filling = mt5.ORDER_FILLING_IOC

        # ── Calcolo lotto dinamico (risk %) ──────────────────────────────
        if lot_mode == "risk":
            account = mt5.account_info()
            equity  = account.equity if account else 10000.0
            sl_dist = abs(price - sl)
            if sl_dist > 0 and point > 0:
                pip_size = point * 10
                sl_pips  = sl_dist / pip_size

                # pip_value per lotto standard (1 lot = $10/pip)
                sym_upper = symbol.upper()
                if "XAU" in sym_upper or "GOLD" in sym_upper:
                    pip_value = 10.0
                elif "JPY" in sym_upper:
                    pip_value = 1000.0 / closes[i] if closes[i] > 0 else 10.0
                else:
                    pip_value = 10.0

                risk_amount = equity * risk_pct / 100.0
                lot_size    = risk_amount / (sl_pips * pip_value)

                # Arrotonda al volume minimo/massimo del simbolo
                vol_min  = info_sym.volume_min
                vol_step = info_sym.volume_step
                if vol_step > 0:
                    lot_size = max(vol_min, round(round(lot_size / vol_step) * vol_step, 2))
                lot_size = min(lot_size, info_sym.volume_max)

                self._log(
                    f"📐 Risk {risk_pct}% | Equity={equity:.0f} | "
                    f"SL={sl_pips:.1f} pips | Lotto={lot_size}"
                )
            else:
                lot_size = info_sym.volume_min
                self._log(f"⚠️ SL dist=0, uso lotto minimo {lot_size}", "WARN")

        self._log(f"📊 Segnale: {'BUY' if action == 'buy' else 'SELL'} {symbol} | {lot_size} lotti")

        return {
            "symbol": symbol, "lot_size": lot_size, "direction": action,
            "price": price, "sl": sl, "tp": tp,
            "filling": filling, "deviation": deviation,
            "magic": magic, "bar_index": i,
        }

    def _execute_order(self, mt5, sig):
        """Invia l'ordine a MT5 dopo il filtro di coerenza valutaria."""
        symbol   = sig["symbol"]
        action   = sig["direction"]
        lot_size = sig["lot_size"]
        price    = sig["price"]
        sl       = sig["sl"]
        tp       = sig["tp"]
        magic    = sig["magic"]

        req = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol,
            "volume": lot_size,
            "type": mt5.ORDER_TYPE_BUY if action == "buy" else mt5.ORDER_TYPE_SELL,
            "price": price, "sl": sl, "tp": tp,
            "deviation": sig["deviation"], "magic": magic,
            "comment": "VSFx", "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": sig["filling"],
        }

        result = mt5.order_send(req)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            direct = "BUY" if action == "buy" else "SELL"
            self.total_trades += 1
            self.last_signal_bar[symbol] = sig["bar_index"]
            self._log(f"{direct} {symbol} | {lot_size} lotti @ {price} | SL={sl} TP={tp}")
            if self.cfg.get("tg_notify_trade", True):
                emoji = "🟢" if action == "buy" else "🔴"
                self._tg(
                    f"{emoji} <b>{direct}</b> — {symbol}\n"
                    f"📦 Lotti: <b>{lot_size}</b>\n"
                    f"💵 Prezzo: <b>{price}</b>\n"
                    f"🛑 SL: <b>{sl}</b>\n"
                    f"🎯 TP: <b>{tp}</b>\n"
                    f"🕐 {datetime.now().strftime('%H:%M:%S')}"
                )
        elif result:
            self._log(f"Ordine fallito {symbol}: {result.retcode} {result.comment}", "ERROR")
            if self.cfg.get("tg_notify_error", True):
                self._tg(f"❌ <b>Ordine fallito</b> — {symbol}\nCodice: {result.retcode}")


# ─────────────────────────────────────────────────────────────────
# API — bridge Python ↔ JavaScript
# ─────────────────────────────────────────────────────────────────
class Api:
    def __init__(self):
        self.engine = None
        self.cfg    = load_config()
        self._log_lines = []
        self._is_maximized = False

    def get_config(self):
        return json.dumps(self.cfg)

    def save_config(self, cfg_json):
        try:
            cfg = json.loads(cfg_json)
            for k in _STRATEGY_KEYS:
                cfg[k] = DEFAULT_CONFIG[k]
            self.cfg = cfg
            save_config(cfg)
            # Aggiorna anche il bot in esecuzione se presente
            if self.engine and self.engine.running:
                self.engine.cfg = cfg
            return "ok"
        except Exception as e:
            return f"error:{e}"

    def start_bot(self, cfg_json):
        try:
            cfg = json.loads(cfg_json)
            for k in _STRATEGY_KEYS:
                cfg[k] = DEFAULT_CONFIG[k]
            self.cfg = cfg
            save_config(cfg)
            self.engine = BotEngine(cfg, log_callback=self._on_log, status_callback=self._on_status)
            self.engine.start()
            return "ok"
        except Exception as e:
            return f"error:{e}"

    def stop_bot(self):
        if self.engine:
            self.engine.stop()
        return "ok"

    def get_logs(self):
        lines = self._log_lines[:]
        self._log_lines = []
        return json.dumps(lines)

    def get_account_info(self):
        try:
            import MetaTrader5 as mt5
            info = mt5.account_info()
            if not info:
                return json.dumps(None)
            positions = mt5.positions_get() or []
            open_profit = sum(p.profit for p in positions)
            from datetime import datetime, timedelta
            date_from = datetime.now() - timedelta(days=30)
            history = mt5.history_deals_get(date_from, datetime.now()) or []
            deals = [d for d in history if d.type in (0, 1) and d.entry == 1]
            trades = []
            wins = 0; losses = 0
            gross_profit = 0; gross_loss = 0
            peak = info.balance; drawdown = 0; running_bal = info.balance
            for d in sorted(deals, key=lambda x: x.time, reverse=True)[:20]:
                pnl = round(d.profit, 2)
                trades.append({
                    "time":   datetime.fromtimestamp(d.time).strftime("%H:%M"),
                    "symbol": d.symbol,
                    "type":   "BUY" if d.type == 0 else "SELL",
                    "volume": d.volume,
                    "profit": pnl,
                })
            for d in deals:
                pnl = d.profit
                if pnl > 0: wins += 1; gross_profit += pnl
                elif pnl < 0: losses += 1; gross_loss += abs(pnl)
            total = wins + losses
            winrate = round(wins / total * 100, 1) if total > 0 else 0
            pf = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 0
            return json.dumps({
                "equity":      round(info.equity, 2),
                "balance":     round(info.balance, 2),
                "profit":      round(open_profit, 2),
                "currency":    info.currency,
                "positions":   len(positions),
                "winrate":     winrate,
                "profit_factor": pf,
                "wins":        wins,
                "losses":      losses,
                "trades":      trades,
            })
        except Exception as e:
            return json.dumps(None)

    def get_session_info(self):
        cfg = self.cfg
        enabled = cfg.get("use_session_filter", False)
        start_h = cfg.get("session_start_hour", 7)
        end_h = cfg.get("session_end_hour", 19.5)
        now = datetime.now()
        current_hour = now.hour + now.minute / 60.0
        is_weekday = now.weekday() < 5
        in_range = is_weekday and start_h <= current_hour < end_h
        # Formatta orari per display
        start_m = int((start_h % 1) * 60)
        end_m = int((end_h % 1) * 60)
        start_str = f"{int(start_h):02d}:{start_m:02d}"
        end_str = f"{int(end_h):02d}:{end_m:02d}"
        return json.dumps({
            "enabled": enabled,
            "start": start_str,
            "end": end_str,
            "in_range": in_range,
            "is_weekday": is_weekday,
        })

    def get_logo_b64(self):
        if LOGO_FILE.exists():
            try:
                with open(LOGO_FILE, "rb") as f:
                    return base64.b64encode(f.read()).decode()
            except Exception:
                pass
        return ""

    def open_telegram(self):
        import webbrowser
        webbrowser.open("https://t.me/getidsbot")
        return "ok"

    def minimize_window(self):
        import webview
        for w in webview.windows:
            w.minimize()
        return "ok"

    def toggle_maximize(self):
        import webview
        for w in webview.windows:
            try:
                if self._is_maximized:
                    w.restore()
                    self._is_maximized = False
                else:
                    w.maximize()
                    self._is_maximized = True
            except Exception:
                w.toggle_fullscreen()
                self._is_maximized = not self._is_maximized
        return "ok"

    def check_update(self):
        result = _check_update()
        return json.dumps(result)

    def download_update(self, url):
        return _download_and_install(url)

    def close_window(self):
        import webview
        for w in webview.windows:
            w.destroy()
        return "ok"

    def move_window(self, dx, dy):
        try:
            import webview
            for w in webview.windows:
                x, y = w.x, w.y
                w.move(x + int(dx), y + int(dy))
        except Exception:
            pass
        return "ok"

    def test_telegram(self, chat_id, token=""):
        return _send_telegram(
            chat_id, token,
            "✅ <b>VaultSystemFx</b>\nNotifiche Telegram attive e funzionanti!"
        )

    def browse_mt5(self):
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(
            title="Seleziona terminal64.exe",
            filetypes=[("MetaTrader 5", "terminal64.exe"), ("Eseguibili", "*.exe"), ("Tutti", "*.*")]
        )
        root.destroy()
        return path or ""

    def _on_log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_lines.append({"ts": ts, "msg": msg})
        if len(self._log_lines) > 500:
            self._log_lines = self._log_lines[-500:]

    def _on_status(self, text):
        self._log_lines.append({"ts": "", "msg": f"__STATUS__{text}"})

    def run_backtest(self, symbols_json, date_from, date_to, lot, mode="fixed", risk="1", capital="10000"):
        """Esegue backtest della strategia sui dati storici per uno o più simboli."""
        import time as _time
        start_time = _time.time()
        try:
            import MetaTrader5 as mt5
            import numpy as np
            from datetime import datetime, timedelta

            # Parse symbols list
            symbols = json.loads(symbols_json) if symbols_json.startswith('[') else [symbols_json]
            lot = float(lot)
            risk_pct = float(risk)
            capital_start = float(capital)
            use_risk_mode = (mode == "risk")

            # Inizializza MT5 con credenziali
            path = self.cfg.get("mt5_path", "")
            login = self.cfg.get("mt5_login", "")
            password = self.cfg.get("mt5_password", "")
            server = self.cfg.get("mt5_server", "")

            if not mt5.terminal_info():
                init_args = {"path": path} if path else {}
                if not mt5.initialize(**init_args):
                    return json.dumps({"error": "Impossibile inizializzare MT5. Verifica il percorso."})
                if login and password and server:
                    if not mt5.login(int(login), password, server):
                        return json.dumps({"error": f"Login MT5 fallito. Verifica credenziali."})

            # Verifica connessione
            if not mt5.terminal_info():
                return json.dumps({"error": "MT5 non connesso. Avvia prima il bot o apri MT5."})

            # Parse date
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)

            # Parametri strategia
            cfg = DEFAULT_CONFIG
            donch_period = cfg.get("donchian_period", 96)
            lwti_period = cfg.get("lwti_period", 25)
            lwti_thresh = cfg.get("lwti_threshold", 20.0)
            vol_period = cfg.get("volume_ma_period", 30)
            atr_period = cfg.get("atr_period", 14)
            consol_mult = cfg.get("consolidation_mult", 0.5)
            min_body = cfg.get("min_body_ratio", 0.65)
            rr = cfg.get("rr_ratio", 2.0)
            sl_buffer_pts = cfg.get("sl_buffer_points", 5)
            needed = max(donch_period, lwti_period, vol_period, atr_period) + 10

            # Risultati aggregati
            all_trades = []
            all_equity = []
            total_balance = capital_start if use_risk_mode else 10000.0
            symbols_ok = []

            for symbol in symbols:
                # Abilita simbolo
                mt5.symbol_select(symbol, True)

                # Scarica dati M5
                rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5, dt_from, dt_to)
                if rates is None or len(rates) < 100:
                    continue  # Skip simbolo senza dati

                symbols_ok.append(symbol)
                info_sym = mt5.symbol_info(symbol)
                if not info_sym:
                    continue
                point = info_sym.point
                digits = info_sym.digits

                highs = rates["high"]
                lows = rates["low"]
                closes = rates["close"]
                opens = rates["open"]
                volumes = rates["tick_volume"].astype(float)
                times = rates["time"]

                position = None

                for i in range(needed, len(rates)):
                    current_time = datetime.fromtimestamp(times[i])

                    # Filtro sessione
                    if current_time.weekday() > 4:
                        continue
                    hour_dec = current_time.hour + current_time.minute / 60.0
                    if hour_dec < 7 or hour_dec >= 19.5:
                        continue

                    close_ = closes[i]
                    open_ = opens[i]
                    high_ = highs[i]
                    low_ = lows[i]

                    # Gestisci posizione aperta
                    if position:
                        pos_lot = position.get("lot", lot)
                        if position["type"] == "buy":
                            if low_ <= position["sl"]:
                                pnl = (position["sl"] - position["entry"]) / point * pos_lot
                                total_balance += pnl
                                all_trades.append({"date": current_time.strftime("%d/%m"), "symbol": symbol, "type": "BUY", "entry": round(position["entry"], digits), "exit": round(position["sl"], digits), "profit": round(pnl, 2)})
                                position = None
                            elif high_ >= position["tp"]:
                                pnl = (position["tp"] - position["entry"]) / point * pos_lot
                                total_balance += pnl
                                all_trades.append({"date": current_time.strftime("%d/%m"), "symbol": symbol, "type": "BUY", "entry": round(position["entry"], digits), "exit": round(position["tp"], digits), "profit": round(pnl, 2)})
                                position = None
                        else:
                            if high_ >= position["sl"]:
                                pnl = (position["entry"] - position["sl"]) / point * pos_lot
                                total_balance += pnl
                                all_trades.append({"date": current_time.strftime("%d/%m"), "symbol": symbol, "type": "SELL", "entry": round(position["entry"], digits), "exit": round(position["sl"], digits), "profit": round(pnl, 2)})
                                position = None
                            elif low_ <= position["tp"]:
                                pnl = (position["entry"] - position["tp"]) / point * pos_lot
                                total_balance += pnl
                                all_trades.append({"date": current_time.strftime("%d/%m"), "symbol": symbol, "type": "SELL", "entry": round(position["entry"], digits), "exit": round(position["tp"], digits), "profit": round(pnl, 2)})
                                position = None

                    all_equity.append({"date": current_time.strftime("%d/%m"), "equity": round(total_balance, 2)})

                    if position:
                        continue

                    # Calcola indicatori
                    upper = np.max(highs[i-donch_period:i])
                    lower = np.min(lows[i-donch_period:i])
                    middle = (upper + lower) / 2.0
                    bw = upper - lower
                    bw_prev = np.max(highs[i-donch_period-1:i-1]) - np.min(lows[i-donch_period-1:i-1])

                    tr_vals = []
                    for j in range(i-atr_period, i):
                        tr = max(highs[j] - lows[j], abs(highs[j] - closes[j-1]), abs(lows[j] - closes[j-1]))
                        tr_vals.append(tr)
                    atr = np.mean(tr_vals)

                    is_consol = bw < atr * consol_mult
                    expanding = bw > bw_prev

                    def calc_lwti(idx):
                        s = idx - lwti_period + 1
                        if s < 0: return 0.0
                        hh = np.max(highs[s:idx+1])
                        ll = np.min(lows[s:idx+1])
                        rng = hh - ll
                        return (2.0 * (closes[idx] - ll) / rng - 1.0) * 100.0 if rng > 0 else 0.0

                    lwti_cur = calc_lwti(i)
                    lwti_prev = calc_lwti(i-1)

                    vol_cur = volumes[i]
                    vol_ma = np.mean(volumes[i-vol_period:i])

                    candle_range = high_ - low_
                    candle_body = abs(close_ - open_)
                    strong = (candle_body / candle_range >= min_body) if candle_range > 0 else False
                    bullish = close_ > open_
                    bearish = close_ < open_
                    engulf_l = close_ > highs[i-1]
                    engulf_s = close_ < lows[i-1]

                    long_sig = (close_ > upper and lwti_cur > lwti_thresh and lwti_cur > lwti_prev
                                and vol_cur > vol_ma and bullish and strong and engulf_l
                                and expanding and not is_consol)
                    short_sig = (close_ < lower and lwti_cur < -lwti_thresh and lwti_cur < lwti_prev
                                 and vol_cur > vol_ma and bearish and strong and engulf_s
                                 and expanding and not is_consol)

                    sl_buffer = sl_buffer_pts * point

                    if long_sig and not position:
                        entry = close_
                        sl = middle - sl_buffer
                        tp = entry + (entry - sl) * rr
                        # Calcola lot dinamico in risk mode
                        trade_lot = lot
                        if use_risk_mode:
                            sl_dist = abs(entry - sl) / point
                            risk_amount = total_balance * risk_pct / 100.0
                            # pip value: ~10 per lot standard (semplificato)
                            pip_value = 10.0 if "JPY" not in symbol else 1000.0 / close_
                            if "XAU" in symbol:
                                pip_value = 1.0
                            trade_lot = risk_amount / (sl_dist * pip_value) if sl_dist > 0 else 0.01
                            trade_lot = max(0.01, min(10.0, round(trade_lot, 2)))
                        position = {"type": "buy", "entry": entry, "sl": sl, "tp": tp, "lot": trade_lot}
                    elif short_sig and not position:
                        entry = close_
                        sl = middle + sl_buffer
                        tp = entry - (sl - entry) * rr
                        # Calcola lot dinamico in risk mode
                        trade_lot = lot
                        if use_risk_mode:
                            sl_dist = abs(sl - entry) / point
                            risk_amount = total_balance * risk_pct / 100.0
                            pip_value = 10.0 if "JPY" not in symbol else 1000.0 / close_
                            if "XAU" in symbol:
                                pip_value = 1.0
                            trade_lot = risk_amount / (sl_dist * pip_value) if sl_dist > 0 else 0.01
                            trade_lot = max(0.01, min(10.0, round(trade_lot, 2)))
                        position = {"type": "sell", "entry": entry, "sl": sl, "tp": tp, "lot": trade_lot}

            if not symbols_ok:
                return json.dumps({"error": "Nessun simbolo con dati sufficienti"})

            # Parametri strategia (stessi del bot)
            cfg = DEFAULT_CONFIG
            donch_period = cfg.get("donchian_period", 96)
            lwti_period = cfg.get("lwti_period", 25)
            lwti_thresh = cfg.get("lwti_threshold", 20.0)
            vol_period = cfg.get("volume_ma_period", 30)
            atr_period = cfg.get("atr_period", 14)
            consol_mult = cfg.get("consolidation_mult", 0.5)
            min_body = cfg.get("min_body_ratio", 0.65)
            rr = cfg.get("rr_ratio", 2.0)
            sl_buffer_pts = cfg.get("sl_buffer_points", 5)

            info_sym = mt5.symbol_info(symbol)
            if not info_sym:
                return json.dumps({"error": f"Simbolo {symbol} non trovato"})
            point = info_sym.point
            digits = info_sym.digits

            highs = rates["high"]
            lows = rates["low"]
            closes = rates["close"]
            opens = rates["open"]
            volumes = rates["tick_volume"].astype(float)
            times = rates["time"]

            # Simula trade
            trades = []
            equity_curve = []
            balance = 10000.0
            position = None  # {"type", "entry", "sl", "tp", "time"}

            # Debug counters
            debug_bars = len(rates)
            debug_signals = 0
            debug_in_session = 0

            needed = max(donch_period, lwti_period, vol_period, atr_period) + 10

            for i in range(needed, len(rates)):
                current_time = datetime.fromtimestamp(times[i])

                # Filtro sessione (7:00 - 19:30, lun-ven)
                if current_time.weekday() > 4:
                    continue
                hour_dec = current_time.hour + current_time.minute / 60.0
                if hour_dec < 7 or hour_dec >= 19.5:
                    continue

                debug_in_session += 1
                close_ = closes[i]
                open_ = opens[i]
                high_ = highs[i]
                low_ = lows[i]

                # Gestisci posizione aperta
                if position:
                    if position["type"] == "buy":
                        if low_ <= position["sl"]:
                            pnl = (position["sl"] - position["entry"]) / point * lot
                            balance += pnl
                            trades.append({"date": current_time.strftime("%d/%m"), "type": "BUY", "entry": round(position["entry"], digits), "exit": round(position["sl"], digits), "profit": round(pnl, 2)})
                            position = None
                        elif high_ >= position["tp"]:
                            pnl = (position["tp"] - position["entry"]) / point * lot
                            balance += pnl
                            trades.append({"date": current_time.strftime("%d/%m"), "type": "BUY", "entry": round(position["entry"], digits), "exit": round(position["tp"], digits), "profit": round(pnl, 2)})
                            position = None
                    else:  # sell
                        if high_ >= position["sl"]:
                            pnl = (position["entry"] - position["sl"]) / point * lot
                            balance += pnl
                            trades.append({"date": current_time.strftime("%d/%m"), "type": "SELL", "entry": round(position["entry"], digits), "exit": round(position["sl"], digits), "profit": round(pnl, 2)})
                            position = None
                        elif low_ <= position["tp"]:
                            pnl = (position["entry"] - position["tp"]) / point * lot
                            balance += pnl
                            trades.append({"date": current_time.strftime("%d/%m"), "type": "SELL", "entry": round(position["entry"], digits), "exit": round(position["tp"], digits), "profit": round(pnl, 2)})
                            position = None

                equity_curve.append({"date": current_time.strftime("%d/%m"), "equity": round(balance, 2)})

                # Skip se già in posizione
                if position:
                    continue

                # Calcola indicatori (stessa logica del bot live)
                # Donchian
                upper = np.max(highs[i-donch_period:i])
                lower = np.min(lows[i-donch_period:i])
                middle = (upper + lower) / 2.0
                bw = upper - lower
                bw_prev = np.max(highs[i-donch_period-1:i-1]) - np.min(lows[i-donch_period-1:i-1])

                # ATR
                tr_vals = []
                for j in range(i-atr_period, i):
                    tr = max(highs[j] - lows[j], abs(highs[j] - closes[j-1]), abs(lows[j] - closes[j-1]))
                    tr_vals.append(tr)
                atr = np.mean(tr_vals)

                is_consol = bw < atr * consol_mult
                expanding = bw > bw_prev

                # LWTI (formula corretta: range -100 to +100)
                def calc_lwti(idx):
                    s = idx - lwti_period + 1
                    if s < 0: return 0.0
                    hh = np.max(highs[s:idx+1])
                    ll = np.min(lows[s:idx+1])
                    rng = hh - ll
                    return (2.0 * (closes[idx] - ll) / rng - 1.0) * 100.0 if rng > 0 else 0.0

                lwti_cur = calc_lwti(i)
                lwti_prev = calc_lwti(i-1)

                # Volume
                vol_cur = volumes[i]
                vol_ma = np.mean(volumes[i-vol_period:i])

                # Candle analysis
                candle_range = high_ - low_
                candle_body = abs(close_ - open_)
                strong = (candle_body / candle_range >= min_body) if candle_range > 0 else False
                bullish = close_ > open_
                bearish = close_ < open_
                engulf_l = close_ > highs[i-1]
                engulf_s = close_ < lows[i-1]

                # Segnali (stessa logica del bot live)
                long_sig = (close_ > upper and lwti_cur > lwti_thresh and lwti_cur > lwti_prev
                            and vol_cur > vol_ma and bullish and strong and engulf_l
                            and expanding and not is_consol)
                short_sig = (close_ < lower and lwti_cur < -lwti_thresh and lwti_cur < lwti_prev
                             and vol_cur > vol_ma and bearish and strong and engulf_s
                             and expanding and not is_consol)

                sl_buffer = sl_buffer_pts * point

                if long_sig and not position:
                    debug_signals += 1
                    entry = close_
                    sl = middle - sl_buffer
                    tp = entry + (entry - sl) * rr
                    position = {"type": "buy", "entry": entry, "sl": sl, "tp": tp}
                elif short_sig and not position:
                    debug_signals += 1
                    entry = close_
                    sl = middle + sl_buffer
                    tp = entry - (sl - entry) * rr
                    position = {"type": "sell", "entry": entry, "sl": sl, "tp": tp}

            # Calcola statistiche aggregate
            wins = len([t for t in all_trades if t["profit"] > 0])
            losses = len([t for t in all_trades if t["profit"] <= 0])
            total = wins + losses
            winrate = round(wins / total * 100, 1) if total > 0 else 0

            gross_profit = sum(t["profit"] for t in all_trades if t["profit"] > 0)
            gross_loss = abs(sum(t["profit"] for t in all_trades if t["profit"] < 0))
            pf = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 0

            net_profit = total_balance - 10000.0
            expectancy = round(net_profit / total, 2) if total > 0 else 0

            # Max drawdown
            peak = 10000.0
            max_dd = 0
            for eq in all_equity:
                if eq["equity"] > peak:
                    peak = eq["equity"]
                dd = (peak - eq["equity"]) / peak * 100
                if dd > max_dd:
                    max_dd = dd

            # Riduci equity curve per il grafico (max 100 punti)
            if len(all_equity) > 100:
                step = len(all_equity) // 100
                all_equity = all_equity[::step]

            duration = round(_time.time() - start_time, 1)

            return json.dumps({
                "total": total,
                "wins": wins,
                "losses": losses,
                "winrate": winrate,
                "profit_factor": pf,
                "net_profit": round(net_profit, 2),
                "max_dd": round(max_dd, 2),
                "expectancy": expectancy,
                "period": f"{date_from} → {date_to}",
                "symbols": symbols_ok,
                "trades": all_trades[-50:],  # ultimi 50
                "equity_curve": all_equity,
                "duration": duration,
            })
        except Exception as e:
            return json.dumps({"error": str(e)})


# ─────────────────────────────────────────────────────────────────
# HTML / CSS / JS
# ─────────────────────────────────────────────────────────────────
HTML = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<title>VaultSystemFx</title>
<style>
:root{
--bg-primary:#06080d;--bg-secondary:#0a0e17;--bg-card:rgba(12,16,24,0.85);--bg-input:#0a0e17;
--border-subtle:rgba(255,255,255,0.06);--border-hover:rgba(99,139,255,0.4);
--text-primary:#f4f7ff;--text-secondary:#7a8ba8;--text-muted:#4a5568;
--accent-primary:#638bff;--accent-secondary:#a78bfa;--accent-success:#34d399;--accent-danger:#f87171;
--accent-gradient:linear-gradient(135deg,#638bff 0%,#a78bfa 50%,#34d399 100%);
--glow-primary:rgba(99,139,255,0.5);--glow-success:rgba(52,211,153,0.5);
--radius-sm:8px;--radius-md:12px;--radius-lg:16px;--radius-xl:20px;
--shadow-md:0 8px 32px rgba(0,0,0,0.3);--shadow-glow:0 0 30px var(--glow-primary);
--transition-fast:0.15s cubic-bezier(0.4,0,0.2,1);--transition-base:0.3s cubic-bezier(0.4,0,0.2,1);
--font-sans:'Plus Jakarta Sans',-apple-system,BlinkMacSystemFont,sans-serif;
--font-mono:'JetBrains Mono','Fira Code',Consolas,monospace;
}
*{margin:0;padding:0;box-sizing:border-box;-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;}
html,body{background:var(--bg-primary)!important;}
body{background:var(--bg-primary);color:var(--text-primary);font-family:var(--font-sans);font-size:15px;height:100vh;width:100vw;display:flex;flex-direction:column;overflow:hidden;-webkit-user-select:none;user-select:none;}
::selection{background:var(--accent-primary);color:white;}
::-webkit-scrollbar{width:8px;}::-webkit-scrollbar-track{background:transparent;}::-webkit-scrollbar-thumb{background:linear-gradient(180deg,var(--accent-primary),var(--accent-secondary));border-radius:8px;}
.header{background:var(--bg-card);backdrop-filter:blur(20px);padding:14px 28px;height:auto;min-height:76px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border-subtle);flex-shrink:0;gap:16px;}
.header-left{display:flex;align-items:center;gap:16px;}
.logo{width:44px;height:44px;border-radius:var(--radius-md);object-fit:cover;border:1px solid var(--border-subtle);transition:var(--transition-base);}
.logo:hover{border-color:var(--accent-primary);box-shadow:var(--shadow-glow);}
.logo-ph{width:44px;height:44px;border-radius:var(--radius-md);background:var(--accent-gradient);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:18px;color:#fff;}
.title-block h1{font-size:20px;font-weight:700;color:var(--text-primary);letter-spacing:-0.02em;}
.title-block p{font-size:12px;color:var(--text-muted);letter-spacing:0.1em;text-transform:uppercase;margin-top:2px;}
.accent-line{height:2px;background:var(--accent-gradient);flex-shrink:0;}
.status-pill{display:flex;align-items:center;gap:8px;background:var(--bg-input);border:1px solid var(--border-subtle);border-radius:50px;padding:8px 16px;font-size:13px;font-weight:600;color:var(--text-muted);transition:var(--transition-base);}
.status-dot{width:8px;height:8px;border-radius:50%;background:var(--text-muted);transition:var(--transition-base);}
.status-pill.active{color:var(--accent-primary);border-color:var(--accent-primary);}
.status-pill.active .status-dot{background:var(--accent-primary);box-shadow:0 0 12px var(--glow-primary);animation:pulse 2s ease-in-out infinite;}
@keyframes pulse{0%,100%{opacity:1;}50%{opacity:0.5;}}
.status-pill.error{color:var(--accent-danger);border-color:var(--accent-danger);}
.status-pill.error .status-dot{background:var(--accent-danger);}
.status-pill.waiting{color:var(--text-secondary);border-color:rgba(99,139,255,0.3);}
.status-pill.waiting .status-dot{background:var(--text-secondary);animation:pulse 1.5s ease-in-out infinite;}
.session-box{display:flex;align-items:center;gap:10px;background:linear-gradient(135deg,rgba(16,22,36,0.9),rgba(12,16,24,0.95));border:1px solid var(--border-subtle);border-radius:var(--radius-md);padding:8px 14px;margin-right:10px;transition:var(--transition-base);}
.session-box:hover{border-color:var(--border-hover);}
.session-box.off{opacity:0.5;}
.session-icon{width:28px;height:28px;border-radius:50%;background:linear-gradient(135deg,rgba(99,139,255,0.2),rgba(167,139,250,0.15));display:flex;align-items:center;justify-content:center;flex-shrink:0;}
.session-icon svg{width:14px;height:14px;stroke:var(--accent-primary);}
.session-info{display:flex;flex-direction:column;gap:1px;}
.session-label{color:var(--text-muted);font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;}
.session-times{display:flex;align-items:center;gap:6px;}
.session-time-input{background:rgba(99,139,255,0.08);border:none;border-radius:4px;color:var(--accent-primary);font-family:var(--font-mono);font-size:11px;font-weight:600;padding:3px 6px;width:50px;cursor:pointer;-webkit-user-select:text;user-select:text;outline:none;text-align:center;transition:var(--transition-fast);}.session-time-input:focus{background:rgba(99,139,255,0.15);box-shadow:0 0 0 2px rgba(99,139,255,0.2);}.session-time-input::-webkit-calendar-picker-indicator{display:none;}.session-time-input::-webkit-datetime-edit-ampm-field{display:none;}
.session-sep{color:var(--text-muted);font-size:10px;font-weight:600;}
.session-status{font-size:10px;font-weight:700;padding:3px 8px;border-radius:10px;margin-left:4px;}
.session-status.in-range{color:var(--accent-success);background:rgba(52,211,153,0.12);}
.session-status.out-range{color:var(--accent-danger);background:rgba(248,113,113,0.12);}
.session-status.disabled{color:var(--text-muted);background:rgba(74,85,104,0.2);}
.tabs-bar{background:var(--bg-card);backdrop-filter:blur(16px);display:flex;padding:0 28px;border-bottom:1px solid var(--border-subtle);flex-shrink:0;gap:4px;}
.tab-btn{background:transparent;border:none;color:var(--text-muted);font-family:var(--font-sans);font-size:14px;font-weight:500;padding:16px 20px;cursor:pointer;border-bottom:2px solid transparent;transition:var(--transition-fast);position:relative;}
.tab-btn:hover{color:var(--text-secondary);background:rgba(255,255,255,0.02);}
.tab-btn.active{color:var(--accent-primary);border-bottom-color:var(--accent-primary);font-weight:600;}
.icon{display:inline-block;width:16px;height:16px;margin-right:6px;vertical-align:middle;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;}
.icon-dashboard{background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23638bff' stroke-width='2'%3E%3Crect x='3' y='3' width='7' height='9' rx='1'/%3E%3Crect x='14' y='3' width='7' height='5' rx='1'/%3E%3Crect x='14' y='12' width='7' height='9' rx='1'/%3E%3Crect x='3' y='16' width='7' height='5' rx='1'/%3E%3C/svg%3E") center/contain no-repeat;}
.icon-mt5{background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23638bff' stroke-width='2'%3E%3Crect x='2' y='3' width='20' height='14' rx='2'/%3E%3Cpath d='M8 21h8M12 17v4'/%3E%3Cpath d='M6 8l4 3-4 3M12 14h4'/%3E%3C/svg%3E") center/contain no-repeat;}
.icon-symbols{background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23638bff' stroke-width='2'%3E%3Ccircle cx='12' cy='12' r='8'/%3E%3Cpath d='M12 8v8M8 12h8'/%3E%3Cpath d='M12 2v2M12 20v2M2 12h2M20 12h2'/%3E%3C/svg%3E") center/contain no-repeat;}
.icon-log{background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23638bff' stroke-width='2'%3E%3Cpath d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'/%3E%3Cpolyline points='14 2 14 8 20 8'/%3E%3Cline x1='16' y1='13' x2='8' y2='13'/%3E%3Cline x1='16' y1='17' x2='8' y2='17'/%3E%3C/svg%3E") center/contain no-repeat;}
.icon-guide{background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23638bff' stroke-width='2'%3E%3Cpath d='M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z'/%3E%3Cpath d='M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z'/%3E%3C/svg%3E") center/contain no-repeat;}
.icon-telegram{background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23638bff' stroke-width='2'%3E%3Cpath d='M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z'/%3E%3C/svg%3E") center/contain no-repeat;}
.icon-backtest{background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23638bff' stroke-width='2'%3E%3Cpolyline points='22 12 18 12 15 21 9 3 6 12 2 12'/%3E%3C/svg%3E") center/contain no-repeat;}
.icon-chart{background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23638bff' stroke-width='2'%3E%3Cpolyline points='23 6 13.5 15.5 8.5 10.5 1 18'/%3E%3Cpolyline points='17 6 23 6 23 12'/%3E%3C/svg%3E") center/contain no-repeat;}
.icon-list{background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23638bff' stroke-width='2'%3E%3Cline x1='8' y1='6' x2='21' y2='6'/%3E%3Cline x1='8' y1='12' x2='21' y2='12'/%3E%3Cline x1='8' y1='18' x2='21' y2='18'/%3E%3Ccircle cx='4' cy='6' r='1' fill='%23638bff'/%3E%3Ccircle cx='4' cy='12' r='1' fill='%23638bff'/%3E%3Ccircle cx='4' cy='18' r='1' fill='%23638bff'/%3E%3C/svg%3E") center/contain no-repeat;}
.icon-play{background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23fff' stroke='none'%3E%3Cpolygon points='5 3 19 12 5 21 5 3'/%3E%3C/svg%3E") center/contain no-repeat;}
.content{flex:1;overflow-y:auto;padding:20px 28px;scrollbar-width:thin;scrollbar-color:var(--accent-primary) transparent;}
.tab-panel{display:none;animation:fadeIn 0.3s ease-out;}
@keyframes fadeIn{from{opacity:0;transform:translateY(8px);}to{opacity:1;transform:translateY(0);}}
.tab-panel.active{display:block;}
.card{background:var(--bg-card);backdrop-filter:blur(16px);border:1px solid var(--border-subtle);border-radius:var(--radius-xl);padding:28px;margin-bottom:20px;transition:var(--transition-base);}
.card:hover{border-color:var(--border-hover);}
.card-title{font-size:18px;font-weight:700;color:var(--text-primary);margin-bottom:6px;}
.card-sub{font-size:14px;color:var(--text-muted);margin-bottom:24px;}
.form-row{display:grid;grid-template-columns:180px 1fr;align-items:center;gap:16px;margin-bottom:16px;}
.form-row.with-btn{grid-template-columns:180px 1fr 48px;}
.form-row label{font-size:14px;font-weight:500;color:var(--text-secondary);}
input[type=text],input[type=password]{background:var(--bg-input);border:1px solid var(--border-subtle);border-radius:var(--radius-md);color:var(--text-primary);font-family:var(--font-sans);font-size:14px;padding:12px 16px;width:100%;outline:none;transition:var(--transition-base);-webkit-user-select:text;user-select:text;}
input[type=text]:focus,input[type=password]:focus{border-color:var(--accent-primary);box-shadow:0 0 0 3px rgba(99,139,255,0.15);}
input[type=text]::placeholder,input[type=password]::placeholder{color:var(--text-muted);}
.btn-icon{background:var(--bg-input);border:1px solid var(--border-subtle);border-radius:var(--radius-md);color:var(--text-secondary);font-size:16px;padding:12px 14px;cursor:pointer;transition:var(--transition-base);}
.btn-icon:hover{border-color:var(--accent-primary);color:var(--accent-primary);background:rgba(99,139,255,0.1);}
.capital-box{background:var(--bg-card);border:1px solid var(--border-subtle);border-radius:var(--radius-lg);padding:18px 22px;margin-bottom:20px;display:flex;align-items:center;gap:20px;flex-wrap:wrap;transition:var(--transition-base);}
.capital-box:hover{border-color:var(--border-hover);}
.capital-label{font-size:15px;color:var(--accent-primary);font-weight:600;min-width:140px;display:flex;align-items:center;gap:8px;}
.capital-input{background:var(--bg-input);border:1px solid var(--border-subtle);border-radius:var(--radius-md);padding:10px 16px;font-size:14px;color:var(--text-primary);width:160px;outline:none;font-family:var(--font-mono);transition:var(--transition-base);-webkit-user-select:text;user-select:text;}
.capital-input:focus{border-color:var(--accent-primary);box-shadow:0 0 0 3px rgba(99,139,255,0.15);}
.capital-hint{font-size:13px;color:var(--text-muted);}
.add-row{display:flex;gap:12px;margin-bottom:18px;align-items:center;}
.add-input{background:var(--bg-input);border:1px solid var(--border-subtle);border-radius:var(--radius-md);padding:10px 14px;font-size:14px;color:var(--text-primary);width:150px;outline:none;font-family:var(--font-sans);transition:var(--transition-base);-webkit-user-select:text;user-select:text;}
.add-input:focus{border-color:var(--accent-primary);box-shadow:0 0 0 3px rgba(99,139,255,0.15);}
.btn-add{background:var(--accent-primary);border:none;border-radius:var(--radius-md);padding:10px 20px;font-size:14px;font-weight:600;color:#fff;cursor:pointer;transition:var(--transition-base);position:relative;overflow:hidden;}
.btn-add:hover{transform:translateY(-2px);box-shadow:0 8px 24px var(--glow-primary);}
.sym-header{display:grid;grid-template-columns:48px 1fr 130px 130px 110px 40px;gap:10px;padding:10px 14px;background:var(--bg-card);border-radius:var(--radius-md);margin-bottom:8px;font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.1em;}
.sym-row{display:grid;grid-template-columns:48px 1fr 130px 130px 110px 40px;gap:10px;align-items:center;padding:12px 14px;background:var(--bg-input);border:1px solid var(--border-subtle);border-radius:var(--radius-md);margin-bottom:6px;transition:var(--transition-base);}
.sym-row:hover{background:var(--bg-card);border-color:var(--border-hover);}
.toggle{position:relative;width:40px;height:22px;cursor:pointer;display:block;}
.toggle input{display:none;}
.toggle-bg{position:absolute;inset:0;background:rgba(255,255,255,0.1);border-radius:22px;transition:var(--transition-base);}
.toggle-knob{position:absolute;width:16px;height:16px;border-radius:50%;background:var(--text-muted);left:3px;top:3px;transition:var(--transition-base);box-shadow:0 2px 4px rgba(0,0,0,0.2);}
.toggle input:checked ~ .toggle-bg{background:var(--accent-primary);}
.toggle input:checked ~ .toggle-knob{left:21px;background:#fff;box-shadow:0 0 8px var(--glow-primary);}
.be-toggle-wrap{display:flex;align-items:center;gap:10px;}
.be-toggle-label{font-size:13px;color:var(--text-muted);font-weight:600;}
.be-info-icon{width:20px;height:20px;border-radius:50%;background:rgba(99,139,255,0.3);color:var(--accent-primary);font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center;cursor:pointer;transition:var(--transition-base);position:relative;border:1px solid var(--accent-primary);}
.be-info-icon:hover{background:var(--accent-primary);color:#fff;}
.be-tooltip{position:absolute;top:calc(100% + 12px);right:-10px;width:320px;background:var(--bg-secondary);border:1px solid var(--accent-primary);border-radius:var(--radius-md);padding:14px 16px;font-size:12px;color:var(--text-secondary);line-height:1.6;opacity:0;visibility:hidden;transform:translateY(-5px);transition:all 0.2s ease;z-index:99999;box-shadow:0 12px 40px rgba(0,0,0,0.6);pointer-events:none;}
.be-tooltip::before{content:'';position:absolute;bottom:100%;right:18px;border:8px solid transparent;border-bottom-color:var(--accent-primary);}
.be-info-icon:hover .be-tooltip{opacity:1;visibility:visible;transform:translateY(0);}
.be-tooltip strong{color:var(--accent-primary);}
.be-tooltip .be-warn{color:#f87171;font-weight:600;margin-top:8px;display:block;}
.bt-config{background:var(--bg-input);border:1px solid var(--border-subtle);border-radius:var(--radius-lg);padding:20px;margin-top:16px;}
.bt-row{display:flex;align-items:flex-end;gap:20px;flex-wrap:wrap;}
.bt-field label{font-size:12px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em;}
.bt-select,.bt-input{background:var(--bg-card);border:1px solid var(--border-subtle);border-radius:var(--radius-md);padding:10px 14px;font-size:14px;color:var(--text-primary);outline:none;font-family:var(--font-mono);transition:var(--transition-base);min-width:140px;}
.mode-sel{position:relative;width:140px;}
.mode-btn{background:linear-gradient(135deg,var(--bg-card),rgba(99,139,255,0.05));border:1px solid var(--border-subtle);border-radius:var(--radius-md);padding:10px 14px;font-size:14px;color:var(--text-primary);cursor:pointer;display:flex;align-items:center;justify-content:space-between;gap:10px;transition:all 0.3s;user-select:none;}
.mode-btn:hover{border-color:var(--accent-primary);background:linear-gradient(135deg,rgba(99,139,255,0.1),rgba(167,139,250,0.05));box-shadow:0 0 15px rgba(99,139,255,0.15);}
.mode-btn.open{border-color:var(--accent-primary);border-radius:var(--radius-md) var(--radius-md) 0 0;background:linear-gradient(135deg,rgba(99,139,255,0.15),rgba(167,139,250,0.08));}
.mode-arrow{width:14px;height:14px;stroke:var(--accent-primary);transition:transform 0.3s cubic-bezier(0.4,0,0.2,1);}
.mode-btn.open .mode-arrow{transform:rotate(180deg);}
.mode-dd{position:absolute;top:100%;left:0;right:0;background:linear-gradient(180deg,var(--bg-secondary),var(--bg-card));border:1px solid var(--accent-primary);border-top:none;border-radius:0 0 var(--radius-md) var(--radius-md);overflow:hidden;max-height:0;opacity:0;transition:all 0.3s cubic-bezier(0.4,0,0.2,1);z-index:100;box-shadow:0 8px 20px rgba(0,0,0,0.3);}
.mode-dd.open{max-height:150px;opacity:1;}
.mode-opt{padding:12px 14px;font-size:14px;color:var(--text-secondary);cursor:pointer;transition:all 0.2s;display:flex;align-items:center;gap:10px;border-left:3px solid transparent;}
.mode-opt svg{width:16px;height:16px;stroke:transparent;transition:all 0.2s;}
.mode-opt:hover{background:rgba(99,139,255,0.1);color:var(--text-primary);border-left-color:var(--accent-primary);}
.mode-opt.sel{color:var(--accent-primary);font-weight:600;background:rgba(99,139,255,0.08);}
.mode-opt.sel svg{stroke:var(--accent-primary);}
.bt-select:focus,.bt-input:focus{border-color:var(--accent-primary);box-shadow:0 0 0 3px rgba(99,139,255,0.15);}
.bt-input[type="number"]{-moz-appearance:textfield;padding-right:8px;}
.bt-input[type="number"]::-webkit-outer-spin-button,.bt-input[type="number"]::-webkit-inner-spin-button{-webkit-appearance:none;margin:0;}
.bt-field{display:flex;flex-direction:column;gap:6px;position:relative;}
.bt-field .num-wrap{position:relative;display:flex;align-items:center;}
.bt-field .num-wrap input{width:100%;padding-right:28px;}
.bt-field .num-btns{position:absolute;right:4px;display:flex;flex-direction:column;gap:2px;}
.bt-field .num-btn{width:20px;height:14px;background:linear-gradient(135deg,rgba(99,139,255,0.15),rgba(167,139,250,0.1));border:1px solid rgba(99,139,255,0.3);border-radius:4px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all 0.2s;}
.bt-field .num-btn:hover{background:linear-gradient(135deg,rgba(99,139,255,0.3),rgba(167,139,250,0.2));border-color:var(--accent-primary);transform:scale(1.1);}
.bt-field .num-btn:active{transform:scale(0.95);}
.bt-field .num-btn svg{width:10px;height:10px;stroke:var(--accent-primary);stroke-width:2.5;}
.bt-results{margin-top:24px;animation:fadeIn 0.4s ease;}
.bt-sym-check{display:flex;align-items:center;gap:6px;cursor:pointer;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border-subtle);border-radius:var(--radius-md);transition:var(--transition-base);font-size:13px;color:var(--text-secondary);}
.bt-sym-check:hover{border-color:var(--accent-primary);}
.bt-sym-check input{accent-color:var(--accent-primary);width:14px;height:14px;}
.bt-sym-check input:checked+span{color:var(--accent-primary);font-weight:600;}
@keyframes fadeIn{from{opacity:0;transform:translateY(10px);}to{opacity:1;transform:translateY(0);}}
.bt-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:20px;}
.sym-name{font-size:14px;font-weight:600;color:var(--text-primary);font-family:var(--font-mono);}
.sym-name.off{color:var(--text-muted);}
.csel{position:relative;width:120px;}.csel-btn{background:var(--bg-input);border:1px solid var(--border-subtle);border-radius:var(--radius-md);padding:8px 12px;font-size:13px;color:var(--text-secondary);cursor:pointer;display:flex;align-items:center;justify-content:space-between;gap:8px;transition:var(--transition-base);user-select:none;}.csel-btn:hover,.csel-btn.open{border-color:var(--accent-primary);color:var(--accent-primary);}.csel-btn.open{border-radius:var(--radius-md) var(--radius-md) 0 0;}.csel-arrow{font-size:10px;transition:transform 0.3s;}.csel-btn.open .csel-arrow{transform:rotate(180deg);}.csel-dd{position:absolute;top:100%;left:0;right:0;background:var(--bg-secondary);border:1px solid var(--accent-primary);border-top:none;border-radius:0 0 var(--radius-md) var(--radius-md);overflow:hidden;max-height:0;transition:max-height 0.3s cubic-bezier(0.4,0,0.2,1),opacity 0.2s;opacity:0;z-index:99;}.csel-dd.open{max-height:120px;opacity:1;}.csel-opt{padding:10px 14px;font-size:13px;color:var(--text-secondary);cursor:pointer;transition:var(--transition-fast);}.csel-opt:hover{background:rgba(99,139,255,0.1);color:var(--accent-primary);}.csel-opt.sel{color:var(--accent-primary);font-weight:600;background:rgba(99,139,255,0.15);}
.val-cell{display:flex;align-items:center;gap:6px;}
.num-wrap{position:relative;display:inline-flex;align-items:center;}
.num-wrap input[type="number"]{-moz-appearance:textfield;}
.num-wrap input[type="number"]::-webkit-outer-spin-button,.num-wrap input[type="number"]::-webkit-inner-spin-button{-webkit-appearance:none;margin:0;}
.num-wrap .num-btns{position:absolute;right:4px;display:flex;flex-direction:column;gap:2px;}
.num-wrap .num-btn{width:20px;height:14px;background:linear-gradient(135deg,rgba(99,139,255,0.15),rgba(167,139,250,0.1));border:1px solid rgba(99,139,255,0.3);border-radius:4px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all 0.2s;}
.num-wrap .num-btn:hover{background:linear-gradient(135deg,rgba(99,139,255,0.3),rgba(167,139,250,0.2));border-color:var(--accent-primary);transform:scale(1.1);}
.num-wrap .num-btn:active{transform:scale(0.95);}
.num-wrap .num-btn svg{width:10px;height:10px;stroke:var(--accent-primary);stroke-width:2.5;fill:none;}
.val-input{background:var(--bg-input);border:1px solid var(--border-subtle);border-radius:var(--radius-sm);padding:8px 10px;padding-right:24px;font-size:14px;color:var(--text-primary);width:90px;outline:none;font-family:var(--font-mono);transition:var(--transition-base);-webkit-user-select:text;user-select:text;-moz-appearance:textfield;}.val-input::-webkit-outer-spin-button,.val-input::-webkit-inner-spin-button{-webkit-appearance:none;margin:0;}.val-input:focus{border-color:var(--accent-primary);box-shadow:0 0 0 3px rgba(99,139,255,0.15);}
.val-lbl{font-size:13px;color:var(--text-muted);font-weight:600;min-width:24px;}.val-lbl.pct{color:var(--accent-primary);}
.calc-cell{background:var(--bg-input);border:1px solid var(--border-subtle);border-radius:var(--radius-sm);padding:8px 12px;font-size:13px;color:var(--text-muted);font-family:var(--font-mono);text-align:center;transition:var(--transition-base);}.calc-cell.risk{border-color:rgba(99,139,255,0.3);color:var(--accent-primary);font-weight:500;}
.btn-rm{background:transparent;border:none;color:var(--text-muted);cursor:pointer;font-size:18px;padding:6px 10px;border-radius:var(--radius-sm);transition:var(--transition-base);}.btn-rm:hover{color:var(--accent-danger);background:rgba(248,113,113,0.1);}
.legend{margin-top:18px;padding:16px 20px;background:var(--bg-input);border-radius:var(--radius-md);border-left:3px solid var(--accent-primary);font-size:13px;color:var(--text-muted);line-height:2;}
.log-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;}.log-title{font-size:18px;font-weight:700;color:var(--text-primary);}
.log-box{background:var(--bg-input);border:1px solid var(--border-subtle);border-radius:var(--radius-lg);padding:20px;height:calc(100vh - 280px);overflow-y:auto;font-family:var(--font-mono);font-size:13px;line-height:2;scrollbar-width:thin;-webkit-user-select:text;user-select:text;}
.log-ts{color:var(--text-muted);margin-right:10px;opacity:0.6;}.log-info{color:var(--text-muted);}.log-warn{color:#fbbf24;}.log-error{color:var(--accent-danger);}.log-trade{color:var(--accent-success);font-weight:600;}
.bottom-bar{background:var(--bg-card);backdrop-filter:blur(16px);border-top:1px solid var(--border-subtle);padding:16px 28px;display:flex;align-items:center;gap:12px;flex-shrink:0;}
.btn-start{background:var(--accent-primary);border:none;border-radius:var(--radius-md);padding:14px 32px;font-size:15px;font-weight:700;color:#fff;cursor:pointer;transition:var(--transition-base);position:relative;overflow:hidden;}.btn-start:hover{transform:translateY(-2px);box-shadow:0 8px 32px var(--glow-primary);}.btn-start:disabled{opacity:0.4;cursor:not-allowed;transform:none;box-shadow:none;}
.btn-stop{background:transparent;border:1px solid var(--accent-danger);border-radius:var(--radius-md);padding:14px 32px;font-size:15px;font-weight:700;color:var(--accent-danger);cursor:pointer;transition:var(--transition-base);}.btn-stop:hover{background:rgba(248,113,113,0.1);}.btn-stop:disabled{opacity:0.4;cursor:not-allowed;}
.spacer{flex:1;}.save-fb{font-size:14px;font-weight:600;color:var(--accent-success);opacity:0;transition:opacity 0.3s;}.save-fb.show{opacity:1;}
.btn-save{background:var(--bg-input);border:1px solid var(--border-subtle);border-radius:var(--radius-md);padding:14px 24px;font-size:14px;font-weight:600;color:var(--text-secondary);cursor:pointer;transition:var(--transition-base);}.btn-save:hover{border-color:var(--accent-primary);color:var(--accent-primary);background:rgba(99,139,255,0.1);}
.guide-step{display:flex;gap:18px;margin-bottom:24px;align-items:flex-start;}.guide-num{min-width:32px;height:32px;border-radius:50%;background:var(--accent-gradient);display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:700;color:#fff;flex-shrink:0;margin-top:2px;box-shadow:0 4px 12px var(--glow-primary);}.guide-title{font-size:15px;font-weight:700;color:var(--text-primary);margin-bottom:8px;}.guide-body{font-size:14px;color:var(--text-secondary);line-height:1.8;}.guide-body strong{color:var(--text-primary);}.guide-body code{background:var(--bg-input);border:1px solid var(--border-subtle);border-radius:var(--radius-sm);padding:2px 8px;font-family:var(--font-mono);font-size:13px;color:var(--accent-primary);}.guide-warn{background:rgba(251,191,36,0.1);border:1px solid rgba(251,191,36,0.2);border-left:3px solid #fbbf24;border-radius:var(--radius-md);padding:14px 18px;font-size:14px;color:var(--text-secondary);margin-top:12px;line-height:1.7;}
.req-card{background:linear-gradient(135deg,rgba(248,113,113,0.08),rgba(251,191,36,0.05));border:1px solid rgba(248,113,113,0.2);}.req-card .card-title{display:flex;align-items:center;gap:12px;}.req-icon{width:28px;height:28px;background:linear-gradient(135deg,#f87171,#fbbf24);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:800;color:#fff;box-shadow:0 4px 15px rgba(248,113,113,0.4);animation:pulse-warn 2s infinite;}.req-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:20px 0;}.req-item{background:var(--bg-card);border:1px solid var(--border-subtle);border-radius:var(--radius-md);padding:20px;transition:var(--transition-base);}.req-item:hover{border-color:var(--accent-primary);transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,0,0,0.2);}.req-header{display:flex;align-items:center;gap:12px;margin-bottom:14px;font-size:16px;font-weight:700;color:var(--text-primary);}.req-header svg{width:24px;height:24px;stroke:var(--accent-primary);}.req-body{font-size:14px;color:var(--text-secondary);line-height:1.8;}.req-body strong{color:var(--accent-success);}.req-link{display:inline-flex;align-items:center;gap:6px;color:var(--accent-primary);font-weight:600;text-decoration:none;transition:var(--transition-fast);}.req-link:hover{color:#fff;text-shadow:0 0 10px var(--accent-primary);}.req-warn{display:flex;align-items:center;gap:12px;background:rgba(251,191,36,0.1);border:1px solid rgba(251,191,36,0.25);border-radius:var(--radius-md);padding:14px 18px;font-size:13px;color:#fbbf24;}.req-warn svg{width:20px;height:20px;stroke:#fbbf24;flex-shrink:0;}@keyframes pulse-warn{0%,100%{box-shadow:0 4px 15px rgba(248,113,113,0.4);}50%{box-shadow:0 4px 25px rgba(248,113,113,0.7);}}
.btn-tg{background:linear-gradient(135deg,#0088cc,#00bbff);border:none;border-radius:var(--radius-md);padding:12px 24px;font-size:14px;font-weight:700;color:#fff;cursor:pointer;margin-top:14px;transition:var(--transition-base);display:inline-flex;align-items:center;gap:10px;}.btn-tg:hover{transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,136,204,0.4);}
.equity-box{display:none;align-items:center;gap:20px;background:linear-gradient(135deg,rgba(99,139,255,0.08),rgba(167,139,250,0.04));border:1px solid rgba(99,139,255,0.15);border-radius:var(--radius-md);padding:10px 18px;margin-right:12px;transition:var(--transition-base);}.equity-box:hover{border-color:rgba(99,139,255,0.3);box-shadow:0 4px 20px rgba(99,139,255,0.1);}.equity-box.show{display:flex;}.equity-label{font-size:9px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.12em;margin-bottom:2px;}.equity-val{font-size:15px;font-weight:700;color:var(--text-primary);font-family:var(--font-mono);}.equity-change{font-size:13px;font-weight:700;padding:4px 10px;border-radius:20px;}.equity-change.pos{color:var(--accent-success);background:rgba(52,211,153,0.12);}.equity-change.neg{color:var(--accent-danger);background:rgba(248,113,113,0.12);}
.update-overlay{display:none;position:fixed;inset:0;background:rgba(6,8,13,0.9);backdrop-filter:blur(8px);z-index:999;align-items:center;justify-content:center;}.update-overlay.show{display:flex;}.update-box{background:var(--bg-card);backdrop-filter:blur(20px);border:1px solid var(--border-hover);border-radius:var(--radius-xl);padding:40px;width:440px;text-align:center;box-shadow:0 24px 64px rgba(0,0,0,0.5);}.update-icon{font-size:48px;margin-bottom:16px;}.update-title{font-size:20px;font-weight:700;color:var(--text-primary);margin-bottom:10px;}.update-ver{font-size:14px;color:var(--accent-primary);margin-bottom:10px;font-family:var(--font-mono);}.update-note{font-size:14px;color:var(--text-secondary);margin-bottom:28px;line-height:1.7;}.update-progress{display:none;background:var(--bg-input);border-radius:var(--radius-sm);height:8px;margin-bottom:20px;overflow:hidden;}.update-progress-bar{height:100%;background:var(--accent-gradient);border-radius:var(--radius-sm);width:0%;transition:width 0.3s;}.update-btns{display:flex;gap:14px;justify-content:center;}.btn-update-now{background:var(--accent-primary);border:none;border-radius:var(--radius-md);padding:14px 32px;font-size:14px;font-weight:700;color:#fff;cursor:pointer;transition:var(--transition-base);}.btn-update-now:hover{transform:translateY(-2px);box-shadow:0 8px 24px var(--glow-primary);}.btn-update-later{background:transparent;border:1px solid var(--border-subtle);border-radius:var(--radius-md);padding:14px 28px;font-size:14px;font-weight:600;color:var(--text-secondary);cursor:pointer;transition:var(--transition-base);}.btn-update-later:hover{border-color:var(--accent-primary);color:var(--text-primary);}
.titlebar{height:36px;background:var(--bg-primary);display:flex;align-items:center;justify-content:space-between;padding:0 14px 0 18px;flex-shrink:0;-webkit-app-region:drag;app-region:drag;user-select:none;border-bottom:1px solid var(--border-subtle);}.titlebar-left{display:flex;align-items:center;gap:10px;}.titlebar-icon{width:16px;height:16px;border-radius:50%;background:var(--accent-gradient);box-shadow:0 0 8px var(--glow-primary);}.titlebar-title{font-size:12px;color:var(--text-muted);font-weight:500;letter-spacing:0.02em;}.titlebar-btns{display:flex;gap:6px;-webkit-app-region:no-drag;app-region:no-drag;}.titlebar-btn{width:32px;height:24px;border:none;border-radius:var(--radius-sm);cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:12px;transition:var(--transition-fast);background:transparent;}.tb-min{color:var(--text-muted);}.tb-min:hover{background:rgba(255,255,255,0.06);color:var(--text-primary);}.tb-max{color:var(--text-muted);font-size:10px;}.tb-max:hover{background:rgba(255,255,255,0.06);color:var(--text-primary);}.tb-close{color:var(--text-muted);}.tb-close:hover{background:var(--accent-danger);color:#fff;}
.dash-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:16px;}.stat-card{background:linear-gradient(145deg,rgba(12,16,24,0.9),rgba(16,22,36,0.95));backdrop-filter:blur(16px);border:1px solid rgba(255,255,255,0.05);border-radius:var(--radius-lg);padding:20px 22px;transition:var(--transition-base);position:relative;overflow:hidden;}.stat-card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(99,139,255,0.3),transparent);}.stat-card:hover{border-color:rgba(99,139,255,0.25);transform:translateY(-2px);box-shadow:0 8px 32px rgba(99,139,255,0.06);}.stat-label{font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;}.stat-value{font-size:26px;font-weight:700;color:var(--text-primary);font-family:var(--font-mono);}.stat-value.pos{color:var(--accent-success);text-shadow:0 0 20px rgba(52,211,153,0.3);}.stat-value.neg{color:var(--accent-danger);text-shadow:0 0 20px rgba(248,113,113,0.3);}.stat-value.blue{color:var(--accent-primary);text-shadow:0 0 20px rgba(99,139,255,0.3);}.stat-sub{font-size:13px;color:var(--text-muted);margin-top:6px;}
.dash-row{display:grid;grid-template-columns:1fr 1fr;gap:16px;height:calc(100vh - 330px);}.chart-card{background:linear-gradient(145deg,rgba(12,16,24,0.9) 0%,rgba(16,22,36,0.95) 100%);backdrop-filter:blur(20px);border:1px solid rgba(99,139,255,0.12);border-radius:var(--radius-lg);padding:22px;display:flex;flex-direction:column;transition:var(--transition-base);position:relative;overflow:hidden;}.chart-card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(99,139,255,0.4),rgba(167,139,250,0.3),transparent);}.chart-card::after{content:'';position:absolute;inset:0;background:radial-gradient(ellipse at 50% 0%,rgba(99,139,255,0.04) 0%,transparent 70%);pointer-events:none;}.chart-card:hover{border-color:rgba(99,139,255,0.3);box-shadow:0 0 40px rgba(99,139,255,0.06),inset 0 0 60px rgba(99,139,255,0.02);}.chart-title{font-size:15px;font-weight:700;color:var(--text-primary);margin-bottom:18px;display:flex;align-items:center;gap:10px;position:relative;z-index:1;}.chart-wrap{position:relative;flex:1;z-index:1;}
.trades-card{background:var(--bg-card);backdrop-filter:blur(16px);border:1px solid var(--border-subtle);border-radius:var(--radius-lg);padding:22px;overflow:hidden;display:flex;flex-direction:column;}.trades-scroll{overflow-y:auto;flex:1;max-height:200px;scrollbar-width:thin;}.trades-scroll::-webkit-scrollbar{width:6px;}.trades-scroll::-webkit-scrollbar-thumb{background:var(--accent-primary);border-radius:6px;}
.trade-row{display:grid;grid-template-columns:80px 100px 1fr 70px 80px;gap:10px;align-items:center;padding:10px 12px;border-radius:var(--radius-sm);margin-bottom:4px;font-size:13px;transition:var(--transition-fast);}.trade-row:hover{background:rgba(255,255,255,0.02);}.trade-row.hdr{background:var(--bg-input);color:var(--text-muted);font-weight:700;text-transform:uppercase;letter-spacing:0.08em;font-size:11px;}.trade-row.even{background:var(--bg-input);}.trade-side{font-weight:700;font-size:13px;font-family:var(--font-mono);}.trade-side.buy{color:var(--accent-success);}.trade-side.sell{color:var(--accent-danger);}.trade-pnl{font-family:var(--font-mono);}.trade-pnl.pos{color:var(--accent-success);font-weight:600;}.trade-pnl.neg{color:var(--accent-danger);font-weight:600;}.no-trades{text-align:center;color:var(--text-muted);font-size:14px;padding:40px 0;}
.lang-sel{display:flex;align-items:center;gap:6px;margin-right:14px;}.lang-btn{background:none;border:none;color:var(--text-muted);font-size:12px;font-weight:600;cursor:pointer;padding:4px 8px;transition:var(--transition-fast);font-family:var(--font-sans);}.lang-btn:hover{color:var(--text-secondary);}.lang-btn.active{color:var(--accent-primary);}.lang-div{color:var(--text-muted);font-size:12px;}
</style>
</head>
<body>
<div class="update-overlay" id="update-overlay"><div class="update-box"><div class="update-icon">&#x1F4E6;</div><div class="update-title">Aggiornamento disponibile!</div><div class="update-ver" id="update-ver">Versione 1.0.0 → 1.1.0</div><div class="update-note" id="update-note"></div><div class="update-progress" id="update-progress"><div class="update-progress-bar" id="update-bar"></div></div><div class="update-btns"><button class="btn-update-now" id="btn-update-now" onclick="doUpdate()">&#x21E9; Aggiorna ora</button><button class="btn-update-later" onclick="document.getElementById('update-overlay').classList.remove('show')">Dopo</button></div></div></div>
<div class="titlebar" id="titlebar"><div class="titlebar-left"><div class="titlebar-icon"></div><span class="titlebar-title">VaultSystemFx</span></div><div class="titlebar-btns"><button class="titlebar-btn tb-min" onclick="minimizeWin()" title="Minimizza"><svg width="10" height="2" viewBox="0 0 10 2"><rect fill="currentColor" width="10" height="2" rx="1"/></svg></button><button class="titlebar-btn tb-max" onclick="toggleMaxWin()" title="Massimizza"><svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="1" y="1" width="8" height="8" rx="1.5"/></svg></button><button class="titlebar-btn tb-close" onclick="closeWin()" title="Chiudi"><svg width="10" height="10" viewBox="0 0 10 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><line x1="1" y1="1" x2="9" y2="9"/><line x1="9" y1="1" x2="1" y2="9"/></svg></button></div></div>
<div class="header"><div class="header-left"><div id="logo-wrap"></div><div class="title-block"><h1>VaultSystemFx</h1><p>Automated Trading System</p></div></div><div style="display:flex;align-items:center;"><div class="equity-box" id="equity-box"><div style="text-align:center;"><div class="equity-label">Equity</div><div class="equity-val" id="equity-val">—</div></div><div style="width:1px;height:24px;background:linear-gradient(180deg,transparent,rgba(99,139,255,0.3),transparent);margin:0 4px;"></div><div style="text-align:center;"><div class="equity-label">Balance</div><div class="equity-val" id="balance-val">—</div></div><div id="equity-change" class="equity-change"></div></div><div class="session-box" id="session-box"><div class="session-icon"><svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg></div><div class="session-info"><span class="session-label">Sessione</span><div class="session-times"><input type="time" id="session_start" value="07:00" class="session-time-input"><span class="session-sep">→</span><input type="time" id="session_end" value="19:30" class="session-time-input"></div></div><span class="session-status disabled" id="session-status">OFF</span></div><div class="lang-sel"><button class="lang-btn active" onclick="setLang('it')">ITA</button><span class="lang-div">|</span><button class="lang-btn" onclick="setLang('en')">ENG</button></div><div class="status-pill" id="status-pill"><div class="status-dot"></div><span id="status-text">Fermo</span></div></div></div>
<div class="accent-line"></div>
<div class="tabs-bar">
  <button class="tab-btn active" id="tbdash" onclick="switchTab('dashboard','tbdash')"><span class="icon icon-dashboard"></span>Dashboard</button>
  <button class="tab-btn" id="tbmt5" onclick="switchTab('mt5','tbmt5')"><span class="icon icon-mt5"></span>Account MT5</button>
  <button class="tab-btn" id="tbsym" onclick="switchTab('symbols','tbsym')"><span class="icon icon-symbols"></span>Simboli</button>
  <button class="tab-btn" id="tblog" onclick="switchTab('log','tblog')"><span class="icon icon-log"></span>Log</button>
  <button class="tab-btn" id="tbguide" onclick="switchTab('guide','tbguide')"><span class="icon icon-guide"></span>Guida</button>
  <button class="tab-btn" id="tbtg" onclick="switchTab('telegram','tbtg')"><span class="icon icon-telegram"></span>Telegram</button>
  <button class="tab-btn" id="tbbt" onclick="switchTab('backtest','tbbt')"><span class="icon icon-backtest"></span>Backtest</button>
</div>
<div class="content">
  <div class="tab-panel active" id="tab-dashboard">
    <div class="dash-grid"><div class="stat-card"><div class="stat-label">Equity</div><div class="stat-value blue" id="d-equity">—</div><div class="stat-sub" id="d-balance">Balance: —</div></div><div class="stat-card"><div class="stat-label">Profitto Aperto</div><div class="stat-value" id="d-profit">—</div><div class="stat-sub" id="d-trades-open">Posizioni: 0</div></div><div class="stat-card"><div class="stat-label">Win Rate</div><div class="stat-value" id="d-winrate">—</div><div class="stat-sub" id="d-wl">Win: 0 | Loss: 0</div></div><div class="stat-card"><div class="stat-label">Profit Factor</div><div class="stat-value" id="d-pf">—</div><div class="stat-sub" id="d-dd">Drawdown: —</div></div></div>
    <div class="dash-row"><div class="chart-card"><div class="chart-title"><span class="icon icon-chart"></span>Curva Equity</div><div class="chart-wrap"><canvas id="equity-chart"></canvas></div></div><div class="trades-card"><div class="chart-title"><span class="icon icon-list"></span>Ultimi Trade</div><div class="trade-row hdr"><span>Ora</span><span>Simbolo</span><span>Tipo</span><span>Lotto</span><span>P&amp;L</span></div><div class="trades-scroll"><div id="trades-list"><div class="no-trades">Nessun trade ancora</div></div></div></div></div>
  </div>
  <div class="tab-panel" id="tab-mt5"><div class="card"><div class="card-title">Connessione MetaTrader 5</div><div class="card-sub">Percorso del terminale e credenziali dell'account</div><div class="form-row with-btn"><label>Percorso terminal64.exe</label><input type="text" id="mt5_path" placeholder="C:/Program Files/.../terminal64.exe"><button class="btn-icon" id="browse-btn">...</button></div><div class="form-row"><label>Login (numero)</label><input type="text" id="mt5_login" placeholder="123456789"></div><div class="form-row"><label>Password</label><input type="password" id="mt5_password" placeholder=""></div><div class="form-row"><label>Server</label><input type="text" id="mt5_server" placeholder="BrokerName-Live"></div></div></div>
  <div class="tab-panel" id="tab-symbols"><div class="card"><div class="card-title" style="display:flex;justify-content:space-between;align-items:center;"><span>Simboli e dimensione lotto</span><div style="display:flex;gap:16px;align-items:center;"><div class="be-toggle-wrap"><div class="be-info-icon">i<div class="be-tooltip"><strong>Break Even Automatico</strong><br><br>Quando attivo, lo SL viene spostato automaticamente a Break Even (+ qualche pip di profit) quando il trade raggiunge <strong>+20 pips</strong> di profitto.<br><br>Il BE non viene messo esattamente all'entrata, ma leggermente in positivo per garantire un minimo guadagno anche se il prezzo torna indietro.</div></div><label class="toggle" style="margin:0;"><input type="checkbox" id="be_enabled"><div class="toggle-bg"></div><div class="toggle-knob"></div></label><span class="be-toggle-label">BE Auto</span></div><div class="be-toggle-wrap"><div class="be-info-icon">i<div class="be-tooltip" id="daily-loss-tooltip"><strong>Stop Giornaliero</strong><br><br>Quando attivo, se la perdita giornaliera raggiunge il valore impostato in euro, il bot smette di operare per il resto della giornata.<br><br>Il controllo viene fatto confrontando il balance attuale con quello di inizio giornata.</div></div><label class="toggle" style="margin:0;"><input type="checkbox" id="daily_loss_enabled"><div class="toggle-bg"></div><div class="toggle-knob"></div></label><span class="be-toggle-label daily-loss-label">Stop</span><div class="num-wrap" style="margin-left:6px;"><input type="number" id="daily_loss_amount" value="300" min="10" max="100000" step="10" style="width:70px;padding:4px 6px;padding-right:22px;border-radius:6px;border:1px solid var(--border-subtle);background:var(--bg-card);color:var(--text-primary);font-size:12px;text-align:center;"><div class="num-btns" style="right:2px;gap:1px;"><div class="num-btn" data-target="daily_loss_amount" data-delta="10" style="width:16px;height:10px;"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" style="width:8px;height:8px;"><path d="M18 15l-6-6-6 6"/></svg></div><div class="num-btn" data-target="daily_loss_amount" data-delta="-10" style="width:16px;height:10px;"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" style="width:8px;height:8px;"><path d="M6 9l6 6 6-6"/></svg></div></div></div><span style="color:var(--text-muted);font-size:12px;margin-left:2px;">€</span></div></div></div><div class="card-sub">Lotti fissi oppure rischio % automatico per ogni simbolo</div><div class="capital-box"><span class="capital-label">&#x1F4B0; Capitale Live</span><div style="display:flex;flex-direction:column;gap:2px;"><span id="cap-equity-val" style="font-size:15px;font-weight:700;color:#638bff;font-family:Consolas,monospace;">— Non connesso</span><span style="font-size:16px;color:#4a5568;">Equity live da MT5 — aggiornata ogni 3s</span></div><div id="cap-profit" style="font-size:15px;font-weight:700;"></div></div><div class="add-row"><input class="add-input" id="new_sym" type="text" placeholder="SIMBOLO"><input class="add-input" id="new_val" type="number" value="0.07" step="0.01" min="0.01" style="width:80px;"><button class="btn-add" id="add-btn">+ Aggiungi</button></div><div class="sym-header"><span>ON</span><span>Simbolo</span><span>Modalita</span><span>Valore</span><span>Lotto</span><span></span></div><div id="sym-list"></div><div class="legend"><span style="color:#638bff;font-weight:600;">Rischio %</span> - lotto auto: Capitale x % / (ATR x pip value)<br><span style="color:#7a8ba8;font-weight:600;">Fisso</span> - lotto manuale invariabile</div></div></div>
  <div class="tab-panel" id="tab-log"><div class="log-header"><span class="log-title">Log in tempo reale</span><button class="btn-save" id="clear-btn" style="padding:6px 14px;">Pulisci</button></div><div class="log-box" id="log-box"></div></div>
  <div class="tab-panel" id="tab-guide"><div class="card req-card"><div class="card-title"><span class="req-icon">!</span> Requisiti Obbligatori</div><div class="card-sub">Prima di iniziare, assicurati di avere questi requisiti</div><div class="req-grid"><div class="req-item"><div class="req-header"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg><span>Account FPG</span></div><div class="req-body">Crea un account sul broker <strong>FPG (Fortune Prime Global)</strong>. La registrazione e completamente <strong>GRATUITA</strong>.<br><br><a href="https://portal.fortuneprime.com/getview?view=register&token=0pSM1g" target="_blank" class="req-link">Registrati su FPG &rarr;</a></div></div><div class="req-item"><div class="req-header"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg><span>VPS Windows 11</span></div><div class="req-body">Acquista una VPS con <strong>Windows 11</strong> per far girare il bot 24/7. La piu economica e <strong>Contabo</strong>.<br><br><a href="https://contabo.com/en/vps/cloud-vps-10/?image=windows-server.308&qty=1&contract=12&storage-type=cloud-vps-10-150-gb-ssd" target="_blank" class="req-link">Vai su Contabo &rarr;</a></div></div></div><div class="req-warn"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg><span>Il bot funziona SOLO su Windows. La VPS deve rimanere sempre accesa per operare 24/7.</span></div></div><div class="card"><div class="card-title">&#x1F4CB; Come impostare i Simboli e Lotti</div><div class="card-sub">Segui questi passi per configurare correttamente i simboli</div><div class="guide-step"><div class="guide-num">1</div><div class="guide-text"><div class="guide-title">Trova i simboli del tuo broker</div><div class="guide-body">Apri MetaTrader 5 e vai su <strong>Visualizza &rarr; Simboli</strong> (CTRL+U). Cerca i simboli che vuoi tradare. Il nome esatto potrebbe avere un suffisso come <code>-P</code>, <code>m</code>, o un punto — esempio: <code>EURUSD-P</code>, <code>EURUSDm</code>, <code>EURUSD.</code></div></div></div><div class="guide-step"><div class="guide-num">2</div><div class="guide-text"><div class="guide-title">Aggiungi un simbolo</div><div class="guide-body">Nel tab <strong>Simboli &amp; Lotti</strong>, scrivi il nome esatto del simbolo nel campo di testo (es. <code>EURUSD-P</code>) e clicca <strong>+ Aggiungi</strong>. Il simbolo appare nella lista.</div></div></div><div class="guide-step"><div class="guide-num">3</div><div class="guide-text"><div class="guide-title">Abilita o disabilita un simbolo</div><div class="guide-body">Usa il <strong>toggle</strong> a sinistra di ogni simbolo per attivarlo o disattivarlo. Il bot opera solo sui simboli con toggle attivo (blu).</div></div></div><div class="guide-step"><div class="guide-num">4</div><div class="guide-text"><div class="guide-title">Imposta il lotto</div><div class="guide-body">Scegli la modalit&agrave; <strong>Fisso</strong> e inserisci il lotto manualmente (es. <code>0.07</code>). Oppure usa <strong>Rischio %</strong> per il calcolo automatico — vedi la sezione qui sotto.</div></div></div><div class="guide-step"><div class="guide-num">5</div><div class="guide-text"><div class="guide-title">Salva le impostazioni</div><div class="guide-body">Clicca sempre <strong>Salva</strong> in basso a destra dopo ogni modifica. Le impostazioni vengono salvate automaticamente anche quando clicchi <strong>Avvia Bot</strong>.</div></div></div></div><div class="card"><div class="card-title">&#x1F4B0; Come funziona il Rischio %</div><div class="card-sub">Il bot calcola il lotto automaticamente in base al tuo capitale</div><div class="guide-step"><div class="guide-num">1</div><div class="guide-text"><div class="guide-title">Inserisci il capitale del tuo account</div><div class="guide-body">Nel tab <strong>Simboli &amp; Lotti</strong>, inserisci il saldo attuale del tuo conto MT5 nel campo <strong>Capitale Account</strong> (es. <code>10000</code> per $10.000). Questo valore &egrave; la base per il calcolo del rischio.</div></div></div><div class="guide-step"><div class="guide-num">2</div><div class="guide-text"><div class="guide-title">Seleziona modalit&agrave; Rischio %</div><div class="guide-body">Per ogni simbolo, apri il menu a tendina e scegli <strong>Rischio %</strong>. Inserisci la percentuale che vuoi rischiare per ogni trade — ad esempio <code>1.0</code> significa rischiare l'1% del capitale per ogni operazione.</div></div></div><div class="guide-step"><div class="guide-num">3</div><div class="guide-text"><div class="guide-title">Il lotto viene calcolato automaticamente</div><div class="guide-body">La formula usata &egrave;: <code>Capitale &times; % &divide; (ATR &times; Pip Value)</code>. Il lotto viene calcolato in <strong>tempo reale</strong> ad ogni trade in base all'ATR del momento — per questo nella colonna vedi <code>live</code> invece di un numero fisso.</div></div></div><div class="guide-step"><div class="guide-num">4</div><div class="guide-text"><div class="guide-title">Consiglio sul rischio</div><div class="guide-body">Si consiglia di impostare un rischio tra <strong>0.5% e 2%</strong> per trade. Un rischio superiore al 3% per trade &egrave; considerato elevato e pu&ograve; portare a perdite significative in caso di serie negative.</div></div></div><div class="guide-warn">&#x26A0; Il capitale inserito &egrave; solo indicativo per il calcolo del lotto. Aggiornalo manualmente quando il saldo del tuo conto cambia significativamente.</div></div></div>
  <div class="tab-panel" id="tab-telegram"><div class="card"><div class="card-title">&#x1F4F1; Notifiche Telegram</div><div class="card-sub">Ricevi un messaggio su ogni trade, avvio e stop del bot</div><div class="guide-step"><div class="guide-num">1</div><div class="guide-text"><div class="guide-title">Connetti il bot Telegram</div><div class="guide-body">Clicca il bottone qui sotto per aprire <strong>@getidsbot</strong> su Telegram. Clicca <strong>Start</strong> — ti risponde automaticamente con il tuo Chat ID.</div><button class="btn-tg" onclick="openTelegram()">&#x1F4AC; Ottieni il mio Chat ID</button></div></div><div class="guide-step"><div class="guide-num">2</div><div class="guide-text"><div class="guide-title">Inserisci il tuo Chat ID</div><div class="guide-body">Copia il numero che ti ha mandato il bot e incollalo qui sotto.</div><div style="display:flex;gap:10px;margin-top:10px;align-items:center;"><input type="text" id="tg_chat_id" placeholder="Es. 123456789" style="width:200px;-webkit-user-select:text;user-select:text;"><button class="btn-add" onclick="testTelegram()" id="tg-test-btn">&#x2713; Testa notifica</button></div><div id="tg-feedback" style="font-size:16px;margin-top:8px;color:#4a5568;"></div></div></div><div class="guide-step"><div class="guide-num">3</div><div class="guide-text"><div class="guide-title">Token del bot (solo se usi un bot diverso)</div><div class="guide-body">Se stai usando <strong>@VaultSystemFx_bot</strong> lascia questo campo vuoto. Inserisci un token solo se hai un bot Telegram personale.</div><input type="text" id="tg_token" placeholder="Lascia vuoto per usare @VaultSystemFx_bot" style="width:100%;margin-top:10px;-webkit-user-select:text;user-select:text;"></div></div><div style="background:#0a0e17;border:1px solid #0a0e17;border-radius:10px;padding:16px;margin-top:8px;"><div style="font-size:16px;font-weight:700;color:#f4f7ff;margin-bottom:12px;">Notifiche attive</div><div style="display:flex;flex-direction:column;gap:10px;"><label style="display:flex;align-items:center;gap:10px;cursor:pointer;"><input type="checkbox" id="tg_notify_trade" checked style="accent-color:#638bff;width:14px;height:14px;"><span style="font-size:16px;color:#7a8ba8;">Trade aperti (BUY/SELL con prezzo, SL, TP)</span></label><label style="display:flex;align-items:center;gap:10px;cursor:pointer;"><input type="checkbox" id="tg_notify_start" checked style="accent-color:#638bff;width:14px;height:14px;"><span style="font-size:16px;color:#7a8ba8;">Avvio e stop del bot</span></label><label style="display:flex;align-items:center;gap:10px;cursor:pointer;"><input type="checkbox" id="tg_notify_error" checked style="accent-color:#638bff;width:14px;height:14px;"><span style="font-size:16px;color:#7a8ba8;">Errori di connessione MT5</span></label></div></div></div></div>
  <div class="tab-panel" id="tab-backtest">
    <div class="card">
      <div class="card-title"><span class="icon icon-backtest"></span>Backtest Strategia</div>
      <div class="card-sub">Testa la strategia sui dati storici per vedere le performance</div>
      <div class="bt-config">
        <div class="bt-field" style="margin-bottom:16px;"><label>Simboli (seleziona uno o piu)</label>
          <div style="display:flex;flex-wrap:wrap;gap:12px;margin-top:8px;" id="bt-symbols-wrap">
            <label class="bt-sym-check"><input type="checkbox" value="EURUSD-P" checked><span>EURUSD-P</span></label>
            <label class="bt-sym-check"><input type="checkbox" value="GBPUSD-P"><span>GBPUSD-P</span></label>
            <label class="bt-sym-check"><input type="checkbox" value="USDJPY-P"><span>USDJPY-P</span></label>
            <label class="bt-sym-check"><input type="checkbox" value="USDCAD-P"><span>USDCAD-P</span></label>
            <label class="bt-sym-check"><input type="checkbox" value="GBPJPY-P"><span>GBPJPY-P</span></label>
            <label class="bt-sym-check"><input type="checkbox" value="EURJPY-P"><span>EURJPY-P</span></label>
            <label class="bt-sym-check"><input type="checkbox" value="EURGBP-P"><span>EURGBP-P</span></label>
            <label class="bt-sym-check"><input type="checkbox" value="XAUUSD-P"><span>XAUUSD-P</span></label>
          </div>
        </div>
        <div class="bt-field" style="margin-bottom:16px;"><label>Simboli custom (separati da virgola)</label><input type="text" id="bt-symbol-custom" class="bt-input" placeholder="es. AUDUSD-P, NZDUSD-P" style="width:300px;margin-top:6px;"></div>
        <div class="bt-row">
          <div class="bt-field"><label>Da</label><input type="date" id="bt-from" class="bt-input"></div>
          <div class="bt-field"><label>A</label><input type="date" id="bt-to" class="bt-input"></div>
          <div class="bt-field"><label>Modalità</label><div class="mode-sel" id="mode-sel"><div class="mode-btn" id="mode-btn" onclick="toggleModeDD()"><span id="mode-val">Lotto Fisso</span><svg class="mode-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M6 9l6 6 6-6"/></svg></div><div class="mode-dd" id="mode-dd"><div class="mode-opt sel" data-val="fixed" onclick="selectBtMode('fixed')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>Lotto Fisso</div><div class="mode-opt" data-val="risk" onclick="selectBtMode('risk')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>Rischio %</div></div></div><input type="hidden" id="bt-mode" value="fixed"></div>
          <div class="bt-field" id="bt-lot-wrap"><label>Lotto</label><div class="num-wrap"><input type="number" id="bt-lot" class="bt-input" value="0.1" step="0.01" min="0.01" style="width:90px;"><div class="num-btns"><div class="num-btn" onclick="stepNum('bt-lot',0.01)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M18 15l-6-6-6 6"/></svg></div><div class="num-btn" onclick="stepNum('bt-lot',-0.01)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M6 9l6 6 6-6"/></svg></div></div></div></div>
          <div class="bt-field" id="bt-risk-wrap" style="display:none;"><label>Rischio %</label><div class="num-wrap"><input type="number" id="bt-risk" class="bt-input" value="1" step="0.1" min="0.1" max="10" style="width:80px;"><div class="num-btns"><div class="num-btn" onclick="stepNum('bt-risk',0.1)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M18 15l-6-6-6 6"/></svg></div><div class="num-btn" onclick="stepNum('bt-risk',-0.1)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M6 9l6 6 6-6"/></svg></div></div></div></div>
          <div class="bt-field" id="bt-capital-wrap" style="display:none;"><label>Capitale</label><div class="num-wrap"><input type="number" id="bt-capital" class="bt-input" value="10000" step="100" min="100" style="width:110px;"><div class="num-btns"><div class="num-btn" onclick="stepNum('bt-capital',100)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M18 15l-6-6-6 6"/></svg></div><div class="num-btn" onclick="stepNum('bt-capital',-100)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M6 9l6 6 6-6"/></svg></div></div></div></div>
        </div>
        <div class="bt-row" style="margin-top:16px;">
          <button class="btn-add" id="bt-run" onclick="runBacktest()" style="padding:12px 28px;"><span class="icon icon-play" style="width:12px;height:12px;"></span>Avvia Backtest</button>
          <div id="bt-status" style="margin-left:16px;color:#7a8ba8;font-size:14px;"></div>
        </div>
      </div>
    </div>
    <div class="bt-results" id="bt-results" style="display:none;">
      <div class="dash-grid">
        <div class="stat-card"><div class="stat-label">Trade Totali</div><div class="stat-value blue" id="bt-total">—</div><div class="stat-sub" id="bt-period">Periodo: —</div></div>
        <div class="stat-card"><div class="stat-label">Win Rate</div><div class="stat-value" id="bt-winrate">—</div><div class="stat-sub" id="bt-wl">Win: 0 | Loss: 0</div></div>
        <div class="stat-card"><div class="stat-label">Profit Factor</div><div class="stat-value" id="bt-pf">—</div><div class="stat-sub" id="bt-expectancy">Expectancy: —</div></div>
        <div class="stat-card"><div class="stat-label">Profitto Netto</div><div class="stat-value" id="bt-profit">—</div><div class="stat-sub" id="bt-dd">Max Drawdown: —</div></div>
      </div>
      <div class="dash-row" style="margin-top:20px;">
        <div class="chart-card" style="flex:1;"><div class="chart-title"><span class="icon icon-chart"></span>Curva Equity Backtest</div><div class="chart-wrap"><canvas id="bt-chart"></canvas></div></div>
        <div class="trades-card" style="flex:1;max-width:520px;"><div class="chart-title"><span class="icon icon-list"></span>Dettaglio Trade</div><div class="trade-row hdr" style="grid-template-columns:60px 80px 60px 70px 70px 70px;"><span>Data</span><span>Simbolo</span><span>Tipo</span><span>Entry</span><span>Exit</span><span>P&amp;L</span></div><div class="trades-scroll" style="max-height:300px;"><div id="bt-trades"></div></div></div>
      </div>
    </div>
  </div>
</div>
<div class="bottom-bar"><button class="btn-start" id="btn-start"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style="margin-right:8px;"><polygon points="5 3 19 12 5 21 5 3"/></svg>AVVIA BOT</button><button class="btn-stop" id="btn-stop" disabled><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style="margin-right:8px;"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>FERMA</button><div class="spacer"></div><span class="save-fb" id="save-fb">Salvato</span><button class="btn-save" id="save-btn"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px;"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>Salva</button></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script>
var cfg={};var equityHistory=[];var equityChart=null;var tradeHistory=[];var symRows=[];var openDD=null;var rid=0;
function minimizeWin(){window.pywebview.api.minimize_window();}function toggleMaxWin(){window.pywebview.api.toggle_maximize();}function closeWin(){window.pywebview.api.close_window();}
var updateUrl='';function checkUpdate(){window.pywebview.api.check_update().then(function(raw){var data=JSON.parse(raw);if(!data)return;updateUrl=data.url;document.getElementById('update-ver').textContent='Versione attuale: 1.1.0  →  Nuova: '+data.version;document.getElementById('update-note').textContent=data.note||"Nuove funzionalita e miglioramenti.";document.getElementById('update-overlay').classList.add('show');});}
function doUpdate(){var btn=document.getElementById('btn-update-now');var prog=document.getElementById('update-progress');var bar=document.getElementById('update-bar');btn.disabled=true;btn.textContent='Download in corso...';prog.style.display='block';var pct=0;var iv=setInterval(function(){pct=Math.min(pct+2,90);bar.style.width=pct+'%';},200);window.pywebview.api.download_update(updateUrl).then(function(res){clearInterval(iv);if(res==='ok'){bar.style.width='100%';btn.innerHTML='&#10003; Riavvio in corso...';}else{btn.textContent='Errore — riprova';btn.disabled=false;}});}
document.getElementById('titlebar').addEventListener('dblclick',function(e){if(e.target.closest('.titlebar-btns'))return;toggleMaxWin();});
function switchTab(name,btnId){var panels=document.querySelectorAll('.tab-panel');for(var i=0;i<panels.length;i++)panels[i].classList.remove('active');var btns=document.querySelectorAll('.tab-btn');for(var i=0;i<btns.length;i++)btns[i].classList.remove('active');document.getElementById('tab-'+name).classList.add('active');document.getElementById(btnId).classList.add('active');}
function setStatus(text,state){var pill=document.getElementById('status-pill');pill.className='status-pill'+(state?' '+state:'');document.getElementById('status-text').textContent=text;}
function escHtml(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function calcLot(mode,val,capital){if(mode==='fixed')return parseFloat(val).toFixed(2);return'live';}
function getCapital(){return liveEquity>0?liveEquity:10000;}
function refreshAllCalc(){for(var i=0;i<symRows.length;i++){var r=symRows[i];var row=document.getElementById('row_'+r.id);if(!row)continue;var mode=row.getAttribute('data-mode');var val=row.querySelector('.val-input').value;var calc=row.querySelector('.calc-cell');if(mode==='risk'){calc.textContent='live';}}}
function makeSelectHTML(mode,id){var tr=T[curLang]||T['it'];var lbl=mode==='risk'?tr['mode-risk']:tr['legend2'];var fSel=mode==='fixed'?' sel':'';var rSel=mode==='risk'?' sel':'';var h='<div class="csel" id="cs_'+id+'">';h+='<div class="csel-btn" id="csb_'+id+'">';h+='<span id="sv_'+id+'">'+lbl+'</span>';h+='<span class="csel-arrow">&#9660;</span></div>';h+='<div class="csel-dd" id="dd_'+id+'">';h+='<div class="csel-opt'+fSel+'" id="opt_fixed_'+id+'">'+tr['legend2']+'</div>';h+='<div class="csel-opt'+rSel+'" id="opt_risk_'+id+'">'+tr['mode-risk']+'</div>';h+='</div></div>';return h;}
function toggleDD(id){if(openDD&&openDD!==id)closeDD(openDD);var dd=document.getElementById('dd_'+id);var btn=document.getElementById('csb_'+id);if(dd.classList.contains('open')){closeDD(id);}else{dd.classList.add('open');btn.classList.add('open');openDD=id;}}
function closeDD(id){var dd=document.getElementById('dd_'+id);var btn=document.getElementById('csb_'+id);if(dd)dd.classList.remove('open');if(btn)btn.classList.remove('open');if(openDD===id)openDD=null;}
function selectMode(id,mode){closeDD(id);var tr=T[curLang]||T['it'];document.getElementById('sv_'+id).textContent=mode==='risk'?tr['mode-risk']:tr['legend2'];var fOpt=document.getElementById('opt_fixed_'+id);var rOpt=document.getElementById('opt_risk_'+id);fOpt.className='csel-opt'+(mode==='fixed'?' sel':'');rOpt.className='csel-opt'+(mode==='risk'?' sel':'');var row=document.getElementById('row_'+id);var inp=row.querySelector('.val-input');var lbl=row.querySelector('.val-lbl');var calc=row.querySelector('.calc-cell');var btns=row.querySelectorAll('.num-btn');row.setAttribute('data-mode',mode);var stp=mode==='risk'?0.1:0.01;if(mode==='risk'){inp.value='1.0';inp.step='0.1';inp.max='100';lbl.textContent='%';lbl.className='val-lbl pct';calc.className='calc-cell risk';calc.textContent='live';}else{inp.value='0.07';inp.step='0.01';inp.max='99';lbl.textContent='lot';lbl.className='val-lbl';calc.className='calc-cell';calc.textContent='0.07';}if(btns[0])btns[0].dataset.delta=stp;if(btns[1])btns[1].dataset.delta=-stp;}
function buildRow(symbol,mode,lot,riskPct,enabled){var id='r'+(rid++);var val=mode==='risk'?riskPct:lot;var est=mode==='risk'?'live':calcLot('fixed',val,0);var chk=enabled?' checked':'';var offCls=enabled?'':' off';var h='<div class="sym-row" id="row_'+id+'" data-mode="'+mode+'" data-symbol="'+symbol+'">';h+='<label class="toggle"><input type="checkbox"'+chk+' id="chk_'+id+'"><div class="toggle-bg"></div><div class="toggle-knob"></div></label>';h+='<span class="sym-name'+offCls+'" id="sn_'+id+'">'+symbol+'</span>';h+=makeSelectHTML(mode,id);h+='<div class="val-cell">';h+='<div class="num-wrap"><input class="val-input" type="number" value="'+val+'" step="'+(mode==='risk'?'0.1':'0.01')+'" min="0.01" max="'+(mode==='risk'?'100':'99')+'" id="vi_'+id+'" style="padding-right:28px;"><div class="num-btns"><div class="num-btn" data-target="vi_'+id+'" data-delta="'+(mode==='risk'?'0.1':'0.01')+'"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M18 15l-6-6-6 6"/></svg></div><div class="num-btn" data-target="vi_'+id+'" data-delta="-'+(mode==='risk'?'0.1':'0.01')+'"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M6 9l6 6 6-6"/></svg></div></div></div>';h+='<span class="val-lbl'+(mode==='risk'?' pct':'')+'" id="vl_'+id+'">'+(mode==='risk'?'%':'lot')+'</span></div>';h+='<div class="calc-cell'+(mode==='risk'?' risk':'')+'" id="cc_'+id+'">'+(mode==='risk'?'~':'')+est+'</div>';h+='<button class="btn-rm" id="rm_'+id+'">x</button>';h+='</div>';document.getElementById('sym-list').insertAdjacentHTML('beforeend',h);document.getElementById('chk_'+id).addEventListener('change',function(){var nm=document.getElementById('sn_'+id);if(this.checked)nm.classList.remove('off');else nm.classList.add('off');});document.getElementById('csb_'+id).addEventListener('click',function(){toggleDD(id);});document.getElementById('opt_fixed_'+id).addEventListener('click',function(){selectMode(id,'fixed');});document.getElementById('opt_risk_'+id).addEventListener('click',function(){selectMode(id,'risk');});document.getElementById('vi_'+id).addEventListener('input',function(){var row2=document.getElementById('row_'+id);var m=row2.getAttribute('data-mode');var cc=document.getElementById('cc_'+id);if(m==='risk')cc.textContent='live';else cc.textContent=parseFloat(this.value||0).toFixed(2);});document.getElementById('rm_'+id).addEventListener('click',function(){var el=document.getElementById('row_'+id);if(el)el.remove();symRows=symRows.filter(function(r){return r.id!==id;});});symRows.push({id:id,symbol:symbol});}
function openTelegram(){window.pywebview.api.open_telegram();}
function testTelegram(){var t=T[curLang]||T['it'];var chatId=document.getElementById('tg_chat_id').value.trim();var token=document.getElementById('tg_token').value.trim();var fb=document.getElementById('tg-feedback');if(!chatId){fb.style.color='#f87171';fb.textContent=t['tg-enter-chatid'];return;}fb.style.color='#7a8ba8';fb.textContent=t['tg-sending'];window.pywebview.api.test_telegram(chatId,token).then(function(res){if(res==='ok'){fb.style.color='#34d399';fb.textContent='&#10003; '+t['tg-sent'];}else{fb.style.color='#f87171';fb.textContent='&#10005; '+t['tg-error']+' '+res;}});}
function collectConfig(){var symbols=[];for(var i=0;i<symRows.length;i++){var r=symRows[i];var row=document.getElementById('row_'+r.id);if(!row)continue;var mode=row.getAttribute('data-mode');var enabled=document.getElementById('chk_'+r.id).checked;var val=parseFloat(document.getElementById('vi_'+r.id).value)||0.07;symbols.push({symbol:r.symbol,enabled:enabled,lot_mode:mode,lot:mode==='fixed'?val:0.07,risk_pct:mode==='risk'?val:1.0});}var startParts=document.getElementById('session_start').value.split(':');var endParts=document.getElementById('session_end').value.split(':');var startH=parseInt(startParts[0]||'7')+(parseInt(startParts[1]||'0')/60);var endH=parseInt(endParts[0]||'19')+(parseInt(endParts[1]||'30')/60);return{mt5_path:document.getElementById('mt5_path').value.trim(),mt5_login:document.getElementById('mt5_login').value.trim(),mt5_password:document.getElementById('mt5_password').value.trim(),mt5_server:document.getElementById('mt5_server').value.trim(),symbols:symbols,session_start_hour:startH,session_end_hour:endH,tg_chat_id:document.getElementById('tg_chat_id').value.trim(),tg_token:document.getElementById('tg_token').value.trim(),tg_notify_trade:document.getElementById('tg_notify_trade').checked,tg_notify_start:document.getElementById('tg_notify_start').checked,tg_notify_error:document.getElementById('tg_notify_error').checked,be_enabled:document.getElementById('be_enabled').checked,daily_loss_enabled:document.getElementById('daily_loss_enabled').checked,daily_loss_amount:parseFloat(document.getElementById('daily_loss_amount').value)||300};}
function saveConfig(){window.pywebview.api.save_config(JSON.stringify(collectConfig())).then(function(){var fb=document.getElementById('save-fb');fb.classList.add('show');setTimeout(function(){fb.classList.remove('show');},2500);});}
function startBot(){var t=T[curLang]||T['it'];var c=collectConfig();if(!c.mt5_login||!c.mt5_password){alert(t['alert-mt5-cred']);return;}window.pywebview.api.start_bot(JSON.stringify(c)).then(function(res){if(res==='ok'){document.getElementById('btn-start').disabled=true;document.getElementById('btn-stop').disabled=false;setStatus(t['status-starting'],'waiting');}});}
function stopBot(){var t=T[curLang]||T['it'];window.pywebview.api.stop_bot().then(function(){document.getElementById('btn-start').disabled=false;document.getElementById('btn-stop').disabled=true;setStatus(t['status-stopped'],'');});}
function initApp(){window._appInited=true;setTimeout(checkUpdate,3000);window.pywebview.api.get_session_info().then(function(raw){updateSession(JSON.parse(raw));});window.pywebview.api.get_logo_b64().then(function(b64){var w=document.getElementById('logo-wrap');w.innerHTML=b64?'<img class="logo" src="data:image/png;base64,'+b64+'">':'<div class="logo-ph">V</div>';});window.pywebview.api.get_config().then(function(raw){cfg=JSON.parse(raw);document.getElementById('mt5_path').value=cfg.mt5_path||'';document.getElementById('mt5_login').value=String(cfg.mt5_login||'');document.getElementById('mt5_password').value=cfg.mt5_password||'';document.getElementById('mt5_server').value=cfg.mt5_server||'';var sh=cfg.session_start_hour||7;var eh=cfg.session_end_hour||19.5;var shH=Math.floor(sh);var shM=Math.round((sh%1)*60);var ehH=Math.floor(eh);var ehM=Math.round((eh%1)*60);document.getElementById('session_start').value=(shH<10?'0':'')+shH+':'+(shM<10?'0':'')+shM;document.getElementById('session_end').value=(ehH<10?'0':'')+ehH+':'+(ehM<10?'0':'')+ehM;if(cfg.tg_chat_id)document.getElementById('tg_chat_id').value=cfg.tg_chat_id;if(cfg.tg_token)document.getElementById('tg_token').value=cfg.tg_token;if(cfg.tg_notify_trade===false)document.getElementById('tg_notify_trade').checked=false;if(cfg.tg_notify_start===false)document.getElementById('tg_notify_start').checked=false;if(cfg.tg_notify_error===false)document.getElementById('tg_notify_error').checked=false;if(cfg.be_enabled===true)document.getElementById('be_enabled').checked=true;if(cfg.daily_loss_enabled===true)document.getElementById('daily_loss_enabled').checked=true;if(cfg.daily_loss_amount)document.getElementById('daily_loss_amount').value=cfg.daily_loss_amount;var syms=cfg.symbols||[];for(var i=0;i<syms.length;i++){var s=syms[i];buildRow(s.symbol,s.lot_mode||'fixed',s.lot||0.07,s.risk_pct||1.0,s.enabled!==false);}});document.getElementById('browse-btn').addEventListener('click',function(){window.pywebview.api.browse_mt5().then(function(p){if(p)document.getElementById('mt5_path').value=p;});});document.getElementById('add-btn').addEventListener('click',function(){var sym=document.getElementById('new_sym').value.trim().toUpperCase();var val=parseFloat(document.getElementById('new_val').value)||0.07;if(!sym)return;for(var i=0;i<symRows.length;i++){if(symRows[i].symbol===sym)return;}buildRow(sym,'fixed',val,1.0,true);document.getElementById('new_sym').value='';});document.getElementById('save-btn').addEventListener('click',saveConfig);document.getElementById('btn-start').addEventListener('click',startBot);document.getElementById('btn-stop').addEventListener('click',stopBot);document.getElementById('clear-btn').addEventListener('click',function(){document.getElementById('log-box').innerHTML='';});document.addEventListener('click',function(e){if(!e.target.closest('.csel')&&openDD)closeDD(openDD);});setInterval(function(){window.pywebview.api.get_logs().then(function(raw){var lines=JSON.parse(raw);for(var i=0;i<lines.length;i++){var l=lines[i];if(l.msg.indexOf('__STATUS__')===0){var txt=l.msg.slice(10);var st='';if(txt.indexOf('Attivo')>=0||txt.indexOf('Connesso')>=0)st='active';else if(txt.indexOf('Errore')>=0)st='error';else if(txt.indexOf('Attesa')>=0||txt.indexOf('Analisi')>=0)st='waiting';setStatus(txt,st);}else{var box=document.getElementById('log-box');var d=document.createElement('div');var cls='log-info';if(l.msg.indexOf('[ERROR]')>=0)cls='log-error';else if(l.msg.indexOf('[WARN]')>=0)cls='log-warn';else if(l.msg.indexOf('BUY')>=0||l.msg.indexOf('SELL')>=0)cls='log-trade';d.innerHTML=(l.ts?'<span class="log-ts">'+l.ts+'</span>':'')+'<span class="'+cls+'">'+escHtml(l.msg)+'</span>';box.appendChild(d);box.scrollTop=box.scrollHeight;while(box.children.length>500)box.removeChild(box.firstChild);}}});},500);var liveEquity=0;function initChart(){var ctx=document.getElementById('equity-chart').getContext('2d');var grad=ctx.createLinearGradient(0,0,0,ctx.canvas.parentElement.offsetHeight||300);grad.addColorStop(0,'rgba(99,139,255,0.25)');grad.addColorStop(0.4,'rgba(167,139,250,0.1)');grad.addColorStop(1,'rgba(6,8,13,0)');var lineGrad=ctx.createLinearGradient(0,0,ctx.canvas.parentElement.offsetWidth||600,0);lineGrad.addColorStop(0,'#638bff');lineGrad.addColorStop(0.5,'#a78bfa');lineGrad.addColorStop(1,'#34d399');equityChart=new Chart(ctx,{type:'line',data:{labels:[],datasets:[{data:[],borderColor:lineGrad,backgroundColor:grad,borderWidth:2.5,pointRadius:0,pointHoverRadius:6,pointHoverBackgroundColor:'#fff',pointHoverBorderColor:'#638bff',pointHoverBorderWidth:3,tension:0.4,fill:true},{data:[],borderColor:'rgba(99,139,255,0.08)',borderWidth:1,pointRadius:0,tension:0.4,fill:false,borderDash:[4,4]}]},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},plugins:{legend:{display:false},tooltip:{backgroundColor:'rgba(12,16,24,0.95)',borderColor:'rgba(99,139,255,0.3)',borderWidth:1,titleColor:'#f4f7ff',bodyColor:'#7a8ba8',titleFont:{family:'JetBrains Mono',size:12,weight:'600'},bodyFont:{family:'JetBrains Mono',size:11},padding:12,cornerRadius:10,displayColors:false,callbacks:{label:function(c){if(c.datasetIndex===1)return null;return'Equity: '+c.parsed.y.toLocaleString('it-IT',{minimumFractionDigits:2});}}}},scales:{x:{display:true,grid:{display:false},ticks:{color:'rgba(74,85,104,0.5)',font:{size:9,family:'JetBrains Mono'},maxRotation:0,maxTicksLimit:6}},y:{grid:{color:'rgba(99,139,255,0.04)',lineWidth:1},border:{display:false,dash:[3,3]},ticks:{color:'#4a5568',font:{size:10,family:'JetBrains Mono'},padding:8,callback:function(v){return v.toLocaleString('it-IT');}}}},animation:{duration:600,easing:'easeInOutQuart'}}});}function updateDashboard(data){if(!data)return;var cur=data.currency||'USD';var fmt=function(n){return cur+' '+n.toLocaleString('it-IT',{minimumFractionDigits:2,maximumFractionDigits:2});};document.getElementById('d-equity').textContent=fmt(data.equity);document.getElementById('d-balance').textContent='Balance: '+fmt(data.balance);var profEl=document.getElementById('d-profit');profEl.textContent=(data.profit>=0?'+':'')+fmt(data.profit);profEl.className='stat-value '+(data.profit>0?'pos':data.profit<0?'neg':'blue');document.getElementById('d-trades-open').textContent=(T[curLang]||T['it'])['open-positions']+' '+data.positions;var wr=document.getElementById('d-winrate');wr.textContent=data.winrate+'%';wr.className='stat-value '+(data.winrate>=50?'pos':'neg');document.getElementById('d-wl').textContent='Win: '+data.wins+' | Loss: '+data.losses;var pf=document.getElementById('d-pf');pf.textContent=data.profit_factor||'—';pf.className='stat-value '+(data.profit_factor>=1?'pos':data.profit_factor>0?'neg':'blue');var now=new Date().toLocaleTimeString('it-IT',{hour:'2-digit',minute:'2-digit',second:'2-digit'});equityHistory.push({t:now,v:data.equity});if(equityHistory.length>60)equityHistory.shift();if(equityChart){var labels=equityHistory.map(function(e){return e.t;});var vals=equityHistory.map(function(e){return e.v;});equityChart.data.labels=labels;equityChart.data.datasets[0].data=vals;if(vals.length>0){var avg=vals.reduce(function(a,b){return a+b;},0)/vals.length;equityChart.data.datasets[1].data=vals.map(function(){return avg;});}equityChart.update();}var list=document.getElementById('trades-list');if(!data.trades||data.trades.length===0){list.innerHTML='<div class="no-trades">'+(T[curLang]||T['it'])['no-trades']+'</div>';}else{list.innerHTML=data.trades.map(function(t,i){var cls=t.profit>=0?'pos':'neg';var sign=t.profit>=0?'+':'';return'<div class="trade-row '+(i%2===0?'even':'')+'">'+'<span style="color:#4a5568">'+t.time+'</span>'+'<span style="color:#f4f7ff;font-family:Consolas">'+t.symbol+'</span>'+'<span class="trade-side '+t.type.toLowerCase()+'">'+t.type+'</span>'+'<span style="color:#7a8ba8">'+t.volume+'</span>'+'<span class="trade-pnl '+cls+'">'+sign+t.profit.toFixed(2)+'</span>'+'</div>';}).join('');}liveEquity=data.equity;var box=document.getElementById('equity-box');var capVal=document.getElementById('cap-equity-val');box.classList.add('show');document.getElementById('equity-val').textContent=fmt(data.equity);document.getElementById('balance-val').textContent=fmt(data.balance);capVal.textContent=fmt(data.equity);capVal.style.color='#638bff';var chg=document.getElementById('equity-change');var capP=document.getElementById('cap-profit');if(data.profit>0){chg.textContent='+'+data.profit.toFixed(2);chg.className='equity-change pos';capP.textContent='+'+cur+' '+data.profit.toFixed(2);capP.style.color='#34d399';}else if(data.profit<0){chg.textContent=data.profit.toFixed(2);chg.className='equity-change neg';capP.textContent=cur+' '+data.profit.toFixed(2);capP.style.color='#f87171';}else{chg.textContent='';capP.textContent='';}}function updateSession(data){var box=document.getElementById('session-box');var statusEl=document.getElementById('session-status');if(!data){box.classList.add('off');statusEl.textContent='OFF';statusEl.className='session-status disabled';return;}if(!data.enabled){box.classList.add('off');statusEl.textContent='OFF';statusEl.className='session-status disabled';}else{box.classList.remove('off');var st=T[curLang]||T['it'];if(data.in_range){statusEl.textContent=st['session-active'];statusEl.className='session-status in-range';}else{statusEl.textContent=data.is_weekday?st['session-out-hours']:st['session-weekend'];statusEl.className='session-status out-range';}}}initChart();setInterval(function(){window.pywebview.api.get_session_info().then(function(raw){updateSession(JSON.parse(raw));});},3000);setInterval(function(){window.pywebview.api.get_account_info().then(function(raw){var data=JSON.parse(raw);if(!data){document.getElementById('equity-box').classList.remove('show');document.getElementById('cap-equity-val').textContent=(T[curLang]||T['it'])['not-connected'];document.getElementById('cap-equity-val').style.color='#4a5568';return;}updateDashboard(data);});},3000);}
var btChart=null;
var modeOpen=false;
function toggleModeDD(){var btn=document.getElementById('mode-btn');var dd=document.getElementById('mode-dd');modeOpen=!modeOpen;if(modeOpen){btn.classList.add('open');dd.classList.add('open');}else{btn.classList.remove('open');dd.classList.remove('open');}}
function selectBtMode(mode){document.getElementById('bt-mode').value=mode;var t=T[curLang]||T['it'];document.getElementById('mode-val').textContent=mode==='fixed'?t['mode-fixed']:t['mode-risk'];var opts=document.querySelectorAll('.mode-opt');for(var i=0;i<opts.length;i++){if(opts[i].getAttribute('data-val')===mode)opts[i].classList.add('sel');else opts[i].classList.remove('sel');}toggleModeDD();toggleBtMode();}
function toggleBtMode(){var mode=document.getElementById('bt-mode').value;document.getElementById('bt-lot-wrap').style.display=mode==='fixed'?'flex':'none';document.getElementById('bt-risk-wrap').style.display=mode==='risk'?'flex':'none';document.getElementById('bt-capital-wrap').style.display=mode==='risk'?'flex':'none';}
function stepNum(id,delta){var inp=document.getElementById(id);if(!inp)return;var val=parseFloat(inp.value)||0;var min=parseFloat(inp.min)||0;var max=parseFloat(inp.max)||999999;var step=parseFloat(inp.step)||1;var decimals=step<1?Math.abs(Math.floor(Math.log10(step))):0;val=Math.round((val+delta)*Math.pow(10,decimals))/Math.pow(10,decimals);if(val<min)val=min;if(val>max)val=max;inp.value=val.toFixed(decimals);inp.dispatchEvent(new Event('input'));}
document.addEventListener('click',function(e){var btn=e.target.closest('.num-btn');if(btn&&btn.dataset.target&&btn.dataset.delta){stepNum(btn.dataset.target,parseFloat(btn.dataset.delta));}});
function initBtChart(){var ctx=document.getElementById('bt-chart').getContext('2d');var grad=ctx.createLinearGradient(0,0,0,250);grad.addColorStop(0,'rgba(52,211,153,0.3)');grad.addColorStop(1,'rgba(6,8,13,0)');btChart=new Chart(ctx,{type:'line',data:{labels:[],datasets:[{data:[],borderColor:'#34d399',backgroundColor:grad,borderWidth:2,pointRadius:0,tension:0.3,fill:true}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{display:true,grid:{display:false},ticks:{color:'#4a5568',font:{size:9},maxTicksLimit:8}},y:{grid:{color:'rgba(99,139,255,0.05)'},ticks:{color:'#4a5568',font:{size:10}}}}}});}
function runBacktest(){var tr=T[curLang]||T['it'];var symbols=[];var checks=document.querySelectorAll('#bt-symbols-wrap input[type=checkbox]:checked');for(var i=0;i<checks.length;i++)symbols.push(checks[i].value);var custom=document.getElementById('bt-symbol-custom').value.trim().toUpperCase();if(custom){var customArr=custom.split(',');for(var i=0;i<customArr.length;i++){var s=customArr[i].trim();if(s&&symbols.indexOf(s)===-1)symbols.push(s);}}var from=document.getElementById('bt-from').value;var to=document.getElementById('bt-to').value;var mode=document.getElementById('bt-mode').value;var lot=document.getElementById('bt-lot').value;var risk=document.getElementById('bt-risk').value;var capital=document.getElementById('bt-capital').value;if(!from||!to){alert(tr['alert-select-dates']);return;}if(symbols.length===0){alert(tr['alert-select-symbol']);return;}var status=document.getElementById('bt-status');var btn=document.getElementById('bt-run');btn.disabled=true;status.innerHTML='<span style="color:#638bff;">'+tr['bt-running']+' '+symbols.length+' '+tr['bt-symbols-count']+'...</span>';window.pywebview.api.run_backtest(JSON.stringify(symbols),from,to,lot,mode,risk,capital).then(function(raw){btn.disabled=false;try{var data=JSON.parse(raw);if(data.error){status.innerHTML='<span style="color:#f87171;">'+data.error+'</span>';return;}status.textContent=tr['bt-completed']+' '+data.duration+'s - '+(data.symbols?data.symbols.length:1)+' '+tr['bt-symbols-count'];document.getElementById('bt-results').style.display='block';document.getElementById('bt-total').textContent=data.total;document.getElementById('bt-period').textContent=tr['bt-period-label']+' '+data.period;var wr=document.getElementById('bt-winrate');wr.textContent=data.winrate+'%';wr.className='stat-value '+(data.winrate>=50?'pos':'neg');document.getElementById('bt-wl').textContent='Win: '+data.wins+' | Loss: '+data.losses;var pf=document.getElementById('bt-pf');pf.textContent=data.profit_factor;pf.className='stat-value '+(data.profit_factor>=1?'pos':'neg');document.getElementById('bt-expectancy').textContent='Expectancy: '+data.expectancy;var prof=document.getElementById('bt-profit');prof.textContent=(data.net_profit>=0?'+':'')+data.net_profit.toFixed(2);prof.className='stat-value '+(data.net_profit>=0?'pos':'neg');document.getElementById('bt-dd').textContent='Max DD: '+data.max_dd.toFixed(2)+'%';if(!btChart)initBtChart();btChart.data.labels=data.equity_curve.map(function(e){return e.date;});btChart.data.datasets[0].data=data.equity_curve.map(function(e){return e.equity;});btChart.update();var list=document.getElementById('bt-trades');list.innerHTML=data.trades.slice(0,50).map(function(t,i){var cls=t.profit>=0?'pos':'neg';var sign=t.profit>=0?'+':'';return'<div class="trade-row '+(i%2===0?'even':'')+'" style="grid-template-columns:60px 80px 60px 70px 70px 70px;">'+'<span style="color:#4a5568">'+t.date+'</span>'+'<span style="color:#f4f7ff;font-size:11px;">'+t.symbol+'</span>'+'<span class="trade-side '+t.type.toLowerCase()+'">'+t.type+'</span>'+'<span style="color:#7a8ba8">'+t.entry+'</span>'+'<span style="color:#7a8ba8">'+t.exit+'</span>'+'<span class="trade-pnl '+cls+'">'+sign+t.profit.toFixed(2)+'</span>'+'</div>';}).join('');}catch(e){status.innerHTML='<span style="color:#f87171;">'+tr['bt-error-js']+' '+e.message+'</span>';}}).catch(function(e){btn.disabled=false;status.innerHTML='<span style="color:#f87171;">'+tr['bt-error-call']+' '+e+'</span>';});}
function initBacktest(){var today=new Date();var past=new Date();past.setMonth(past.getMonth()-3);var toEl=document.getElementById('bt-to');var fromEl=document.getElementById('bt-from');var runEl=document.getElementById('bt-run');if(toEl)toEl.value=today.toISOString().split('T')[0];if(fromEl)fromEl.value=past.toISOString().split('T')[0];if(runEl)runEl.addEventListener('click',runBacktest);document.addEventListener('click',function(e){if(modeOpen&&!e.target.closest('.mode-sel')){toggleModeDD();}});}
window.addEventListener('pywebviewready',function(){initApp();initBacktest();});
(function(){var attempts=0;var iv=setInterval(function(){attempts++;if(attempts>50){clearInterval(iv);return;}try{if(window.pywebview&&window.pywebview.api&&typeof window.pywebview.api.get_config==='function'){clearInterval(iv);if(!window._appInited){window._appInited=true;initApp();}}}catch(e){}},200);})();
var T={
it:{
'tab-dashboard':'Dashboard','tab-mt5':'Account MT5','tab-symbols':'Simboli','tab-log':'Log','tab-guide':'Guida','tab-telegram':'Telegram','tab-backtest':'Backtest',
'session':'Sessione','equity':'Equity','balance':'Balance','open-profit':'Profitto Aperto','winrate':'Win Rate','profit-factor':'Profit Factor',
'equity-curve':'Curva Equity','last-trades':'Ultimi Trade','no-trades':'Nessun trade ancora','time':'Ora','symbol':'Simbolo','type':'Tipo','lot':'Lotto','pnl':'P&L',
'mt5-title':'Connessione MetaTrader 5','mt5-sub':'Percorso del terminale e credenziali dell\\'account','mt5-path':'Percorso terminal64.exe','mt5-login':'Login (numero)','mt5-password':'Password','mt5-server':'Server',
'sym-title':'Simboli e dimensione lotto','sym-sub':'Lotti fissi oppure rischio % automatico per ogni simbolo','capital-live':'Capitale Live','equity-live-desc':'Equity live da MT5 — aggiornata ogni 3s','add-btn':'+ Aggiungi','on':'ON','mode':'Modalita','value':'Valore','lot-calc':'Lotto','legend1':'Rischio %','legend1-desc':' - lotto auto: Capitale x % / (ATR x pip value)','legend2':'Fisso','legend2-desc':' - lotto manuale invariabile',
'mode-fixed':'Lotto Fisso','mode-risk':'Rischio %','be-auto':'BE Auto','daily-loss':'Stop',
'daily-loss-tooltip':'<strong>Stop Giornaliero</strong><br><br>Quando attivo, se la perdita giornaliera raggiunge il valore in euro impostato, il bot smette di operare per il resto della giornata.',
'be-tooltip':'<strong>Break Even Automatico</strong><br><br>Quando attivo, lo SL viene spostato automaticamente a Break Even (+ qualche pip di profit) quando il trade raggiunge la soglia di profitto.<br><br><strong>Forex:</strong> +20 pips<br><strong>XAUUSD:</strong> +200 pips<br><br>Il BE non viene messo esattamente all\\'entrata, ma leggermente in positivo per garantire un minimo guadagno anche se il prezzo torna indietro.',
'log-title':'Log in tempo reale','clear-btn':'Pulisci',
'req-title':'Requisiti Obbligatori','req-sub':'Prima di iniziare, assicurati di avere questi requisiti',
'req-fpg':'Account FPG','req-fpg-desc':'Crea un account sul broker <strong>FPG (Fortune Prime Global)</strong>. La registrazione e completamente <strong>GRATUITA</strong>.','req-fpg-btn':'Registrati su FPG &rarr;',
'req-vps':'VPS Windows 11','req-vps-desc':'Acquista una VPS con <strong>Windows 11</strong> per far girare il bot 24/7. La piu economica e <strong>Contabo</strong>.','req-vps-btn':'Vai su Contabo &rarr;',
'req-warn':'Il bot funziona SOLO su Windows. La VPS deve rimanere sempre accesa per operare 24/7.',
'guide1-title':'Come impostare i Simboli e Lotti','guide1-sub':'Segui questi passi per configurare correttamente i simboli',
'g1s1-title':'Trova i simboli del tuo broker','g1s1-body':'Apri MetaTrader 5 e vai su <strong>Visualizza &rarr; Simboli</strong> (CTRL+U). Cerca i simboli che vuoi tradare. Il nome esatto potrebbe avere un suffisso come <code>-P</code>, <code>m</code>, o un punto — esempio: <code>EURUSD-P</code>, <code>EURUSDm</code>, <code>EURUSD.</code>',
'g1s2-title':'Aggiungi un simbolo','g1s2-body':'Nel tab <strong>Simboli &amp; Lotti</strong>, scrivi il nome esatto del simbolo nel campo di testo (es. <code>EURUSD-P</code>) e clicca <strong>+ Aggiungi</strong>. Il simbolo appare nella lista.',
'g1s3-title':'Abilita o disabilita un simbolo','g1s3-body':'Usa il <strong>toggle</strong> a sinistra di ogni simbolo per attivarlo o disattivarlo. Il bot opera solo sui simboli con toggle attivo (blu).',
'g1s4-title':'Imposta il lotto','g1s4-body':'Scegli la modalita <strong>Fisso</strong> e inserisci il lotto manualmente (es. <code>0.07</code>). Oppure usa <strong>Rischio %</strong> per il calcolo automatico — vedi la sezione qui sotto.',
'g1s5-title':'Salva le impostazioni','g1s5-body':'Clicca sempre <strong>Salva</strong> in basso a destra dopo ogni modifica. Le impostazioni vengono salvate automaticamente anche quando clicchi <strong>Avvia Bot</strong>.',
'guide2-title':'Come funziona il Rischio %','guide2-sub':'Il bot calcola il lotto automaticamente in base al tuo capitale',
'g2s1-title':'Inserisci il capitale del tuo account','g2s1-body':'Nel tab <strong>Simboli &amp; Lotti</strong>, inserisci il saldo attuale del tuo conto MT5 nel campo <strong>Capitale Account</strong> (es. <code>10000</code> per $10.000). Questo valore e la base per il calcolo del rischio.',
'g2s2-title':'Seleziona modalita Rischio %','g2s2-body':'Per ogni simbolo, apri il menu a tendina e scegli <strong>Rischio %</strong>. Inserisci la percentuale che vuoi rischiare per ogni trade — ad esempio <code>1.0</code> significa rischiare l\\'1% del capitale per ogni operazione.',
'g2s3-title':'Il lotto viene calcolato automaticamente','g2s3-body':'La formula usata e: <code>Capitale x % / (ATR x Pip Value)</code>. Il lotto viene calcolato in <strong>tempo reale</strong> ad ogni trade in base all\\'ATR del momento — per questo nella colonna vedi <code>live</code> invece di un numero fisso.',
'g2s4-title':'Consiglio sul rischio','g2s4-body':'Si consiglia di impostare un rischio tra <strong>0.5% e 2%</strong> per trade. Un rischio superiore al 3% per trade e considerato elevato e puo portare a perdite significative in caso di serie negative.',
'guide2-warn':'Il capitale inserito e solo indicativo per il calcolo del lotto. Aggiornalo manualmente quando il saldo del tuo conto cambia significativamente.',
'tg-title':'Notifiche Telegram','tg-sub':'Ricevi un messaggio su ogni trade, avvio e stop del bot',
'tg-s1-title':'Connetti il bot Telegram','tg-s1-body':'Clicca il bottone qui sotto per aprire <strong>@getidsbot</strong> su Telegram. Clicca <strong>Start</strong> — ti risponde automaticamente con il tuo Chat ID.','tg-get-id':'Ottieni il mio Chat ID',
'tg-s2-title':'Inserisci il tuo Chat ID','tg-s2-body':'Copia il numero che ti ha mandato il bot e incollalo qui sotto.','tg-test':'Testa notifica','tg-placeholder':'Es. 123456789',
'tg-s3-title':'Token del bot (solo se usi un bot diverso)','tg-s3-body':'Se stai usando <strong>@VaultSystemFx_bot</strong> lascia questo campo vuoto. Inserisci un token solo se hai un bot Telegram personale.','tg-token-placeholder':'Lascia vuoto per usare @VaultSystemFx_bot',
'tg-notify-title':'Notifiche attive','tg-notify-trade':'Trade aperti (BUY/SELL con prezzo, SL, TP)','tg-notify-start':'Avvio e stop del bot','tg-notify-error':'Errori di connessione MT5',
'bt-title':'Backtest Strategia','bt-sub':'Testa la strategia sui dati storici per vedere le performance',
'bt-symbols-label':'Simboli (seleziona uno o piu)','bt-custom-label':'Simboli custom (separati da virgola)','bt-custom-placeholder':'es. AUDUSD-P, NZDUSD-P',
'bt-from':'Da','bt-to':'A','bt-mode':'Modalita','bt-lot':'Lotto','bt-risk':'Rischio %','bt-capital':'Capitale','bt-run':'Avvia Backtest',
'bt-total':'Trade Totali','bt-winrate':'Win Rate','bt-pf':'Profit Factor','bt-net':'Profitto Netto','bt-curve':'Curva Equity Backtest','bt-detail':'Dettaglio Trade',
'bt-date':'Data','bt-entry':'Entry','bt-exit':'Exit',
'btn-start':'Avvia Bot','btn-stop':'FERMA','btn-save':'Salva','saved':'Salvato',
'alert-mt5-cred':'Inserisci login e password MT5.','status-starting':'Avvio...','status-stopped':'Fermo',
'alert-select-dates':'Seleziona le date di inizio e fine.','alert-select-symbol':'Seleziona almeno un simbolo.',
'bt-running':'Backtest in corso su','bt-symbols-count':'simboli','bt-completed':'Completato in',
'tg-enter-chatid':'Inserisci il Chat ID prima!','tg-sending':'Invio messaggio di test...','tg-sent':'Messaggio inviato! Controlla Telegram.','tg-error':'Errore:',
'bt-period-label':'Periodo:','bt-error-js':'Errore JS:','bt-error-call':'Errore chiamata:',
'open-positions':'Posizioni aperte:','session-active':'ATTIVO','session-out-hours':'FUORI ORARIO','session-weekend':'WEEKEND','not-connected':'— Non connesso'
},
en:{
'tab-dashboard':'Dashboard','tab-mt5':'MT5 Account','tab-symbols':'Symbols','tab-log':'Log','tab-guide':'Guide','tab-telegram':'Telegram','tab-backtest':'Backtest',
'session':'Session','equity':'Equity','balance':'Balance','open-profit':'Open Profit','winrate':'Win Rate','profit-factor':'Profit Factor',
'equity-curve':'Equity Curve','last-trades':'Recent Trades','no-trades':'No trades yet','time':'Time','symbol':'Symbol','type':'Type','lot':'Lot','pnl':'P&L',
'mt5-title':'MetaTrader 5 Connection','mt5-sub':'Terminal path and account credentials','mt5-path':'Path to terminal64.exe','mt5-login':'Login (number)','mt5-password':'Password','mt5-server':'Server',
'sym-title':'Symbols and lot size','sym-sub':'Fixed lots or automatic risk % per symbol','capital-live':'Live Capital','equity-live-desc':'Live equity from MT5 — updated every 3s','add-btn':'+ Add','on':'ON','mode':'Mode','value':'Value','lot-calc':'Lot','legend1':'Risk %','legend1-desc':' - auto lot: Capital x % / (ATR x pip value)','legend2':'Fixed','legend2-desc':' - manual fixed lot',
'mode-fixed':'Fixed Lot','mode-risk':'Risk %','be-auto':'Auto BE','daily-loss':'Stop',
'daily-loss-tooltip':'<strong>Daily Loss Limit</strong><br><br>When enabled, if the daily loss reaches the set amount in euros, the bot stops trading for the rest of the day.',
'be-tooltip':'<strong>Automatic Break Even</strong><br><br>When enabled, SL is automatically moved to Break Even (+ a few pips profit) when the trade reaches the profit threshold.<br><br><strong>Forex:</strong> +20 pips<br><strong>XAUUSD:</strong> +200 pips<br><br>BE is not placed exactly at entry, but slightly in profit to guarantee a minimum gain even if price retraces.',
'log-title':'Real-time Log','clear-btn':'Clear',
'req-title':'Mandatory Requirements','req-sub':'Before starting, make sure you have these requirements',
'req-fpg':'FPG Account','req-fpg-desc':'Create an account on <strong>FPG (Fortune Prime Global)</strong> broker. Registration is completely <strong>FREE</strong>.','req-fpg-btn':'Register on FPG &rarr;',
'req-vps':'Windows 11 VPS','req-vps-desc':'Purchase a VPS with <strong>Windows 11</strong> to run the bot 24/7. <strong>Contabo</strong> offers the cheapest.','req-vps-btn':'Go to Contabo &rarr;',
'req-warn':'The bot works ONLY on Windows. The VPS must always be on to operate 24/7.',
'guide1-title':'How to set up Symbols and Lots','guide1-sub':'Follow these steps to correctly configure symbols',
'g1s1-title':'Find your broker\\'s symbols','g1s1-body':'Open MetaTrader 5 and go to <strong>View &rarr; Symbols</strong> (CTRL+U). Search for symbols you want to trade. The exact name may have a suffix like <code>-P</code>, <code>m</code>, or a dot — example: <code>EURUSD-P</code>, <code>EURUSDm</code>, <code>EURUSD.</code>',
'g1s2-title':'Add a symbol','g1s2-body':'In the <strong>Symbols &amp; Lots</strong> tab, type the exact symbol name in the text field (e.g. <code>EURUSD-P</code>) and click <strong>+ Add</strong>. The symbol appears in the list.',
'g1s3-title':'Enable or disable a symbol','g1s3-body':'Use the <strong>toggle</strong> on the left of each symbol to enable or disable it. The bot only trades symbols with active toggle (blue).',
'g1s4-title':'Set the lot size','g1s4-body':'Choose <strong>Fixed</strong> mode and enter the lot manually (e.g. <code>0.07</code>). Or use <strong>Risk %</strong> for automatic calculation — see section below.',
'g1s5-title':'Save settings','g1s5-body':'Always click <strong>Save</strong> at bottom right after any change. Settings are also saved automatically when you click <strong>Start Bot</strong>.',
'guide2-title':'How Risk % works','guide2-sub':'The bot calculates lot automatically based on your capital',
'g2s1-title':'Enter your account capital','g2s1-body':'In the <strong>Symbols &amp; Lots</strong> tab, enter your current MT5 account balance in <strong>Account Capital</strong> field (e.g. <code>10000</code> for $10,000). This value is the base for risk calculation.',
'g2s2-title':'Select Risk % mode','g2s2-body':'For each symbol, open the dropdown and choose <strong>Risk %</strong>. Enter the percentage you want to risk per trade — for example <code>1.0</code> means risking 1% of capital per trade.',
'g2s3-title':'Lot is calculated automatically','g2s3-body':'Formula used: <code>Capital x % / (ATR x Pip Value)</code>. Lot is calculated in <strong>real-time</strong> on each trade based on current ATR — that\\'s why you see <code>live</code> in the column instead of a fixed number.',
'g2s4-title':'Risk recommendation','g2s4-body':'It\\'s recommended to set risk between <strong>0.5% and 2%</strong> per trade. Risk above 3% per trade is considered high and can lead to significant losses in losing streaks.',
'guide2-warn':'The capital entered is only indicative for lot calculation. Update it manually when your account balance changes significantly.',
'tg-title':'Telegram Notifications','tg-sub':'Receive a message on every trade, bot start and stop',
'tg-s1-title':'Connect Telegram bot','tg-s1-body':'Click the button below to open <strong>@getidsbot</strong> on Telegram. Click <strong>Start</strong> — it will reply with your Chat ID.','tg-get-id':'Get my Chat ID',
'tg-s2-title':'Enter your Chat ID','tg-s2-body':'Copy the number the bot sent you and paste it below.','tg-test':'Test notification','tg-placeholder':'E.g. 123456789',
'tg-s3-title':'Bot token (only if using different bot)','tg-s3-body':'If using <strong>@VaultSystemFx_bot</strong> leave this empty. Enter a token only if you have a personal Telegram bot.','tg-token-placeholder':'Leave empty to use @VaultSystemFx_bot',
'tg-notify-title':'Active notifications','tg-notify-trade':'Open trades (BUY/SELL with price, SL, TP)','tg-notify-start':'Bot start and stop','tg-notify-error':'MT5 connection errors',
'bt-title':'Strategy Backtest','bt-sub':'Test the strategy on historical data to see performance',
'bt-symbols-label':'Symbols (select one or more)','bt-custom-label':'Custom symbols (comma separated)','bt-custom-placeholder':'e.g. AUDUSD-P, NZDUSD-P',
'bt-from':'From','bt-to':'To','bt-mode':'Mode','bt-lot':'Lot','bt-risk':'Risk %','bt-capital':'Capital','bt-run':'Run Backtest',
'bt-total':'Total Trades','bt-winrate':'Win Rate','bt-pf':'Profit Factor','bt-net':'Net Profit','bt-curve':'Backtest Equity Curve','bt-detail':'Trade Details',
'bt-date':'Date','bt-entry':'Entry','bt-exit':'Exit',
'btn-start':'Start Bot','btn-stop':'STOP','btn-save':'Save','saved':'Saved',
'alert-mt5-cred':'Enter MT5 login and password.','status-starting':'Starting...','status-stopped':'Stopped',
'alert-select-dates':'Select start and end dates.','alert-select-symbol':'Select at least one symbol.',
'bt-running':'Running backtest on','bt-symbols-count':'symbols','bt-completed':'Completed in',
'tg-enter-chatid':'Enter Chat ID first!','tg-sending':'Sending test message...','tg-sent':'Message sent! Check Telegram.','tg-error':'Error:',
'bt-period-label':'Period:','bt-error-js':'JS Error:','bt-error-call':'Call error:',
'open-positions':'Open positions:','session-active':'ACTIVE','session-out-hours':'OUT OF HOURS','session-weekend':'WEEKEND','not-connected':'— Not connected'
}
};
var curLang='it';
function setLang(lang){
curLang=lang;var t=T[lang];
document.querySelectorAll('.lang-btn').forEach(function(b){b.classList.toggle('active',b.textContent===(lang==='it'?'ITA':'ENG'));});
// Tabs
var tabs=document.querySelectorAll('.tab-btn');
tabs[0].innerHTML='<span class="icon icon-dashboard"></span>'+t['tab-dashboard'];
tabs[1].innerHTML='<span class="icon icon-mt5"></span>'+t['tab-mt5'];
tabs[2].innerHTML='<span class="icon icon-symbols"></span>'+t['tab-symbols'];
tabs[3].innerHTML='<span class="icon icon-log"></span>'+t['tab-log'];
tabs[4].innerHTML='<span class="icon icon-guide"></span>'+t['tab-guide'];
tabs[5].innerHTML='<span class="icon icon-telegram"></span>'+t['tab-telegram'];
tabs[6].innerHTML='<span class="icon icon-backtest"></span>'+t['tab-backtest'];
// Header
var sl=document.querySelector('.session-label');if(sl)sl.textContent=t['session'];
// Dashboard
var cards=document.querySelectorAll('#tab-dashboard .stat-label');
if(cards[0])cards[0].textContent=t['equity'];if(cards[1])cards[1].textContent=t['open-profit'];if(cards[2])cards[2].textContent=t['winrate'];if(cards[3])cards[3].textContent=t['profit-factor'];
var ct=document.querySelectorAll('#tab-dashboard .chart-title');
if(ct[0])ct[0].innerHTML='<span class="icon icon-chart"></span>'+t['equity-curve'];if(ct[1])ct[1].innerHTML='<span class="icon icon-list"></span>'+t['last-trades'];
var hdr=document.querySelector('#tab-dashboard .trade-row.hdr');if(hdr)hdr.innerHTML='<span>'+t['time']+'</span><span>'+t['symbol']+'</span><span>'+t['type']+'</span><span>'+t['lot']+'</span><span>'+t['pnl']+'</span>';
var nt=document.querySelector('.no-trades');if(nt)nt.textContent=t['no-trades'];
// MT5
var mt5=document.querySelector('#tab-mt5 .card-title');if(mt5)mt5.textContent=t['mt5-title'];
var mt5s=document.querySelector('#tab-mt5 .card-sub');if(mt5s)mt5s.textContent=t['mt5-sub'];
var mt5Labels=document.querySelectorAll('#tab-mt5 .form-row label');
if(mt5Labels[0])mt5Labels[0].textContent=t['mt5-path'];if(mt5Labels[1])mt5Labels[1].textContent=t['mt5-login'];if(mt5Labels[2])mt5Labels[2].textContent=t['mt5-password'];if(mt5Labels[3])mt5Labels[3].textContent=t['mt5-server'];
// Symbols
var symT=document.querySelector('#tab-symbols .card-title span');if(symT)symT.textContent=t['sym-title'];
var symS=document.querySelector('#tab-symbols .card-sub');if(symS)symS.textContent=t['sym-sub'];
var capL=document.querySelector('.capital-label');if(capL)capL.innerHTML='&#x1F4B0; '+t['capital-live'];
var addB=document.getElementById('add-btn');if(addB)addB.textContent=t['add-btn'];
var sh=document.querySelector('.sym-header');if(sh)sh.innerHTML='<span>'+t['on']+'</span><span>'+t['symbol']+'</span><span>'+t['mode']+'</span><span>'+t['value']+'</span><span>'+t['lot-calc']+'</span><span></span>';
var leg=document.querySelector('.legend');if(leg)leg.innerHTML='<span style="color:#638bff;font-weight:600;">'+t['legend1']+'</span>'+t['legend1-desc']+'<br><span style="color:#7a8ba8;font-weight:600;">'+t['legend2']+'</span>'+t['legend2-desc'];
// Update symbol row dropdowns
for(var i=0;i<symRows.length;i++){var sr=symRows[i];var row=document.getElementById('row_'+sr.id);if(!row)continue;var mode=row.getAttribute('data-mode');var sv=document.getElementById('sv_'+sr.id);if(sv)sv.textContent=mode==='risk'?t['mode-risk']:t['legend2'];var optF=document.getElementById('opt_fixed_'+sr.id);var optR=document.getElementById('opt_risk_'+sr.id);if(optF)optF.textContent=t['legend2'];if(optR)optR.textContent=t['mode-risk'];}
var dailyLossLabel=document.querySelector('.daily-loss-label');if(dailyLossLabel)dailyLossLabel.textContent=t['daily-loss'];
var dailyLossTooltip=document.getElementById('daily-loss-tooltip');if(dailyLossTooltip)dailyLossTooltip.innerHTML=t['daily-loss-tooltip'];
var beLabels=document.querySelectorAll('.be-toggle-label:not(.daily-loss-label)');if(beLabels[0])beLabels[0].textContent=t['be-auto'];
var beTooltip=document.querySelectorAll('.be-tooltip:not(#daily-loss-tooltip)');if(beTooltip[0])beTooltip[0].innerHTML=t['be-tooltip'];
// Mode dropdown
var modeVal=document.getElementById('mode-val');if(modeVal)modeVal.textContent=document.getElementById('bt-mode').value==='fixed'?t['mode-fixed']:t['mode-risk'];
var modeOpts=document.querySelectorAll('.mode-opt');if(modeOpts[0])modeOpts[0].innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>'+t['mode-fixed'];if(modeOpts[1])modeOpts[1].innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>'+t['mode-risk'];
// Log
var logT=document.querySelector('.log-title');if(logT)logT.textContent=t['log-title'];
var clrB=document.getElementById('clear-btn');if(clrB)clrB.textContent=t['clear-btn'];
// Guide - Requirements
var reqCard=document.querySelector('.req-card');if(reqCard){
var rc=reqCard.querySelector('.card-title');if(rc)rc.innerHTML='<span class="req-icon">!</span> '+t['req-title'];
var rs=reqCard.querySelector('.card-sub');if(rs)rs.textContent=t['req-sub'];
var ri=reqCard.querySelectorAll('.req-item');
if(ri[0]){ri[0].querySelector('.req-header span').textContent=t['req-fpg'];ri[0].querySelector('.req-body').innerHTML=t['req-fpg-desc']+'<br><br><a href="https://portal.fortuneprime.com/getview?view=register&token=0pSM1g" target="_blank" class="req-link">'+t['req-fpg-btn']+'</a>';}
if(ri[1]){ri[1].querySelector('.req-header span').textContent=t['req-vps'];ri[1].querySelector('.req-body').innerHTML=t['req-vps-desc']+'<br><br><a href="https://contabo.com/en/vps/cloud-vps-10/?image=windows-server.308&qty=1&contract=12&storage-type=cloud-vps-10-150-gb-ssd" target="_blank" class="req-link">'+t['req-vps-btn']+'</a>';}
var rw=reqCard.querySelector('.req-warn span');if(rw)rw.textContent=t['req-warn'];
}
// Guide cards
var guideCards=document.querySelectorAll('#tab-guide .card:not(.req-card)');
if(guideCards[0]){
guideCards[0].querySelector('.card-title').innerHTML='&#x1F4CB; '+t['guide1-title'];
guideCards[0].querySelector('.card-sub').textContent=t['guide1-sub'];
var steps=guideCards[0].querySelectorAll('.guide-step');
if(steps[0]){steps[0].querySelector('.guide-title').textContent=t['g1s1-title'];steps[0].querySelector('.guide-body').innerHTML=t['g1s1-body'];}
if(steps[1]){steps[1].querySelector('.guide-title').textContent=t['g1s2-title'];steps[1].querySelector('.guide-body').innerHTML=t['g1s2-body'];}
if(steps[2]){steps[2].querySelector('.guide-title').textContent=t['g1s3-title'];steps[2].querySelector('.guide-body').innerHTML=t['g1s3-body'];}
if(steps[3]){steps[3].querySelector('.guide-title').textContent=t['g1s4-title'];steps[3].querySelector('.guide-body').innerHTML=t['g1s4-body'];}
if(steps[4]){steps[4].querySelector('.guide-title').textContent=t['g1s5-title'];steps[4].querySelector('.guide-body').innerHTML=t['g1s5-body'];}
}
if(guideCards[1]){
guideCards[1].querySelector('.card-title').innerHTML='&#x1F4B0; '+t['guide2-title'];
guideCards[1].querySelector('.card-sub').textContent=t['guide2-sub'];
var steps2=guideCards[1].querySelectorAll('.guide-step');
if(steps2[0]){steps2[0].querySelector('.guide-title').textContent=t['g2s1-title'];steps2[0].querySelector('.guide-body').innerHTML=t['g2s1-body'];}
if(steps2[1]){steps2[1].querySelector('.guide-title').textContent=t['g2s2-title'];steps2[1].querySelector('.guide-body').innerHTML=t['g2s2-body'];}
if(steps2[2]){steps2[2].querySelector('.guide-title').textContent=t['g2s3-title'];steps2[2].querySelector('.guide-body').innerHTML=t['g2s3-body'];}
if(steps2[3]){steps2[3].querySelector('.guide-title').textContent=t['g2s4-title'];steps2[3].querySelector('.guide-body').innerHTML=t['g2s4-body'];}
var gw=guideCards[1].querySelector('.guide-warn');if(gw)gw.innerHTML='&#x26A0; '+t['guide2-warn'];
}
// Telegram
var tgCard=document.querySelector('#tab-telegram .card');if(tgCard){
tgCard.querySelector('.card-title').innerHTML='&#x1F4F1; '+t['tg-title'];
tgCard.querySelector('.card-sub').textContent=t['tg-sub'];
var tgSteps=tgCard.querySelectorAll('.guide-step');
if(tgSteps[0]){tgSteps[0].querySelector('.guide-title').textContent=t['tg-s1-title'];tgSteps[0].querySelector('.guide-body').innerHTML=t['tg-s1-body'];tgSteps[0].querySelector('.btn-tg').innerHTML='&#x1F4AC; '+t['tg-get-id'];}
if(tgSteps[1]){tgSteps[1].querySelector('.guide-title').textContent=t['tg-s2-title'];tgSteps[1].querySelector('.guide-body').textContent=t['tg-s2-body'];var tgTest=document.getElementById('tg-test-btn');if(tgTest)tgTest.innerHTML='&#x2713; '+t['tg-test'];document.getElementById('tg_chat_id').placeholder=t['tg-placeholder'];}
if(tgSteps[2]){tgSteps[2].querySelector('.guide-title').textContent=t['tg-s3-title'];tgSteps[2].querySelector('.guide-body').innerHTML=t['tg-s3-body'];document.getElementById('tg_token').placeholder=t['tg-token-placeholder'];}
var notifyBox=tgCard.querySelector('div[style*="background:#0a0e17"]');if(notifyBox){
notifyBox.querySelector('div').textContent=t['tg-notify-title'];
var spans=notifyBox.querySelectorAll('label span');if(spans[0])spans[0].textContent=t['tg-notify-trade'];if(spans[1])spans[1].textContent=t['tg-notify-start'];if(spans[2])spans[2].textContent=t['tg-notify-error'];
}}
// Backtest
var btCard=document.querySelector('#tab-backtest .card');if(btCard){
btCard.querySelector('.card-title').innerHTML='<span class="icon icon-backtest"></span>'+t['bt-title'];
btCard.querySelector('.card-sub').textContent=t['bt-sub'];
var btLabels=btCard.querySelectorAll('.bt-field > label');
if(btLabels[0])btLabels[0].textContent=t['bt-symbols-label'];if(btLabels[1])btLabels[1].textContent=t['bt-custom-label'];
var btCustom=document.getElementById('bt-symbol-custom');if(btCustom)btCustom.placeholder=t['bt-custom-placeholder'];
if(btLabels[2])btLabels[2].textContent=t['bt-from'];if(btLabels[3])btLabels[3].textContent=t['bt-to'];if(btLabels[4])btLabels[4].textContent=t['bt-mode'];
if(btLabels[5])btLabels[5].textContent=t['bt-lot'];if(btLabels[6])btLabels[6].textContent=t['bt-risk'];if(btLabels[7])btLabels[7].textContent=t['bt-capital'];
}
var btRun=document.getElementById('bt-run');if(btRun)btRun.innerHTML='<span class="icon icon-play" style="width:12px;height:12px;"></span>'+t['bt-run'];
// Backtest results
var btRes=document.getElementById('bt-results');if(btRes){
var btLabels2=btRes.querySelectorAll('.stat-label');if(btLabels2[0])btLabels2[0].textContent=t['bt-total'];if(btLabels2[1])btLabels2[1].textContent=t['bt-winrate'];if(btLabels2[2])btLabels2[2].textContent=t['bt-pf'];if(btLabels2[3])btLabels2[3].textContent=t['bt-net'];
var btCt=btRes.querySelectorAll('.chart-title');if(btCt[0])btCt[0].innerHTML='<span class="icon icon-chart"></span>'+t['bt-curve'];if(btCt[1])btCt[1].innerHTML='<span class="icon icon-list"></span>'+t['bt-detail'];
var btHdr=btRes.querySelector('.trade-row.hdr');if(btHdr)btHdr.innerHTML='<span>'+t['bt-date']+'</span><span>'+t['symbol']+'</span><span>'+t['type']+'</span><span>'+t['bt-entry']+'</span><span>'+t['bt-exit']+'</span><span>'+t['pnl']+'</span>';
}
// Bottom bar
var startB=document.getElementById('btn-start');if(startB)startB.innerHTML='<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style="margin-right:8px;"><polygon points="5 3 19 12 5 21 5 3"/></svg>'+t['btn-start'].toUpperCase();
var stopB=document.getElementById('btn-stop');if(stopB)stopB.innerHTML='<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style="margin-right:8px;"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>'+t['btn-stop'];
var saveB=document.getElementById('save-btn');if(saveB)saveB.innerHTML='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px;"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>'+t['btn-save'];
var saveFb=document.getElementById('save-fb');if(saveFb)saveFb.textContent=t['saved'];
localStorage.setItem('vsfx_lang',lang);
}
document.addEventListener('DOMContentLoaded',function(){var saved=localStorage.getItem('vsfx_lang');if(saved)setLang(saved);});
</script>
</body>
</html>
"""

# ─────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import base64
    import webview

    # LICENSE CHECK DISABLED
    # ok, msg = _check_license()
    # if not ok:
    #     if msg == "NEED_ACTIVATION":
    #         if not _show_activation_dialog():
    #             sys.exit(0)
    #     else:
    #         import tkinter as tk
    #         from tkinter import messagebox
    #         root = tk.Tk(); root.withdraw()
    #         messagebox.showerror("Licenza non autorizzata", msg + "\n\nContatta il supporto: vaultsystemassistence@gmail.com")
    #         root.destroy(); sys.exit(0)

    html_file = _INTERNAL / "index.html"
    if html_file.exists():
        with open(html_file, "r", encoding="utf-8") as f:
            page_html = f.read()
    else:
        page_html = HTML

    api    = Api()
    window = webview.create_window(
        "VaultSystemFx", html=page_html, js_api=api,
        width=1440, height=820, resizable=True,
        background_color="#06080d",
        min_size=(1000, 700),
        frameless=True,
        easy_drag=True,
    )
    webview.start(debug=False)