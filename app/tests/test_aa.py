
import pandas as pd
import matplotlib.pyplot as plt

# df = pd.read_json("note.json")
# df['created_at'] = pd.to_datetime(df['created_at'])
#
# df.set_index('created_at').resample('D').size().plot(kind='line')
# plt.show()



import numpy as np
import matplotlib
matplotlib.use('TkAgg')  # 或 'Qt5Agg'（如果你安装了 PyQt5）
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, Button

# 初始参数
freq_init = 2.0
amp_init = 1.0

# 生成 x 数据
x = np.linspace(0, 2 * np.pi, 500)

# 创建图形和轴
fig, ax = plt.subplots(figsize=(10, 6))
plt.subplots_adjust(left=0.25, bottom=0.3)  # 留出空间放控件

# 初始 y 数据
y = amp_init * np.sin(freq_init * x)
line, = ax.plot(x, y, lw=2, color='blue')
ax.set_ylim(-3, 3)
ax.set_title('Interactive Sine Wave\nUse sliders to adjust frequency and amplitude')

# 创建滑块区域
ax_freq = plt.axes([0.25, 0.15, 0.5, 0.03])  # [left, bottom, width, height]
ax_amp = plt.axes([0.25, 0.10, 0.5, 0.03])

# 创建滑块
slider_freq = Slider(ax_freq, 'Frequency', 0.1, 10.0, valinit=freq_init)
slider_amp = Slider(ax_amp, 'Amplitude', 0.1, 3.0, valinit=amp_init)

# 更新函数
def update(val):
    freq = slider_freq.val
    amp = slider_amp.val
    line.set_ydata(amp * np.sin(freq * x))
    fig.canvas.draw_idle()

# 绑定滑块事件
slider_freq.on_changed(update)
slider_amp.on_changed(update)

# 创建重置按钮
ax_reset = plt.axes([0.8, 0.02, 0.1, 0.04])
button_reset = Button(ax_reset, 'Reset', color='lightgray', hovercolor='0.95')

def reset(event):
    slider_freq.reset()
    slider_amp.reset()

button_reset.on_clicked(reset)

# 显示图形（会弹出交互窗口）
plt.show()


