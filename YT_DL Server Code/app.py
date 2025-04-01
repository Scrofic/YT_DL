import os
import sys
from uuid import uuid4
from flask import Flask, request, render_template, jsonify, Response
from urllib.parse import quote
import yt_dlp as youtube_dl

# ----------------------------------------------------------------
# 輸出過濾器：過濾掉包含 "Running on" 的訊息
# ----------------------------------------------------------------
class FilterStream:
    def __init__(self, stream):
        self.stream = stream
    def write(self, s):
        if "Running on" in s:
            return  # 過濾掉包含 "Running on" 的訊息
        self.stream.write(s)
    def flush(self):
        self.stream.flush()

sys.stdout = FilterStream(sys.stdout)
sys.stderr = FilterStream(sys.stderr)

# ----------------------------------------------------------------
# 資源路徑處理：根據執行環境（開發 vs 打包）返回正確路徑
# ----------------------------------------------------------------
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS  # cx_Freeze or PyInstaller 打包後會存在
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# ----------------------------------------------------------------
# Flask 與應用程式邏輯
# ----------------------------------------------------------------
# 直接使用已打包進 .exe 中的 yt_dlp 模組
app = Flask(__name__,
            static_folder=resource_path("static"),
            template_folder=resource_path("templates"))

# 使用 tasks 字典存放每個下載任務的進度與狀態
tasks = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    # 為此次下載請求生成一個隨機 task_id
    task_id = str(uuid4())
    tasks[task_id] = {'progress': '0%', 'completed': False}

    url_link = request.form['url']
    fmt = request.form['format']

    # 根據格式選擇不同的 yt-dlp 參數
    if fmt == 'mp3':
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'downloads/%(title)s_{task_id}.%(ext)s',
            'ffmpeg_location': resource_path('ffmpeg.exe'),
            'progress_hooks': [lambda d: progress_hook(d, task_id)],
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
    else:  # mp4 模式
        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': f'downloads/%(title)s_{task_id}.%(ext)s',
            'ffmpeg_location': resource_path('ffmpeg.exe'),
            'progress_hooks': [lambda d: progress_hook(d, task_id)],
            'merge_output_format': 'mp4'
        }

    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url_link, download=True)
            file_path = ydl.prepare_filename(info_dict)

        # 如果是 mp3 模式，更新檔案副檔名
        if fmt == 'mp3':
            file_path = os.path.splitext(file_path)[0] + ".mp3"

        tasks[task_id]['completed'] = True

        if not os.path.exists(file_path):
            app.logger.error(f"檔案不存在：{file_path}")
            return jsonify({'status': '失敗', 'error': f"檔案不存在：{file_path}", 'task_id': task_id}), 404

        def generate():
            try:
                with open(file_path, "rb") as f:
                    while True:
                        chunk = f.read(8192)
                        if not chunk:
                            break
                        yield chunk
            finally:
                try:
                    os.remove(file_path)
                    app.logger.info(f"已刪除檔案：{file_path}")
                except Exception as e:
                    app.logger.error(f"刪除檔案 {file_path} 時發生錯誤：{e}")

        response = Response(generate(), mimetype="application/octet-stream")
        filename = os.path.basename(file_path)
        quoted_filename = quote(filename)
        response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quoted_filename}"
        response.headers["X-Task-ID"] = task_id

        return response

    except Exception as e:
        tasks[task_id]['completed'] = True
        app.logger.error(f"下載失敗：{str(e)}")
        return jsonify({'status': '失敗', 'error': str(e), 'task_id': task_id}), 500

def progress_hook(d, task_id):
    if d.get('status') == 'downloading':
        tasks[task_id]['progress'] = d.get('_percent_str', tasks[task_id]['progress'])
    elif d.get('status') == 'finished':
        tasks[task_id]['progress'] = '100%'

@app.route('/progress', methods=['GET'])
def progress_status():
    task_id = request.args.get('task_id')
    if not task_id:
        return jsonify({'status': '失敗', 'error': '缺少 task_id 參數'}), 400
    task_info = tasks.get(task_id)
    if not task_info:
        return jsonify({'status': '失敗', 'error': '未知的 task_id'}), 404
    return jsonify(task_info)

if __name__ == '__main__':
    if not os.path.exists('downloads'):
        os.makedirs('downloads')
    try:
        app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
    except KeyboardInterrupt:
        print("\n服務器偵測到 Ctrl+C，正在關閉...")
    finally:
        input("服務器已停止，請按 Enter 鍵退出...")