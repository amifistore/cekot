#!/usr/bin/env python3
import os
import sys
import signal
import subprocess

def cleanup_bot_processes():
    """Clean up any leftover bot processes"""
    print("🔄 Cleaning up bot processes...")
    
    try:
        # Untuk Windows
        if os.name == 'nt':
            result = subprocess.run(['tasklist', '/fi', 'imagename eq python.exe'], 
                                  capture_output=True, text=True)
            lines = result.stdout.split('\n')
            for line in lines:
                if 'python' in line.lower() and 'main.py' in line.lower():
                    parts = line.split()
                    if len(parts) > 1:
                        pid = parts[1]
                        os.kill(int(pid), signal.SIGTERM)
                        print(f"✅ Stopped process PID: {pid}")
        
        # Untuk Linux/Mac
        else:
            # Cari proses Python yang menjalankan bot
            result = subprocess.run(['pgrep', '-f', 'python.*main.py'], 
                                  capture_output=True, text=True)
            if result.stdout:
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    if pid:
                        os.kill(int(pid), signal.SIGTERM)
                        print(f"✅ Stopped process PID: {pid}")
            
            # Hapus lock file
            lock_file = "bot_instance.lock"
            if os.path.exists(lock_file):
                os.remove(lock_file)
                print("✅ Removed lock file")
    
    except Exception as e:
        print(f"❌ Cleanup error: {e}")
    
    print("✅ Cleanup completed!")

if __name__ == '__main__':
    cleanup_bot_processes()
