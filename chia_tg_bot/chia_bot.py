import logging, re, os, json, yaml, datetime, psutil, time, sys, pickle, socket, threading
from subprocess import Popen, PIPE
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, Bot, ReplyKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext, MessageHandler, Filters, ConversationHandler
from multiprocessing import Process, current_process, Queue
from requests import Request, Session, get
from requests.exceptions import ConnectionError, Timeout, TooManyRedirects
from wakeonlan import send_magic_packet
from flask import Flask, request
from plots_creator import Plot, get_script_dir, Plots, plots_on_disk, socket_client

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.WARNING
)

logger = logging.getLogger(__name__)

PASSWORD = range(1)
app = Flask(__name__)

def socket_server(port):
    print("socket server started at port "+str(port))
    host = "0.0.0.0"
    port = int(port)
    mySocket = socket.socket()
    mySocket.bind((host,port))


    while True:
        mySocket.listen(1)
        conn, addr = mySocket.accept()
        print ("Connection from: " + str(addr[0]))
        data = pickle.loads(conn.recv(2048))
        safety_addr = False
        node = "UNKNOWN"
        for key, value in CONFIG_DICT["NODE_LIST"].items():
            if value == addr[0]:
                safety_addr = True
                node = key
        if not data or not safety_addr:
            conn.close()
            time.sleep(1)
            continue
        if type(data) is dict:
            q = data["q"]
            data = data["data"]
        print ("from connected  user: " + str(data))
        data = eval(data)
        data = pickle.dumps(data)
        conn.sendall(data)

    conn.close()

#Харвестеры будут отправлять свои клавиатуры фулл ноде
def get_keyboard():
    keyboard = [[InlineKeyboardButton("Статус Chia Blockchain", callback_data='get_status()'), InlineKeyboardButton("System info", callback_data='get_sys_info()')],
                []]
    line = InlineKeyboardButton("SSD info", callback_data='get_ssd_status()')
    if CONFIG_DICT["SSD_DEVICES"]: keyboard[1].append(line)
    line = InlineKeyboardButton("Узнать баланс", callback_data='get_balance()')
    if CONFIG_DICT["FULL_NODE"]: keyboard[1].append(line)
    return keyboard

def num_to_scale(value, numsimb):
    # Type 1: ▓▓▓▓▓▓▓▓░░░░░░░░  
    simbols = round((value/100)*numsimb)
    hole = round(numsimb - simbols)
    if simbols > numsimb:
        simbols = numsimb
    i = 0
    text = ""
    while i < simbols:
        text += "▓"
        i +=1
    while i < numsimb:
        text += "░"
        i +=1
    text += ""
    return(text)

def time_delta_rus(delta):
    match = re.findall(r"(\d+) day.*,(.+)$", delta)
    if match:
        if int(match[0][0][-1:]) == 1: days = "день"
        elif int(match[0][0][-1:]) > 1 and int(match[0][0][-1:]) < 5: days = "дня"
        else: days = "дней"
        return("{0} {1} {2}".format(match[0][0], days, match[0][1]))
    else:
        return(delta)

def dict_open(source_dict, final_dict={}, list_source=None):
    if not list_source:
        for key, value in source_dict.items():
            if type(value) is dict:
                final_dict.update(dict_open(value, final_dict))
            else: 
                if type(value) is list:
                    for key_list in value:
                      final_dict.update(dict_open(value, final_dict, list_source=True)) 
                else: final_dict[key] = value
    else:
        for key_list in source_dict:
            if type(key_list) is dict:
                final_dict.update(dict_open(key_list, final_dict))
            else: final_dict[key_list] = key_list
    return final_dict

def disk_list(min_size, min_free=None, full=None):
    disk_part = psutil.disk_partitions(all=True)
    Disk_list = {}
    for partitions in disk_part:
        if (partitions[0].startswith("/dev/sd") or partitions[0].startswith("/dev/nvm") or partitions[0] == '/' or (re.search(r"\d+.\d+.\d+.\d+", partitions[0]) and full)):
            d = psutil.disk_usage(partitions[1])
            if d[0] > min_size:
                if min_free:
                    if min_free < d[2]:
                        Disk_list[partitions[1]] = d[2]
                else:
                    Disk_list[partitions[0]] = [d[0], d[1], d[2], d[3], partitions[1]]
    return(Disk_list)
def start(update: Update, context: CallbackContext) -> None:
    if update["message"]["chat"]["id"] in auth_num and auth_num[update["message"]["chat"]["id"]] > 4:
        update.message.reply_text('Превышено количество попыток, обратитесь к администратору')
        return ConversationHandler.END
    if update['message']['chat']['id'] not in CONFIG_DICT["CHAT_IDS"]:
        update.message.reply_text('Требуется авторизация, введите пароль:')
        return PASSWORD

    #Если ферма не указана для этого пользователя, то выбираем №1
    if not "farm" in context.user_data:
        context.user_data["farm"] = 1
    reply_keyboard = [list(CONFIG_DICT["NODE_LIST"])]
    reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, resize_keyboard=True, one_time_keyboard=False, input_field_placeholder='Выберите номер NODE')
    text = "NODE "+str(context.user_data["farm"])+"\n"
    reply_message(update, text, reply_markup)
    chat_ids_to_harvesters()
    reply_message(update, START_TEXT)

def chat_ids_to_harvesters(chat_ids=None):
    if not chat_ids:
        chat_dict_to_send = {"data": "chat_ids_to_harvesters(q)", "q": CONFIG_DICT["CHAT_IDS"]}
        for key, value in CONFIG_DICT["NODE_LIST"].items():
            if key == 1: continue
            print(socket_client(value, CONFIG_DICT["HARVESTER_PORT"], chat_dict_to_send))
    else:
        globals()["CONFIG_DICT"]["CHAT_IDS"] = chat_ids
        with open(CONFIG_PATCH, "w") as f:
            f.write(yaml.dump(CONFIG_DICT, sort_keys=False))
        return "Записал chat_ids на харвестер"

def refresh_chat_ids_for_new_user():
    for key in CONFIG_DICT["CHAT_IDS"]:
        FILTER_CHAT_IDS[key] = "not set"
        MESSAGES[key] = None
        KEYBOARD[key] = get_keyboard()
        REPLY_MARKUP[key] = InlineKeyboardMarkup(KEYBOARD[key])

def password(update: Update, _: CallbackContext) -> None:
    if update.message.text == CONFIG_DICT["PASSWORD"] and (update["message"]["chat"]["id"] not in auth_num or auth_num[update["message"]["chat"]["id"]] < 5): 
        USERS_FILTER.add_user_ids(update['message']['chat']['id'])
        if CONFIG_DICT["CHAT_IDS"]:
            if not update['message']['chat']['id'] in CONFIG_DICT["CHAT_IDS"]:
                globals()["CONFIG_DICT"]["CHAT_IDS"][update['message']['chat']['id']] = "on"
                refresh_chat_ids_for_new_user()
                chat_ids_to_harvesters()
        else:
            globals()["CONFIG_DICT"]["CHAT_IDS"] = {}
            globals()["CONFIG_DICT"]["CHAT_IDS"][update['message']['chat']['id']] = "on"
            refresh_chat_ids_for_new_user()
            chat_ids_to_harvesters()
        globals()["Q_for_message"].put(CONFIG_DICT)
        with open(CONFIG_PATCH, "w") as f:
            f.write(yaml.dump(CONFIG_DICT, sort_keys=False))
        globals()["auth_num"][update["message"]["chat"]["id"]] = 0
        start(update, _)
        return ConversationHandler.END
    else:
        if update["message"]["chat"]["id"] in auth_num: globals()["auth_num"][update["message"]["chat"]["id"]] += 1
        else: globals()["auth_num"][update["message"]["chat"]["id"]] = 1
        message_to_all("Неудачная авторизация № {3} от {0}, {1} {2}".format(update["message"]["chat"]["id"], update["message"]["chat"]["first_name"], 
                                                                            update["message"]["chat"]["last_name"], auth_num[update["message"]["chat"]["id"]]), None)
        print("Неудачная авторизация № {3} от {0}, {1} {2}".format(update["message"]["chat"]["id"], update["message"]["chat"]["first_name"], 
                                                                            update["message"]["chat"]["last_name"], auth_num[update["message"]["chat"]["id"]]))
        if auth_num[update["message"]["chat"]["id"]] > 4:
            update.message.reply_text('Превышено количество попыток, обратитесь к администратору')
            return ConversationHandler.END
        time.sleep(auth_num[update["message"]["chat"]["id"]])
        update.message.reply_text('Пароль не верный, попробуйте снова (осталось {0})'.format(5 - auth_num[update["message"]["chat"]["id"]]))
        return PASSWORD

def help_command(arg=None):
    """Send a message when the command /help is issued."""
    text = 'Пользуйтесь кнопками, для появления кнопок наберите любое сообщение.\n\
Для переключения между нодами наберите <int> номер компьютера\n\
Для изменения таймера Watchdog наберите /wd <int> (секунд), для отключения Watchdog наберите /wd 0.\n\
Для изменения количества параллельных плотов наберите /parallel_plots <int>\n\
Для выбора таблицы начала следующего плота наберите /table <int>\n\
Для изменения настроек засева наберите /set_plot_config <int>\n\
Для включения/отключения отображения бесшумных уведомлений наберите /notify <on/off>\n\
Для просмотра журнала watchdog наберите /log <int> (часов)\n\
Для наблюдением за количеством плотов прошедших фильтр наберите /filter <int> (>= количества плотов прошедших фильтр)\n\n\
Не все плоты могут быть отменены. При засеве разных плотов с одинаковыми параметрами, бот не сможет найти и закрыть определенный процесс chia\
Для корректной работы кнопок при создании плота, из-за ограничений Telegram, абсолютный путь к корню ваших дисков не должен превышать 52 байта UTF-8(52 символа для латинского алфавита)'
    retur = {"text":text}
    return(retur)
@app.route('/get_balance')
def get_balance():
    flist = ['Sync status: ','Total Balance: ','Pending Total Balance: ','Spendable: ']
    fdict = {}

    cli = os.popen('/usr/lib/chia-blockchain/resources/app.asar.unpacked/daemon/chia wallet show').read()
    for i in range(len(flist)):
        n=cli.find(flist[i])+len(flist[i])
        k=cli.find('\n', n)
        fdict[flist[i]]= cli[n:k]
        if flist[i] == 'Sync status: ' and fdict[flist[i]] != "Synced":
            fdict[flist[i]] = cli[n:k]+" ❗"
    text = "<b>Balance info:</b>\n"
    for key, value in fdict.items():
        text = text + "{0} {1}".format(key,value) + "\n"

    if CONFIG_DICT["API_KEY_COINMARKETCUP"]:
        url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'
        parameters = {'id':'9258'}
        headers = {'Accepts': 'application/json','X-CMC_PRO_API_KEY': CONFIG_DICT["API_KEY_COINMARKETCUP"],}

        session = Session()
        session.headers.update(headers)

        try:
            response = session.get(url, params=parameters)
            data = json.loads(response.text)

            url = "https://www.cbr-xml-daily.ru/daily_json.js"
            r = get(url)
            USD_price = float(r.json()["Valute"]["USD"]["Value"])

            chia_price_usd = float(data["data"]["9258"]["quote"]["USD"]["price"])
            chia_percent_change_24h = float(data["data"]["9258"]["quote"]["USD"]["percent_change_24h"])
            result = re.match(r"[0-9.e-]*", fdict['Total Balance: '])
            XCH_balance = float(result.group(0))
            text = text+"{0} XCH * {1}$({2}%) * {3}₽ = {0} * {4} = {5} ₽\n".format(XCH_balance, round(chia_price_usd,2), round(chia_percent_change_24h), round(USD_price,2), 
            round(chia_price_usd*USD_price), 
            round(XCH_balance*chia_price_usd*USD_price))
        except (ValueError, ConnectionError, Timeout, TooManyRedirects) as e:
            print(e)
    else: 
        pass
    retur = {"text":text}
    if(request):
        return(text)
    else:
        return(retur)

