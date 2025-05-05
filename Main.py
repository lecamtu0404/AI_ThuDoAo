# main.py
import sys
import os
import shutil
from datetime import datetime
import google.generativeai as genai
from PIL import Image

from PyQt6.QtWidgets import (QApplication, QMainWindow, QLabel, QPushButton, 
                           QVBoxLayout, QHBoxLayout, QWidget, QFileDialog, 
                           QTextEdit, QMessageBox, QInputDialog, QLineEdit,
                           QFrame, QScrollArea, QGridLayout)
from PyQt6.QtGui import QPixmap, QFont
from PyQt6.QtCore import Qt, QThread, pyqtSignal

# Thư mục lưu trữ
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'results'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def read_api_key():
    """Đọc API key từ file"""
    try:
        with open('api_key.txt', 'r') as file:
            return file.read().strip()
    except:
        return None

class ImageDropZone(QFrame):
    """Widget khu vực chọn ảnh"""
    clicked = pyqtSignal()
    
    def __init__(self, title, placeholder_text):
        super().__init__()
        self.title = title
        self.placeholder_text = placeholder_text
        self.image_path = None
        self.init_ui()
        self.setAcceptDrops(True)
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Tiêu đề
        title_label = QLabel(self.title)
        title_label.setStyleSheet('font-size: 16pt; font-weight: bold;')
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Khung chứa ảnh
        self.content_frame = QFrame()
        self.content_frame.setStyleSheet('QFrame {background-color: #f7f7f7; border: 2px dashed #cccccc; border-radius: 10px;}')
        content_layout = QVBoxLayout(self.content_frame)
        
        # Text hướng dẫn
        self.placeholder_label = QLabel(self.placeholder_text)
        self.placeholder_label.setStyleSheet('font-size: 12pt; color: #777;')
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Ảnh thumbnail
        self.thumbnail = QLabel()
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail.setVisible(False)
        self.thumbnail.setFixedSize(150, 150)
        self.thumbnail.setScaledContents(True)
        
        content_layout.addWidget(self.placeholder_label)
        content_layout.addWidget(self.thumbnail)
        
        layout.addWidget(title_label)
        layout.addWidget(self.content_frame)
        
        # Kết nối sự kiện click
        self.content_frame.mousePressEvent = self.on_click
        
    def on_click(self, event):
        self.clicked.emit()
        
    def set_image(self, image_path):
        if image_path and os.path.exists(image_path):
            self.image_path = image_path
            pixmap = QPixmap(image_path)
            self.thumbnail.setPixmap(pixmap)
            self.thumbnail.setVisible(True)
            self.placeholder_label.setVisible(False)
        else:
            self.reset()
            
    def reset(self):
        self.image_path = None
        self.thumbnail.setVisible(False)
        self.placeholder_label.setVisible(True)
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            file_path = event.mimeData().urls()[0].toLocalFile()
            self.set_image(file_path)
            event.acceptProposedAction()

class ResultCard(QFrame):
    """Widget hiển thị kết quả"""
    def __init__(self, id):
        super().__init__()
        self.id = id
        self.result_image_path = None
        self.init_ui()
        
    def init_ui(self):
        self.setStyleSheet('QFrame {background-color: white; border-radius: 12px; border: 1px solid #e0e0e0;}')
        
        layout = QVBoxLayout(self)
        
        # Khung ảnh kết quả
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setText("Chưa có kết quả")
        self.image_label.setStyleSheet('background-color: #f7f7f7; border-radius: 8px; color: #777; font-size: 14pt;')
        self.image_label.setMinimumSize(200, 280)
        
        # Nút lưu kết quả
        self.save_btn = QPushButton("Lưu ảnh")
        self.save_btn.setEnabled(False)
        self.save_btn.setStyleSheet('QPushButton {background-color: #3a86ff; border-radius: 6px; color: white; padding: 6px 12px;}'
                                    'QPushButton:disabled {background-color: #cccccc;}')
        
        layout.addWidget(self.image_label)
        layout.addWidget(self.save_btn)
        
    def display_image(self, image_path):
        self.result_image_path = image_path
        pixmap = QPixmap(image_path)
        self.image_label.setPixmap(pixmap.scaled(
            self.image_label.width(), 
            self.image_label.height(),
            Qt.AspectRatioMode.KeepAspectRatio
        ))
        self.save_btn.setEnabled(True)
        
    def update_progress(self, value):
        if value < 100:
            self.image_label.setText(f"Đang xử lý... {value}%")
            
    def save_image(self, parent):
        if not self.result_image_path:
            return
            
        save_path, _ = QFileDialog.getSaveFileName(
            parent, 
            f'Lưu Ảnh Kết Quả {self.id + 1}', 
            f'thudo_result_{self.id + 1}.png', 
            'PNG (*.png);;JPEG (*.jpg)'
        )
        
        if save_path:
            shutil.copy2(self.result_image_path, save_path)
            QMessageBox.information(parent, 'Thành công', f'Đã lưu ảnh vào: {save_path}')

