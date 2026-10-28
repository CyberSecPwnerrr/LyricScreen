from PyQt6.QtGui import QPainter


AA = (
    QPainter.RenderHint.Antialiasing
    | QPainter.RenderHint.TextAntialiasing
    | QPainter.RenderHint.SmoothPixmapTransform
)

BLEND = {
    "normal": QPainter.CompositionMode.CompositionMode_SourceOver,
    "screen": QPainter.CompositionMode.CompositionMode_Screen,
    "overlay": QPainter.CompositionMode.CompositionMode_Overlay,
    "soft": QPainter.CompositionMode.CompositionMode_SoftLight,
    "add": QPainter.CompositionMode.CompositionMode_Plus,
}

QSS_TEMPLATE = """
QDialog{background:@BG@;}
QWidget#side{background:@BG2A@;border-right:1px solid @LINE@;}
QWidget#main{background:transparent;}
QLabel{color:@TX@;background:transparent;}
QLabel#brand{color:@ACC@;font-size:13px;font-weight:800;letter-spacing:5px;padding:20px 18px 0px 18px;}
QLabel#title{font-size:22px;font-weight:700;color:@TX@;padding:18px 24px 2px 24px;}
QLabel#brand,QLabel#title{font-family:"@FAM@";}
QLabel#section{color:@ACC@;font-size:11px;font-weight:800;letter-spacing:3px;padding:1px 0 1px 10px;margin:14px 0 6px 0;border-left:3px solid @ACC@;}
QPushButton#sechead{background:transparent;border:none;border-bottom:1px solid @LINE@;border-radius:0px;color:@DIM@;font-size:11px;font-weight:800;letter-spacing:2px;text-align:left;padding:11px 24px 9px 2px;margin-top:6px;}
QPushButton#sechead:hover{background:transparent;color:@TX@;border-bottom:1px solid @ACC@;}
QPushButton#sechead:checked{color:@ACC@;}
QLabel#rowlabel{color:@TX@;font-size:12px;font-weight:600;}
QLabel#hint{color:@DIM@;font-size:11px;}
QLabel#nptitle{color:@TX@;font-size:11px;font-weight:700;}
QLabel#npartist{color:@DIM@;font-size:10px;}
QWidget#npcard{background:@SFA@;border:1px solid @LINE@;border-radius:10px;}
QListWidget#nav{background:transparent;border:none;outline:none;padding:4px 8px;}
QListWidget#nav::item{color:@DIM@;padding:8px 14px;border:none;background:transparent;font-size:12px;font-weight:600;}
QListWidget#nav::item:hover{color:@TX@;background:transparent;}
QListWidget#nav::item:selected{color:@TX@;background:transparent;}
QListWidget#nav[mstyle="compact"]{padding:2px 6px;}
QListWidget#nav[mstyle="compact"]::item{padding:5px 10px;font-size:11px;}
QListWidget#nav[mstyle="minimal"]{padding:6px 4px;}
QListWidget#nav[mstyle="minimal"]::item{padding:11px 0px;font-size:17px;font-weight:500;}
QListWidget#nav[mstyle="modern"]{padding:4px 14px;}
QListWidget#nav[mstyle="modern"]::item{padding:6px 8px;font-size:12px;}
QListWidget#nav[mstyle="fancy"]{padding:8px 10px;}
QListWidget#nav[mstyle="fancy"]::item{padding:13px 16px;font-size:13px;font-weight:700;}
QScrollArea{border:none;background:transparent;}
QScrollArea>QWidget>QWidget{background:transparent;}
QScrollBar:vertical{background:transparent;width:6px;margin:2px;}
QScrollBar::handle:vertical{background:@LINE@;border-radius:3px;min-height:30px;}
QScrollBar::handle:vertical:hover{background:@ACC@;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}
QPushButton{background:@SFA@;border:1px solid @LINE@;border-radius:8px;padding:6px 14px;color:@TX@;font-size:12px;font-weight:600;}
QPushButton:hover{border-color:@ACC@;background:@ACCA@;}
QPushButton:pressed{background:@ACCA2@;}
QPushButton:disabled{color:@DIM@;border-color:@LINE@;}
QPushButton#primary{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 @ACC@,stop:1 @SEC@);color:@BG@;border:none;font-weight:800;padding:7px 24px;}
QPushButton#primary:hover{background:@SEC@;}
QPushButton#seg{border-radius:8px;padding:6px 14px;}
QPushButton#seg:checked{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 @ACC@,stop:1 @SEC@);color:@BG@;border-color:@ACC@;font-weight:800;}
QPushButton#pos{background:@SFA@;border:1px solid @LINE@;border-radius:7px;color:@DIM@;font-size:10px;font-weight:700;padding:0;}
QPushButton#pos:checked{background:@ACCA2@;border-color:@ACC@;color:@TX@;}
QSlider::groove:horizontal{height:4px;background:@LINE@;border-radius:2px;}
QSlider::sub-page:horizontal{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 @ACC@,stop:1 @SEC@);border-radius:2px;}
QSlider::handle:horizontal{background:@TX@;width:12px;height:12px;margin:-5px 0;border-radius:6px;border:2px solid @ACC@;}
QSlider::handle:horizontal:hover{background:@ACC@;width:14px;height:14px;margin:-6px 0;border-radius:7px;border:2px solid @TX@;}
QComboBox,QSpinBox,QLineEdit{background:@SFA@;border:1px solid @LINE@;border-radius:8px;padding:5px 10px;color:@TX@;font-size:12px;selection-background-color:@ACC@;selection-color:@BG@;}
QComboBox:hover,QSpinBox:hover,QLineEdit:hover{border-color:@ACC@;}
QComboBox::drop-down{border:none;width:22px;}
QComboBox QAbstractItemView{background:@BG2@;color:@TX@;border:1px solid @LINE@;border-radius:8px;selection-background-color:@ACCA@;outline:none;padding:4px;}
QSpinBox::up-button,QSpinBox::down-button{width:0;border:none;}
QToolTip{background:@BG2@;color:@TX@;border:1px solid @ACC@;border-radius:6px;padding:5px;}
QMenu{background:@BG2@;color:@TX@;border:1px solid @LINE@;border-radius:10px;padding:6px;}
QMenu::item{padding:8px 26px 8px 18px;border-radius:7px;}
QMenu::item:selected{background:@ACCA@;}
QMenu::separator{height:1px;background:@LINE@;margin:5px 8px;}
QMenu::indicator{width:14px;height:14px;}
QMenu#glass{background:transparent;border:none;padding:9px;}
QMenu#glass::item{padding:9px 30px 9px 18px;border-radius:10px;margin:1px 0;}
QMenu#glass::item:selected{background:@ACCA2@;}
QMenu#glass::separator{height:1px;background:@LINE@;margin:6px 12px;}
"""