@app.route('/get_status')
def get_status():
    text = ""
    if CONFIG_DICT["FULL_NODE"]:
        text += "<b>Chia status:</b>\n"
        flist = ['Farming status: ','Total chia farmed: ','Block rewards: ','Plot count for all harvesters: ','Total size of plots: ','Estimated network space: ','Expected time to win: ']
        fdict = {}
        cli = os.popen('/usr/lib/chia-blockchain/resources/app.asar.unpacked/daemon/chia wallet show').read()
        cli = cli + os.popen('/usr/lib/chia-blockchain/resources/app.asar.unpacked/daemon/chia farm summary').read()
        # cli_remote = [0, 0]
        convert = {"M":1*10**12, "G":1*10**9, "T":1*10**6, "P":1*10**3, "E":1}
        try:
            total_size_of_plots = re.findall(r"Total size of plots: (\d*.\d*)\s([MGTPE])iB", cli)
            net_space = re.findall(r"Estimated network space: (\d*.\d*)\s([MGTPE])iB", cli)
            sec_to_win = round((1/((float(total_size_of_plots[0][0])/convert[total_size_of_plots[0][1]])/(float(net_space[0][0])/convert[net_space[0][1]]) * 4608))*3600*24)
            percent_in_day = round((float(total_size_of_plots[0][0])/convert[total_size_of_plots[0][1]])/(float(net_space[0][0])/convert[net_space[0][1]]) * 4608 * 100, 2)
            time_to_win = str(datetime.timedelta(seconds=sec_to_win))
        except(ZeroDivisionError, IndexError):
            time_to_win = "нет плотов"
            percent_in_day = ""
        for i in range(len(flist)):
            n=cli.find(flist[i])+len(flist[i])
            k=cli.find('\n', n)
            fdict[flist[i]]= cli[n:k]
            if flist[i] == 'Farming status: ' and fdict[flist[i]] != "Farming":
                fdict[flist[i]] = cli[n:k]+" ❗"

        for key, value in fdict.items():
            text += "{0} {1}".format(key,value) + "\n"
        text += "Расчетное время выигрыша: " + time_delta_rus(time_to_win) + " ("+str(percent_in_day)+"%)\n"
    Stat = {"Final_file_size": [], "Total_time": [],"Copy_time": [], "AVG_Final_file_size":0, "AVG_Total_time":0, "AVG_Copy_time":0, "AVG_time_per_Gb": 0, "space_left":0}
    dir_plots = []
    progress_plots = []
    num_string = 0
    num_finish_files = 0
    if os.path.exists(CONFIG_DICT["PLOTLOGPATCH"]):
        file_list = os.listdir(CONFIG_DICT["PLOTLOGPATCH"])
        file_dict = {}
        #Будем учитывать только последние лог файлы, для этого отсорируем список файлов директории лога по дате создания
        for filename in file_list:
            file_dict[filename] = os.path.getmtime(CONFIG_DICT["PLOTLOGPATCH"]+"/"+filename)
        sorted_tuples = sorted(file_dict.items(), key=lambda item: item[1], reverse=True)
        sorted_file_dict = {k: v for k, v in sorted_tuples}
    else: sorted_file_dict = []

    try:
        with open(globals()["CONFIG_DICT"]["PLOTS_FILE"], "rb") as f:
            all_plots = pickle.load(f)
    except(FileNotFoundError):
        all_plots = []
    list_of_plots_name = []

    sorted_file_list = list(sorted_file_dict)
    for filename in sorted_file_list[:CONFIG_DICT["NUM_PARALLEL_PLOTS"] + 20]:
        with open(CONFIG_DICT["PLOTLOGPATCH"]+"/"+filename, 'r') as f:
            log = f.read()
        try:
            Stat["Final_file_size"].append(float(re.findall(r"Final File size: (\w+.\w+)", log)[0]))
            Stat["Total_time"].append(float(re.findall(r"Total time = (\w+.\w+)", log)[0]))
            num_string += log.count("\n")
            num_finish_files += 1
            try:
                Stat["Copy_time"].append(float(re.findall(r"Copy time = (\w+.\w+)", log)[0]))
            except(IndexError):
                Stat["Copy_time"].append(0)
        except(IndexError):
            try:
                if (time.time() - os.path.getmtime(CONFIG_DICT["PLOTLOGPATCH"]+"/"+filename)) < 100000:

                    for plot in all_plots:
                        if plot.__class__.__name__ == "Plot":
                            if filename.count(plot.name):
                                list_of_plots_name.append(plot.name)

                    if list_of_plots_name.count(filename[:-4]):
                        for plot in all_plots:
                            if plot.__class__.__name__ == "Plot":
                                if filename.count(plot.name):
                                    dir_plots.append(plot.temp+"/temp ["+str(plot.temp2)+"/plots] ➜➜➜ "+plot.dest+"/plots: (k"+plot.size+")")
                                    progress_plots.append(log.count("\n"))
                    else:
                        tmp = re.findall(r"Starting plotting progress into temporary dirs: /\w+/(.+) and /\w+/(.+)", log)
                        dir_plots.append(tmp[0][0]+" ["+tmp[0][1]+"]")
                        progress_plots.append(log.count("\n"))
            except(IndexError):
                print("Призошло исключение в функции get_status.re.(filename:"+filename+")")
    try:
        num_string_100 = num_string / num_finish_files
    except(ZeroDivisionError):
        num_string_100 = 2627
    text += "<b>Текущие плоты:</b>\n"
    for dirp, progp in zip(dir_plots, progress_plots):
        text = text + dirp+"\n"+num_to_scale((progp/num_string_100*100), 20)+" "+str(round(progp/num_string_100*100))+"%\n"

    try:
        Stat["AVG_Final_file_size"] = sum(Stat["Final_file_size"]) / len(Stat["Final_file_size"])
        Stat["AVG_Total_time"] = sum(Stat["Total_time"]) / len(Stat["Total_time"])
        Stat["AVG_Copy_time"] = sum(Stat["Copy_time"]) / len(Stat["Copy_time"])
        Stat["AVG_time_per_Gb"] = (Stat["AVG_Total_time"]+Stat["AVG_Copy_time"]) / (Stat["AVG_Final_file_size"] * (1.024**3))
        text = text + "Среднее время на Гб: {0} ".format(str(datetime.timedelta(seconds=round(Stat["AVG_time_per_Gb"])))) + "\n"
    except(ZeroDivisionError):
        pass
    Disk_dict = disk_list(1100000000000)
    for value in Disk_dict.values():
        kol_plots_dict = choose_plot_size(float(value[2]))
        if kol_plots_dict:
            Stat["space_left"] += kol_plots_dict[1][0]*PLOTS_SIZES[32]*K + kol_plots_dict[1][1]*PLOTS_SIZES[33]*K
    act_plots = num_act_plots(4)["num"]
    if not act_plots: time_left = "∞"
    else: time_left = str(datetime.timedelta(seconds=round(((Stat["space_left"]/(1000**3)) * Stat["AVG_time_per_Gb"])/act_plots)))
    text = text + "Осталось засеять: {0} Гб за {1} ".format(round(Stat["space_left"]/(1000**3)), time_delta_rus(time_left)) + "\n" 
    try:
        with open(CONFIG_DICT["LOGPATCH"], 'r') as f:
            log = f.read()
        match = re.findall(r"Found [0-9] proofs. Time: (\d+.\d+) s. Total", log)
        time_summ = 0
        for otklik in match:
            time_summ += float(otklik)
        avg_time = time_summ / len(match)
        text = text + "Среднее время отклика: {0} с., попыток в логе: {1}".format(round(avg_time, 4), len(match)) + "\n"
    except(FileNotFoundError, IndexError, ZeroDivisionError):
        print("Призошло исключение в функции get_status.time_proof")

    #Кнопки
    if globals()["CONFIG_DICT"]["AUTO_P"] == True:
        keyboard = [[InlineKeyboardButton("Откл автозасев", callback_data='autoplot(False)_confirm')]]
    else:
        keyboard = [[InlineKeyboardButton("Вкл автозасев", callback_data='autoplot(True)_confirm')]]
    if act_plots > 0:
        line = InlineKeyboardButton("Отменить", callback_data='dell_plot()')
        keyboard[0].append(line)
    line = InlineKeyboardButton("Создать", callback_data='cpb(q)')  
    keyboard[0].append(line)
    retur = {"text":text, "keyboard":keyboard}
    if(request):
        return(text)
    else:
        return(retur)

@app.route('/get_ssd_status')
def get_ssd_status():
    text = ""
    famous_params_ssd = {"info_name": "Name",
                        "protocol": "Protocol",
                        "percentage_used": "Used %",
                        "data_units_read": "Reads",
                        "data_units_written": "Writes", 
                        "hours": "Power on time hours", 
                        "power_cycle_count": "Power cycle count", 
                        "current": "Temperature",
                        "warning_temp_time": "Warning temp time",
                        "critical_comp_time": "Critical comp time"}

    for key, value in CONFIG_DICT["SSD_DEVICES"].items():
        text += "<b>"+key+":</b>\n"
        command = ('sudo smartctl -A -j '+value).split()
        sudo_password = CONFIG_DICT["SUDO_PASS"]

        p = Popen(['sudo', '--stdin'] + command, stdout=PIPE, stdin=PIPE, stderr=PIPE,
                universal_newlines=True)
        cli = p.communicate(sudo_password + '\n')[0]
        data = json.loads(cli)
        final_dict = dict_open(data)

        for key, value in final_dict.items():
            if key in famous_params_ssd:
                text += "{0}: {1}\n".format(famous_params_ssd[key], value)

    retur = {"text":text}
    if(request):
        return(text)
    else:
        return(retur)

@app.route('/get_sys_info')
def get_sys_info():
    Used_RAM = psutil.virtual_memory()[2]

    Used_SWAP = psutil.swap_memory()[3]

    Used_CPU = psutil.cpu_percent(interval=1, percpu=False)

    CPU_freq = round(psutil.cpu_freq(percpu=False)[0])

    Disk_list = disk_list(min_size=250*1000000000, full=True)
    Disk_list_keys = list(Disk_list.keys())
    Disk_list_keys.sort()

    CPU_temp = psutil.sensors_temperatures(fahrenheit=False)["coretemp"][0][1]

    fan_list = psutil.sensors_fans()
    FAN = "no fan"
    for key, value in fan_list.items():
        for i in value:
            if i[1]>0:
                FAN = i[1]

    Sys_start_at = datetime.datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
    
    text = "<b>System info:</b>\n"
    text = text + "<b>RAM:</b>\nUsed_RAM: {0}%. Used_SWAP: {1} %\n<b>CPU:</b>\nUsed_CPU: {2} %. CPU_freq: {3} MHz.\nCPU_Temp: {4} C. FAN: {5} RPM\n<b>HDD/NVME:</b>\n".format(Used_RAM,Used_SWAP,Used_CPU,CPU_freq,CPU_temp, FAN)
    for key in Disk_list_keys:
        #Get temperature
        command = ('sudo hddtemp -n '+key).split()
        sudo_password = CONFIG_DICT["SUDO_PASS"]

        p = Popen(['sudo', '--stdin'] + command, stdout=PIPE, stdin=PIPE, stderr=PIPE,
                universal_newlines=True)
        cli = p.communicate(sudo_password + '\n')[0]
        if len(cli) > 4 or not cli:
            cli = ""
        else: cli = "("+cli[:-1]+"℃)"
        if Disk_list[key][2] > 330000000000:

            text = text + "{0} ({1}){4}:\nTotal: {2} GB. Free: {3} GB\nUsed: {5} {6}%".format(key, Disk_list[key][4],round((Disk_list[key][0]/1000000000), 2),round((Disk_list[key][2]/1000000000), 2), cli, num_to_scale(Disk_list[key][3], 19), Disk_list[key][3]) + "\n"
        else:
            text = text + "{0} ({1}){4}:\nTotal: {2} GB. Free: <u>{3}</u> GB ❗\nUsed: {5} {6}%".format(key, Disk_list[key][4], round((Disk_list[key][0]/1000000000), 2),round((Disk_list[key][2]/1000000000), 2), cli, num_to_scale(Disk_list[key][3], 19), Disk_list[key][3]) + "\n"
    text = text + "System start at: {0}".format(Sys_start_at) + "\n"
    #Кнопки
    if psutil.swap_memory()[0] > 0:
        keyboard = [[InlineKeyboardButton("Откл.SWAP", callback_data='swap(False)')]]
    else:
        keyboard = [[InlineKeyboardButton("Вкл.SWAP", callback_data='swap(True)')]]
    line = InlineKeyboardButton("Переместить", callback_data='mpb(q)')  
    keyboard[0].append(line)
    line = InlineKeyboardButton("k32/k33", callback_data='plplan()')
    keyboard[0].append(line)
    line = InlineKeyboardButton("DELL", callback_data='dpb()')
    keyboard[0].append(line)
    retur = {"text":text, "keyboard":keyboard}
    if(request):
        return(text)
    else:
        return(retur)
def swap(do):
    if do:
        command = 'sudo swapon -a'.split()
    else:
        command = 'sudo swapoff -a'.split()
    sudo_password = CONFIG_DICT["SUDO_PASS"]

    p = Popen(['sudo', '--stdin'] + command, stdout=PIPE, stdin=PIPE, stderr=PIPE,
              universal_newlines=True)
    cli = p.communicate(sudo_password + '\n')[0]

    swap_size = psutil.swap_memory()[0]
    text = "Размер файла SWAP: {0} MB.\n".format(round(swap_size/1000000))
    retur = {"text":text}
    return(retur)

def cancel():
    text = "Отмена\n"
    retur = {"text":text}
    return(retur)

