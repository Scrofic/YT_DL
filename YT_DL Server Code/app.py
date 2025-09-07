import os
import sys
import socket
from uuid import uuid4
from flask import Flask, request, render_template, jsonify, Response
from urllib.parse import quote
import yt_dlp as youtube_dl
import time
import logging

class FilterStream:
    def __init__(self, stream):
        self.stream = stream

    def write(self, s):
        ignore_phrases = [
            "Running on http://",
            "Press CTRL+C to quit",
            "WARNING: This is a development server.",
            "Do not use it in a production deployment.",
            "Use a production WSGI server instead."
        ]
        if any(phrase in s for phrase in ignore_phrases):
            return  # 過濾啟動訊息
        self.stream.write(s)

    def flush(self):
        self.stream.flush()

sys.stderr = FilterStream(sys.stderr)

def resource_path(relative_path):
    """ 獲取資源的絕對路徑，適用打包環境 """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_port():
    """ 讀取或創建 port.txt 以獲取端口號 """
    port_file = "port.txt"
    default_port = 5000
    port_to_use = default_port
    if not os.path.exists(port_file):
        try:
            with open(port_file, "w") as f:
                f.write(str(default_port))
            print(f"port.txt 不存在，已建立並設定預設端口號：{default_port}")
            port_to_use = default_port
        except Exception as e:
            print(f"[ERROR] 建立 port.txt 發生錯誤：{e}，使用預設端口號：{default_port}")
            port_to_use = default_port
    else:
        try:
            with open(port_file, "r") as f:
                port_str = f.read().strip()
            if not port_str:
                print(f"[INFO] port.txt 為空，使用預設端口號：{default_port}")
                port_to_use = default_port
                try: # 寫回預設值
                    with open(port_file, "w") as f:
                        f.write(str(default_port))
                except Exception as e:
                    print(f"[WARNING] 無法將預設端口寫回 port.txt: {e}")
            else:
                try:
                    port_to_use = int(port_str)
                    print(f"從 port.txt 讀取到端口號：{port_to_use}")
                except ValueError:
                    print(f"[ERROR] port.txt 內容 '{port_str}' 不是有效的端口號，使用預設端口號：{default_port}")
                    port_to_use = default_port
        except Exception as e:
            print(f"[ERROR] 讀取 port.txt 發生錯誤：{e}，使用預設端口號：{default_port}")
            port_to_use = default_port

    # 端口範圍檢查
    if not 1024 <= port_to_use <= 65535:
        print(f"[WARNING] 端口號 {port_to_use} 不在範圍 (1024-65535)，將使用預設端口號 {default_port}")
        port_to_use = default_port

    return port_to_use

# 邏輯
app = Flask(__name__,
            static_folder=resource_path("static"),
            template_folder=resource_path("templates"))

# 配置 Flask 日誌記錄
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

app.logger.setLevel(logging.INFO)

# 存放下載進度與狀態
tasks = {}

