import ctypes
import os
import sys

# 获取DLL路径
current_dir = os.path.dirname(os.path.abspath(__file__))
dll_path = os.path.join(current_dir, "mylib.dll")

# 加载DLL
try:
    mylib = ctypes.CDLL(dll_path)
    print("DLL loaded successfully!")
except Exception as e:
    print(f"Error loading DLL: {e}")
    sys.exit(1)

# 设置函数参数和返回类型
mylib.Add.argtypes = [ctypes.c_int, ctypes.c_int]
mylib.Add.restype = ctypes.c_int

mylib.Multiply.argtypes = [ctypes.c_int, ctypes.c_int]
mylib.Multiply.restype = ctypes.c_int

mylib.Greet.argtypes = [ctypes.c_char_p]
mylib.Greet.restype = ctypes.c_char_p

mylib.PrintMessage.argtypes = [ctypes.c_char_p]
mylib.PrintMessage.restype = None

# 测试函数
if __name__ == "__main__":
    # 测试整数运算
    result_add = mylib.Add(5, 3)
    print(f"5 + 3 = {result_add}")

    result_mul = mylib.Multiply(5, 3)
    print(f"5 * 3 = {result_mul}")

    # 测试字符串处理
    name = "World".encode('utf-8')
    greeting = mylib.Greet(name)
    print(greeting.decode('utf-8'))

    # 测试无返回值的函数
    msg = "This is a test message".encode('utf-8')
    mylib.PrintMessage(msg)