#cancel_plot
def dell_plot(pid=None):
    try:
        with open(CONFIG_DICT["PLOTS_FILE"], "rb") as f:
            all_plots = pickle.load(f)
        if not all_plots:
            text = "Я ничего не сеял\n"
            retur = {"text":text}
            return(retur)
    except(FileNotFoundError):
        text = "Не нашел файла с плотами\n"
        retur = {"text":text}
        return(retur)

    if not pid:
        file_list = os.listdir(CONFIG_DICT["PLOTLOGPATCH"])
        file_list.sort()
        dir_plots = []
        progress_plots = []
        pid_plots = []
        num_string = 0
        num_finish_files = 0
        for filename in file_list:
            with open(CONFIG_DICT["PLOTLOGPATCH"]+"/"+filename, 'r') as f:
                log = f.read()

            if re.search(r"Total time = (\w+.\w+)", log):
                num_string += log.count("\n")
                num_finish_files += 1

            for plot in all_plots:
                if plot.__class__.__name__ == "Plot":
                    if filename.count(plot.name):
                                    dir_plots.append(plot.temp+"/temp ["+str(plot.temp2)+"/plots] ➜➜➜ "+plot.dest+"/plots")
                                    progress_plots.append(log.count("\n"))
                                    pid_plots.append(plot.pid)

        try:
            num_string_100 = num_string / num_finish_files
        except(ZeroDivisionError):
            num_string_100 = 2627
        text = "<b>Выберите плот для отмены:</b>\n"
        i = 0
        keyboard = [[]]
        lvl1 = 0
        lvl2 = 0
        for dirp, progp, pid  in zip(dir_plots, progress_plots, pid_plots):
            i += 1
            text = text + dirp+":\n"+str(i)+") "+num_to_scale((progp/num_string_100*100), 20)+" "+str(round(progp/num_string_100*100))+"%\n"
            line = InlineKeyboardButton(str(i), callback_data='dell_plot('+str(pid)+')')
            if lvl1 < 4:            
                keyboard[lvl2].append(line)
                lvl1 += 1
            else:
                lvl2 += 1
                lvl1 = 0
                keyboard.append([])
                keyboard[lvl2].append(line)
        retur = {"text":text, "keyboard":keyboard}
        return(retur)
    else:
        tmp = 0
        tmp2 = 0
        dst = 0
        proc = 0
        log = 0
        pf = 0
        for plot in all_plots:
            if plot.__class__.__name__ == "Plot":
                for another_plot in all_plots:
                    if another_plot.__class__.__name__ == "Plot":
                        if plot.cmd == another_plot.cmd and plot.name != another_plot.name:
                            text = "Не могу удалить этот плот. Его команда совпадает с командой другого плота, не смогу закрыть процес chia\n"
                            retur = {"text":text}
                            return(retur)
                if plot.pid == pid:
                    #Удаляем чиа процесс, парсер процесс
                    for process in psutil.process_iter():
                        if process.cmdline().count(plot.cmd):
                            process.terminate()
                            proc += 1
                        if " ".join(process.cmdline()) == re.sub(r"'", '', plot.cmd):
                            process.terminate()
                            proc += 1
                        if process.pid == plot.pid:
                            process.terminate()
                            proc += 1         
                    #Удаляем файлы с дисков
                    temp = plot.temp+"/temp"
                    try:
                        file_list = os.listdir(temp)
                        for filename in file_list:
                            if filename.count(plot.name):
                                os.remove(temp+"/"+filename)
                                tmp += 1
                    except(FileNotFoundError):
                        print("Не смог удалить файлы из {0}".format(temp))
                    if plot.temp2:
                        temp2 = plot.temp2+"/plots"
                        try:
                            file_list = os.listdir(temp2)
                            for filename in file_list:
                                if filename.count(plot.name) and filename.count("2.tmp"):
                                    os.remove(temp2+"/"+filename)
                                    tmp2 += 1
                        except(FileNotFoundError):
                            print("Не смог удалить файлы из {0}".format(temp2))
                    dest = plot.dest+"/plots"
                    try:
                        file_list = os.listdir(dest)
                        for filename in file_list:
                            if filename.count(plot.name) and filename.count("2.tmp"):
                                os.remove(temp2+"/"+filename)
                                dst += 1
                    except(FileNotFoundError):
                        print("Не смог удалить файлы из {0}".format(dest))
                    #Удаляем log файл
                    file_list = os.listdir(CONFIG_DICT["PLOTLOGPATCH"])
                    for filename in file_list:
                        if filename.count(plot.name):
                            os.remove(CONFIG_DICT["PLOTLOGPATCH"]+"/"+filename)
                            log += 1
                    #Удаляем этот плот из plots_file.sys
                    all_plots.remove(plot)
                    pf += 1
                    break
        with open(CONFIG_DICT["PLOTS_FILE"],"wb") as f:
            pickle.dump(all_plots, f)
        text = "Завершил {0} процесса\nУдалил {1} файлов в {2}\nУдалил {3} файлов в {4}\nУдалил {5} файлов в {6}\nУдалил {7} лог-файл\nУдалил {8} запись из plots_file.sys\n".format(proc, tmp, temp, tmp2, temp2, dst, dest, log, pf)
        retur = {"text":text}
        return(retur)
#create_plot_button
def cpb(query, param=""):
    if globals()['Q_for_create_plot_button'].empty():
        que = {}
        que["id"] = query["id"]
        que["first_name"] = query["first_name"]
        que["time"] = time.time()
    else:
        que = globals()['Q_for_create_plot_button'].get()
        if que["id"] != query["id"]:
            if time.time() - que["time"] < 90:
                globals()['Q_for_create_plot_button'].put(que)
                text = que["first_name"]+" уже создает плот, подождите."
                retur = {"text":text}
                return(retur)
            else:
                que = {}
                que["id"] = query["id"]
                que["first_name"] = query["first_name"]
                que["time"] = time.time()
        if not param:
            globals()['Q_for_create_plot_button'].put(que)
    #Обработаем параметр
    parameters = ("-t ", "-2 ", "-d ", "-z ")
    for p in parameters:
        if p == param[:3]:
            que[p] = param[3:]
            if not ("-t " in que and "-2 " in que and "-d " in que and "-z " in que):
                globals()['Q_for_create_plot_button'].put(que)
    keyboard = [[InlineKeyboardButton("Отмена", callback_data='cpb(q, "no")')]]
    if param == "no":
        try:
            que = globals()['Q_for_create_plot_button'].get_nowait()
        except:
            pass
        text = "Сбросил параметры\n"
        keyboard = [[]]
        retur = {"text":text, "keyboard":keyboard}
        return(retur)
    #Начинаем выбор
    #size
    if not "-z " in que:
        text = ""
        for key in parameters:
            if key in que:
                text += key+": "+que[key]+"\n"
        text += "Выберите размер плота:\n\n"
        lvl1 = 0
        lvl2 = 0
        k = 1024**3
        plots_sizes = {"32":239, "33":521, "34":1041, "35":2175}
        for key in plots_sizes.keys():
            line = InlineKeyboardButton(key, callback_data='cpb(q, "-z '+key+'")')
            if lvl1 < 5:            
                keyboard[lvl2].append(line)
                lvl1 += 1
            else:
                lvl2 += 1
                lvl1 = 0
                keyboard.append([])
                keyboard[lvl2].append(line)
        retur = {"text":text, "keyboard":keyboard}
        return(retur)

    #temp
    if not "-t " in que and "-z " in que:
        text = ""
        for key in parameters:
            if key in que:
                text += key+": "+que[key]+"\n"
        text += "Выберите диск для temp папки:\n\n"
        lvl1 = 0
        lvl2 = 0
        k = 1024**3
        plots_sizes = {"25":1.8, "32":239, "33":521, "34":1041, "35":2175}
        Disk_list = disk_list(CONFIG_DICT["MIN_DISK_TOTAL"]*1000000000, plots_sizes[que["-z "]]*k, True)
        if CONFIG_DICT["SSD"]:
            Disk_list2 = disk_list(10*1000000000, 1)
            not_enought_disks = []
            for patch in CONFIG_DICT["SSD"].keys():
                if patch in Disk_list2:
                    if Disk_list2[patch] >= plots_sizes[que["-z "]]*k:
                        Disk_list[patch] = Disk_list2[patch]
                    else: not_enought_disks.append(patch)
                if patch.count("home") and "/" in Disk_list2:
                    if Disk_list2["/"] >= plots_sizes[que["-z "]]*k:
                        Disk_list[patch] = Disk_list2["/"]
                    else: not_enought_disks.append(patch)
                if patch not in Disk_list and patch not in not_enought_disks:
                    Disk_list[patch] = 0
        if Disk_list:
            for patch, free in Disk_list.items():
                text += "{0}:\nFree: {1} GB\n".format(patch,round((free/1000000000), 2))
                line = InlineKeyboardButton(re.findall(r"/([^/]+)$", patch)[0], callback_data='cpb(q, "-t '+patch+'")')
                if lvl1 < 4:            
                    keyboard[lvl2].append(line)
                    lvl1 += 1
                else:
                    lvl2 += 1
                    lvl1 = 0
                    keyboard.append([])
                    keyboard[lvl2].append(line)
        else:
            while True:
                try:
                    que = globals()['Q_for_create_plot_button'].get_nowait()
                except:
                    break
            text = "На ваших дисках не достаточно свободного места\n"
        retur = {"text":text, "keyboard":keyboard}
        return(retur)

    if not "-2 " in que and "-z " in que:
        text = ""
        for key in parameters:
            if key in que:
                text += key+": "+que[key]+"\n"
        text += "Выберите диск для temp2 папки:\n\n"
        lvl1 = 0
        lvl2 = 0
        k = 1024**3
        plots_sizes = {"25":0.6, "32":101.4, "33":208.8, "34":429.8, "35":884.1}
        Disk_list = disk_list(CONFIG_DICT["MIN_DISK_TOTAL"]*1000000000, plots_sizes[que["-z "]]*k, True)
        if CONFIG_DICT["SSD"]:
            Disk_list2 = disk_list(10*1000000000, 1)
            not_enought_disks = []
            for patch in CONFIG_DICT["SSD"].keys():
                if patch in Disk_list2:
                    if Disk_list2[patch] >= plots_sizes[que["-z "]]*k:
                        Disk_list[patch] = Disk_list2[patch]
                    else: not_enought_disks.append(patch)
                if patch.count("home") and "/" in Disk_list2:
                    if Disk_list2["/"] >= plots_sizes[que["-z "]]*k:
                        Disk_list[patch] = Disk_list2["/"]
                    else: not_enought_disks.append(patch)
                if patch not in Disk_list and patch not in not_enought_disks:
                    Disk_list[patch] = 0
        for patch, free in Disk_list.items():
            text += "{0}:\nFree: {1} GB\n".format(patch,round((free/1000000000), 2))
            line = InlineKeyboardButton(re.findall(r"/([^/]+)$", patch)[0], callback_data='cpb(q, "-2 '+patch+'")')
            if lvl1 < 4:            
                keyboard[lvl2].append(line)
                lvl1 += 1
            else:
                lvl2 += 1
                lvl1 = 0
                keyboard.append([])
                keyboard[lvl2].append(line)
        retur = {"text":text, "keyboard":keyboard}
        return(retur)

    if not "-d " in que:
        text = ""
        for key in parameters:
            if key in que:
                text += key+": "+que[key]+"\n"
        text += "Выберите диск для конечной папки:\n\n"
        lvl1 = 0
        lvl2 = 0
        k = 1024**3
        plots_sizes = {"25":0.6, "32":101.4, "33":208.8, "34":429.8, "35":884.1}
        Disk_list = disk_list(CONFIG_DICT["MIN_DISK_TOTAL"]*1000000000, plots_sizes[que["-z "]]*k, True)
        if CONFIG_DICT["SSD"]:
            Disk_list2 = disk_list(10*1000000000, 1)
            not_enought_disks = []
            for patch in CONFIG_DICT["SSD"].keys():
                if patch in Disk_list2:
                    if Disk_list2[patch] >= plots_sizes[que["-z "]]*k:
                        Disk_list[patch] = Disk_list2[patch]
                    else: not_enought_disks.append(patch)
                if patch.count("home") and "/" in Disk_list2:
                    if Disk_list2["/"] >= plots_sizes[que["-z "]]*k:
                        Disk_list[patch] = Disk_list2["/"]
                    else: not_enought_disks.append(patch)
                if patch not in Disk_list and patch not in not_enought_disks:
                    Disk_list[patch] = 0
        for patch, free in Disk_list.items():
            text += "{0}:\nFree: {1} GB\n".format(patch,round((free/1000000000), 2))
            line = InlineKeyboardButton(re.findall(r"/([^/]+)$", patch)[0], callback_data='cpb(q, "-d '+patch+'")')
            if lvl1 < 4:            
                keyboard[lvl2].append(line)
                lvl1 += 1
            else:
                lvl2 += 1
                lvl1 = 0
                keyboard.append([])
                keyboard[lvl2].append(line)
        retur = {"text":text, "keyboard":keyboard}
        return(retur)

    if "-t " in que and "-2 " in que and "-d " in que and "-z " in que:
        if param == "yes":
            create_plot(que["-t "], que["-d "], que["-2 "], que["-z "])
            try:
                que = globals()['Q_for_create_plot_button'].get_nowait()
            except:
                pass
            text = "Создаю плот...\n"
            keyboard = []
        elif param == "no":
            try:
                que = globals()['Q_for_create_plot_button'].get_nowait()
            except:
                pass
            text = "Сбросил параметры\n"
            keyboard = []
        else:
            text = "size: {0}\ntemp: {1}\ntemp2: {2}\ndest: {3}\nСоздаю плот?\n".format(que["-z "], que["-t "], que["-2 "], que["-d "])
            keyboard = [[InlineKeyboardButton("Да", callback_data='cpb(q, "yes")'), InlineKeyboardButton("Отмена", callback_data='cpb(q, "no")')]]
            globals()['Q_for_create_plot_button'].put(que)
        retur = {"text":text, "keyboard":keyboard}
        return(retur)