@app.route('/')
def index():
    """ 提供主頁面 """
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    """ 處理下載請求 """
    task_id = str(uuid4())
    tasks[task_id] = {'progress': '0%', 'completed': False, 'status': '初始化', 'error': None}

    url_link = request.form['url']
    fmt = request.form['format']
    tasks[task_id]['status'] = '準備下載'
    app.logger.info(f"任務 {task_id}: 收到請求，URL: {url_link}, 格式: {fmt}")

    # mp3 格式
    if fmt == 'mp3':
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': 'downloads/%(title)s - %(id)s.%(ext)s',
            'ffmpeg_location': resource_path('ffmpeg.exe'),
            'progress_hooks': [lambda d: progress_hook(d, task_id)],
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'postprocessor_args': ['-loglevel', 'error'],
            'nocheckcertificate': True,
            'quiet': True,
            'no_warnings': True,
            'logtostderr': False,
        }
    # mov 格式
    elif fmt == 'mov':
        ydl_opts = {

            'format': 'bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio/best[ext=mp4]/best',
            'outtmpl': 'downloads/%(title)s - %(id)s.%(ext)s',
            'ffmpeg_location': resource_path('ffmpeg.exe'),
            'progress_hooks': [lambda d: progress_hook(d, task_id)],
            # 合併成 mov 格式
            'merge_output_format': 'mov',
            # 限制 FFmpeg 的輸出日誌
            'postprocessor_args': ['-loglevel', 'error'],
            'nocheckcertificate': True,
            'quiet': True,
            'no_warnings': True,
            'logtostderr': False,
        }
    # mp4 格式
    else:
        ydl_opts = {
            'format': 'bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio/best[ext=mp4]/best',
            'outtmpl': 'downloads/%(title)s - %(id)s.%(ext)s',
            'ffmpeg_location': resource_path('ffmpeg.exe'),
            'progress_hooks': [lambda d: progress_hook(d, task_id)],
            'merge_output_format': 'mp4',
            'postprocessor_args': ['-c:a', 'aac', '-b:a', '192k', '-loglevel', 'error'],
            'nocheckcertificate': True,
            'quiet': True,
            'no_warnings': True,
            'logtostderr': False,
        }

    try:
        tasks[task_id]['status'] = '下載中'
        app.logger.info(f"任務 {task_id}: 開始使用 yt-dlp 下載...")

        original_file_path = None # 記錄 yt-dlp 最初路徑

        # yt-dlp 下載
        with youtube_dl.YoutubeDL(ydl_opts) as ydl: # [16]
            info_dict = ydl.extract_info(url_link, download=False) # 獲取資訊
            original_file_path = ydl.prepare_filename(info_dict) # 獲取路徑
            app.logger.info(f"任務 {task_id}: yt-dlp 預期原始路徑: {original_file_path}")
            # 再執行下載和處理
            ydl.process_info(info_dict)

        # ---- 檔名修正 ----
        file_path = original_file_path # 默認使用原計算路徑

        if fmt == 'mp3':
            base_path = os.path.splitext(original_file_path)[0]
            expected_mp3_path = base_path + ".mp3"
            app.logger.info(f"任務 {task_id}: MP3 格式，檢查實際 MP3 路徑: {expected_mp3_path}")
            if os.path.exists(expected_mp3_path):
                file_path = expected_mp3_path
                app.logger.info(f"任務 {task_id}: 找到 MP3 檔案，更新路徑為: {file_path}")
            else:
                app.logger.warning(f"任務 {task_id}: 預期的 MP3 檔案 {expected_mp3_path} 未找到! 將使用原始計算路徑 {original_file_path}")

        elif fmt == 'mov':
            # 檢查是否需要修正路徑
            if not original_file_path.lower().endswith('.mov'):
                actual_mov_path = os.path.splitext(original_file_path)[0] + ".mov"
                app.logger.info(f"任務 {task_id}: MOV 格式，原始路徑非 mov，檢查實際 mov 路徑: {actual_mov_path}")
                if os.path.exists(actual_mov_path):
                    file_path = actual_mov_path
                    app.logger.info(f"任務 {task_id}: 找到實際 mov 檔案，更新路徑為: {file_path}")
                else:
                    app.logger.warning(f"任務 {task_id}: 預期的 MOV 檔案 {actual_mov_path} 未找到，將繼續使用原始路徑 {original_file_path}")

        elif fmt == 'mp4':
            # 檢查是否需要修正路徑
            if not original_file_path.lower().endswith('.mp4'):
                actual_mp4_path = os.path.splitext(original_file_path)[0] + ".mp4"
                app.logger.info(f"任務 {task_id}: MP4 格式，原始路徑非 mp4，檢查實際 mp4 路徑: {actual_mp4_path}")
                if os.path.exists(actual_mp4_path):
                    file_path = actual_mp4_path
                    app.logger.info(f"任務 {task_id}: 找到實際 mp4 檔案，更新路徑為: {file_path}")
                else:
                    app.logger.warning(f"任務 {task_id}: 預期的 MP4 檔案 {actual_mp4_path} 未找到，將繼續使用原始路徑 {original_file_path}")

        # 標註完成
        tasks[task_id]['completed'] = True
        tasks[task_id]['status'] = '下載完成，準備傳輸'
        app.logger.info(f"任務 {task_id}: 檔案準備就緒，最終檢查路徑: {file_path}")

        # 檢查最終的檔案路徑是否存在
        if not file_path or not os.path.exists(file_path):
            error_msg = f"最終檔案不存在於路徑：{file_path}"
            app.logger.error(f"任務 {task_id}: {error_msg}")
            tasks[task_id]['status'] = '失敗'
            tasks[task_id]['error'] = error_msg
            return jsonify({'status': '失敗', 'error': tasks[task_id]['error'], 'task_id': task_id}), 404

        # 讀取並傳輸文件內容
        def generate():
            bytes_sent = 0
            try:
                with open(file_path, "rb") as f:
                    while True:
                        chunk = f.read(8192)
                        if not chunk:
                            break
                        yield chunk
                        bytes_sent += len(chunk)
                # 傳輸完成更新狀態
                tasks[task_id]['status'] = '傳輸完成'
                app.logger.info(f"任務 {task_id}: 檔案傳輸完成 ({bytes_sent} bytes)，路徑: {file_path}")
            except Exception as e:
                 # 傳輸過程出錯
                 tasks[task_id]['status'] = '傳輸錯誤'
                 tasks[task_id]['error'] = f"讀取或傳輸檔案時出錯: {str(e)}"
                 app.logger.error(f"任務 {task_id}: 讀取/傳輸檔案 {file_path} 時發生錯誤：{e}")
            finally:
                # 刪除伺服器上的檔案
                try:
                    os.remove(file_path)
                    app.logger.info(f"任務 {task_id}: 已刪除檔案：{file_path}")
                except FileNotFoundError:
                     app.logger.warning(f"任務 {task_id}: 嘗試刪除檔案時未找到：{file_path}")
                except Exception as e:
                     app.logger.error(f"任務 {task_id}: 刪除檔案 {file_path} 時發生錯誤：{e}")

        # 創建響應對象
        response = Response(generate(), mimetype="application/octet-stream")
        filename = os.path.basename(file_path)
        quoted_filename = quote(filename)
        response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quoted_filename}"
        response.headers["X-Task-ID"] = task_id
        app.logger.info(f"任務 {task_id}: 開始向客戶端傳輸檔案: {filename}")

        return response

    except youtube_dl.utils.DownloadError as e:
        error_message = f"yt-dlp 下載錯誤: {str(e)}"
        tasks[task_id]['completed'] = True
        tasks[task_id]['status'] = '失敗'
        tasks[task_id]['error'] = error_message
        app.logger.error(f"任務 {task_id}: {error_message} (URL: {url_link})")
        return jsonify({'status': '失敗', 'error': tasks[task_id]['error'], 'task_id': task_id}), 500
    except Exception as e:
        error_message = f"處理下載請求時發生未知錯誤: {str(e)}"
        tasks[task_id]['completed'] = True
        tasks[task_id]['status'] = '失敗'
        tasks[task_id]['error'] = error_message
        app.logger.error(f"任務 {task_id}: {error_message} (URL: {url_link})", exc_info=True) # exc_info=True 記錄 traceback
        return jsonify({'status': '失敗', 'error': tasks[task_id]['error'], 'task_id': task_id}), 500

