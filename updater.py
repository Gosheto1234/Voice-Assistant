import sys
import os
import shutil
import time
import subprocess

def main():
    if len(sys.argv) != 3:
        print("Usage: updater.exe <new_file.exe> <old_file.exe>")
        time.sleep(3)
        return

    new_file = sys.argv[1]
    old_file = sys.argv[2]

    print(f"Replacing {old_file} with {new_file}")

    try:
        # Wait for old process to fully exit
        time.sleep(2)

        # On Windows, you can't overwrite a running exe,
        # so we rename the old one first (optional)
        backup = old_file + ".bak"
        if os.path.exists(backup):
            os.remove(backup)
        os.rename(old_file, backup)

        # Move new file into place
        shutil.move(new_file, old_file)
        print("Replacement done.")

        # Relaunch the updated app
        subprocess.Popen([old_file])
        print("App restarted.")

    except Exception as e:
        print(f"Update failed: {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()