#dell_plot_button
def dpb(param=""):
    if globals()['Q_for_dell_plot_button'].empty():
        que = {}
    else:
        que = globals()['Q_for_dell_plot_button'].get()
    parameters = ("-d ", "-o ", "-z ", "-n ")
    for p in parameters:
        if p == param[:3]:
            if p == "-o " and param[3:] == "False": que[p] = False
            else: que[p] = param[3:]
            if not ("-d " in que and "-o " in que and "-z " in que and "-n " in que):
                globals()['Q_for_dell_plot_button'].put(que)
    keyboard = [[InlineKeyboardButton("Отмена", callback_data='dpb("no")')]]
    if param == "no":
        try:
            que = globals()['Q_for_dell_plot_button'].get_nowait()
        except:
            pass
        text = "Сбросил параметры\n"
        keyboard = [[]]
        retur = {"text":text, "keyboard":keyboard}
        return(retur)

    #disk
    if not "-d " in que:
        text = ""
        for key in parameters:
            if key in que:
                text += key+": "+str(que[key])+"\n"
        text += "Выберите диск c которого хотите удалить:\n\n"
        lvl1 = 0
        lvl2 = 0
        Disk_list = disk_list(109*1000000000, 1, True)
        if CONFIG_DICT["SSD"]:
            Disk_list2 = disk_list(10*1000000000, 1)
            for patch in CONFIG_DICT["SSD"].keys():
                if patch in Disk_list2:
                    Disk_list[patch] = Disk_list2[patch]
                if patch.count("home") and "/" in Disk_list2:
                    Disk_list[patch] = Disk_list2["/"]
                if patch not in Disk_list:
                    Disk_list[patch] = 0
                
        for patch, free in Disk_list.items():
            text += "{0}: Free: {1} GB\n".format(patch,round((free/1000000000), 2))
            try:
                line = InlineKeyboardButton(re.findall(r"/([^/]+)$", patch)[0], callback_data='dpb("-d '+patch+'")')
                if lvl1 < 4:            
                    keyboard[lvl2].append(line)
                    lvl1 += 1
                else:
                    lvl2 += 1
                    lvl1 = 0
                    keyboard.append([])
                    keyboard[lvl2].append(line)
            except(IndexError):
                pass
        retur = {"text":text, "keyboard":keyboard}
        return(retur)
    #Old
    if not "-o " in que:
        text = ""
        for key in parameters:
            if key in que:
                text += key+": "+str(que[key])+"\n"
        text += "Выберите возраст плотов:\n\n"
        line = InlineKeyboardButton("Старые(not NFT)", callback_data='dpb("-o True")')
        keyboard[0].append(line)
        line = InlineKeyboardButton("Любые", callback_data='dpb("-o False")')
        keyboard[0].append(line)
        retur = {"text":text, "keyboard":keyboard}
        return(retur)
    #size
    if not "-z " in que and "-d " in que and "-o " in que:
        text = ""
        for key in parameters:
            if key in que:
                text += key+": "+str(que[key])+"\n"
        plot_list = plots_on_disk(patch=que["-d "], old=que["-o "])
        dig = 0
        for key, value in plot_list.items():
            if key.isdigit():
                dig += 1
                size = key
        if dig == 0:
            while True:
                try:
                    que = globals()['Q_for_dell_plot_button'].get_nowait()
                except:
                    break
            text = "Не нашел плотов на этом диске\n"
            retur = {"text":text}
            return(retur)
        if dig != 1:
            text += "Выберите тип плота\n"
            lvl1 = 0
            lvl2 = 0
            for key, value in plot_list.items():
                if key.isdigit():
                    text += "Нашел {0} плотов k{1}\n".format(value, key)
                    line = InlineKeyboardButton("k"+str(key), callback_data='dpb("-z '+str(key)+'")')
                    if lvl1 < 4:            
                        keyboard[lvl2].append(line)
                        lvl1 += 1
                    else:
                        lvl2 += 1
                        lvl1 = 0
                        keyboard.append([])
                        keyboard[lvl2].append(line)
            retur = {"text":text, "keyboard":keyboard}
            return(retur)
        if dig == 1:
            que["-z "] = str(size)
            for key, value in plot_list.items():
                if key.isdigit():
                    text += "Нашел {0} плотов k{1}\n".format(value, key)
    #kolvo
    if not "-n " in que and "-z " in que and "-o " in que:
        if "text" not in locals():
            text = ""
            for key in parameters:
                if key in que:
                    text += key+": "+str(que[key])+"\n"
        text += "Выберите количество плотов для удаления:\n\n"
        lvl1 = 0
        lvl2 = 0
        plot_list = plots_on_disk(patch=que["-d "], old=que["-o "])
        for key, value in plot_list.items():
            if key.isdigit() and key == que["-z "]:
                if value < 10:
                    num_but = value
                else: num_but = 10
        if "num_but" in locals():
            for i in range(num_but):
                line = InlineKeyboardButton(i+1, callback_data='dpb("-n '+str(i+1)+'")')
                if lvl1 < 5:            
                    keyboard[lvl2].append(line)
                    lvl1 += 1
                else:
                    lvl2 += 1
                    lvl1 = 0
                    keyboard.append([])
                    keyboard[lvl2].append(line)
        else:
            text = "На диске нет подходящих плотов\n"
            keyboard = [[]]
        retur = {"text":text, "keyboard":keyboard}
        return(retur)

    if "-d " in que and "-o " in que and "-z " in que and "-n " in que:
        if param == "yes":
            deleted_plot_list = plots_on_disk(patch=que["-d "], old=que["-o "], dell=que["-n "], size=que["-z "])
            try:
                que = globals()['Q_for_dell_plot_button'].get_nowait()
            except:
                pass
            n = 0
            for key, value in deleted_plot_list.items():
                if key != "num_del" and value == "del":
                    n += 1
            nft_or_not={True:"not NFT", False:"Любой"}
            text = "Удалил: {0} плотов размером {1} ({2}) с диска {3}.".format(n, que["-z "], nft_or_not[bool(que["-o "])], que["-d "])
            keyboard = []
        else:
            text = "на: {0}\nстарые: {1}\nразмер: k{2}\nколичество: {3}\nУдаляем?\n".format(que["-d "], str(que["-o "]), que["-z "], que["-n "])
            keyboard = [[InlineKeyboardButton("Да", callback_data='dpb("yes")'), InlineKeyboardButton("Отмена", callback_data='dpb("no")')]]
            globals()['Q_for_dell_plot_button'].put(que)
        retur = {"text":text, "keyboard":keyboard}
        return(retur)

#move_plot_button
def mpb(query, param=""):
    if globals()['Q_for_move_plot_button'].empty():
        que = {}
        que["id"] = query["id"]
        que["first_name"] = query["first_name"]
        que["time"] = time.time()
    else:
        que = globals()['Q_for_move_plot_button'].get()
        if que["id"] != query["id"]:
            if time.time() - que["time"] < 90:
                globals()['Q_for_move_plot_button'].put(que)
                text = que["first_name"]+" уже начинает копирование, подождите."
                retur = {"text":text}
                return(retur)
            else:
                que = {}
                que["id"] = query["id"]
                que["first_name"] = query["first_name"]
                que["time"] = time.time()
        if not param:
            globals()['Q_for_move_plot_button'].put(que)
            try:
                with open(CONFIG_DICT["PLOTS_FILE"], "rb") as f:
                    all_plots = pickle.load(f)
                    text = ""
                    for plot in all_plots:
                        if plot.__class__.__name__ == "Plots":
                            text += "к{0} из {1} в {2}\n{3} {4}/{5}".format(plot.size, plot.source, plot.dest, num_to_scale(((int(plot.num) - int(plot.num_est) + 0.5)/int(plot.num))*100, 19), int(plot.num)-int(plot.num_est), int(plot.num))
            except(FileNotFoundError):
                pass
    #Покажем если уже идет копирование
    try:
        with open(CONFIG_DICT["PLOTS_FILE"], "rb") as f:
            all_plots = pickle.load(f)
            text = ""
            for plot in all_plots:
                if plot.__class__.__name__ == "Plots":
                    text += "к{0} из {1} в {2}\n{3} {4}/{5}\n\n".format(plot.size, plot.source, plot.dest, num_to_scale(((int(plot.num) - int(plot.num_est) + 0.5)/int(plot.num))*100, 19), int(plot.num)-int(plot.num_est), int(plot.num))
    except(FileNotFoundError):
        all_plots = []
        pass
    #Обработаем параметр
    parameters = ("-s ", "-z ", "-n ", "-d ")
    for p in parameters:
        if p == param[:3]:
            que[p] = param[3:]
            if not ("-s " in que and "-d " in que and "-n " in que and "-z " in que):
                globals()['Q_for_move_plot_button'].put(que)
    keyboard = [[InlineKeyboardButton("Отмена", callback_data='mpb(q, "no")')]]
    if param == "no":
        try:
            que = globals()['Q_for_move_plot_button'].get_nowait()
        except:
            pass
        text = "Сбросил параметры\n"
        keyboard = [[]]
        retur = {"text":text, "keyboard":keyboard}
        return(retur)
    #Начинаем выбор папок
    #source
    if not "-s " in que:
        if "text" not in locals():
            text = ""
        for key in parameters:
            if key in que:
                text += key+": "+que[key]+"\n"
        text += "Выберите диск c которого хотите переместить:\n\n"
        lvl1 = 0
        lvl2 = 0
        Disk_list = disk_list(109*1000000000, 1, True)
        if CONFIG_DICT["SSD"]:
            Disk_list2 = disk_list(10*1000000000, 1)
            not_enought_disks = []
            for patch in CONFIG_DICT["SSD"].keys():
                if patch in Disk_list2:
                    Disk_list[patch] = Disk_list2[patch]
                if patch.count("home") and "/" in Disk_list2:
                    Disk_list[patch] = Disk_list2["/"]
                if patch not in Disk_list:
                    Disk_list[patch] = 0
                
        for patch, free in Disk_list.items():
            text += "{0}: Free: {1} GB\n".format(patch,round((free/1000000000), 2))
            try:
                line = InlineKeyboardButton(re.findall(r"/([^/]+)$", patch)[0], callback_data='mpb(q, "-s '+patch+'")')
                if lvl1 < 4:            
                    keyboard[lvl2].append(line)
                    lvl1 += 1
                else:
                    lvl2 += 1
                    lvl1 = 0
                    keyboard.append([])
                    keyboard[lvl2].append(line)
            except(IndexError):
                pass
        retur = {"text":text, "keyboard":keyboard}
        return(retur)
    #size
    if not "-z " in que and "-s " in que:
        text = ""
        plot_list = plots_on_disk(que["-s "])
        dig = 0
        for key, value in plot_list.items():
            if key.isdigit():
                dig += 1
                size = key
        if dig == 0:
            while True:
                try:
                    que = globals()['Q_for_move_plot_button'].get_nowait()
                except:
                    break
            text = "Не нашел плотов на этом диске\n"
            retur = {"text":text}
            return(retur)
        if dig != 1:
            for key in parameters:
                if key in que:
                    text += key+": "+que[key]+"\n\n"

            text += "Выберите тип плота\n"
            lvl1 = 0
            lvl2 = 0
            for key, value in plot_list.items():
                if key.isdigit():
                    text += "Нашел {0} плотов k{1}\n".format(value, key)
                    line = InlineKeyboardButton("k"+str(key), callback_data='mpb(q, "-z '+str(key)+'")')
                    if lvl1 < 4:            
                        keyboard[lvl2].append(line)
                        lvl1 += 1
                    else:
                        lvl2 += 1
                        lvl1 = 0
                        keyboard.append([])
                        keyboard[lvl2].append(line)
            retur = {"text":text, "keyboard":keyboard}
            return(retur)
        if dig == 1:
            que["-z "] = str(size)
            for key, value in plot_list.items():
                if key.isdigit():
                    text += "Нашел {0} плотов k{1}\n".format(value, key)


    if not "-n " in que and "-z " in que and "-s " in que:
        #Не дадим копировать одинаковые плоты с одного диска одновременно
        for plot in all_plots:
            if plot.__class__.__name__ == "Plots":
                if plot.source == que["-s "] and plot.size == que["-z "]:
                    while True:
                        try:
                            que = globals()['Q_for_move_plot_button'].get_nowait()
                        except:
                            break
                    text = "Уже идет копирование с этого диска\n"
                    retur = {"text":text}
                    return(retur)

        if "text" not in locals():
            text = ""
        for key in parameters:
            if key in que:
                text += key+": "+que[key]+"\n"
        text += "Выберите количество плотов которое хотите переместить:\n\n"
        lvl1 = 0
        lvl2 = 0
        plot_list = plots_on_disk(que["-s "])
        for key, value in plot_list.items():
            if key.isdigit() and key == que["-z "]:
                if value < 10:
                    num_but = value
                else: num_but = 10
        for i in range(num_but):
            line = InlineKeyboardButton(i+1, callback_data='mpb(q, "-n '+str(i+1)+'")')
            if lvl1 < 5:            
                keyboard[lvl2].append(line)
                lvl1 += 1
            else:
                lvl2 += 1
                lvl1 = 0
                keyboard.append([])
                keyboard[lvl2].append(line)
        retur = {"text":text, "keyboard":keyboard}
        return(retur)

    if not "-d " in que:
        text = ""
        for key in parameters:
            if key in que:
                text += key+": "+que[key]+"\n"
        text += "Выберите диск на который хотите переместить:\n\n"
        lvl1 = 0
        lvl2 = 0
        k = 1024**3
        plots_sizes = {"25":0.6, "32":101.4, "33":208.8, "34":429.8, "35":884.1}
        Disk_list = disk_list(109*1000000000, plots_sizes[que["-z "]]*k*int(que["-n "]), True)
        if CONFIG_DICT["SSD"]:
            Disk_list2 = disk_list(10*1000000000, 1)
            not_enought_disks = []
            for patch in CONFIG_DICT["SSD"].keys():
                if patch in Disk_list2:
                    if Disk_list2[patch] >= plots_sizes[que["-z "]]*k*int(que["-n "]):
                        Disk_list[patch] = Disk_list2[patch]
                    else: not_enought_disks.append(patch)
                if patch.count("home") and "/" in Disk_list2:
                    if Disk_list2["/"] >= plots_sizes[que["-z "]]*k*int(que["-n "]):
                        Disk_list[patch] = Disk_list2["/"]
                    else: not_enought_disks.append(patch)
                if patch not in Disk_list and patch not in not_enought_disks:
                    Disk_list[patch] = 0
        if Disk_list:       
            for patch, free in Disk_list.items():
                if patch == que["-s "]:
                    continue
                text += "{0}: Free: {1} GB\n".format(patch,round((free/1000000000), 2))
                try:
                    line = InlineKeyboardButton(re.findall(r"/([^/]+)$", patch)[0], callback_data='mpb(q, "-d '+patch+'")')
                    if lvl1 < 4:            
                        keyboard[lvl2].append(line)
                        lvl1 += 1
                    else:
                        lvl2 += 1
                        lvl1 = 0
                        keyboard.append([])
                        keyboard[lvl2].append(line)
                except(IndexError):
                    pass
        else:
            try:
                que = globals()['Q_for_move_plot_button'].get_nowait()
            except:
                pass
            text = "На ваших дисках не достаточно места, для перемещения\n"
            keyboard = [[]]
        retur = {"text":text, "keyboard":keyboard}
        return(retur)



    if "-s " in que and "-n " in que and "-z " in que and "-d " in que:
        if param == "yes":
            patch = "python3 "+SCRIPT_DIR+"/plot_move.py"
            for key, value in que.items():
                if key == "id":
                    patch += " '-i "+str(value)+"'"
                else:
                    patch += " '"+str(key)+str(value)+"'"
            process = Popen(patch, shell=True)
            try:
                que = globals()['Q_for_move_plot_button'].get_nowait()
            except:
                pass
            text = "Начинаю перемещение...\nПо завершению пришлю уведомление\n"
            keyboard = []
        else:
            text = "из: {0}\nв: {1}\nразмер: k{2}\nколичество: {3}\nНачинаю перемещение?\n".format(que["-s "], que["-d "], que["-z "], que["-n "])
            keyboard = [[InlineKeyboardButton("Да", callback_data='mpb(q, "yes")'), InlineKeyboardButton("Отмена", callback_data='mpb(q, "no")')]]
            globals()['Q_for_move_plot_button'].put(que)
        retur = {"text":text, "keyboard":keyboard}
        return(retur)

