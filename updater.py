import sys, zipfile, os, time, subprocess

def main():
    if len(sys.argv) < 3:
        print("Usage: updater.exe <update.zip> <main_app.exe>")
        sys.exit(1)

    zip_path = sys.argv[1]
    main_app = sys.argv[2]

    print("Waiting for main app to exit...")
    time.sleep(2)  # Let the main app shut down

    print(f"Extracting {zip_path}...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(".")
    os.remove(zip_path)

    print("Update complete. Restarting app...")
    subprocess.Popen([main_app])
    sys.exit(0)

if __name__ == "__main__":
    main()