def progress_hook(d, task_id):
    """ yt-dlp 進度回調函數 """
    if task_id not in tasks:
        app.logger.warning(f"收到未知任務 {task_id} 的進度回調")
        return

    task = tasks[task_id]
    current_status_msg = task.get('status', '未知')
    is_completed = task.get('completed', False)

    # 避免 '傳輸中' 或 '傳輸完成' 被覆蓋
    if is_completed and '傳輸' in current_status_msg:
        return

    status = d.get('status')
    if status == 'downloading':
        progress_str = d.get('_percent_str', task.get('progress', '0%')).strip()
        speed_str = d.get('speed_str', d.get('speed', '? B/s'))
        eta_str = d.get('eta_str', d.get('eta', '?s'))
        total_bytes_str = d.get('_total_bytes_str', d.get('total_bytes_estimate_str', '?'))
        downloaded_bytes_str = d.get('_downloaded_bytes_str', d.get('downloaded_bytes', '? B')) # 兼容舊key

        task['progress'] = progress_str
        task['status'] = f"下載中: {downloaded_bytes_str}/{total_bytes_str} ({speed_str} @ ETA {eta_str})"

    elif status == 'error':
        error_detail = d.get('error', '未知下載錯誤')
        task['status'] = '下載出錯'
        task['error'] = str(error_detail)
        task['completed'] = True
        app.logger.error(f"任務 {task_id}: 進度報告錯誤: {error_detail}")

    elif status == 'finished':
        # 'finished' 單個文件下載完成
        task['progress'] = '100%'
        # 不立即覆蓋狀態
        if '下載中' in current_status_msg or current_status_msg == '準備下載':
            task['status'] = '下載/處理完成'
        app.logger.info(f"任務 {task_id}: 進度報告 'finished' 狀態.")

    elif status == 'postprocessing':
        # 獲取後處理信息
        postprocessor = d.get('postprocessor')
        if postprocessor:
            task['status'] = f"後處理中: {postprocessor}..."
            app.logger.info(f"任務 {task_id}: 進度報告 'postprocessing' 狀態: {postprocessor}")