def plplan(disk=None):
    if not disk:
        text = "Выберите диск для более подробной информации\n"
        keyboard = [[]]
        disk_part = psutil.disk_partitions(all=True)
        lvl1 = 0
        lvl2 = 0
        for partitions in disk_part:
            if (partitions[0].startswith("/dev/sd") or partitions[0].startswith("/dev/nvm")):
                d = psutil.disk_usage(partitions[1])
                total = d[1]+d[2]
                answ = choose_plot_size(total)
                if answ:
                    text += "{0}: k32:{1}, k33:{2} |{3}Gb\n".format(partitions.mountpoint, answ[1][0], answ[1][1], round(answ[0], 2))
                    mountpoint = re.findall(r"/([^/]+)$", partitions.mountpoint)
                    if mountpoint: point = mountpoint[0]
                    else: continue
                    line = InlineKeyboardButton(point, callback_data='plplan("'+partitions.mountpoint+'")')
                    if lvl1 < 4:            
                        keyboard[lvl2].append(line)
                        lvl1 += 1
                    else:
                        lvl2 += 1
                        lvl1 = 0
                        keyboard.append([])
                        keyboard[lvl2].append(line)
    else:
        keyboard = [[InlineKeyboardButton("Назад", callback_data='plplan()')]]
        text = "Диск: "+disk+"\nРасчет исходя из емкости диска:\n"
        d = psutil.disk_usage(disk)
        total = d[1]+d[2]
        answ = choose_plot_size(total)
        text += "k32:{0}, k33:{1} |{2}Gb\n".format(answ[1][0], answ[1][1], round(answ[0], 2))
        answ = choose_plot_size(d[2])
        if answ:
            text += "Расчет исходя из свободного ({0}Gb) места:\nk32:{1}, k33:{2} |{3}Gb\n".format(round(d[2]*1e-9,1), answ[1][0], answ[1][1], round(answ[0], 2))
        else: text += "Не достаточно свободного места для создания плота\n"
        text += "Нашел на диске: \n"
        plot_list = plots_on_disk(disk)
        for key, value in plot_list.items():
            if key.isdigit():
                text += "k{0}:{1}, ".format(key, value)
                line = InlineKeyboardButton("k"+str(key), callback_data='mpb(q, "-z '+str(key)+'")')
        text = text[:-2] + "\n"
    retur = {"text":text, "keyboard":keyboard}
    return(retur)

def plot_config(sata_as_ssd=None, use_k33=None):
    if sata_as_ssd == "yes":
        globals()["CONFIG_DICT"]["SATA_AS_SSD"] = "yes"
        text = "Использую SATA как SSD\n"
    elif sata_as_ssd == "no":
        globals()["CONFIG_DICT"]["SATA_AS_SSD"] = "no"
        text = "Не использую SATA как SSD\n"
    if use_k33 == "yes":
        globals()["CONFIG_DICT"]["USE_K33"] = "yes"
        text = "Использую K33 плоты\n"
    elif use_k33 == "no":
        globals()["CONFIG_DICT"]["USE_K33"] = "no"
        text = "Не использую K33 плоты\n"
    with open(CONFIG_PATCH, "w") as f:
        f.write(yaml.dump(CONFIG_DICT, sort_keys=False))

    que = {"AUTO_P":CONFIG_DICT["AUTO_P"], 
            "COMPUTING_TABLE": CONFIG_DICT["COMPUTING_TABLE"], 
            "NUM_PARALLEL_PLOTS": CONFIG_DICT["NUM_PARALLEL_PLOTS"],
            "SATA_AS_SSD": CONFIG_DICT["SATA_AS_SSD"],
            "USE_K33": CONFIG_DICT["USE_K33"]}
    globals()['Q'].put(que)
    retur = {"text":text}
    return(retur)
        
