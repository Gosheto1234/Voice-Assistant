import sys, os, shutil, time, subprocess

def main():
    if len(sys.argv) != 3:
        print("Usage: updater.exe <new_file> <old_file>")
        time.sleep(3)
        return

    new_file, old_file = sys.argv[1], sys.argv[2]
    print(f"Replacing {old_file} with {new_file}")

    # give the original process a moment to fully exit
    time.sleep(2)

    # backup & remove the old exe
    bak = old_file + ".bak"
    if os.path.exists(bak):
        os.remove(bak)
    os.rename(old_file, bak)

    # move the new exe into place
    shutil.move(new_file, old_file)

    # clean up backup if you want, or leave it around
    os.remove(bak)

    # signal the main app that we just updated
    with open("just_updated.flag", "w") as f:
        f.write("updated")

    # restart the updated app
    subprocess.Popen([old_file], close_fds=True)
    print("App restarted.")

if __name__ == "__main__":
    main()
