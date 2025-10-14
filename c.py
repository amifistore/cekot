import os
import time

print("🧨 Force killing semua proses Python...")
os.system('pkill -9 -f python')
time.sleep(5)
print("✅ Semua proses dihentikan!")
print("🚀 Menjalankan bot...")
os.system('python main.py')