def button(update, context):
    query = update.callback_query
    if not "farm" in context.user_data:
        context.user_data["farm"] = 1
    text = "NODE "+str(context.user_data["farm"])+"\n\n"
    q = {"id":str(query["message"]["chat"]["id"]), "first_name":str(query["message"]["chat"]["first_name"])}
    query_data = str(query.data)
    print(query["message"]["chat"]["first_name"]+"---->"+query_data)
    if query["message"]["chat"]["id"] not in CONFIG_DICT["CHAT_IDS"]:
        message_to_all("Подозрительная активность от {0}, {1} {2}".format(query["message"]["chat"]["id"], query["message"]["chat"]["first_name"], 
                                                                            query["message"]["chat"]["last_name"]), None)
        print("Подозрительная активность от {0}, {1} {2}".format(query["message"]["chat"]["id"], query["message"]["chat"]["first_name"], 
                                                                            query["message"]["chat"]["last_name"]))
        return

    reply_markup = InlineKeyboardMarkup(KEYBOARD[query["message"]["chat"]["id"]])

    query.answer()
    query.edit_message_text(text="Выполняю...", parse_mode="HTML", reply_markup=reply_markup)

    if query_data[len(query_data)-len("confirm"):] == "confirm":
        text = "Вы уверены?\n"
        keyboard = [[InlineKeyboardButton("Да", callback_data=query_data[:(len(query_data)-len("_confirm"))]), InlineKeyboardButton("Отмена", callback_data="cancel()")]]
    else: 

        if int(context.user_data["farm"]) == 1:
            retur = eval(query_data)
        else:
            data = {"data": query_data, "q": q}
            retur = socket_client(CONFIG_DICT["NODE_LIST"][int(context.user_data["farm"])], CONFIG_DICT["HARVESTER_PORT"], data)
        text += retur["text"]
        keyboard = retur.get("keyboard")
        if keyboard:
            for line in KEYBOARD[query["message"]["chat"]["id"]]:
                keyboard.append(line)
        else:
            keyboard = KEYBOARD[query["message"]["chat"]["id"]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    current_datetime = datetime.datetime.fromtimestamp(time.mktime(datetime.datetime.now().timetuple()))
    text = text+"<b>Обновлено: {}</b>".format(current_datetime)


    query.edit_message_text(text=text, parse_mode="HTML", reply_markup=reply_markup)


#*************************************************************************************************************************
def autoplot(auto):
    if auto == True:
        if globals()["CONFIG_DICT"]["AUTO_P"] == True:
            text = "Не могу включить дважды\n"
            retur = {"text":text}
            return(retur)
        else:
            globals()["CONFIG_DICT"]["AUTO_P"] = True
            with open(CONFIG_PATCH, "w") as f:
                f.write(yaml.dump(CONFIG_DICT, sort_keys=False))

            que = {"AUTO_P":CONFIG_DICT["AUTO_P"], 
            "COMPUTING_TABLE": CONFIG_DICT["COMPUTING_TABLE"], 
            "NUM_PARALLEL_PLOTS": CONFIG_DICT["NUM_PARALLEL_PLOTS"],
            "SATA_AS_SSD": CONFIG_DICT["SATA_AS_SSD"],
            "USE_K33": CONFIG_DICT["USE_K33"]}
            globals()['Q'].put(que)

            text = "Включил автозасев\n"
            retur = {"text":text}
            return(retur)
    if auto == False:
        if globals()["CONFIG_DICT"]["AUTO_P"] == False:
            text = "Не могу отключить дважды\n"
            retur = {"text":text}
            return(retur)
        else:
            globals()["CONFIG_DICT"]["AUTO_P"] = False
            with open(CONFIG_PATCH, "w") as f:
                f.write(yaml.dump(CONFIG_DICT, sort_keys=False))

            que = {"AUTO_P":CONFIG_DICT["AUTO_P"], 
            "COMPUTING_TABLE": CONFIG_DICT["COMPUTING_TABLE"], 
            "NUM_PARALLEL_PLOTS": CONFIG_DICT["NUM_PARALLEL_PLOTS"],
            "SATA_AS_SSD": CONFIG_DICT["SATA_AS_SSD"],
            "USE_K33": CONFIG_DICT["USE_K33"]}
            globals()['Q'].put(que)

            text = "Выключил автозасев\n"
            retur = {"text":text}
            return(retur)


def num_act_plots(table):
    num = 0
    num_with_table = 0
    ready = False
    weight_of_plots = {25:0.1, 32:1, 33:2, 34:4, 35:8}
    try:
        os.mkdir(CONFIG_DICT["PLOTLOGPATCH"])
    except(OSError):
        pass
    file_list = os.listdir(CONFIG_DICT["PLOTLOGPATCH"])
    for filename in file_list:
        with open(CONFIG_DICT["PLOTLOGPATCH"]+"/"+filename, 'r') as f:
            log = f.read()
        if (time.time() - os.path.getmtime(CONFIG_DICT["PLOTLOGPATCH"]+"/"+filename)) < 100000:
            if log.count("Total time") == 0:
                size = int(re.findall(r'Plot size is: (\d+)', log)[0])
                
                num += weight_of_plots[size]
                if re.search(r'Computing table '+str(table), log):
                    num_with_table += weight_of_plots[size]
    if num_with_table == num:
        ready = True        
    dict = {"num":num, "ready":ready}
    return(dict)

def choose_plot_size(free):
    k32 = 101.4*(1024**3)
    k33 = 208.8*(1024**3)
    num_k32 = free // k32
    num_k33 = 1 + (free // k33)

    result = {}
    for i32 in range(int(num_k32+1)):
        for i33 in range(int(num_k33+1)):
            ostatok = int(free - k32*i32 - k33*i33)
            if ostatok < 0 or (not i32 and not i33):
                continue
            list_numbers = [i32, i33]
            result[ostatok/1000000000] = list_numbers
    result_sorted = sorted(result.items())
    if result_sorted:
        return result_sorted[0]

def create_plot(temp, dest, temp2=None, size=32):
    if not temp2:
        temp2 = ''
    patch = "python3 "+SCRIPT_DIR+"/plots_creator.py"
    patch += " '-t "+temp+"' '-2 "+temp2+"' '-d "+dest+"' '-z "+str(size)+"'"
    # patch = patch.split()
    print(patch)
    process = Popen(patch, shell=True)


def plot_manager():
    
    while True:
        que = globals()['Q'].get()
        if que["AUTO_P"]:
            break
        else:
            continue
    while True:
        if "last_time" in locals() and datetime.datetime.now() - last_time < datetime.timedelta(seconds=60):
            time.sleep(5)
            continue
        if globals()['Q'].empty() and que["AUTO_P"]:
            num_act_plots_dict = num_act_plots(que["COMPUTING_TABLE"])
            if num_act_plots_dict["num"] < que["NUM_PARALLEL_PLOTS"] and num_act_plots_dict["ready"]:
                temp = None
                temp2 = None
                dest = None
                Disk_list = disk_list(CONFIG_DICT["MIN_DISK_TOTAL"]*1000000000, CONFIG_DICT["MIN_DISK_FREE"]*1000000000)
                if not Disk_list:
                    #Не нашел куда сеять
                    last_time = datetime.datetime.now()
                    time.sleep(5)
                    continue
                try:
                    with open(globals()["CONFIG_DICT"]["PLOTS_FILE"], "rb") as f:
                        all_plots = pickle.load(f)
                except(FileNotFoundError):
                    all_plots = []
                if que["USE_K33"] == "yes":
                    plots_sizes = {}
                    bad_patch = []
                    busy_disks = []
                    for patch in Disk_list.keys():
                        was_dest = False
                        if "free" in locals(): del(free)
                        #Проверим сеется ли что-то на диск
                        for plot in all_plots:
                            if plot.__class__.__name__ == "Plot":
                                if plot.temp == patch:
                                    bad_patch.append(patch)
                                    continue
                                if plot.temp2 == patch:
                                    busy_disks.append(patch)
                                if plot.dest == patch:
                                    busy_disks.append(patch)
                                    if not was_dest:
                                        d = psutil.disk_usage(patch)
                                        total = d[1]+d[2]
                                        answ1 = plots_on_disk(patch)
                                        for key, value in answ1.items():
                                            if key.isdigit():
                                                if "free" not in locals(): free = total - K*PLOTS_SIZES[int(key)]*value
                                                else: free -= K*PLOTS_SIZES[int(key)]*value
                                        was_dest = True
                                    if "free" not in locals(): free = total - K*PLOTS_SIZES[int(plot.size)]
                                    else: free -= K*PLOTS_SIZES[int(plot.size)]
                        #Посчитаем сколько нужно плотов на каждый диск(если диск стоит - из свободного места, если на него сеят - исходя из общего объема (минус то что есть и то что сеят))            
                        if patch not in bad_patch:
                            if "free" in locals(): answ2 = choose_plot_size(free) 
                            else: answ2 = choose_plot_size(Disk_list[patch])
                            if answ2 and (answ2[1][0] > 0 or answ2[1][1] > 0):
                                plots_sizes[patch] = {32:answ2[1][0], 33:answ2[1][1]}
                    if not plots_sizes:
                        #Не нашел куда сеять
                        last_time = datetime.datetime.now()
                        time.sleep(5)
                        continue
                    #отсортируем список дисков, вверху не сата и менее используемые, c необходимостью в плоте к33
                    plots_sizes_sorted = {}
                    for_sort = {}
                    for patch in plots_sizes.keys():
                        if re.search(r"[Ss][Aa][Tt][Aa]", patch):
                            for_sort[patch] = 1000
                        else: for_sort[patch] = 0
                        for key in busy_disks:
                            if key == patch:
                                for_sort[patch] += 10
                        if plots_sizes[patch][33] == 0:
                            for_sort[patch] += 1
                    sorted_tuples = sorted(for_sort.items(), key=lambda item: item[1])
                    sorted_for_sort= {k: v for k, v in sorted_tuples}
                    for key in sorted_for_sort.keys():
                        plots_sizes_sorted[key] = plots_sizes[key]
                    #Будем пробовать сеять подходящий вариант
                    for i in range(len(plots_sizes_sorted)):
                        if plots_sizes_sorted[list(plots_sizes_sorted)[i]][33] > 0: size = 33
                        else: size = 32
                        #Выбираем темп папку, сначала САТА
                        for patch, free in Disk_list.items():
                            if re.search(r"[Ss][Aa][Tt][Aa]", patch):
                                busy_sata = []                        
                                for plot in all_plots:
                                    if plot.__class__.__name__ == "Plot":
                                        if plot.temp == patch or plot.dest == patch:
                                            busy_sata.append(patch)
                                if (free - PLOTS_SIZES_PLOTTING[size] * K) >= 0 and patch not in busy_sata and (list(plots_sizes_sorted)[i] == patch or que["SATA_AS_SSD"] == "yes"):
                                    temp = patch
                                    break
                        
                        if not temp and CONFIG_DICT["SSD"]:
                            #Найдем ССД на которых есть свободное место
                            ssd_chart = {}
                            for patch, disk in CONFIG_DICT["SSD"].items():
                                free = psutil.disk_usage(disk).free
                                total_space = psutil.disk_usage(disk).used + free
                                for plot in all_plots:
                                    if plot.__class__.__name__ == "Plot":
                                        if plot.temp == patch:
                                            total_space -= PLOTS_SIZES_PLOTTING[size] * K
                                if free >= PLOTS_SIZES_PLOTTING[size] * K and total_space >= PLOTS_SIZES_PLOTTING[size] * K:
                                    ssd_chart[patch] = 0
                                #Сделаем рейтинг ССД
                                for plot in all_plots:
                                    if plot.__class__.__name__ == "Plot":
                                        if plot.temp == patch:
                                            ssd_chart[patch] += 1
                            sorted_tuples = sorted(ssd_chart.items(), key=lambda item: item[1])
                            sorted_ssd_chart = {k: v for k, v in sorted_tuples}
                            if sorted_ssd_chart:
                                temp = list(sorted_ssd_chart.keys())[0]
                        if not temp:
                            #Не нашел чем сеять
                            continue
                        
                        #Решим что делать с temp2
                        temp2_to_dest_num = 0
                        for plot in all_plots:
                            if plot.__class__.__name__ == "Plot":
                                if plot.temp2 == list(plots_sizes_sorted)[i]:
                                    temp2_to_dest_num += 1
                        if temp2_to_dest_num < 2:    #Число плотов, которые будут сеятся на этот диск без копирования в конце
                            temp2 = list(plots_sizes_sorted)[i]
                            dest = temp2
                        else:
                            temp2 = None
                            dest = list(plots_sizes_sorted)[i]
                        if not dest:
                            #Не нашел куда сеять
                            continue
                        # Создаем плот
                        create_plot(temp, dest, temp2, size)
                        break
                    last_time = datetime.datetime.now()
                    time.sleep(5)
                    continue

#Если сеем только к32, старый код
                else:
                    # Вычислим сколько нужно свободного места на каждом диске
                    one_plot = 109*1000000000
                    plot_with_temp = 260*1000000000 - one_plot
                    not_free_disk = []
                    for patch in Disk_list.keys():
                        for plot in all_plots:
                            if plot.__class__.__name__ == "Plot":
                                if plot.temp == patch:
                                    Disk_list[patch] -= plot_with_temp
                                if plot.dest == patch:
                                    Disk_list[patch] -= one_plot

                                # plot_sizes = choose_plot_size(Disk_list[patch])
                                # if not plot_sizes

                                if Disk_list[patch] < one_plot:
                                    not_free_disk.append(patch)
                    for patch in not_free_disk:
                        Disk_list.pop(patch, 'some')
                    if not Disk_list:
                        #Не нашел куда сеять
                        last_time = datetime.datetime.now()
                        time.sleep(5)
                        continue
                    #Выбираем темп папку, сначала САТА
                    for patch, free in Disk_list.items():
                        if re.search(r"[Ss][Aa][Tt][Aa]", patch):
                            if not all_plots:
                                if (free - plot_with_temp) >= one_plot:
                                    temp = patch
                                    break    
                            busy_sata = []                        
                            for plot in all_plots:
                                if plot.__class__.__name__ == "Plot":
                                    if plot.temp == patch or plot.dest == patch:
                                        busy_sata.append(patch)
                            if (free - plot_with_temp) >= one_plot and busy_sata.count(patch) == 0:
                                temp = patch
                                break
                    
                    if not temp and CONFIG_DICT["SSD"]:
                        #Найдем ССД на которых есть свободное место
                        ssd_chart = {}
                        for patch, disk in CONFIG_DICT["SSD"].items():
                            free = psutil.disk_usage(disk).free
                            total_space = psutil.disk_usage(disk).used + free
                            for plot in all_plots:
                                if plot.__class__.__name__ == "Plot":
                                    if plot.temp == patch:
                                        total_space -= one_plot + plot_with_temp
                            if free >= one_plot + plot_with_temp and total_space >= one_plot + plot_with_temp:
                                ssd_chart[patch] = 0
                            #Сделаем рейтинг ССД
                            for plot in all_plots:
                                if plot.__class__.__name__ == "Plot":
                                    if plot.temp == patch:
                                        ssd_chart[patch] += 1
                        sorted_tuples = sorted(ssd_chart.items(), key=lambda item: item[1])
                        sorted_ssd_chart = {k: v for k, v in sorted_tuples}
                        if sorted_ssd_chart:
                            temp = list(sorted_ssd_chart.keys())[0]
                    if not temp:
                        #Не нашел чем сеять
                        last_time = datetime.datetime.now()
                        time.sleep(5)
                        continue
                    #Выбираем куда будем сеять, 
                    #Если сеялка сата, сеем на нее
                    if re.search(r"[Ss][Aa][Tt][Aa]", temp) and que["SATA_AS_SSD"] == "no":
                        temp2 = temp
                        dest = temp2
                    #если плотов больше нет, на первый попавшийсся диск
                    if not all_plots and not temp2 and que["SATA_AS_SSD"] == "no":
                        temp2 = list(Disk_list.keys())[0]
                        dest = temp2

                    if not dest:
                        #сделаем рейтинг дисков, сеем на который сеется меньше всего сейчас
                        disk_chart = {}
                        if que["SATA_AS_SSD"] == "yes":
                            usb_free_disks = []
                            for patch, free in Disk_list.items():
                                if not re.search(r"[Ss][Aa][Tt][Aa]", patch) and free >= one_plot:
                                    usb_free_disks.append(patch)
                        for patch, free in Disk_list.items():
                            if (re.search(r"[Ss][Aa][Tt][Aa]", temp) and que["SATA_AS_SSD"] == "yes" and re.search(r"[Ss][Aa][Tt][Aa]", patch) and usb_free_disks) or free < one_plot:   #если сеялка сата и она должна сеять на усб и есть свободные усб.
                                continue
                            disk_chart[patch] = 0
                            for plot in all_plots:
                                if plot.__class__.__name__ == "Plot":
                                    if plot.dest == patch and re.search(r"[Ss][Aa][Tt][Aa]", plot.dest) and re.search(r"[Ss][Aa][Tt][Aa]", plot.temp):
                                        disk_chart.pop(patch, 'some')
                                        continue
                                    if plot.dest == patch:
                                        disk_chart[patch] += 1
                        if disk_chart:
                            sorted_tuples = sorted(disk_chart.items(), key=lambda item: item[1])
                            sorted_disk_chart = {k: v for k, v in sorted_tuples}
                            the_best_disk = list(sorted_disk_chart.keys())[0]
                            temp2_to_dest_num = 0
                            for plot in all_plots:
                                if plot.__class__.__name__ == "Plot":
                                    if plot.temp2 == the_best_disk:
                                        temp2_to_dest_num += 1
                            if temp2_to_dest_num < 2:    #Число плотов, которые будут сеятся на этот диск без копирования в конце
                                temp2 = the_best_disk
                                dest = temp2
                            else:
                                temp2 = None
                                dest = the_best_disk
                    if not dest:
                        #Не нашел куда сеять
                        last_time = datetime.datetime.now()
                        time.sleep(5)
                        continue
                    # Создаем плот
                    create_plot(temp, dest, temp2)
                    
            time.sleep(5)
        else:
            if not globals()['Q'].empty():
                que = globals()['Q'].get()
                continue
            else:
                time.sleep(5)
                continue


#*************************************************************************************************************************
def not_sleep(it):
    while True:
        start_time = datetime.datetime.now()
        Disk_list = disk_list(CONFIG_DICT["MIN_DISK_TOTAL"]*1000000000, 1)

        i = 0
        while i < it:
                for key in Disk_list.keys():
                        if key == "/":
                                continue
                        try:
                                f = open(key+"/sleep.txt")
                                log = f.read()
                        except(FileNotFoundError):
                                f = open(key+"/sleep.txt", 'w')
                                log = ""
                        
                        
                        if log.count("\n") > 1000:
                                f = open(key+"/sleep.txt", 'w')
                        else:
                                f = open(key+"/sleep.txt", 'a')
                                f.write(str(datetime.datetime.now()-start_time)+"\n")
                                f.close()
                i += 1
        time.sleep(60)

def watchdog():
    print("Watchdog started")
    while True:
        if CONFIG_DICT["WD_INTERVAL"] == 0: time.sleep(5)
        else:
            time.sleep(CONFIG_DICT["WD_INTERVAL"])
            cli = os.popen('/usr/lib/chia-blockchain/resources/app.asar.unpacked/daemon/chia wallet show').read()
            cli = cli + os.popen('/usr/lib/chia-blockchain/resources/app.asar.unpacked/daemon/chia farm summary').read()
            stat = {}
            try:
                stat["Sync status: "] = re.findall(r"Sync status: (.+)", cli)[0]
                stat["Farming status: "] = re.findall(r"Farming status: (.+)", cli)[0]
                stat["Plot count for all harvesters: "] = int(re.findall(r"Plot count for all harvesters: (\d+)", cli)[0])
                if not plot_count_all_harvesters or plot_count_all_harvesters <= stat["Plot count for all harvesters: "]:
                    globals()["plot_count_all_harvesters"] = stat["Plot count for all harvesters: "]
            except(IndexError):
                stat["Sync status: "] = "None"
                stat["Farming status: "] = "None"
                stat["Plot count for all harvesters: "] = 0
            if stat["Sync status: "] != "Synced" or stat["Farming status: "] != "Farming" or stat["Plot count for all harvesters: "] < (plot_count_all_harvesters - 10):
                try:
                        f = open(CONFIG_DICT["WATCHDOG_LOG"])
                        log = []
                        for line in f:
                            log.append(line)
                except(FileNotFoundError):
                        f = open(CONFIG_DICT["WATCHDOG_LOG"], 'w')
                        log = []
                dt = datetime.datetime.now()
                if log:
                    f = open(CONFIG_DICT["WATCHDOG_LOG"], 'a')
                    try:
                        last_log = log[len(log)-1]
                        last_time = re.findall(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})    Sync status:", last_log)[0]
                        last_time_timestam = datetime.datetime.strptime(last_time, "%Y-%m-%d %H:%M:%S")
                    except(IndexError):
                        last_time_timestam = datetime.datetime.fromtimestamp(time.mktime(dt.timetuple())) - datetime.timedelta(hours=0, minutes=61)
                else:
                    last_time_timestam = datetime.datetime.fromtimestamp(time.mktime(dt.timetuple())) - datetime.timedelta(hours=0, minutes=61)
                    f = open(CONFIG_DICT["WATCHDOG_LOG"], 'a')
                timestamp_now = datetime.datetime.fromtimestamp(time.mktime(dt.timetuple()))
                if timestamp_now - last_time_timestam > datetime.timedelta(hours=0, minutes=60):
                    text = "Watchdog alert❗\n"
                    for key, value in stat.items():
                        text += "{0} {1}".format(key,value) + "\n"
                    message_to_all(text, None)
                log = "{0}    Sync status:{1}    Farming status:{2}    Plot count:{3} (было {4})\n".format(str(timestamp_now), stat["Sync status: "], stat["Farming status: "], stat["Plot count for all harvesters: "], plot_count_all_harvesters)
                f.write(log)
                f.close()
        
def set_watchdog_interval(arg=None):
    if arg and str(arg).isdigit():
        arg = int(round(float(arg)))
        if arg < 60 and arg != 0:
            text = 'Слишком часто, могу опрашивать не чаще 60 секунд.'
            retur = {"text":text}
            return(retur) 

        globals()["CONFIG_DICT"]["WD_INTERVAL"] = arg
        with open(CONFIG_PATCH, "w") as f:
            f.write(yaml.dump(CONFIG_DICT, sort_keys=False))
        if arg != 0: text = 'Установил интервал обновления: '+str(arg)
        else: text = 'Отключил Watchdog'
        retur = {"text":text}
        return(retur)

    else:
        text = 'Текущее значение: '+str(CONFIG_DICT["WD_INTERVAL"])+'\nНабери: /wd <seconds>'
        retur = {"text":text}
        return(retur)

def set_parallel_plots(arg=None):
    if arg and str(arg).isdigit():
        arg = int(round(float(arg)))
        if arg < 1 or arg > 10:
            text = 'Диапазон от 1 до 10'
            retur = {"text":text}
            return(retur)
        globals()["CONFIG_DICT"]["NUM_PARALLEL_PLOTS"] = arg
        with open(CONFIG_PATCH, "w") as f:
            f.write(yaml.dump(CONFIG_DICT, sort_keys=False))

        que = {"AUTO_P":CONFIG_DICT["AUTO_P"], 
            "COMPUTING_TABLE": CONFIG_DICT["COMPUTING_TABLE"], 
            "NUM_PARALLEL_PLOTS": CONFIG_DICT["NUM_PARALLEL_PLOTS"],
            "SATA_AS_SSD": CONFIG_DICT["SATA_AS_SSD"],
            "USE_K33": CONFIG_DICT["USE_K33"]}
        globals()['Q'].put(que)

        text = 'Число параллельных плотов: '+str(globals()["CONFIG_DICT"]["NUM_PARALLEL_PLOTS"])
        retur = {"text":text}
        return(retur)

    else:
        text = 'Текущее значение: '+str(CONFIG_DICT["NUM_PARALLEL_PLOTS"])+'\nНабери: /parallel_plots <int>'
        retur = {"text":text}
        return(retur)

def set_table(arg=None) -> None:
    if arg and str(arg).isdigit():
        arg = int(round(float(arg)))
        if arg < 1 or arg > 7:
            text = 'Диапазон от 1 до 7'
            retur = {"text":text}
            return(retur)
        globals()["CONFIG_DICT"]["COMPUTING_TABLE"] = arg
        with open(CONFIG_PATCH, "w") as f:
            f.write(yaml.dump(CONFIG_DICT, sort_keys=False))

        que = {"AUTO_P":CONFIG_DICT["AUTO_P"], 
            "COMPUTING_TABLE": CONFIG_DICT["COMPUTING_TABLE"], 
            "NUM_PARALLEL_PLOTS": CONFIG_DICT["NUM_PARALLEL_PLOTS"],
            "SATA_AS_SSD": CONFIG_DICT["SATA_AS_SSD"],
            "USE_K33": CONFIG_DICT["USE_K33"]}
        globals()['Q'].put(que)

        text = 'Начало следующего плота на таблице: '+str(globals()["CONFIG_DICT"]["COMPUTING_TABLE"])
        retur = {"text":text}
        return(retur)

    else:
        text = 'Текущее значение: '+str(CONFIG_DICT["COMPUTING_TABLE"])+'\nНабери: /table <int>'
        retur = {"text":text}
        return(retur)

def set_plot_config(arg=None):
    keyboard = [[]]
    if CONFIG_DICT["SATA_AS_SSD"] == "no":
        keyboard[0].append(InlineKeyboardButton("Использовать SATA", callback_data='plot_config(sata_as_ssd="yes")'))
    else: 
        keyboard[0].append(InlineKeyboardButton("Не использовать SATA", callback_data='plot_config(sata_as_ssd="no")'))

    if CONFIG_DICT["USE_K33"] == "no":
        keyboard[0].append(InlineKeyboardButton("Использовать K33", callback_data='plot_config(use_k33="yes")'))
    else: 
        keyboard[0].append(InlineKeyboardButton("Не использовать K33", callback_data='plot_config(use_k33="no")'))
    
    text = "Настройки засева:\nПараллельных плотов: {0} (/parallel_plots)\nТаблица начала плота: {1} (/table)\nИспользование SATA для засева: {2}\nИспользование К33 плотов: {3}\n".format(CONFIG_DICT["NUM_PARALLEL_PLOTS"], 
            CONFIG_DICT["COMPUTING_TABLE"], 
            CONFIG_DICT["SATA_AS_SSD"], CONFIG_DICT["USE_K33"])
                                                                
    retur = {"text":text, "keyboard":keyboard}
    return(retur)

def set_notify(arg=None, chat_id=None):
    if arg:
        if arg != "on" and arg != "off":
            text = 'Набери: /notify <on/off>'
            retur = {"text":text}
            return(retur)
        if CONFIG_DICT["CHAT_IDS"][chat_id]:
            globals()["CONFIG_DICT"]["CHAT_IDS"][chat_id] = arg
            globals()["Q_for_message"].put(CONFIG_DICT)
            with open(CONFIG_PATCH, "w") as f:
                f.write(yaml.dump(CONFIG_DICT, sort_keys=False))
            text = "Статус уведомлений для {0} теперь {1}".format(chat_id, globals()["CONFIG_DICT"]["CHAT_IDS"][chat_id])
            retur = {"text":text}
            return(retur)
        else:
            text = "Я вас не знаю"
            retur = {"text":text}
            return(retur)
    else:
        text = 'Текущее значение: '+str(CONFIG_DICT["CHAT_IDS"][chat_id])+'\nНабери: /notify <on/off>'
        retur = {"text":text}
        return(retur)

def set_filter(arg=None, chat_id=None):
    if (arg or arg == 0) and str(arg).isdigit():
        arg = int(round(float(arg)))
        if arg < 0:
            text = 'Число должно быть положительным'
            retur = {"text":text}
            return(retur)
        globals()["FILTER_CHAT_IDS"][chat_id] = arg 
        text = "Статус уведомлений фильтра для {0} теперь {1}".format(chat_id, FILTER_CHAT_IDS[chat_id])
        retur = {"text":text}
        return(retur)
    else:
        text = 'Текущее значение: '+str(FILTER_CHAT_IDS[chat_id])+'\nНабери: /filter <int> (плоты прошедшие фильтр)'
        retur = {"text":text}
        return(retur)

def show_log(arg=None):
    if arg and str(arg).isdigit():
        arg = float(arg)
        if arg < 0:
            text ='Число должно быть положительным'
            retur = {"text":text}
            return(retur)
        with open(CONFIG_DICT["WATCHDOG_LOG"]) as f:
            log = []
            for line in f:
                log.append(line)

        dt = datetime.datetime.now()
        timestamp_now = datetime.datetime.fromtimestamp(time.mktime(dt.timetuple()))
        text = ""
        for line in log:
            log_time = re.findall(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", line)[0]
            log_time_timestam = datetime.datetime.strptime(log_time, "%Y-%m-%d %H:%M:%S")
            if timestamp_now - log_time_timestam < datetime.timedelta(hours=arg):
                text += line
        retur = {"text":text}
        return(retur)
    
    else:
        text = 'Набери: /log <int> (часов)'
        retur = {"text":text}
        return(retur)

def reply_message(update, text, reply_markup=None):
    if update['message']['chat']['id'] in MESSAGES and MESSAGES[update['message']['chat']['id']]:
        globals()["MESSAGES"][update['message']['chat']['id']].edit_reply_markup(reply_markup=None)
        globals()["MESSAGES"][update['message']['chat']['id']] = None
    if not reply_markup:
        reply_markup = REPLY_MARKUP[update['message']['chat']['id']]
    mes = update.message.reply_text(text, reply_markup=reply_markup)
    if hasattr(reply_markup, 'inline_keyboard'):
        globals()["MESSAGES"][update['message']['chat']['id']] = mes

def message(chat_id, text, disable_notification, node=1):
    chat_id = int(chat_id)
    if CONFIG_DICT["FULL_NODE"]:
        bot = Bot(token=CONFIG_DICT["TELEGRAM_BOT_TOKEN"])
        if chat_id in MESSAGES and MESSAGES[chat_id]:
            try:
                globals()["MESSAGES"][chat_id].edit_reply_markup(reply_markup=None)
            except:
                pass
            globals()["MESSAGES"][chat_id] = None
        text = "NODE "+str(node)+"\n"+text
        globals()["MESSAGES"][chat_id] = bot.send_message(chat_id=chat_id, text=text, disable_notification=disable_notification, reply_markup=REPLY_MARKUP[chat_id])
    else:
        q = {"chat_id": chat_id, "text": text, "disable_notification": disable_notification}
        data = {"data": 'message(chat_id=q["chat_id"], text=q["text"], disable_notification=q["disable_notification"], node=node)', "q": q}
        socket_client(CONFIG_DICT["NODE_LIST"][1], CONFIG_DICT["FULL_NODE_PORT"], data)
    

def message_to_all(text, disable_notification, node=1):
    if CONFIG_DICT["FULL_NODE"]:
        bot = Bot(token=globals()["CONFIG_DICT"]["TELEGRAM_BOT_TOKEN"])
        if not globals()["Q_for_message"].empty():
            globals()["CONFIG_DICT"] = globals()["Q_for_message"].get()
        if CONFIG_DICT["CHAT_IDS"]:
            for chat_id, notify in CONFIG_DICT["CHAT_IDS"].items():
                if notify == "on" or not disable_notification:
                    if chat_id in MESSAGES and MESSAGES[chat_id]:
                        try:
                            globals()["MESSAGES"][chat_id].edit_reply_markup(reply_markup=None)
                        except:
                            pass
                        globals()["MESSAGES"][chat_id] = None
                    text = "NODE "+str(node)+"\n"+text
                    globals()["MESSAGES"][chat_id] = bot.send_message(chat_id=chat_id, text=text, disable_notification=disable_notification, reply_markup=REPLY_MARKUP[chat_id])
    else:
        q = {"text": text, "disable_notification": disable_notification}
        data = {"data": 'message_to_all(text=q["text"], disable_notification=q["disable_notification"], node=node)', "q": q}
        socket_client(CONFIG_DICT["NODE_LIST"][1], CONFIG_DICT["FULL_NODE_PORT"], data)

def set_farm(update: Update, context: CallbackContext) -> None:
    if not int(update.message.text) in CONFIG_DICT["NODE_LIST"]:
        reply_message(update, "Неправильный номер", reply_markup=REPLY_MARKUP[update['message']['chat']['id']])
        return
    context.user_data["farm"] = update.message.text
    text = "NODE "+str(context.user_data["farm"])+"\n"
    text += START_TEXT
    if int(context.user_data["farm"]) == 1:
        globals()["KEYBOARD"][update['message']['chat']['id']] = get_keyboard()
        globals()["REPLY_MARKUP"][update['message']['chat']['id']] = InlineKeyboardMarkup(KEYBOARD[update['message']['chat']['id']])
    else:
        answ = socket_client(CONFIG_DICT["NODE_LIST"][int(context.user_data["farm"])], CONFIG_DICT["HARVESTER_PORT"], 'get_keyboard()')
        if type(answ) == list:
            globals()["KEYBOARD"][update['message']['chat']['id']] = answ
            globals()["REPLY_MARKUP"][update['message']['chat']['id']] = InlineKeyboardMarkup(KEYBOARD[update['message']['chat']['id']])
        else: text = answ["text"]
    reply_message(update, text, reply_markup=REPLY_MARKUP[update['message']['chat']['id']])

def my_command_handler(update: Update, context: CallbackContext):
    #Если ферма не указана для этого пользователя, то выбираем №1
    if not "farm" in context.user_data:
        context.user_data["farm"] = 1
    text = "NODE "+str(context.user_data["farm"])+"\n\n"
    chat_id = str(update.message.chat.id)
    if update.message.entities:
        command = update.message.text[:update.message.entities[0].length]
        if not context.args: 
            arg = ""
            command_dict_without_arg = {'/notify':'set_notify(chat_id='+chat_id+')',
                                        '/filter':'set_filter(chat_id='+chat_id+')'}
        else: 
            arg = context.args[0]
            command_dict_without_arg = {}
        command_dict= {'/help':'help_command("'+arg+'")',
                        '/wd':'set_watchdog_interval("'+arg+'")',
                        '/parallel_plots':'set_parallel_plots("'+arg+'")',
                        '/table':'set_table("'+arg+'")',
                        '/notify':'set_notify(arg="'+arg+'", chat_id='+chat_id+')',
                        '/filter':'set_filter(arg="'+arg+'", chat_id='+chat_id+')',
                        '/log':'show_log("'+arg+'")',
                        '/set_plot_config':'set_plot_config("'+arg+'")'}
        command_dict.update(command_dict_without_arg)
        print(update.message.chat.first_name+"---->"+command+" "+arg)
        if int(context.user_data["farm"]) == 1:
            retur = eval(command_dict[command])
        else:
            retur = socket_client(CONFIG_DICT["NODE_LIST"][int(context.user_data["farm"])], CONFIG_DICT["HARVESTER_PORT"], command_dict[command])
        text += retur["text"]
        keyboard = retur.get("keyboard")
        if keyboard:
            for line in KEYBOARD[update['message']['chat']['id']]:
                keyboard.append(line)
            reply_markup = InlineKeyboardMarkup(keyboard)
        else:
            reply_markup = None
        if len(text) > 4096:
            with open('bot_send.txt', 'w') as f:
                f.write(text)
            if MESSAGES[update['message']['chat']['id']]:
                globals()["MESSAGES"][update['message']['chat']['id']].edit_reply_markup(reply_markup=None)
            update.message.reply_document(open('bot_send.txt', 'rb'), reply_markup=None)
            globals()["MESSAGES"][update['message']['chat']['id']] = update.message.reply_text("Ответ слишком большой для сообщения", reply_markup=REPLY_MARKUP[update['message']['chat']['id']])
            os.remove('bot_send.txt')
        else:
            if not text or text == "NODE "+str(context.user_data["farm"])+"\n\n":
                text += "Нет данных"
            reply_message(update, text, reply_markup)
    else: start(update, context)
        
def main() -> None:
    """Start the bot."""
    updater = Updater(CONFIG_DICT["TELEGRAM_BOT_TOKEN"])

    conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                PASSWORD: [MessageHandler(Filters.text , password)]},
            fallbacks=[CommandHandler('cancel', cancel)],
            conversation_timeout=(30)
        )
    updater.dispatcher.add_handler(conv_handler)
    updater.dispatcher.add_handler(CallbackQueryHandler(button))
    updater.dispatcher.add_handler(CommandHandler('help', my_command_handler, USERS_FILTER))
    updater.dispatcher.add_handler(MessageHandler(Filters.regex('^(\d{,2})$') & USERS_FILTER, set_farm)),
    updater.dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command & USERS_FILTER, my_command_handler))
    updater.dispatcher.add_handler(CommandHandler("wd", my_command_handler, USERS_FILTER))
    updater.dispatcher.add_handler(CommandHandler("parallel_plots", my_command_handler, USERS_FILTER))
    updater.dispatcher.add_handler(CommandHandler("table", my_command_handler, USERS_FILTER))
    updater.dispatcher.add_handler(CommandHandler("notify", my_command_handler, USERS_FILTER))
    updater.dispatcher.add_handler(CommandHandler("filter", my_command_handler, USERS_FILTER))
    updater.dispatcher.add_handler(CommandHandler("log", my_command_handler, USERS_FILTER))
    updater.dispatcher.add_handler(CommandHandler("set_plot_config", my_command_handler, USERS_FILTER))

    # Start the Bot
    updater.start_polling()

    updater.idle()