@app.route('/progress', methods=['GET'])
def progress_status():
    """ 提供下載進度查詢 """
    task_id = request.args.get('task_id')
    if not task_id:
        return jsonify({'status': '失敗', 'error': '缺少 task_id 參數'}), 400

    task_info = tasks.get(task_id)
    if not task_info:
        return jsonify({
            'progress': 'N/A',
            'completed': False,
            'status': '任務未找到或已過期',
            'error': '未知的 task_id'
        }), 404

    # 返回任務信息
    return jsonify({
        'progress': task_info.get('progress', '0%'),
        'completed': task_info.get('completed', False),
        'status': task_info.get('status', '未知'),
        'error': task_info.get('error', None)
    })

# 主程式
if __name__ == '__main__':
    # 確保 downloads 資料夾存在
    downloads_dir = 'downloads'
    if not os.path.exists(downloads_dir):
        try:
            os.makedirs(downloads_dir)
            print(f"[INFO] '{downloads_dir}' 資料夾已建立。")
        except Exception as e:
            print(f"[ERROR] 無法建立 '{downloads_dir}' 資料夾: {e}")
            sys.exit(1)

    # 讀取或建立 port.txt
    port = get_port()

    # 嘗試獲取本機 IP 地址
    local_ip = "127.0.0.1"
    hostname = "未知主機"
    try:
        hostname = socket.gethostname()
        addr_info = socket.getaddrinfo(hostname, None)
        ipv4_ips = [info[4][0] for info in addr_info if info[0] == socket.AF_INET and not info[4][0].startswith('127.')]
        if ipv4_ips:
            local_ip = ipv4_ips[0]
        else:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            try:
                s.connect(("8.8.8.8", 80))
                lan_ip = s.getsockname()[0]
                if not lan_ip.startswith('127.'):
                    local_ip = lan_ip
            except socket.error:
                pass # 連接失敗，保持 127.0.0.1
            finally:
                s.close()
    except socket.gaierror:
        print(f"[WARNING] 無法解析主機名 '{hostname}'。")
    except Exception as e:
        print(f"[WARNING] 獲取內網 IP 時出錯: {e}")

    # 顯示連線網址
    print("============================================")
    print(f"伺服器準備在端口 {port} 上啟動...")
    print("請在瀏覽器中開啟以下任一網址：")
    print(f"  (本機存取) http://localhost:{port}")
    if local_ip != "127.0.0.1":
        print(f"  (內網存取，可能有效) http://{local_ip}:{port}")
    else:
        print("  (內網存取) 未能自動檢測到有效的內網 IP 地址。")
    print("============================================")
    print("Ctrl+C 停止伺服器。")

    # 啟動伺服器
    try:
        # 使用 Flask 內建伺服器，debug=False 以啟用輸出過濾並減少資源消耗
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False, threaded=True)

    except PermissionError:
        print(f"\n[ERROR] 權限錯誤：無法在端口 {port} 上監聽。請檢查端口是否已被佔用或需要管理員權限。")
    except OSError as e:
        if "address already in use" in str(e).lower() or "僅允許使用一次通訊端位址" in str(e):
            print(f"\n[ERROR] 端口 {port} 已被佔用。請關閉使用該端口的其他程序或在 port.txt 中指定其他端口。")
        else:
            print(f"\n[ERROR] 伺服器啟動失敗 (OSError): {e}")
    except KeyboardInterrupt:
        print("\n偵測到 Ctrl+C，正在關閉伺服器...")
    except Exception as e:
        print(f"\n[ERROR] 伺服器意外終止: {e}", file=sys.stderr)
    finally:
        time.sleep(0.5)
        print("伺服器已停止。")
