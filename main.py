import os
import shutil
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import Signal, QObject, QRunnable, Slot, QThreadPool
from PySide6.QtGui import QFont, QIcon, QColor, QTextCharFormat
from PySide6.QtWidgets import (QApplication, QMainWindow, QPushButton, QTextEdit,
                               QVBoxLayout, QWidget)


class ResourceManager:
    """资源管理器，处理打包和开发环境的资源访问"""

    @staticmethod
    def get_resource_path(relative_path):
        """获取资源路径（适配打包和开发环境）"""
        if hasattr(sys, '_MEIPASS'):
            # 打包后的临时目录
            base_path = Path(sys._MEIPASS)
        else:
            # 开发环境
            base_path = Path(__file__).parent

        # 处理路径中的斜杠
        path = base_path / relative_path
        return str(path).replace('\\', '/')  # 统一使用正斜杠

    @staticmethod
    def get_temp_path(relative_path):
        """获取临时文件路径（用于需要写入的文件）"""
        temp_dir = Path(tempfile.gettempdir()) / "sublime_crack_temp"
        temp_dir.mkdir(exist_ok=True)
        return str(temp_dir / relative_path)


class WorkerSignals(QObject):
    output = Signal(str, str)  # 文本和颜色
    finished = Signal()
    error = Signal(str)