#*************************************************************************************************************************************************
def LogParser(logpatch):
    # ЧИтаем лог файл, отправляем по очереди в каждую функцию для проверки
    log_time_old = datetime.datetime.fromtimestamp(time.mktime(datetime.datetime.now().timetuple())) - datetime.timedelta(seconds=10)
    while True:
        if os.path.exists(logpatch):
            with open(logpatch, "r") as f:
                lines = f.readlines()
                sub_lines = lines[len(lines)-50:]
                for line in sub_lines:
                    log_time = re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.\d{3}", line)
                    if log_time:
                        log_time_timestam = datetime.datetime.strptime(log_time[0], "%Y-%m-%dT%H:%M:%S.%f")
                        if log_time_timestam > log_time_old:
                            plots_check_time(line)
                            log_time_old = log_time_timestam
        time.sleep(5)

def plots_check_time(log):
    # Проверяем, является ли лог проверкой времени отклика плота
    matches = re.findall(
                r"(\w{4}.\w{2}.\w{2}).(\w{2}.\w{2}.\w{2}).+(\d+) plots were eligible for farming .+Found ([0-9]) proofs. Time: (\d+.\d+) s. Total (\d+)", log
            )
    if matches:
        for key, value in FILTER_CHAT_IDS.items():
            if value == "not set":
                continue
            if int(matches[0][2]) >= value:
                message(key, "Фильтр: {0}/{1}. Доказательств: {2}. Отклик: {3}\n{4}".format(matches[0][2], matches[0][5], matches[0][3], round(float(matches[0][4]), 2), datetime.datetime.fromtimestamp(time.mktime(datetime.datetime.now().timetuple()))), True)
                
        if not globals()["plot_count"] and matches[0][5]:
            globals()["plot_count"] = int(matches[0][5])
        if globals()["plot_count"] and (int(matches[0][5]) + 1) < int(globals()["plot_count"]):
            message_to_all("Уменьшилось количество плотов с {0} до {1}, проверьте диски".format(globals()["plot_count"], matches[0][5]), None)
            globals()["plot_count"] = matches[0][5]

        if int(matches[0][3]) > 0:
            message_to_all("Найдено доказательство! в: {0}".format(matches[0][1]), None)

        if float(matches[0][4]) > 5:
            pass
        elif float(matches[0][4]) > 2:
            try:
                f = open(CONFIG_DICT["WATCHDOG_LOG"])
                log = f.read()
            except(FileNotFoundError):
                f = open(CONFIG_DICT["WATCHDOG_LOG"], 'w')
                log = []
            if log.count("\n") > 10000:
                f = open(CONFIG_DICT["WATCHDOG_LOG"], 'w')
            else:
                f = open(CONFIG_DICT["WATCHDOG_LOG"], 'a')
            dt = datetime.datetime.now()
            timestamp_now = datetime.datetime.fromtimestamp(time.mktime(dt.timetuple()))
            log = "{0}    Долгий отклик от плота:{1} сек. Фильтр прошли: {2}/{3}\n".format(str(timestamp_now), matches[0][4], matches[0][2], matches[0][5])
            f.write(log)
            f.close()


    matches = re.findall(r"Adding coin: {'amount': (\d+)", log)
    if matches:
        message_to_all("Пополнение кошелька на: {0}".format(int(matches[0])/1000000000000), None)

    matches = re.findall(
                r"Looking up qualities on (.+) took: (\d.\d+)", log
            )
    if matches:
        f = open(CONFIG_DICT["WATCHDOG_LOG"], 'a')

        dt = datetime.datetime.now()
        timestamp_now = datetime.datetime.fromtimestamp(time.mktime(dt.timetuple()))
        log = "{0}    Долгий отклик от плота:{1}. ({2} сек.)\n".format(str(timestamp_now), matches[0][0], round(float(matches[0][1]), 2))
        f.write(log)
        f.close()

        message_to_all("Долгий отклик от плота: {0}. ({1} сек.)".format(matches[0][0], round(float(matches[0][1]), 2)), True)

