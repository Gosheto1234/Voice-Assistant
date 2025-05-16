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
        time.sleep(2)  # Let the old process fully exit

        # Optional: Rename old file before replacement
        backup = old_file + ".bak"
        if os.path.exists(backup):
            os.remove(backup)
        os.rename(old_file, backup)

        # Move new file into place
        shutil.move(new_file, old_file)
        with open("just_updated.flag", "w") as f:
            f.write(new_file)  # or the new version tag
        print("Replacement done.")

        # Relaunch the updated app
        updater_exe = sys.executable
        subprocess.Popen([old_file], close_fds=True)
        print("App restarted.")

    except Exception as e:
        print(f"Update failed: {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()
