import re, yaml, sys, os, pickle, subprocess, time, datetime
from plots_creator import Plot, get_script_dir, Plots, plots_on_disk, socket_client
from telegram import Bot


if __name__ == '__main__':
    param = sys.argv
    CONFIG_PATCH = get_script_dir()+"/config.yaml"

    with open(CONFIG_PATCH) as f:
        CONFIG_DICT = yaml.load(f.read(), Loader=yaml.FullLoader)  
    bot = Bot(token=CONFIG_DICT["TELEGRAM_BOT_TOKEN"])

    param = sys.argv
    clear_param = {}
    parameters = ("-s ", "-z ", "-n ", "-d ", "-i ")
    for p1 in param:
        for p2 in parameters:
            if p2 == p1[:3]:
                clear_param[p2] = p1[3:]
    clear_param["-d "] +="/plots"

    i = 1
    process = subprocess.run(['/usr/lib/chia-blockchain/resources/app.asar.unpacked/daemon/chia plots show'], check=True, shell=True, stdout=subprocess.PIPE, universal_newlines=True)
    output = process.stdout
    plot_dirs = re.findall(r"\n(/.+)", output)
    if clear_param["-d "] not in plot_dirs:
        process = subprocess.run(["/usr/lib/chia-blockchain/resources/app.asar.unpacked/daemon/chia plots add -d '"+clear_param["-d "]+"'"], check=True, shell=True, stdout=subprocess.PIPE, universal_newlines=True)
        if CONFIG_DICT["NODE_LIST"]:
            q = {"chat_id": clear_param["-i "], "text": process.stdout, "disable_notification": False}
            data = {"data": 'message(chat_id=q["chat_id"], text=q["text"], disable_notification=q["disable_notification"], node=node)', "q": q}
            socket_client(CONFIG_DICT["NODE_LIST"][1], CONFIG_DICT["FULL_NODE_PORT"], data)
        else:
            bot.send_message(chat_id=clear_param["-i "], text=process.stdout, disable_notification=False)
        
    time_start = time.time()
    while i <= int(clear_param["-n "]):
        plot_list = plots_on_disk(clear_param["-s "])
        for key, value in plot_list.items():
            if not key.isdigit() and value == clear_param["-z "]:
                p = Plots(clear_param["-i "], clear_param["-s "], clear_param["-z "], clear_param["-n "], clear_param["-d "], int(clear_param["-n "])-(i-1))
                try:
                    with open(CONFIG_DICT["PLOTS_FILE"], "rb") as f:
                        all_plots = pickle.load(f)
                except(FileNotFoundError):
                    all_plots = []
                all_plots.append(p)
                with open(CONFIG_DICT["PLOTS_FILE"], "wb") as f:
                    pickle.dump(all_plots, f)
                try:
                    os.mkdir(clear_param["-d "])
                except(OSError):
                    pass
                subprocess.call("mv '"+key+"' '"+clear_param["-d "]+"'", shell=True)
                break

        with open(CONFIG_DICT["PLOTS_FILE"], "rb") as f:
            all_plots = pickle.load(f)
        for plot in all_plots:
            if plot.__class__.__name__ == "Plots":
                if plot.id == clear_param["-i "] and plot.source == clear_param["-s "] and plot.size == clear_param["-z "] and plot.dest == clear_param["-d "] and plot.num == clear_param["-n "]:
                    all_plots.remove(plot)
                    del p
                    break
        # if int(clear_param["-n "]) - i > 0:
        #     p = Plots(clear_param["-i "], clear_param["-s "], clear_param["-z "], clear_param["-n "], clear_param["-d "], int(clear_param["-n "])-i)
        #     all_plots.append(p)
        with open(CONFIG_DICT["PLOTS_FILE"], "wb") as f:
            pickle.dump(all_plots, f)
        i += 1
    
    seconds = round(time.time() - time_start)
    time_move = str(datetime.timedelta(seconds=seconds))

    text="Закончил перемещение {0} плотов из {1} в {2}\nВремя выполнения: {3}\n".format(clear_param["-n "], clear_param["-s "], clear_param["-d "], time_move)
    if CONFIG_DICT["NODE_LIST"]:
        q = {"chat_id": clear_param["-i "], "text": text, "disable_notification": False}
        data = {"data": 'message(chat_id=q["chat_id"], text=q["text"], disable_notification=q["disable_notification"], node=node)', "q": q}
        socket_client(CONFIG_DICT["NODE_LIST"][1], CONFIG_DICT["FULL_NODE_PORT"], data)
    else:
        bot.send_message(chat_id=clear_param["-i "], text=text, disable_notification=False)


    
    