def del_trash():
    try:
        with open(CONFIG_DICT["PLOTS_FILE"], "rb") as f:
            all_plots = pickle.load(f)
        if not all_plots:
            print("Ничего не сеялось")
            return
    except(FileNotFoundError):
        print("Не нашел файла с плотами")
        return

    for plot in all_plots:
        if plot.__class__.__name__ == "Plot":
            tmp = 0
            tmp2 = 0
            dst = 0
            print("Очистка плота: {0}:".format(plot.name))
            #Удаляем темп файлы
            temp = plot.temp+"/temp"
            try:
                file_list = os.listdir(temp)
                for filename in file_list:
                    os.remove(temp+"/"+filename)
                    tmp += 1
                print("Удалил {0} файлов в {1}".format(str(tmp), temp))
            except(FileNotFoundError):
                print("Не смог удалить файлы из {0}".format(temp))
            #Удаляем темп2 файлы
            if plot.temp2:
                temp2 = plot.temp2+"/plots"
                try:
                    file_list = os.listdir(temp2)
                    for filename in file_list:
                        if plot.name and filename.count(plot.name) and filename.count("2.tmp"):
                            os.remove(temp2+"/"+filename)
                            tmp2 += 1
                    print("Удалил {0} файлов в {1}".format(str(tmp2), temp2))
                except(FileNotFoundError):
                    print("Не смог удалить файлы из {0}".format(temp2))
            #Удаляем dest файлы
            dest = plot.dest+"/plots"
            try:
                file_list = os.listdir(dest)
                for filename in file_list:
                    if plot.name and filename.count(plot.name) and filename.count("2.tmp"):
                        os.remove(dest+"/"+filename)
                        dst += 1
                print("Удалил {0} файлов в {1}".format(str(dst), dest))
            except(FileNotFoundError):
                print("Не смог удалить файлы из {0}".format(dest))
            #Удаляем log файлы
            file_list = os.listdir(CONFIG_DICT["PLOTLOGPATCH"])
            for filename in file_list:
                if plot.name and filename.count(plot.name):
                    os.remove(CONFIG_DICT["PLOTLOGPATCH"]+"/"+filename)
            print("Удалил лог файл в {0}\n".format(CONFIG_DICT["PLOTLOGPATCH"]))
    #Удаляем plots_file.sys файл
    os.remove(CONFIG_DICT["PLOTS_FILE"])

if __name__ == '__main__':
    param = sys.argv
    CONFIG_PATCH = get_script_dir()+"/config.yaml"
    with open(CONFIG_PATCH) as f:
        CONFIG_DICT = yaml.load(f.read(), Loader=yaml.FullLoader)

    SCRIPT_DIR = get_script_dir()

    Q = Queue()
    Q_for_message = Queue()
    Q_for_create_plot_button = Queue()
    Q_for_move_plot_button = Queue()
    Q_for_dell_plot_button = Queue()

    plot_count = None

    START_TEXT = 'Выберите действие:\n/wd <секунд>\n/parallel_plots <int>; /table <int>\n/set_plot_config; \n/notify <on/off>; /filter <int>\n/log <int> (часов)'

    K = 1024**3
    PLOTS_SIZES = {25:0.6, 32:101.4, 33:208.8, 34:429.8, 35:884.1}
    PLOTS_SIZES_PLOTTING = {25:1.8, 32:239, 33:521, 34:1041, 35:2175}

    FILTER_CHAT_IDS = {}
    REPLY_MARKUP = {}
    KEYBOARD = {}
    MESSAGES = {} #Запоминаем сообщения от пользователей, для последующего удаления из них кнопок, так же создаем переменные о фильтрах и клавиатурах для пользователей
    refresh_chat_ids_for_new_user()

    plot_count_all_harvesters = 0

    try:
        if param[1] != "-s":
            message_to_all("Бот запущен. Проверьте, возможно было отключение электричества", None)
        print("Запуск c параметрами\n")
    except(IndexError):
        print("Запуск без параметров\nСейчас произойдет очистка недосозданных плотов, нажмите ctrl+с для отмены")
        #Задержка при запуске вместе с системой, что бы ты подумал
        t = 15
        while t > 0:       
            print(t)
            t -= 1
            time.sleep(1)
        if CONFIG_DICT["HARVESTER_MAC"]:
            send_magic_packet(*CONFIG_DICT["HARVESTER_MAC"])
        del_trash()
        message_to_all("Бот запущен. Проверьте, возможно было отключение электричества", None)

    Process(target=plot_manager).start()
    que = {"AUTO_P":CONFIG_DICT["AUTO_P"], 
            "COMPUTING_TABLE": CONFIG_DICT["COMPUTING_TABLE"], 
            "NUM_PARALLEL_PLOTS": CONFIG_DICT["NUM_PARALLEL_PLOTS"],
            "SATA_AS_SSD": CONFIG_DICT["SATA_AS_SSD"],
            "USE_K33": CONFIG_DICT["USE_K33"]}
    Q.put(que)

    threading.Thread(target=LogParser, args=(CONFIG_DICT["LOGPATCH"],)).start()  #читаем логи
    # Process(target=app.run(host='0.0.0.0')).start()     -Flask
    # threading.Thread(target=not_sleep, args=(1,)).start()  #not_sleep
    #Для фермы1
    if CONFIG_DICT["FULL_NODE"]:
        threading.Thread(target=watchdog).start()  #WatchDog
        #добавим пользователей из конфига в разрешенные
        USERS_FILTER = Filters.user()
        USERS_FILTER.add_user_ids(list(CONFIG_DICT["CHAT_IDS"]))
        
        auth_num = {} #Число попыток авторизации
        if CONFIG_DICT["NODE_LIST"]:
            threading.Thread(target=socket_server, args=(CONFIG_DICT["FULL_NODE_PORT"],)).start()   #сокет для приема сообщений от харвестеров
        main()  #Запустим телеграмм
    # Для харвестеров
    else:
        threading.Thread(target=socket_server, args=(CONFIG_DICT["HARVESTER_PORT"],)).start()   #сокет для приема команд от фермы1
        
