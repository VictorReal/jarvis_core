import psutil
import os

def get_system_report():
    # 1. Завантаження процесора (CPU)
    cpu_usage = psutil.cpu_percent(interval=0.1)
    
    # 2. Температура (для Raspberry Pi 5)
    # На Pi 5 температура лежить у спеціальному системному файлі
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp = int(f.read()) / 1000  # Переводимо з міліградусів у градуси
    except:
        temp = 0.0 # Для тестів не на Linux

    # 3. Оперативна пам'ять (RAM)
    ram = psutil.virtual_memory()
    ram_usage = ram.percent

    # Формуємо чітку відповідь
    report = (f"Systems check complete. Core temperature is {temp:.1f} degrees Celsius. "
              f"CPU load is at {cpu_usage} percent, and memory usage is {ram_usage} percent. "
              "All systems are within operational limits, Sir.")
    
    return report