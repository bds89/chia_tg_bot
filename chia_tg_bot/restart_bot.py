import psutil, subprocess, time
from plots_creator import get_script_dir

SCRIPT_DIR = get_script_dir()
print("stoping bot...")

k = 1
try_n = 0
while k != 0 and try_n < 3:
    k = 0
    for process in psutil.process_iter():
        for cmd in process.cmdline():
            if "chia_bot.py" in cmd:
                process.kill()
                k += 1
    time.sleep(5)
    try_n += 1
if try_n < 3:
    print("starting bot...")
    subprocess.call("python3 "+SCRIPT_DIR+"/chia_bot.py -s", shell=True)
else: print("can't stop the bot")