class GeminiThread(QThread):
    """Thread xử lý API Gemini"""
    finished_signal = pyqtSignal(bool, str, int)
    progress_signal = pyqtSignal(int, int)
    
    def __init__(self, person_image, clothing_image, prompt, thread_id, api_key):
        super().__init__()
        self.person_image_path = person_image
        self.clothing_image_path = clothing_image
        self.prompt = prompt
        self.thread_id = thread_id
        self.api_key = api_key
        self.is_cancelled = False
        
    def run(self):
        try:
            if self.is_cancelled:
                return
                
            self.progress_signal.emit(30, self.thread_id)
            
            # Cấu hình API Gemini
            genai.configure(api_key=self.api_key)
            
            # Tải ảnh
            person_img = Image.open(self.person_image_path)
            clothing_img = Image.open(self.clothing_image_path)
            
            if self.is_cancelled:
                return
            self.progress_signal.emit(50, self.thread_id)
            
            # Khởi tạo mô hình Gemini
            model = genai.GenerativeModel("gemini-2.0-flash")
            
            # Cấu hình generation 
            temperature = 0.4 + (self.thread_id * 0.1)  # Tăng dần độ sáng tạo
            generation_config = {
                "response_modalities": ["TEXT", "IMAGE"],
                "temperature": temperature,
                "top_k": 32,
                "top_p": 1,
                "max_output_tokens": 2048,
            }
            
            if self.is_cancelled:
                return
            self.progress_signal.emit(70, self.thread_id)
                
            # Gọi API
            response = model.generate_content(
                [self.prompt, person_img, clothing_img],
                generation_config=generation_config
            )
            
            if self.is_cancelled:
                return
            self.progress_signal.emit(90, self.thread_id)
            
            # Xử lý kết quả
            result_image_path = None
            
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'inline_data'):
                    # Lưu ảnh kết quả
                    result_image_path = os.path.join(OUTPUT_FOLDER, f"result_{self.thread_id}_{int(datetime.now().timestamp())}.png")
                    with open(result_image_path, "wb") as f:
                        f.write(part.inline_data.data)
                    break
            
            if result_image_path and not self.is_cancelled:
                self.progress_signal.emit(100, self.thread_id)
                self.finished_signal.emit(True, result_image_path, self.thread_id)
            elif not self.is_cancelled:
                raise Exception(f"API không trả về ảnh kết quả")
                
        except Exception as e:
            if not self.is_cancelled:
                self.finished_signal.emit(False, str(e), self.thread_id)
    
    def cancel(self):
        self.is_cancelled = True

class TryOnApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.person_image_path = None
        self.clothing_image_path = None
        self.result_cards = []
        self.gemini_threads = []
        
        self.init_ui()
        
    def init_ui(self):
        # Thiết lập cửa sổ chính
        self.setWindowTitle('Ứng dụng Thử Đồ Ảo bằng AI')
        self.setMinimumSize(1000, 700)
        
        # Widget chính
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        
        # Panel bên trái - Chọn ảnh
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_panel.setMaximumWidth(400)
        
        # Khu vực ảnh người
        self.person_drop_zone = ImageDropZone('Ảnh Người', 'Chọn ảnh người')
        self.person_drop_zone.clicked.connect(self.upload_person_image)
        
        # Khu vực ảnh quần áo
        self.clothing_drop_zone = ImageDropZone('Ảnh Quần Áo', 'Chọn ảnh quần áo')
        self.clothing_drop_zone.clicked.connect(self.upload_clothing_image)
        
        # Phần prompt
        prompt_label = QLabel('Prompt:')
        prompt_label.setStyleSheet('font-size: 14pt; font-weight: bold;')
        
        self.prompt_text = QTextEdit()
        self.prompt_text.setPlaceholderText('Nhập hướng dẫn cho AI')
        self.prompt_text.setText('Tạo hình ảnh thử đồ ảo toàn thân. Giữ nguyên các đặc điểm khuôn mặt, kiểu tóc, tông màu da, tỷ lệ cơ thể.')
        self.prompt_text.setMaximumHeight(100)
        
        # Nút tạo ảnh
        self.generate_btn = QPushButton('Tạo ảnh thử đồ')
        self.generate_btn.setStyleSheet('QPushButton {font-size: 14pt; font-weight: bold; padding: 10px;'
                                        'background-color: #3a86ff; color: white; border-radius: 8px;}'
                                        'QPushButton:disabled {background-color: #a0c0ff;}')
        self.generate_btn.clicked.connect(self.generate_images)
        
        # Thêm các widget vào layout bên trái
        left_layout.addWidget(self.person_drop_zone)
        left_layout.addWidget(self.clothing_drop_zone)
        left_layout.addWidget(prompt_label)
        left_layout.addWidget(self.prompt_text)
        left_layout.addWidget(self.generate_btn)
        left_layout.addStretch()
        
        # Panel bên phải - Hiển thị kết quả
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Tiêu đề kết quả
        result_title = QLabel('Kết quả')
        result_title.setStyleSheet('font-size: 16pt; font-weight: bold;')
        
        # Tạo scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        
        results_container = QWidget()
        self.results_layout = QGridLayout(results_container)
        
        # Tạo 6 card kết quả
        NUM_RESULTS = 6
        COLS = 2
        
        for i in range(NUM_RESULTS):
            result_card = ResultCard(i)
            row = i // COLS
            col = i % COLS
            self.results_layout.addWidget(result_card, row, col)
            self.result_cards.append(result_card)
            
            # Kết nối nút lưu
            result_card.save_btn.clicked.connect(lambda checked=False, idx=i: self.result_cards[idx].save_image(self))
        
        scroll_area.setWidget(results_container)
        
        right_layout.addWidget(result_title)
        right_layout.addWidget(scroll_area)
        
        # Thêm các panel vào layout chính
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel, 3)  # Tỷ lệ 1:3
        
        # Thiết lập widget chính
        self.setCentralWidget(main_widget)
        
    def upload_person_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, 'Chọn Ảnh Người', '', 'Ảnh (*.png *.jpg *.jpeg *.gif)'
        )
        
        if file_path:
            self.person_image_path = file_path
            self.person_drop_zone.set_image(file_path)
            
    def upload_clothing_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, 'Chọn Ảnh Quần Áo', '', 'Ảnh (*.png *.jpg *.jpeg *.gif)'
        )
        
        if file_path:
            self.clothing_image_path = file_path
            self.clothing_drop_zone.set_image(file_path)
            
    def generate_images(self):
        # Hủy các thread đang chạy (nếu có)
        for thread in self.gemini_threads:
            if thread.isRunning():
                thread.cancel()
        self.gemini_threads.clear()
        
        if not self.person_image_path or not self.clothing_image_path:
            QMessageBox.warning(self, 'Cảnh báo', 'Vui lòng chọn cả ảnh người và ảnh quần áo!')
            return
            
        # Đọc API key
        api_key = read_api_key()
        
        # Kiểm tra API key
        if not api_key:
            api_key, ok = QInputDialog.getText(
                self, 'Nhập API key', 
                'Vui lòng nhập API key:',
                QLineEdit.EchoMode.Password
            )
            if not ok or not api_key:
                return
            
            # Lưu API key vào file
            with open('api_key.txt', 'w') as file:
                file.write(api_key)
                
        # Lấy prompt
        prompt = self.prompt_text.toPlainText().strip() or "Generate a virtual try-on image showing the person wearing the clothing."
        
        # Reset các card kết quả
        for card in self.result_cards:
            card.image_label.setText("Đang xử lý...")
            card.save_btn.setEnabled(False)
        
        # Vô hiệu hóa nút tạo ảnh
        self.generate_btn.setEnabled(False)
        
        # Tạo và khởi động các thread
        for i in range(len(self.result_cards)):
            thread = GeminiThread(self.person_image_path, self.clothing_image_path, prompt, i, api_key)
            thread.progress_signal.connect(self.update_progress)
            thread.finished_signal.connect(self.process_result)
            self.gemini_threads.append(thread)
            thread.start()
            
    def update_progress(self, value, thread_id):
        if thread_id < len(self.result_cards):
            self.result_cards[thread_id].update_progress(value)
        
    def process_result(self, success, message, thread_id):
        if thread_id >= len(self.result_cards):
            return
            
        if success:
            # Hiển thị ảnh kết quả
            self.result_cards[thread_id].display_image(message)
        else:
            # Hiển thị thông báo lỗi
            self.result_cards[thread_id].image_label.setText(f"Lỗi: {message}")
            
        # Kiểm tra nếu tất cả thread đã hoàn thành
        all_done = True
        for thread in self.gemini_threads:
            if thread.isRunning():
                all_done = False
                break
                
        if all_done:
            self.generate_btn.setEnabled(True)

def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    
    window = TryOnApp()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()