class Worker(QRunnable):
    def __init__(self, app_name, source_file_path):
        super(Worker, self).__init__()
        self.app_name = app_name
        self.source_file_path = source_file_path
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        install_dir = None

        try:
            self.signals.output.emit(f"开始查找 {self.app_name} 的安装目录...", "normal")

            # 检查环境变量
            env_var = f"{self.app_name.upper().replace(' ', '_')}_PATH"
            if env_var in os.environ:
                install_dir = Path(os.environ[env_var])
                self.signals.output.emit(f"从环境变量 {env_var} 中找到安装目录: {install_dir}", "success")
            else:
                self.signals.output.emit(f"环境变量 {env_var} 不存在，继续查找...", "normal")

                # 常见安装位置
                common_paths = [
                    Path(f"C:\\Program Files\\{self.app_name}"),
                    Path(f"C:\\Program Files (x86)\\{self.app_name}"),
                    Path(os.environ.get("LOCALAPPDATA", "")) / self.app_name,
                    Path(os.environ.get("APPDATA", "")) / self.app_name,
                ]

                self.signals.output.emit("检查常见安装位置...", "normal")
                for path in common_paths:
                    self.signals.output.emit(f"  检查: {path}", "normal")
                    if path.exists():
                        install_dir = path
                        self.signals.output.emit(f"在常见位置找到安装目录: {install_dir}", "success")
                        break
                else:
                    self.signals.output.emit("在常见位置未找到安装目录，尝试从注册表查找...", "normal")

                    try:
                        import winreg
                        self.signals.output.emit("成功导入 winreg 模块", "normal")
                    except ImportError:
                        winreg = None # 确保变量赋值
                        self.signals.output.emit("无法导入 winreg 模块，跳过注册表查询", "warning")
                        raise FileNotFoundError(f"未能找到 {self.app_name} 的安装目录")

                    # 只有成功导入winreg才执行注册表查询
                    if winreg is not None:
                        keys = [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]
                        subkey = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"

                        self.signals.output.emit("正在查询注册表...", "normal")

                        for key in keys:
                            try:
                                with winreg.OpenKey(key, subkey) as uninstall_key:
                                    i = 0
                                    while True:
                                        try:
                                            subkey_name = winreg.EnumKey(uninstall_key, i)
                                            with winreg.OpenKey(uninstall_key, subkey_name) as app_key:
                                                try:
                                                    display_name, _ = winreg.QueryValueEx(app_key, "DisplayName")
                                                    if self.app_name.lower() in display_name.lower():
                                                        self.signals.output.emit(f"在注册表中找到应用: {display_name}", "success")
                                                        install_location, _ = winreg.QueryValueEx(app_key, "InstallLocation")
                                                        install_dir = Path(install_location)
                                                        self.signals.output.emit(f"从注册表获取安装目录: {install_dir}", "success")
                                                        break
                                                except (FileNotFoundError, OSError):
                                                    pass
                                            i += 1
                                        except WindowsError:
                                            break
                            except WindowsError:
                                pass

                    if install_dir is None:
                        raise FileNotFoundError(f"未能找到 {self.app_name} 的安装目录")

            # 处理源文件路径
            source_path = ResourceManager.get_resource_path(self.source_file_path)
            if not os.path.exists(source_path):
                raise FileNotFoundError(f"源文件不存在: {source_path}")

            if not install_dir.exists():
                raise NotADirectoryError(f"目标目录不存在: {install_dir}")

            target_file = install_dir / os.path.basename(source_path)

            # 创建备份
            if target_file.exists():
                backup_file = install_dir / f"{os.path.basename(source_path)}.bak"
                self.signals.output.emit(f"正在创建备份: {backup_file}", "normal")
                shutil.copy2(target_file, backup_file)
                self.signals.output.emit("备份创建完成", "success")

            # 执行破解
            self.signals.output.emit("正在执行破解...", "normal")
            shutil.copy2(source_path, target_file)
            self.signals.output.emit("破解成功！", "success")

        except Exception as e:
            self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sublime Text Crack")
        self.resize(400, 300)

        # 设置应用图标
        self.setup_icon()

        # 配置
        self.app_name = "Sublime Text"
        self.source_file_path = "crack/sublime_text.exe"  # 修改为相对路径

        # 初始化UI
        self.init_ui()

    def setup_icon(self):
        """加载应用图标"""
        try:
            icon_path = ResourceManager.get_resource_path("sublime_text.png")
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except Exception as e:
            print(f"加载图标失败: {e}")

    def init_ui(self):
        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 输出文本框
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Consolas", 10))
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 5px;
                padding: 8px;
            }
        """)
        layout.addWidget(self.text_edit)

        # 执行按钮
        self.execute_button = QPushButton("Crack")
        self.execute_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.execute_button.setMinimumHeight(40)
        self.execute_button.clicked.connect(self.start_task)
        layout.addWidget(self.execute_button)

        self.setCentralWidget(central_widget)

        # 线程池
        self.threadpool = QThreadPool()
        self.is_executing = False

        # 初始化输出
        self.append_output('准备就绪，点击"Crack"按钮开始操作', "normal")

    def start_task(self):
        if self.is_executing:
            return

        self.text_edit.clear()
        self.execute_button.setEnabled(False)
        self.is_executing = True

        worker = Worker(self.app_name, self.source_file_path)
        worker.signals.output.connect(self.append_output)
        worker.signals.finished.connect(self.task_finished)
        worker.signals.error.connect(self.handle_error)
        self.threadpool.start(worker)

    def append_output(self, text, level="normal"):
        text_format = QTextCharFormat()
        colors = {
            "success": "#2e7d32",
            "warning": "#f57c00",
            "error": "#c62828",
            "normal": "#000000"
        }
        text_format.setForeground(QColor(colors.get(level, "#000000")))

        cursor = self.text_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.setCharFormat(text_format)
        cursor.insertText(text + "\n")
        self.text_edit.setTextCursor(cursor)
        self.text_edit.ensureCursorVisible()
        QApplication.processEvents()

    def handle_error(self, error_message):
        self.append_output(f"错误: {error_message}", "error")

    def task_finished(self):
        self.execute_button.setText("完成")
        self.execute_button.setEnabled(True)
        self.is_executing = False

        # 更新按钮样式
        self.execute_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
        """)

        # 重新绑定点击事件
        self.execute_button.clicked.disconnect()
        self.execute_button.clicked.connect(self.close_application)

    def close_application(self):
        QApplication.quit()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet("QMainWindow { background-color: #f0f0f0; }")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())