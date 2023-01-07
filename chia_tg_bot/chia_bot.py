from distutils.command.install import HAS_USER_SITE
import logging, re, os, json, yaml, datetime, psutil, time, sys, pickle, socket, threading, subprocess, urllib.request, ccxt, math, requests
import paho.mqtt.subscribe as subscribe
import paho.mqtt.publish as publish
from subprocess import Popen, PIPE
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, Bot, ReplyKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext, MessageHandler, Filters, ConversationHandler
from multiprocessing import Process, current_process, Queue
from requests import Request, Session, get
from requests.exceptions import ConnectionError, Timeout, TooManyRedirects
from wakeonlan import send_magic_packet
from flask import Flask, request
from plots_creator import Plot, get_script_dir, Plots, plots_on_disk, socket_client
from language import *
# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.WARNING
)

logger = logging.getLogger(__name__)

PASSWORD, LANGUAGE = range(2)
app = Flask(__name__)

def socket_server(port):
    
    host = "0.0.0.0"
    port = int(port)
    
    while True:
        p = subprocess.Popen(['sudo', '-S', 'lsof', '-i', ':'+str(port)], stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        text = p.communicate(CONFIG_DICT["SUDO_PASS"] + '\n')[0]
        if not text: break
        time.sleep(5)

    global mySocket
    mySocket = socket.socket()
    try_n = 0
    while try_n < 7:
        try:
            mySocket.bind((host,port))
            print("socket server started at port "+str(host)+":"+str(port))
            break
        except(OSError): 
            time.sleep(10)
            try_n += 1

    while True:
        mySocket.listen(1)
        conn, addr = mySocket.accept()
        # print ("Connection from: " + str(addr[0]))
        try: data = pickle.loads(conn.recv(2048))
        except: data = "error_data"
        safety_addr = False
        node = "UNKNOWN"
        for key, value in CONFIG_DICT["NODE_LIST"].items():
            if value == addr[0]:
                safety_addr = True
                node = key
        if not data or not safety_addr:
            if not data: print("recieved bad data")
            if not safety_addr: print("not safety_addr")
            conn.close()
            time.sleep(1)
            continue
        if type(data) is dict:
            q = data["q"]
            data = data["data"]
        # print ("from connected  user: " + str(data))
        if data == "error_data":
            conn.sendall({"text": "Not received data(server error)\n"})
        else:
            data = eval(data)
            data = pickle.dumps(data)
            conn.sendall(data)
            # print("data:")
            # print((data))
    conn.close()

#Харвестеры будут отправлять свои клавиатуры фулл ноде
def get_keyboard():
    keyboard = [[InlineKeyboardButton(LANG["chia_stat"], callback_data='get_status()'), InlineKeyboardButton("System info", callback_data='get_sys_info()')],
                []]
    line = InlineKeyboardButton("SSD info", callback_data='get_ssd_status()')
    if CONFIG_DICT["SSD_DEVICES"]: keyboard[1].append(line)
    line = InlineKeyboardButton(LANG["get_balance"], callback_data='get_balance()')
    if CONFIG_DICT["FULL_NODE"]: keyboard[1].append(line)
    line = InlineKeyboardButton("GPU info", callback_data='get_gpu_info()')
    if CONFIG_DICT["T_REX"]: keyboard[1].append(line)
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
        if len(match[0][0]) == 1 and int(match[0][0][-1:]) == 1: 
            days = LANG["den"]
        elif int(match[0][0][-1:]) > 1 and int(match[0][0][-1:]) < 5: days = LANG["dnya"]
        else: days = LANG["dney"]
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

def sys_crit_params():
    with open(CONFIG_PATCH) as f:
        globals()["CONFIG_DICT"] = yaml.load(f.read(), Loader=yaml.FullLoader)
    text = ""
    text_for_mqtt = ""
    sudo_password = CONFIG_DICT["SUDO_PASS"]
    #SSD temp
    for key, value in CONFIG_DICT["SSD_DEVICES"].items():
        command = ('smartctl -A -j '+value).split()
        p = Popen(['sudo', '--stdin'] + command, stdout=PIPE, stdin=PIPE, stderr=PIPE,
                universal_newlines=True)
        cli = p.communicate(sudo_password + '\n')[0]
        try:
            data = json.loads(cli)
            # text_for_mqtt += "SSD temperature "+str(key)+";"+str(data["temperature"]["current"])+";"
            if "temperature" in data and data["temperature"]["current"] >= CONFIG_DICT["CRITICAL_PARAMS"]["SSD_temperature"]:
                text += "SSD temperature "+str(key)+" = "+str(data["temperature"]["current"])+"℃\n"
        except(json.decoder.JSONDecodeError, IndexError, KeyError):
            continue

    #Psutil params
    USED_RAM = psutil.virtual_memory()[2]
    text_for_mqtt += "USED_RAM;"+str(USED_RAM)+";"
    if USED_RAM >= CONFIG_DICT["CRITICAL_PARAMS"]["USED_RAM%"]:
        text += "USED_RAM = "+str(USED_RAM)+"%\n"
        if psutil.swap_memory()[0] == 0:
            retur = swap(True)
            time.sleep(5)
            if psutil.swap_memory()[0] > 0:
                text += LANG["SWAP_on_on_demand"]+retur["text"]+"\n"
    CPU_temp = psutil.sensors_temperatures(fahrenheit=False)["coretemp"][0][1]
    text_for_mqtt += "CPU_temperature;"+str(CPU_temp)+";"
    if CPU_temp >= CONFIG_DICT["CRITICAL_PARAMS"]["CPU_temperature"]:
        text += "CPU_temperature = "+str(CPU_temp)+"℃\n"
    #Disk temp
    #HDDTEMP
    devices = disk_list(CONFIG_DICT["MIN_DISK_TOTAL"]*1000000000)
    prev_disks = []
    for dev_num, val in devices.items():
        dev = re.findall(r"\D+", dev_num)[0]
        if not dev in prev_disks:
            p = subprocess.Popen(['sudo', '-S', 'hddtemp', dev, '--numeric', '--quiet'], stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            cli = p.communicate(sudo_password + '\n')[0]
            try:
                data = int(cli)
                # text_for_mqtt += "HDD temperature "+dev+" ("+val[4]+");"+str(data)+";"
                if "usb" in val[4]: crit_t = CONFIG_DICT["CRITICAL_PARAMS"]["HDD_temperature"] + 5
                else: crit_t = CONFIG_DICT["CRITICAL_PARAMS"]["HDD_temperature"]
                if data >= crit_t:
                    text += "HDD temperature "+dev+" ("+val[4]+") = "+str(data)+"℃\n"
            except(ValueError):
                continue
            prev_disks.append(dev)
    #smartctl
    # devices = disk_list(CONFIG_DICT["MIN_DISK_TOTAL"]*1000000000)
    # prev_disks = []
    # for dev_num, val in devices.items():
    #     dev = re.findall(r"\D+", dev_num)[0]
    #     if not dev in prev_disks:
    #         p = subprocess.Popen(['sudo', '-S', 'smartctl', '-A', '-j', dev], stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    #         cli = p.communicate(sudo_password + '\n')[0]
    #         try:
    #             data = json.loads(cli)
    #             # text_for_mqtt += "HDD temperature "+dev+" ("+val[4]+");"+str(data["temperature"]["current"])+";"
    #             if "usb" in val[4]: crit_t = CONFIG_DICT["CRITICAL_PARAMS"]["HDD_temperature"] + 5
    #             else: crit_t = CONFIG_DICT["CRITICAL_PARAMS"]["HDD_temperature"]
    #             if "temperature" in data and data["temperature"]["current"] >= crit_t:
    #                 text += "HDD temperature "+dev+" ("+val[4]+") = "+str(data["temperature"]["current"])+"℃\n"
    #         except(json.decoder.JSONDecodeError, IndexError, KeyError):
    #             continue
    #         prev_disks.append(dev)
    #GPU temp
    if CONFIG_DICT["T_REX"]:
        try:
            contents = urllib.request.urlopen("http://127.0.0.1:4067/summary").read()
            data = json.loads(contents)
            for item in data["gpus"]:
                text_for_mqtt += "GPU temperature "+str(item["device_id"])+";"+str(item["temperature"])+";"
                text_for_mqtt += "GPU hashrate "+str(item["device_id"])+";"+str(round(item["hashrate_minute"]/(10**6),2))+";"
                text_for_mqtt += "GPU fan speed "+str(item["device_id"])+";"+str(item["fan_speed"])+";"
                text_for_mqtt += "GPU power "+str(item["device_id"])+";"+str(item["power"])+";"
                    
                if int(item["temperature"]) >= CONFIG_DICT["CRITICAL_PARAMS"]["GPU_temperature"]:
                    text += "GPU temperature "+str(item["device_id"])+" = "+str(item["temperature"])+"℃\n"
        except:
            pass
    mqtt_publish(text_for_mqtt)
    return text


def start(update: Update, context: CallbackContext) -> None:
    if update["message"]["chat"]["id"] in auth_num and auth_num[update["message"]["chat"]["id"]] > 4:
        update.message.reply_text(LANG['kolvo_popytok'])
        return ConversationHandler.END
    if update['message']['chat']['id'] not in CONFIG_DICT["CHAT_IDS"]:
        update.message.reply_text(LANG['need_auth'])
        return PASSWORD

    #Если ферма не указана для этого пользователя, то выбираем №1
    if not "farm" in context.user_data:
        context.user_data["farm"] = 1
    reply_keyboard = [list(CONFIG_DICT["NODE_LIST"])]
    reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, resize_keyboard=True, one_time_keyboard=False, input_field_placeholder=LANG['node_num'])
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
        return LANG["wrote_chat_ids"]

def refresh_chat_ids_for_new_user():
    for key in CONFIG_DICT["CHAT_IDS"]:
        globals()["FILTER_CHAT_IDS"][key] = "not set"
        globals()["MESSAGES"][key] = None
        globals()["KEYBOARD"][key] = get_keyboard()
        globals()["REPLY_MARKUP"][key] = InlineKeyboardMarkup(KEYBOARD[key])

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
        message_to_all("{4} {3} {5} {0}, {1} {2}".format(update["message"]["chat"]["id"], update["message"]["chat"]["first_name"], 
                                                                            update["message"]["chat"]["last_name"], auth_num[update["message"]["chat"]["id"]],
                                                                            LANG["unauth"], LANG["ot"]), None)
        print("{4} {3} {5} {0}, {1} {2}".format(update["message"]["chat"]["id"], update["message"]["chat"]["first_name"], 
                                                                            update["message"]["chat"]["last_name"], auth_num[update["message"]["chat"]["id"]],
                                                                            LANG["unauth"], LANG["ot"]))
        if auth_num[update["message"]["chat"]["id"]] > 4:
            update.message.reply_text(LANG['kolvo_popytok'])
            return ConversationHandler.END
        time.sleep(auth_num[update["message"]["chat"]["id"]])
        update.message.reply_text('{0} {1})'.format(LANG["wrong_pass"], 5 - auth_num[update["message"]["chat"]["id"]]))
        return PASSWORD

def language_to_harvesters(language, full_node=False):
    globals()["CONFIG_DICT"]["LANGUAGE"] = language
    with open(CONFIG_PATCH, "w") as f:
        f.write(yaml.dump(CONFIG_DICT, sort_keys=False))
    globals()["LANG"] = eval(CONFIG_DICT["LANGUAGE"])
    globals()["START_TEXT"] = LANG["start_text"]
    refresh_chat_ids_for_new_user()
    if full_node:
        chat_dict_to_send = {"data": "language_to_harvesters(q)", "q": language}
        for key, value in CONFIG_DICT["NODE_LIST"].items():
            if key == 1: continue
            socket_client(value, CONFIG_DICT["HARVESTER_PORT"], chat_dict_to_send)
    else:
        return "Choose "+language

def choose_language_1(update: Update, _: CallbackContext):
    text = "Please choose a language:\n"
    reply_keyboard = [LANGUAGE_LIST]
    for lang in LANGUAGE_LIST:
        text += lang+"\n"
    reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, resize_keyboard=True, one_time_keyboard=True, input_field_placeholder='Please choose a language')
    reply_message(update, text, reply_markup)
    return LANGUAGE
def choose_language_2(update: Update, _: CallbackContext):
    if not update.message.text in LANGUAGE_LIST: choose_language_1(update, _)
    else:
        language_to_harvesters(update.message.text, True)
        reply_message(update, LANG["apply_lang"])
        start(update, _)
        return ConversationHandler.END
def help_command(arg=None):
    """Send a message when the command /help is issued."""
    text = LANG["help_text"]
    retur = {"text":text}
    return(retur)

def get_binance_bal():
    exchange = ccxt.binance(CONFIG_BINANCE)
    globals()["balances_binance"] = exchange.fetch_balance()
    globals()["markets_binance"] = exchange.load_markets()
    globals()["usdt_exc_binance"] = {}
    for name, bal in globals()["balances_binance"]["free"].items():
        if bal > 0:
            para = name+"/USDT"
            if para in globals()["markets_binance"]:
                globals()["usdt_exc_binance"][name] = exchange.fetchTicker(para)['ask']
    
def get_okex_bal():
    exchange = ccxt.okex5(CONFIG_OKEX)
    globals()["balances_okex"] = exchange.fetch_balance({'type': 'funding'})
    globals()["markets_okex"] = exchange.load_markets()
    globals()["usdt_exc_okex"] = {}
    for name, bal in globals()["balances_okex"]["free"].items():
        if bal > 0:
            para = name+"/USDT"
            if para in globals()["markets_okex"]:
                globals()["usdt_exc_okex"][name] = exchange.fetchTicker(para)['ask']

def get_balance():
    keyboard = [[]]
    if "BINANCE_KEY" in CONFIG_DICT and "BINANCE_SECRET" in CONFIG_DICT:
        binance_thread_get_bal = threading.Thread(target=get_binance_bal)
        binance_thread_get_bal.start()
    if "OKEX_KEY" in CONFIG_DICT and "OKEX_SECRET" in CONFIG_DICT and "OKEX_PASS" in CONFIG_DICT:
        okex_thread_get_bal = threading.Thread(target=get_okex_bal)
        okex_thread_get_bal.start()

    flist = ['Sync status: ']
    fdict = {}

    cli = os.popen('chia   wallet show').read()
    cli_fs = os.popen('chia   farm summary').read()
    for i in range(len(flist)):
        n=cli.find(flist[i])+len(flist[i])
        k=cli.find('\n', n)
        fdict[flist[i]]= cli[n:k]
        if flist[i] == 'Sync status: ' and fdict[flist[i]] != "Synced":
            fdict[flist[i]] = cli[n:k]+" ❗"
    text = "<b>Balance info:</b>\n"
    for key, value in fdict.items():
        text = text + "{0} {1}".format(key,value) + "\n"

    # user bal
    if "WRITE_BALANCES" in CONFIG_DICT and CONFIG_DICT["WRITE_BALANCES"] == True and os.path.exists(MONEY_PATCH):
        with open(MONEY_PATCH) as f:
            money = yaml.load(f.read(), Loader=yaml.FullLoader)
    else:
        money = {"bds89":0, "other":0}

    if CONFIG_DICT["API_KEY_COINMARKETCUP"]:
        url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'
        parameters = {'id':'9258'}
        headers = {'Accepts': 'application/json','X-CMC_PRO_API_KEY': CONFIG_DICT["API_KEY_COINMARKETCUP"],}

        session = Session()
        session.headers.update(headers)

        try:
            response = session.get(url, params=parameters)
            data = json.loads(response.text)

            chia_price_usd = float(data["data"]["9258"]["quote"]["USD"]["price"])
            chia_percent_change_24h = float(data["data"]["9258"]["quote"]["USD"]["percent_change_24h"])
            result = re.findall(r"-Total Balance:\s+(\d+[.]\d+) xch", cli)
            if result: 
                result = result[0]
                XCH_balance = float(result)
                if CONFIG_DICT["LANGUAGE"] == "russian":
                    url = "https://www.cbr-xml-daily.ru/daily_json.js"
                    r = get(url)
                    USD_price = float(r.json()["Valute"]["USD"]["Value"])
                    # all balance
                    text = text+"{0} XCH * {1}$({2}%) * {3}₽ = {0} * {4} = {5} ₽\n".format(round(XCH_balance, 6), round(chia_price_usd,2), round(chia_percent_change_24h), round(USD_price,2), 
                    round(chia_price_usd*USD_price), 
                    round(XCH_balance*chia_price_usd*USD_price))
                    # bds89 balance
                    if "WRITE_BALANCES" in CONFIG_DICT:
                        text += "bds89:\n{0} XCH = {1} ₽\n".format(round(money["bds89"], 6), round(money["bds89"]*chia_price_usd*USD_price))
                        # other balance
                        text += "other:\n{0} XCH = {1} ₽\n".format(round(money["other"], 6), round(money["other"]*chia_price_usd*USD_price))
                else:
                    # all balance
                    text = text+"{0} XCH * {1}$({2}%) = {3} $\n".format(round(XCH_balance, 6), round(chia_price_usd,2), round(chia_percent_change_24h), round(XCH_balance*chia_price_usd,2))
                    # bds89 balance
                    if "WRITE_BALANCES" in CONFIG_DICT:
                        text += "bds89:\n{0} XCH = {1} $\n".format(round(money["bds89"], 6), round(money["bds89"]*chia_price_usd,2))
                        # other balance
                        text += "other:\n{0} XCH = {1} $\n".format(round(money["other"], 6), round(money["other"]*chia_price_usd,2))
        except (ValueError, ConnectionError, Timeout, TooManyRedirects) as e:
            print(e)

    if "BINANCE_KEY" in CONFIG_DICT and "BINANCE_SECRET" in CONFIG_DICT:
        binance_thread_get_bal.join(10)
    if "balances_binance" in globals() and "markets_binance" in globals() and not binance_thread_get_bal.is_alive():
        text += "<b>"+LANG["binance_balances"]+"</b>\n"
        keyboard = [[]]
        lvl1 = 0
        lvl2 = 0
        for name, bal in globals()["balances_binance"]["free"].items():
            if bal > 0:
                para = name+"/USDT"
                if para in globals()["markets_binance"]:
                    usdt_exc = globals()["usdt_exc_binance"][name]
                    if "USD_price" in locals():
                        text +="{0}: {1} * {2}$ = {3} $ = {4} ₽\n".format(name,bal,round(usdt_exc,4),round(bal*usdt_exc,2),round(bal*usdt_exc*USD_price,2))
                    else: 
                        text +="{0}: {1} * {2}$ = {3} $\n".format(name,bal,round(usdt_exc,4),round(bal*usdt_exc,2))
                    #Кнопки
                    line = InlineKeyboardButton(name, callback_data='binance_sell("'+name+'")_confirm')
                    if lvl1 < 5:            
                        keyboard[lvl2].append(line)
                        lvl1 += 1
                    else:
                        lvl2 += 1
                        lvl1 = 0
                        keyboard.append([])
                        keyboard[lvl2].append(line)

                if name == "USDT": 
                    if "USD_price" in locals(): text += "{0}: {1}$ = {2} ₽\n".format(name,bal,round(bal*USD_price,2))
                    else: text += "{0}: {1} $ \n".format(name,bal)
        globals().pop("balances_binance")
        globals().pop("markets_binance")
        globals().pop("usdt_exc_binance")          

    if "OKEX_KEY" in CONFIG_DICT and "OKEX_SECRET" in CONFIG_DICT and "OKEX_PASS" in CONFIG_DICT:
        okex_thread_get_bal.join(10)
    if "balances_okex" in globals() and "markets_okex" in globals() and not okex_thread_get_bal.is_alive():
        text += "<b>"+LANG["okex_balances"]+"</b>\n"
        if not "keyboard" in locals():
            keyboard = [[]]
        for name, bal in globals()["balances_okex"]["free"].items():
            if bal > 0:
                para = name+"/USDT"
                if para in globals()["markets_okex"]:
                    usdt_exc = globals()["usdt_exc_okex"][name]
                    if "USD_price" in locals():
                        text +="{0}: {1} * {2}$ = {3} $ = {4} ₽\n".format(name,bal,round(usdt_exc,4),round(bal*usdt_exc,2),round(bal*usdt_exc*USD_price,2))
                    else: 
                        text +="{0}: {1} * {2}$ = {3} $\n".format(name,bal,round(usdt_exc,4),round(bal*usdt_exc,2))
                    # #Кнопки
                    # line = InlineKeyboardButton(name, callback_data='binance_sell("'+name+'")_confirm')
                    # if lvl1 < 5:            
                    #     keyboard[lvl2].append(line)
                    #     lvl1 += 1
                    # else:
                    #     lvl2 += 1
                    #     lvl1 = 0
                    #     keyboard.append([])
                    #     keyboard[lvl2].append(line)

                if name == "USDT": 
                    if "USD_price" in locals(): text += "{0}: {1}$ = {2} ₽\n".format(name,bal,round(bal*USD_price,2))
                    else: text += "{0}: {1} $ \n".format(name,bal)
        globals().pop("balances_okex")
        globals().pop("markets_okex")
        globals().pop("usdt_exc_okex")


    total_size_of_plots = re.findall(r"Total size of plots: (\d*.\d*)\s([MGTPE])iB", cli_fs)
    net_space = re.findall(r"Estimated network space: (\d*.\d*)\s([MGTPE])iB", cli_fs)
    if net_space and total_size_of_plots and "chia_price_usd" in locals() and "USD_price" in locals():
        convert = {"M":(0.9765625**3)*(10**-9), "G":(0.9765625**2)*(10**-6), "T":0.9765625*(10**-3), "P":1, "E":1.024*(10**3)}

        my_size = float(float(total_size_of_plots[0][0])*convert[total_size_of_plots[0][1]])
        net_space = float(float(net_space[0][0]) * convert[net_space[0][1]])
        XCHperPib = (my_size/net_space)*4608*2
        USDTperPib = round(XCHperPib*float(chia_price_usd), 2)
        RUBperPib = round(USDTperPib*float(USD_price), 2)

        text += "<b>Day profit:</b>\n"
        text += f"{round(XCHperPib, 5)} XCH, {USDTperPib} $, {RUBperPib} ₽\n"

        retur = {"text":text, "keyboard":keyboard}
    else: 
        retur = {"text":text}

    return(retur)

def binance_sell(name):
    text = ""
    exchange = ccxt.binance(CONFIG_BINANCE)
    markets = exchange.load_markets()
    s = name+'/USDT'
    base = markets[s]['base']
    # если выставлять лимитную заявку на продаже по лучшей цене в книге
    bestAsk = exchange.fetchTicker(s)['ask']
    balance = exchange.fetch_balance()[base]['free']
    amount = balance
    #округление до требуемой точности
    amount = (math.floor(amount*10**markets[s]['precision']['amount'])/
            10**markets[s]['precision']['amount'])
    # есть требования на минимальный объем
    if amount < markets[s]['limits']['amount']['min']:
        text += "{0} {1} {2} {3}\n".format(LANG["not_enought_mon"], name, LANG["for_sell_req"], markets[s]['limits']['amount']['min'])
    # на максимальный
    if amount > markets[s]['limits']['amount']['max']:
        amount = 0.9*markets[s]['limits']['amount']['max']
        #округление до требуемой точности
        amount = (math.floor(amount*10**markets[s]['precision']['amount'])/
                10**markets[s]['precision']['amount'])
    # есть требование к этому cost = price * amount
    if markets[s]['limits']['cost']['min'] and amount*bestAsk < markets[s]['limits']['cost']['min']:
        text += "{0} {1} {2} {3}\n".format(LANG["not_enought_mon"], name, LANG["for_sell_req"], round(markets[s]['limits']['cost']['min']/bestAsk,4))
    if markets[s]['limits']['cost']['max'] and amount*bestAsk > markets[s]['limits']['cost']['max']:
        amount = markets[s]['limits']['cost']['max']/bestAsk
        #округление до требуемой точности
        amount = (math.floor(amount*10**markets[s]['precision']['amount'])/
                10**markets[s]['precision']['amount'])
    params = {
        'test': True,  # test if it's valid, but don't actually place it
    }
    if not text:
        #наконец есть жб объем открываем ордер
        order = exchange.create_order(s, 'limit', 'sell', amount, bestAsk)
        for key, value in order.items():
            if value and not type(value) is dict and not type(value) is list:
                text += str(key)+": "+str(value)+"\n"
        print(order)
    retur = {"text":text}
    return(retur)

def auto_power(chat_id, min=None, max=None):
    text = LANG["auto_power_done"]+"\n"
    step = round((max - min) / 5)
    before = []
    max_finded_pl = 0
    max_finded_hash = 0
    while step != 0:
        if not before: pl = min
        p = subprocess.Popen(['sudo', '-S', 'nvidia-smi', '-pl', str(pl)], stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        p.communicate(CONFIG_DICT["SUDO_PASS"] + '\n')[0]
        i = 0
        hash_summ = 0
        time_start = datetime.datetime.now()
        while datetime.datetime.now() - time_start < datetime.timedelta(seconds=300):
            i += 1
            if i == 1: time.sleep(60)
            else: time.sleep(15)
            try:
                contents = urllib.request.urlopen("http://127.0.0.1:4067/summary").read()
                data = json.loads(contents)
                hash_summ += data["hashrate"]
            except:
                text = LANG["auto_power_fail"]
                message(chat_id=chat_id, text=text, disable_notification=False)
                return
        hash1 = hash_summ/i/pl
        if hash1 > max_finded_hash:
            max_finded_pl = pl
            max_finded_hash = hash1
        text += str(pl)+": "+str(round(hash1/(10**6), 3))+"\n"
        print(str(pl)+":"+str(round(hash1/(10**6), 3)))
        if before:
            if hash1 - before[1] > 0:
                if pl - before[0] > 0:
                    before[0] = pl
                    pl += step
                else:
                    before[0] = pl
                    pl -= step              
            else: 
                step = round(step/2)
                if pl - before[0] > 0:
                    if step != 0: before[0] = pl
                    pl -= step
                else:
                    if step != 0: before[0] = pl
                    pl += step
            if pl < min or pl > max:
                if pl <= min: result = min
                if pl >= max: result = max
                p = subprocess.Popen(['sudo', '-S', 'nvidia-smi', '-pl', str(result)], stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                p.communicate(CONFIG_DICT["SUDO_PASS"] + '\n')[0]
                text += "\nPower limit={0}\n1W={1} MH".format(result, round(hash1/(10**6), 3))
                message(chat_id=chat_id, text=text, disable_notification=False)
                return
            if step != 0: before[1] = hash1
            
            
        else: 
            before = [pl, hash1]
            pl += step
    text += "\nPower limit={0}\n1W={1} MH".format(max_finded_pl, round(max_finded_hash/(10**6), 3))
    p = subprocess.Popen(['sudo', '-S', 'nvidia-smi', '-pl', str(max_finded_pl)], stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    p.communicate(CONFIG_DICT["SUDO_PASS"] + '\n')[0]
    # if hash1 - before[1] > 0:
    #     text += "\nPower limit={0}\n1W={1} MH".format(pl, round(hash1/(10**6), 3))
    # else:
    #     text += "\nPower limit={0}\n1W={1} MH".format(before[0], before[1])
    message(chat_id=chat_id, text=text, disable_notification=False)
    return 

def auto_power_start(chat_id, min=None, max=None):
    if NVIDIA:
        max = int(max)
        min = int(min)
        if not max or not min or max - min <= 0:
            text = LANG["auto_power_fail"]
            retur = {"text":text}
            return(retur)
        threading.Thread(target=auto_power, args=(chat_id, min, max,)).start()
        text = LANG["auto_power_start"]
        retur = {"text":text}
        return(retur)
    else:
        text = LANG["auto_power_fail"]
        retur = {"text":text}
        return(retur)

def gpu_pause(p):
    requests.post('http://127.0.0.1:4067/control', json={"pause": p})
    return(get_gpu_info())

def get_gpu_info():
    text = ""
    try:
        contents = urllib.request.urlopen("http://127.0.0.1:4067/summary").read()
    except:
        text = LANG["no_data_from_trex"]
        retur = {"text":text}
        return(retur)
    data = json.loads(contents)
    # text += "{0}: {1}\n".format(LANG["gpu_difficulty"], round(data["difficulty"],2))
    if len(data["gpus"]) > 1:
        text += "{0}: {1}\n{2}: {3}\n\n".format(LANG["hashrate"], round(data["hashrate"]/(10**6),2), LANG["hashrate_day"], round(data["hashrate_day"]/(10**6),2))
    for item in data["gpus"]:
        text += "{0}: {1}\n{2}: {3}\n{4}: {5}\n{6}: {7}\n{8}: {9}\n{10}: {11}\n{12}: {13}\n".format(LANG["gpu_id"], item["gpu_id"], 
                    LANG["gpu_name"], item["name"], LANG["hashrate"], round(item["hashrate"]/(10**6),2), LANG["hashrate_day"], round(item["hashrate_day"]/(10**6),2),
                    LANG["gpu_fan_speed"], item["fan_speed"], LANG["gpu_power"], item["power"], LANG["gpu_temperature"], item["temperature"])

    text += "{0}: {1}\n".format(LANG["gpu_invalid_count"], data["invalid_count"])
    if NVIDIA:
        text += "Power limit: /pl (power limit W)\nAuto power limit: /auto_power (min)W (max)W\n"
    #Кнопки
    if data["paused"]:
        keyboard = [[InlineKeyboardButton("GPU Pause OFF", callback_data='gpu_pause(False)')]]
    else:
        keyboard = [[InlineKeyboardButton("GPU Pause", callback_data='gpu_pause(True)')]]

    retur = {"text":text, "keyboard":keyboard}
    return(retur)


@app.route('/get_status')
def get_status():
    text = ""
    if CONFIG_DICT["FULL_NODE"]:
        text += "<b>Chia status:</b>\n"
        flist = ['Farming status: ','Total chia farmed: ','Block rewards: ','Plot count for all harvesters: ','Total size of plots: ','Estimated network space: ','Expected time to win: ']
        fdict = {}
        # cli = os.popen('chia   wallet show').read()
        cli = os.popen('chia   farm summary').read()
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
        if "WIN_PROGRESS" in globals() and "WIN_reGRESS" in globals():
            text += "{0} {1}%\n".format(num_to_scale((globals()["WIN_PROGRESS"]*100), 19), round(globals()["WIN_PROGRESS"]*100, 2))
            text += "{0}{1} ({2}%)\n".format(LANG["time_to_win"], time_delta_rus(time_to_win), round((1-globals()["WIN_reGRESS"])*100,2))

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
                                    if hasattr(plot, 'threads'): #потом можно удалить это условие
                                        dir_plots.append(plot.temp+"/temp\n["+str(plot.temp2)+"/plots]\n➜ "+plot.dest+"/plots: (k"+plot.size+") (r"+plot.threads+")")
                                    else:
                                        dir_plots.append(plot.temp+"/temp\n["+str(plot.temp2)+"/plots]\n➜ "+plot.dest+"/plots: (k"+plot.size+")")
                                    progress_plots.append(log.count("\n"))
                    else:
                        tmp = re.findall(r"Starting plotting progress into temporary dirs: /\w+/(.+) and /\w+/(.+)", log)
                        dir_plots.append(tmp[0][0]+" ["+tmp[0][1]+"]")
                        progress_plots.append(log.count("\n"))
            except(IndexError):
                print("except IndexError get_status.re.(filename:"+filename+")")
    try:
        num_string_100 = num_string / num_finish_files
    except(ZeroDivisionError):
        num_string_100 = 2627
    text += "<b>"+LANG["now_plots"]+"</b>\n"

    for dirp, progp in zip(dir_plots, progress_plots):
        text = text + dirp+"\n"+num_to_scale((progp/num_string_100*100), 19)+" "+str(round(progp/num_string_100*100))+"%\n"
    try:
        Stat["AVG_Final_file_size"] = sum(Stat["Final_file_size"]) / len(Stat["Final_file_size"])
        Stat["AVG_Total_time"] = sum(Stat["Total_time"]) / len(Stat["Total_time"])
        Stat["AVG_Copy_time"] = sum(Stat["Copy_time"]) / len(Stat["Copy_time"])
        Stat["AVG_time_per_Gb"] = (Stat["AVG_Total_time"]+Stat["AVG_Copy_time"]) / (Stat["AVG_Final_file_size"])
        text = text + "{0} {1} ".format(LANG["avg_time"], str(datetime.timedelta(seconds=round(Stat["AVG_time_per_Gb"])))) + "\n"
    except(ZeroDivisionError):
        pass
    Disk_dict = disk_list(1100000000000)
    for value in Disk_dict.values():
        kol_plots_dict = choose_plot_size(float(value[2]))
        if kol_plots_dict:
            Stat["space_left"] += kol_plots_dict[1][0]*PLOTS_SIZES[32]*K + kol_plots_dict[1][1]*PLOTS_SIZES[33]*K
    act_plots = num_act_plots()["num"]
    if not act_plots: time_left = "∞"
    else: time_left = str(datetime.timedelta(seconds=round(((Stat["space_left"]/(1000**3)) * Stat["AVG_time_per_Gb"])/act_plots)))
    text = text + "{0} {1} GiB {2} {3} ".format(LANG["left_to_plot"], round(Stat["space_left"]/(1000**3)), LANG["za"], time_delta_rus(time_left)) + "\n" 
    # try:
    #     with open(CONFIG_DICT["LOGPATCH"], 'r') as f:
    #         log = f.read()
    #     match = re.findall(r"Found [0-9] proofs. Time: (\d+.\d+) s. Total", log)
    #     time_summ = 0
    #     for otklik in match:
    #         time_summ += float(otklik)
    #     avg_time = time_summ / len(match)
    #     text = text + "{0} {1} {2} {3}".format(LANG["avg_otklik"], round(avg_time, 4), LANG["popyts"], len(match)) + "\n"
    # except(FileNotFoundError, IndexError, ZeroDivisionError):
    #     print("except in get_status.time_proof")
    if "MQTT_dict" in globals():
        text += "<b>MQTT:</b>\n"
        for name, value in MQTT_dict.items():
            text += "{0}: {1}\n".format(name, value)

    #Кнопки
    if globals()["CONFIG_DICT"]["AUTO_P"] == True:
        keyboard = [[InlineKeyboardButton(LANG["off_autoplot"], callback_data='autoplot(False)_confirm')]]
    else:
        keyboard = [[InlineKeyboardButton(LANG["on_autoplot"], callback_data='autoplot(True)_confirm')]]
    if act_plots > 0:
        line = InlineKeyboardButton(LANG["cancel"], callback_data='dell_plot()')
        keyboard[0].append(line)
    line = InlineKeyboardButton(LANG["create"], callback_data='cpb(q)')  
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

def disk_info():
    if "disk_inf" in globals() and time.time() - globals()["disk_inf"]["time"] < 30:
        return
    Disk_list = disk_list(CONFIG_DICT["MIN_DISK_TOTAL"]*1000000000, full=True)
    Disk_list_keys = list(Disk_list.keys())
    Disk_list_keys.sort()
    text = ""
    prev_disks = {}
    sudo_password = CONFIG_DICT["SUDO_PASS"]
    for key in Disk_list_keys:
        temperature = ""
        dev = re.findall(r"\D+", key)[0]
        if not dev in prev_disks:
            #HDDTEMP
            # p = subprocess.Popen(['sudo', '-S', 'hddtemp', dev, '--numeric', '--quiet'], stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            # cli = p.communicate(sudo_password + '\n')[0]
            # try:
            #     temperature = int(cli)   
            # except(ValueError):
            #     pass
            # prev_disks[dev] = temperature
            #smartctl
            p = subprocess.Popen(['sudo', '-S', 'smartctl', '-A', '-j', dev], stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            cli = p.communicate(sudo_password + '\n')[0]
            try:
                data = json.loads(cli)
                temperature = data["temperature"]["current"]       
            except(json.decoder.JSONDecodeError, IndexError, KeyError):
                pass
            prev_disks[dev] = temperature
        else: temperature = prev_disks[dev]

        if temperature and temperature > CONFIG_DICT["CRITICAL_PARAMS"]["HDD_temperature"] - 5:
            text = text + "{0} ({1}) ({4}℃)❗:\nTotal: {2} GB. Free: {3} GB\nUsed: {5} {6}%".format(key, Disk_list[key][4],round((Disk_list[key][0]/1000000000), 2),round((Disk_list[key][2]/1000000000), 2), temperature, num_to_scale(Disk_list[key][3], 19), Disk_list[key][3]) + "\n"
        else:
            text = text + "{0} ({1})({4}℃):\nTotal: {2} GB. Free: {3} GB\nUsed: {5} {6}%".format(key, Disk_list[key][4], round((Disk_list[key][0]/1000000000), 2),round((Disk_list[key][2]/1000000000), 2), temperature, num_to_scale(Disk_list[key][3], 19), Disk_list[key][3]) + "\n"
    
        globals()["disk_inf"] = {}
        globals()["disk_inf"]["text"] = text
        globals()["disk_inf"]["time"] = time.time()

def cpu_use():
    while True:
        psutil.cpu_percent(percpu=False)
        time.sleep(5)

@app.route('/get_sys_info')
def get_sys_info():
    disk_info_thread = threading.Thread(target=disk_info)
    disk_info_thread.start()

    Used_RAM = psutil.virtual_memory()[2]
    Used_SWAP = psutil.swap_memory()[3]

    Used_CPU = psutil.cpu_percent(percpu=False)
    CPU_freq = round(psutil.cpu_freq(percpu=False)[0])
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
    
    disk_info_thread.join(5)
    if not disk_info_thread.is_alive():
        text += globals()["disk_inf"]["text"]

    text = text + "System start at: {0}".format(Sys_start_at) + "\n"
    #Кнопки
    if psutil.swap_memory()[0] > 0:
        keyboard = [[InlineKeyboardButton(LANG["SWAP_off"], callback_data='swap(False)')]]
    else:
        keyboard = [[InlineKeyboardButton(LANG["SWAP_on"], callback_data='swap(True)')]]
    line = InlineKeyboardButton(LANG["move"], callback_data='mpb(q)')  
    keyboard[0].append(line)
    line = InlineKeyboardButton("k32/k33", callback_data='plplan()')
    keyboard[0].append(line)
    line = InlineKeyboardButton("DELL", callback_data='dpb()')
    keyboard[0].append(line)
    line = InlineKeyboardButton("Governor", callback_data='set_governor()')
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
    text = "{0} {1} MB.\n".format(LANG["SWAP_size"], round(swap_size/1000000))
    retur = {"text":text}
    return(retur)

def cancel():
    text = LANG["cancel"]+"\n"
    retur = {"text":text}
    return(retur)

#cancel_plot
def dell_plot(pid=None):
    try:
        with open(CONFIG_DICT["PLOTS_FILE"], "rb") as f:
            all_plots = pickle.load(f)
        if not all_plots:
            text = LANG["not_ploted"]+"\n"
            retur = {"text":text}
            return(retur)
    except(FileNotFoundError):
        text = LANG["no_file_plot"]+"\n"
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
        text = "<b>"+LANG["choose_plot_cancel"]+"</b>\n"
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
                            text = LANG["cant_dell_plot"]+"\n"
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
                        print("{0} {1}".format(LANG["cant_dell_files"], temp))
                    if plot.temp2:
                        temp2 = plot.temp2+"/plots"
                        try:
                            file_list = os.listdir(temp2)
                            for filename in file_list:
                                if filename.count(plot.name) and filename.count("2.tmp"):
                                    os.remove(temp2+"/"+filename)
                                    tmp2 += 1
                        except(FileNotFoundError):
                            print("{0} {1}".format(LANG["cant_dell_files"], temp2))
                    else: temp2 = ""
                    dest = plot.dest+"/plots"
                    try:
                        file_list = os.listdir(dest)
                        for filename in file_list:
                            if filename.count(plot.name) and filename.count("2.tmp"):
                                os.remove(temp2+"/"+filename)
                                dst += 1
                    except(FileNotFoundError):
                        print("{0} {1}".format(LANG["cant_dell_files"], dest))
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
        text = "{0} {1} {2}\n{3} {4} {5} {6}\n{3} {7} {5} {8}\n{3} {9} {5} {10}\{3} {11} {12}\n{3} {13} {14}\n".format(
        LANG["complete"], proc, LANG["procs"], LANG["deleted"], tmp, LANG["files_in"], temp, tmp2, temp2, dst, dest, log, LANG["log_file"], pf, LANG["plots_file"])
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
                text = que["first_name"]+LANG["anybody_create"]
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
    keyboard = [[InlineKeyboardButton(LANG["cancel"], callback_data='cpb(q, "no")')]]
    if param == "no":
        try:
            que = globals()['Q_for_create_plot_button'].get_nowait()
        except:
            pass
        text = LANG["clear_params"]+"\n"
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
        text += LANG["ch_size_plot"]+"\n\n"
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
        text += LANG["temp_disk"]+"\n\n"
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
            text = LANG["not_enought_space"]+"\n"
        retur = {"text":text, "keyboard":keyboard}
        return(retur)

    if not "-2 " in que and "-z " in que:
        text = ""
        for key in parameters:
            if key in que:
                text += key+": "+que[key]+"\n"
        text += LANG["temp2_disk"]+"\n\n"
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
        text += LANG["dest_disc"]+"\n\n"
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
            text = LANG["creating"]+"\n"
            keyboard = []
        elif param == "no":
            try:
                que = globals()['Q_for_create_plot_button'].get_nowait()
            except:
                pass
            text = LANG["clear_params"]+"\n"
            keyboard = []
        else:
            text = "size: {0}\ntemp: {1}\ntemp2: {2}\ndest: {3}\n{4}\n".format(que["-z "], que["-t "], que["-2 "], que["-d "], LANG["create_ask"])
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
        text = LANG["clear_params"]+"\n"
        keyboard = [[]]
        retur = {"text":text, "keyboard":keyboard}
        return(retur)

    #disk
    if not "-d " in que:
        text = ""
        for key in parameters:
            if key in que:
                text += key+": "+str(que[key])+"\n"
        text += LANG["choose_dell_disk"]+"\n\n"
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
        text += LANG["age_plots"]+"\n\n"
        line = InlineKeyboardButton(LANG["old"], callback_data='dpb("-o True")')
        keyboard[0].append(line)
        line = InlineKeyboardButton(LANG["any"], callback_data='dpb("-o False")')
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
            text = LANG["no_plots_on_disk"]+"\n"
            retur = {"text":text}
            return(retur)
        if dig != 1:
            text += LANG["type_plot"]+"\n"
            lvl1 = 0
            lvl2 = 0
            for key, value in plot_list.items():
                if key.isdigit():
                    text += "{0} {1} {2} k{3}\n".format(LANG["find"], value, LANG["plots"], key)
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
                    text += "{0} {1} {2} k{3}\n".format(LANG["find"], value, LANG["plots"], key)
    #kolvo
    if not "-n " in que and "-z " in que and "-o " in que:
        if "text" not in locals():
            text = ""
            for key in parameters:
                if key in que:
                    text += key+": "+str(que[key])+"\n"
        text += LANG["kolvo_to_dell"]+"\n\n"
        lvl1 = 0
        lvl2 = 0
        plot_list = plots_on_disk(patch=que["-d "], old=que["-o "])
        for key, value in plot_list.items():
            if key.isdigit() and key == que["-z "]:
                if value < 10:
                    num_but = value
                else: 
                    num_but = 10
                    all_but = value
        if "num_but" in locals():
            for i in range(num_but):
                if "all_but" in locals():
                    if i == num_but-1:
                        i = all_but - 1
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
            text = LANG["no_good_plots"]+"\n"
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
            nft_or_not={True:"not NFT", False:LANG["any"]}
            text = "{0} {1} {2} {3} ({4}) {5} {6}.".format(LANG["deleted"], n, LANG["plot_of_size"], que["-z "], nft_or_not[bool(que["-o "])], LANG["from_disc"], que["-d "])
            keyboard = []
        else:
            text = "{0} {1}\n{2} {3}\n{4} k{5}\n{6} {7}\n{8}\n".format(LANG["on"], que["-d "], LANG["old2"], str(que["-o "]), LANG["size"], que["-z "], LANG["num"], que["-n "], LANG["will_dell"])
            keyboard = [[InlineKeyboardButton("Да", callback_data='dpb("yes")'), InlineKeyboardButton(LANG["cancel"], callback_data='dpb("no")')]]
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
                text = que["first_name"]+LANG["alredy_move"]
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
    keyboard = [[InlineKeyboardButton(LANG["cancel"], callback_data='mpb(q, "no")')]]
    if param == "no":
        try:
            que = globals()['Q_for_move_plot_button'].get_nowait()
        except:
            pass
        text = LANG["clear_params"]+"\n"
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
        text += LANG["choose_disk_to_move"]+"\n\n"
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
        if "text" not in locals():
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
            text = LANG["not_find_plots"]+"\n"
            retur = {"text":text}
            return(retur)
        if dig != 1:
            for key in parameters:
                if key in que:
                    text += key+": "+que[key]+"\n\n"

            text += LANG["type_plot"]+"\n"
            lvl1 = 0
            lvl2 = 0
            for key, value in plot_list.items():
                if key.isdigit():
                    text += "{0} {1} {2} k{3}\n".format(LANG["find"], value, LANG["plots"], key)
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
            globals()['Q_for_move_plot_button'].get_nowait()
            for key, value in plot_list.items():
                if key.isdigit():
                    text += "{0} {1} {2} k{3}\n".format(LANG["find"], value, LANG["plots"], key)
            globals()['Q_for_move_plot_button'].put(que)


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
                    text = LANG["alredy_moving"]+"\n"
                    retur = {"text":text}
                    return(retur)

        if "text" not in locals():
            text = ""
        for key in parameters:
            if key in que:
                text += key+": "+que[key]+"\n"
        text += LANG["num_plots_to_move"]+"\n\n"
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
        if "text" not in locals():
            text = ""
        for key in parameters:
            if key in que:
                text += key+": "+que[key]+"\n"
        text += LANG["choose_disk_to_move_on"]+"\n\n"
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
            text = LANG["not_enought_space_to_move"]+"\n"
            keyboard = [[]]
        retur = {"text":text, "keyboard":keyboard}
        return(retur)



    if "-s " in que and "-n " in que and "-z " in que and "-d " in que:
        if "text" not in locals():
            text = ""
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
            text = LANG["moving"]+"\n"+LANG["will_send_notify"]+"\n"
            keyboard = []
        else:
            text += "{0} {1}\n{2} {3}\n{4} k{5}\n{6} {7}\n{8}\n".format(LANG["from"], que["-s "], LANG["to"], que["-d "], 
                                                                                        LANG["size"], que["-z "], LANG["num"], que["-n "], LANG["will_move"])
            keyboard = [[InlineKeyboardButton("Да", callback_data='mpb(q, "yes")'), InlineKeyboardButton("Отмена", callback_data='mpb(q, "no")')]]
            globals()['Q_for_move_plot_button'].put(que)
        retur = {"text":text, "keyboard":keyboard}
        return(retur)

def plplan(disk=None):
    if not disk:
        text = LANG["choose_disc_for_info"]+"\n"
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
        keyboard = [[InlineKeyboardButton(LANG["back"], callback_data='plplan()')]]
        text = LANG["disc"]+disk+"\n"+LANG["calc_by_total"]+"\n"
        d = psutil.disk_usage(disk)
        total = d[1]+d[2]
        answ = choose_plot_size(total)
        text += "k32:{0}, k33:{1} |{2}GiB\n".format(answ[1][0], answ[1][1], round(answ[0], 2))
        answ = choose_plot_size(d[2])
        if answ:
            text += "{0} ({1}Gb) {2}\nk32:{3}, k33:{4} |{5}Gb\n".format(LANG["calc_by_free"], round(d[2]*1e-9,1), LANG["space"], answ[1][0], answ[1][1], round(answ[0], 2))
        else: text += LANG["not_enought_space_on_disc"]+"\n"
        text += LANG["find_on_disc"]+"\n"
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
        text = LANG["using_SATA_as_SSD"]+"\n"
    elif sata_as_ssd == "no":
        globals()["CONFIG_DICT"]["SATA_AS_SSD"] = "no"
        text = LANG["not_using_SATA_as_SSD"]+"\n"
    if use_k33 == "yes":
        globals()["CONFIG_DICT"]["USE_K33"] = "yes"
        text = LANG["using_k33"]+"\n"
    elif use_k33 == "no":
        globals()["CONFIG_DICT"]["USE_K33"] = "no"
        text = LANG["using_k33"]+"\n"
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

def set_governor(gov=None):
    if not gov:
        with open('/sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors') as f:
            governors = re.findall(r'\w+', f.read())
        with open('/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor') as f:
            governor = re.findall(r'\w+', f.read())
        text = LANG["current_governor"] +': '+governor[0]+'\n' 
        lvl1 = 0
        lvl2 = 0
        keyboard = [[]]
        for g in governors:
            if g == governor[0]: continue
            line = InlineKeyboardButton(g, callback_data='set_governor("'+g+'")')
            if lvl1 < 3:            
                keyboard[lvl2].append(line)
                lvl1 += 1
            else:
                lvl2 += 1
                lvl1 = 0
                keyboard.append([])
                keyboard[lvl2].append(line)
        retur = {"text":text, "keyboard":keyboard}
        return(retur)

    process = subprocess.run(['ls /sys/devices/system/cpu/'], check=True, shell=True, stdout=subprocess.PIPE, universal_newlines=True)
    output = process.stdout
    cpus = re.findall(r"cpu\d+", output)
    sudo_password = CONFIG_DICT["SUDO_PASS"]
    for cpu in cpus:
        p = subprocess.Popen(['sudo', '-S', 'sh', '-c', 'echo '+gov+' > /sys/devices/system/cpu/'+cpu+'/cpufreq/scaling_governor'], stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        cli = p.communicate(sudo_password + '\n')[0]
    text = LANG["set_governor"] +': '+gov+'\n' 
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
        message_to_all("{0} {1}, {2} {3}".format(LANG["hacking_by"], query["message"]["chat"]["id"], query["message"]["chat"]["first_name"], 
                                                                            query["message"]["chat"]["last_name"]), None)
        print("{0} {1}, {2} {3}".format(LANG["hacking_by"], query["message"]["chat"]["id"], query["message"]["chat"]["first_name"], 
                                                                            query["message"]["chat"]["last_name"]))
        return

    reply_markup = InlineKeyboardMarkup(KEYBOARD[query["message"]["chat"]["id"]])

    query.answer()
    query.edit_message_text(text=LANG["working"], parse_mode="HTML", reply_markup=reply_markup)

    if query_data[len(query_data)-len("confirm"):] == "confirm":
        text = LANG["you_sure"]+"\n"
        keyboard = [[InlineKeyboardButton(LANG["yes"], callback_data=query_data[:(len(query_data)-len("_confirm"))]), InlineKeyboardButton(LANG["cancel"], callback_data="cancel()")]]
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
    text = text+"<b>{0} {1}</b>".format(LANG["refreshed"], current_datetime)


    query.edit_message_text(text=text, parse_mode="HTML", reply_markup=reply_markup)


#*************************************************************************************************************************
def autoplot(auto):
    if auto == True:
        if globals()["CONFIG_DICT"]["AUTO_P"] == True:
            text = LANG["cant_on_twice"]+"\n"
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

            text = LANG["autoplot_turn_on"]+"\n"
            retur = {"text":text}
            return(retur)
    if auto == False:
        if globals()["CONFIG_DICT"]["AUTO_P"] == False:
            text = LANG["cant_off_twice"]+"\n"
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

            text = LANG["autoplot_turn_off"]+"\n"
            retur = {"text":text}
            return(retur)


def num_act_plots(table=None):
    num = 0
    num_with_table = 0
    ready = False
    if table: weight_of_plots = {25:0.1, 32:1, 33:2, 34:4, 35:8}
    else: weight_of_plots = {25:1, 32:1, 33:1, 34:1, 35:1}
        
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
                if table and re.search(r'Computing table '+str(table), log):
                    num_with_table += weight_of_plots[size]
    if num_with_table == num:
        ready = True        
    dict = {"num":num, "ready":ready}
    return(dict)

def choose_plot_size(free):
    k32 = PLOTS_SIZES[32]*K
    k33 = PLOTS_SIZES[33]*K
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

def create_plot(temp, dest, temp2=None, size=32, threads=2):
    if not temp2:
        temp2 = ''
    patch = "python3 "+SCRIPT_DIR+"/plots_creator.py"
    patch += " '-t "+temp+"' '-2 "+temp2+"' '-d "+dest+"' '-z "+str(size)+"' '-r "+str(threads)+"'"
    # patch = patch.split()
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
                        #Проверим сеется ли что-то на диск или копируется
                        for plot in all_plots:
                            #При копировании, не будем на него сеять
                            if plot.__class__.__name__ == "Plots":
                                if patch in plot.dest:
                                    bad_patch.append(patch)
                                    continue
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
                    #отсортируем список дисков, вверху не сата и менее используемые, c необходимостью в плоте к33, на которых всех больше свободного места
                    plots_sizes_sorted = {}
                    for_sort = {}
                    for patch in plots_sizes.keys():
                        if re.search(r"[Ss][Aa][Tt][Aa]", patch): for_sort[patch] = 10000
                        elif re.search(r"[Uu][Ss][Bb]", patch): for_sort[patch] = 0
                        else: for_sort[patch] = 1000
                        for key in busy_disks:
                            if key == patch:
                                for_sort[patch] += 10
                        if plots_sizes[patch][33] == 0:
                            for_sort[patch] += 1
                        for_sort[patch] += 1/(Disk_list[patch]/1000000000000)
                    sorted_tuples = sorted(for_sort.items(), key=lambda item: item[1])
                    sorted_for_sort= {k: v for k, v in sorted_tuples}
                    for key in sorted_for_sort.keys():
                        plots_sizes_sorted[key] = plots_sizes[key]
                    # print(plots_sizes_sorted)
                    sizes = [33,32]
                    #Будем пробовать сеять подходящий вариант
                    for sz in sizes:
                        for i in range(len(plots_sizes_sorted)):
                            temp = None
                            temp2 = None
                            dest = None
                            if plots_sizes_sorted[list(plots_sizes_sorted)[i]][sz] > 0: size = sz
                            else: continue
                            #Выбираем темп папку, сначала САТА
                            #Сначала сам на себя, если это САТА
                            patch = list(plots_sizes_sorted)[i]
                            if re.search(r"[Ss][Aa][Tt][Aa]", patch) and (Disk_list[patch] - PLOTS_SIZES_PLOTTING[size] * K - PLOTS_SIZES[size] * K) >= 0:
                                busy_sata = []
                                for plot in all_plots:
                                    if plot.__class__.__name__ == "Plot":
                                        if plot.temp == patch or plot.dest == patch:
                                            busy_sata.append(patch)
                                if patch not in busy_sata: temp = patch
                            #Если сам на себя не может, поищем другую САТА там где совпадают названия
                            if not temp:
                                for patch, free in Disk_list.items():
                                    if re.search(r"[Ss][Aa][Tt][Aa]", patch) and re.search(r"(\d+_\d+)", patch) and re.search(r"(\d+_\d+)", list(plots_sizes_sorted)[i]):
                                        if re.findall(r"(\d+_\d+)", patch)[0] == re.findall(r"(\d+_\d+)", list(plots_sizes_sorted)[i])[0]:
                                            busy_sata = []                        
                                            for plot in all_plots:
                                                if plot.__class__.__name__ == "Plot":
                                                    if plot.temp == patch or plot.dest == patch:
                                                        busy_sata.append(patch)
                                            if (free - PLOTS_SIZES_PLOTTING[size] * K - PLOTS_SIZES[size] * K) >= 0 and patch not in busy_sata and (list(plots_sizes_sorted)[i] != patch and que["SATA_AS_SSD"] == "yes"):
                                                temp = patch
                                                break
                            #Если сам на себя не может, поищем другую САТА
                            if not temp:
                                for patch, free in Disk_list.items():
                                    if re.search(r"[Ss][Aa][Tt][Aa]", patch):
                                        busy_sata = []                        
                                        for plot in all_plots:
                                            if plot.__class__.__name__ == "Plot":
                                                if plot.temp == patch or plot.dest == patch:
                                                    busy_sata.append(patch)
                                        if (free - PLOTS_SIZES_PLOTTING[size] * K - PLOTS_SIZES[size] * K) >= 0 and patch not in busy_sata and (list(plots_sizes_sorted)[i] != patch and que["SATA_AS_SSD"] == "yes"):
                                            temp = patch
                                            break
                            #Если нечем больше сеять, все-таки попробуем сам на себя, под завязку, если это САТА
                            if not temp:
                                patch = list(plots_sizes_sorted)[i]
                                if re.search(r"[Ss][Aa][Tt][Aa]", patch) and (Disk_list[patch] - PLOTS_SIZES_PLOTTING[size] * K) >= 0:
                                    busy_sata = []
                                    for plot in all_plots:
                                        if plot.__class__.__name__ == "Plot":
                                            if plot.temp == patch or plot.dest == patch:
                                                busy_sata.append(patch)
                                    if patch not in busy_sata: temp = patch
                            #И еще попробуем другую САТА, под завязку
                            if not temp:
                                for patch, free in Disk_list.items():
                                    if re.search(r"[Ss][Aa][Tt][Aa]", patch):
                                        busy_sata = []                        
                                        for plot in all_plots:
                                            if plot.__class__.__name__ == "Plot":
                                                if plot.temp == patch or plot.dest == patch:
                                                    busy_sata.append(patch)
                                        if (free - PLOTS_SIZES_PLOTTING[size] * K) >= 0 and patch not in busy_sata and (list(plots_sizes_sorted)[i] != patch and que["SATA_AS_SSD"] == "yes"):
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
                                            if plot.temp == patch and patch in ssd_chart:
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
                            #Выберем сколько ядер(потоков) использовать
                            proc_thread = psutil.cpu_count()
                            used_threads = 0
                            weight_of_plots = {25:0.1, 32:1, 33:2, 34:4, 35:8}
                            free_parallel_plots = que["NUM_PARALLEL_PLOTS"]
                            for plot in all_plots:
                                if plot.__class__.__name__ == "Plot":
                                    if hasattr(plot, 'threads'): used_threads += int(plot.threads)  #потом можно удалить это условие
                                    else: used_threads += 2
                                    free_parallel_plots -= weight_of_plots[int(plot.size)]
                            free_parallel_plots -= weight_of_plots[int(size)]

                            print("proc_thread="+str(proc_thread))
                            print("used_threads="+str(used_threads))
                            print("free_parallel_plots="+str(free_parallel_plots))
                            if free_parallel_plots == 0 and proc_thread - used_threads >= 4: threads = 4
                            else:
                                if proc_thread - used_threads - free_parallel_plots*2 > 0: threads = 4
                                else: threads = 2
                                        
                            # Создаем плот
                            create_plot(temp, dest, temp2, size, threads)
                            time.sleep(15)
                            break
                        if temp and dest: break
                    if temp and dest: pass
                    else: last_time = datetime.datetime.now()
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
                    #Выберем сколько ядер(потоков) использовать
                    proc_thread = psutil.cpu_count()
                    used_threads = 0
                    weight_of_plots = {25:0.1, 32:1, 33:2, 34:4, 35:8}
                    free_parallel_plots = que["NUM_PARALLEL_PLOTS"]
                    for plot in all_plots:
                        if plot.__class__.__name__ == "Plot":
                            if hasattr(plot, 'threads'): used_threads += int(plot.threads)  #потом можно удалить это условие
                            else: used_threads += 2
                            free_parallel_plots -= weight_of_plots[int(plot.size)]
                    free_parallel_plots -= weight_of_plots[int(size)]
                    if free_parallel_plots == 0 and proc_thread - used_threads >= 2: 
                        threads = proc_thread - used_threads
                        if threads > 8: threads = 8
                    else:
                        if proc_thread - used_threads - free_parallel_plots*2 > 0: threads = 4
                        else: threads = 2
                    # Создаем плот
                    create_plot(temp, dest, temp2, 32, threads)
                    
            time.sleep(5)
        else:
            if not globals()['Q'].empty():
                que = globals()['Q'].get()
                continue
            else:
                time.sleep(5)
                continue


#*************************************************************************************************************************
def not_sleep():
    while True:
        devices = disk_list(CONFIG_DICT["MIN_DISK_TOTAL"]*1000000000)
        prev_disks = []
        for dev_num in devices.keys():
            if dev_num == "/":
                continue
            dev = re.findall(r"\D+", dev_num)[0]
            if not dev in prev_disks:
                prev_disks.append(dev)
                command = ("sudo smartctl -g apm "+dev).split()
                p = subprocess.Popen(command, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                cli = p.communicate(CONFIG_DICT["SUDO_PASS"] + '\n')[0]
                if "APM level is" in cli and not "254" in cli:
                    command = ("sudo -S hdparm -B 254 -S 0 "+dev).split()
                    p = subprocess.Popen(command, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                    p.communicate(CONFIG_DICT["SUDO_PASS"] + '\n')[0]
                    print("sudo -S hdparm -B 254 -S 0 "+dev)

        start_time = datetime.datetime.now()
        for dev_num, val in devices.items():
            dev = re.findall(r"\D+", dev_num)[0]
            if dev in HAVNT_SMART:
                if val[4] == "/":
                    continue
                try:
                    f = open(val[4]+"/sleep.txt")
                    log = f.read()
                except(FileNotFoundError):
                    f = open(val[4]+"/sleep.txt", 'w')
                    log = ""
                
                if log.count("\n") > 1000:
                    f = open(val[4]+"/sleep.txt", 'w')
                else:
                    f = open(val[4]+"/sleep.txt", 'a')
                    f.write(str(datetime.datetime.now()-start_time)+"\n")
                f.close()
        time.sleep(60)
def smartdog():  #Отслеживаем изменение SMART дисков
    famous__smart_attr = ["Raw_Read_Error_Rate",
                        "Power_Cycle_Count",
                        "Reallocated_Sector_Ct",
                        "Seek_Error_Rate",
                        "Spin_Retry_Count",
                        "Helium_Condition_Lower",
                        "Helium_Condition_Upper",
                        "G-Sense_Error_Rate",
                        "Power-Off_Retract_Count",
                        "Load_Cycle_Count",
                        "Reallocated_Event_Count",
                        "Current_Pending_Sector",
                        "Offline_Uncorrectable",
                        "UDMA_CRC_Error_Count"]
    sudo_password = CONFIG_DICT["SUDO_PASS"]
    disk_smart_dict ={}
    while (True):
        now = datetime.datetime.now()
        if now.hour == 0 or not disk_smart_dict:
            devices = disk_list(CONFIG_DICT["MIN_DISK_TOTAL"]*1000000000)
            prev_disks = []
            for dev_num, val in devices.items():
                dev = re.findall(r"\D+", dev_num)[0]
                if not dev in prev_disks:
                    prev_disks.append(dev)
                    p = subprocess.Popen(['sudo', '-S', 'smartctl', '-A', '-j', dev], stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                    cli = p.communicate(sudo_password + '\n')[0]
                    try:
                        data = json.loads(cli)
                    except(json.decoder.JSONDecodeError):
                        continue
                    if not dev in disk_smart_dict:
                        disk_smart_dict[dev] = {}
                    if "ata_smart_attributes" in data:
                        for attr in data["ata_smart_attributes"]["table"]:
                            if attr["name"] in famous__smart_attr:
                                if attr["name"] in disk_smart_dict[dev]:
                                    if disk_smart_dict[dev][attr["name"]]["value"] != attr["value"]:
                                        text = "Диск {0} ({1}), изменилось относительное значение {2} с {3} на {4}. Порог: {5}".format(dev, val[4], attr["name"], disk_smart_dict[dev][attr["name"]]["value"], attr["value"], attr["thresh"])
                                        message_to_all(text, True)
                                        disk_smart_dict[dev][attr["name"]]["value"] = attr["value"]
                                    if disk_smart_dict[dev][attr["name"]]["raw"] < 5000 \
                                        and \
                                    ((disk_smart_dict[dev][attr["name"]]["raw"] != attr["raw"]["value"] and attr["name"] != "Load_Cycle_Count" \
                                        and \
                                    attr["name"] != "Power-Off_Retract_Count") \
                                        or \
                                    (int(attr["raw"]["value"]) - int(disk_smart_dict[dev][attr["name"]]["raw"]) > 2)):
                                        text = "Диск {0} ({1}), изменилось абсолютное значение {2} с {3} на {4}".format(dev, val[4], attr["name"], disk_smart_dict[dev][attr["name"]]["raw"], attr["raw"]["value"])
                                        message_to_all(text, True)
                                        disk_smart_dict[dev][attr["name"]]["raw"] = attr["raw"]["value"]
                            else: disk_smart_dict[dev][attr["name"]] = {"value":attr["value"], "raw":attr["raw"]["value"]}
                    else:
                        HAVNT_SMART.append(dev)
                        print("Диск {0} havn't smart data".format(dev))

            time.sleep(3600)

        time.sleep(1700)
def phase2time():
    if os.path.exists(CONFIG_DICT["PLOTLOGPATCH"]):
        file_list = os.listdir(CONFIG_DICT["PLOTLOGPATCH"])
        file_dict = {}
        #Будем учитывать только последние лог файлы, для этого отсорируем список файлов директории лога по дате создания
        for filename in file_list:
            file_dict[filename] = os.path.getmtime(CONFIG_DICT["PLOTLOGPATCH"]+"/"+filename)
        sorted_tuples = sorted(file_dict.items(), key=lambda item: item[1], reverse=True)
        sorted_file_dict = {k: v for k, v in sorted_tuples}
    else: sorted_file_dict = []
    ph2max = 13000
    sorted_file_list = list(sorted_file_dict)
    for filename in sorted_file_list[:CONFIG_DICT["NUM_PARALLEL_PLOTS"]*2]:
        with open(CONFIG_DICT["PLOTLOGPATCH"]+"/"+filename, 'r') as f:
            log = f.read()
        if re.search(r"Time for phase 2 = (\d+)", log):
            ph2 = re.findall(r"Time for phase 2 = (\d+)", log)[0]
            if float(ph2) > ph2max: ph2max = float(ph2)
    return(ph2max*1.2)

def adding_coin(adding_value, cli):
    message_to_all("{0} {1}".format(LANG["wallet_in"], adding_value, None), None)
    if round(adding_value, 2) == 0.25 or round(adding_value, 2) == 1.75:
        globals()["WIN_PROGRESS"] = 0
        globals()["WIN_reGRESS"] = 0
    
    convert = {"M":1, "G":1*10**3, "T":1*10**6, "P":1*10**9, "E":1*10**12}

    shared_names = ["Local Harvester", "Remote Harvester for IP: 212.75.234.213"]
    try:
        start = cli.index("Local Harvester")
        end = cli.index("Estimated network space") -1
        total_size_of_plots = re.findall(r"Total size of plots: (\d*.\d*)\s([MGTPE])iB", cli)
        size_of_plots = re.findall(r"(.*Harvester.*)\n.*\d+ plots of size: (\d*.\d*)\s([MGTPE])iB", cli)

        share_size = 0
        for string in size_of_plots:
            if string[0] in shared_names: share_size += float(string[1])*convert[string[2]]
        bds_money = (share_size/(float(total_size_of_plots[0][0])*convert[total_size_of_plots[0][1]]))*adding_value/3 + (1-(share_size/(float(total_size_of_plots[0][0])*convert[total_size_of_plots[0][1]])))*adding_value
        bds_money = round(bds_money, 6)
        cli1 = "no transaction"
        cli2 = "no transaction"
        other_money = round((adding_value - bds_money - 0.000001), 6)
        if "XCH_ADDR_BDS89" in CONFIG_DICT and bds_money > 0.01:
            cli1 = os.popen('chia   wallet send -a '+str(bds_money)+' -t '+str(CONFIG_DICT["XCH_ADDR_BDS89"])).read()
        if "XCH_ADDR_OTHER" in CONFIG_DICT and other_money > 0.01:
            time.sleep(2)
            cli2 = os.popen('chia   wallet send -a '+str(other_money)+' -t '+str(CONFIG_DICT["XCH_ADDR_OTHER"])).read()
        # write to file, if havn't adresses
        if "WRITE_BALANCES" in CONFIG_DICT and CONFIG_DICT["WRITE_BALANCES"] == True:
            if not "XCH_ADDR_BDS89" in CONFIG_DICT and not "XCH_ADDR_OTHER" in CONFIG_DICT:
                if os.path.exists(MONEY_PATCH):
                    with open(MONEY_PATCH) as f:
                        money = yaml.load(f.read(), Loader=yaml.FullLoader)
                else:
                    money = {"bds89":0, "other":0}
                money["bds89"] += bds_money
                money["other"] += other_money
                with open(MONEY_PATCH, "w") as f:
                    f.write(yaml.dump(money, sort_keys=False))
        message_to_all("{0} {1}\n{2}\n{3} {4}\n{5}\nINFO:\n{6}".format("bds89: ", bds_money, cli1, "other: ", other_money, cli2, cli[start:end]), None)
    except: print("Error in change balance")


def watchdog():
    print("Watchdog started")
    while True:
        if CONFIG_DICT["WD_INTERVAL"] == 0: time.sleep(5)
        else:
            sys_params = sys_crit_params()
            if sys_params:
                message_to_all("Watchdog alert❗\n"+sys_params, None)
            #наблюдаем за прогрессом плотинга, если что-то стоит сообщаем
            if not "check_plotting_progress" in globals():
                globals()["check_plotting_progress"] = {}
            if "time" in globals()["check_plotting_progress"] and datetime.datetime.now() - globals()["check_plotting_progress"]["time"] < datetime.timedelta(minutes=30): pass
            else:
                text = ""
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

                dict_of_plots = {}

                sorted_file_list = list(sorted_file_dict)
                for filename in sorted_file_list[:CONFIG_DICT["NUM_PARALLEL_PLOTS"]*2]:
                    with open(CONFIG_DICT["PLOTLOGPATCH"]+"/"+filename, 'r') as f:
                        log = f.read()
                    if re.search(r"Total time = (\w+.\w+)", log):
                        num_string += log.count("\n")
                        num_finish_files += 1
                        tmp = re.findall(r"Starting plotting progress into temporary dirs: /\w+/(.+) and /\w+/(.+)", log)[0]
                        ID = re.findall(r"ID: ([\w\d]+)", log)[0]
                        if ID in globals()["check_plotting_progress"]:
                            globals()["check_plotting_progress"].pop(ID)
                    else:
                        try:
                            ID = re.findall(r"ID: ([\w\d]+)", log)[0]
                            dict_of_plots[ID] = {}
                            dict_of_plots[ID]["tmp"] = re.findall(r"Starting plotting progress into temporary dirs: /\w+/(.+) and /\w+/(.+)", log)[0]
                            dict_of_plots[ID]["progr"] = log.count("\n")
                        except(IndexError):
                            print("except IndexError check_plotting_progress(filename:"+filename+")")
                try:
                    num_string_100 = num_string / num_finish_files
                except(ZeroDivisionError):
                    num_string_100 = 2627
                
                for ID, info in dict_of_plots.items():
                    p = round(info["progr"]/num_string_100, 2)
                    if ID in globals()["check_plotting_progress"]:
                        if p == globals()["check_plotting_progress"][ID]["progr"] and (not "time31" in globals()["check_plotting_progress"][ID] or (p != 0.31 and p != 0.32) or datetime.datetime.now() - globals()["check_plotting_progress"][ID]["time31"] > datetime.timedelta(seconds=phase2)):
                            text += "{0}: {1}\n{2} {3}\n".format(LANG["plot_not_response"], info["tmp"], num_to_scale((p*100), 20), str(p*100))
                            globals()["check_plotting_progress"][ID]["progr"] = p
                            globals()["check_plotting_progress"][ID]["tmp"] = info["tmp"]
                            if p == 0.31 or p == 0.32: globals()["check_plotting_progress"][ID]["time31"] = datetime.datetime.now()
                        else:
                            globals()["check_plotting_progress"][ID]["progr"] = p
                            globals()["check_plotting_progress"][ID]["tmp"] = info["tmp"]
                            if p == 0.31 or p == 0.32: globals()["check_plotting_progress"][ID]["time31"] = datetime.datetime.now()
                    else:
                        globals()["check_plotting_progress"][ID] = {}
                        globals()["check_plotting_progress"][ID]["progr"] = p
                        globals()["check_plotting_progress"][ID]["tmp"] = info["tmp"]
                        if p == 0.31 or p == 0.32: globals()["check_plotting_progress"][ID]["time31"] = datetime.datetime.now()
                if text:
                    message_to_all(text, True)
                globals()["check_plotting_progress"]["time"] = datetime.datetime.now()
            if CONFIG_DICT["FULL_NODE"]:
                cli = os.popen('chia   wallet show').read()             
                cli = cli + os.popen('chia   farm summary').read()
                #check balance
                new_balance = re.findall(r"-Total Balance:\s+(\d+[.]\d+) xch", cli)
                if new_balance:
                    new_balance = float(new_balance[0])
                    if "old_balance" in locals():
                        if new_balance > old_balance:
                            print("New Balance: "+str(new_balance))
                            adding_value = new_balance - old_balance
                            old_balance = new_balance
                            print("Balance changed: +"+str(adding_value))

                            adding_coin(adding_value=adding_value, cli=cli)
     
                    else: old_balance = new_balance

                stat = {}
                try:
                    stat["Sync status: "] = re.findall(r"Sync status: (.+)", cli)[0]
                    stat["Farming status: "] = re.findall(r"Farming status: (.+)", cli)[0]
                    stat["Plot count for all harvesters: "] = int(re.findall(r"Plot count for all harvesters: (\d+)", cli)[0])
                    if not plot_count_all_harvesters or plot_count_all_harvesters <= stat["Plot count for all harvesters: "]:
                        globals()["plot_count_all_harvesters"] = stat["Plot count for all harvesters: "]
                    #Посчитаем сколько осталось до выигрыша
                    convert = {"M":1*10**12, "G":1*10**9, "T":1*10**6, "P":1*10**3, "E":1}
                    total_size_of_plots = re.findall(r"Total size of plots: (\d*.\d*)\s([MGTPE])iB", cli)
                    net_space = re.findall(r"Estimated network space: (\d*.\d*)\s([MGTPE])iB", cli)
                    sec_to_win = round((1/((float(total_size_of_plots[0][0])/convert[total_size_of_plots[0][1]])/(float(net_space[0][0])/convert[net_space[0][1]]) * 4608))*3600*24)
                    partial_to_win = CONFIG_DICT["WD_INTERVAL"] / sec_to_win
                    if "WIN_PROGRESS" in globals(): globals()["WIN_PROGRESS"] += partial_to_win
                    else: globals()["WIN_PROGRESS"] = partial_to_win

                    if "WIN_reGRESS" in globals(): globals()["WIN_reGRESS"] = globals()["WIN_reGRESS"]*(1-partial_to_win)
                    else: globals()["WIN_reGRESS"] = (1-partial_to_win)
                except(IndexError):
                    stat["Sync status: "] = "None"
                    stat["Farming status: "] = "None"
                    stat["Plot count for all harvesters: "] = 0
                if stat["Sync status: "] != "Synced" or stat["Farming status: "] != "Farming" or stat["Plot count for all harvesters: "] < (plot_count_all_harvesters - 2):
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
                    log = "{0}    Sync status:{1}    Farming status:{2}    Plot count:{3} ({4} {5})\n".format(str(timestamp_now), stat["Sync status: "], stat["Farming status: "], 
                                                                                                            stat["Plot count for all harvesters: "], LANG["was"], plot_count_all_harvesters)
                    f.write(log)
                    f.close()
                    globals()["plot_count_all_harvesters"] = stat["Plot count for all harvesters: "]
            time.sleep(CONFIG_DICT["WD_INTERVAL"])
        
def set_watchdog_interval(arg=None):
    if arg and str(arg).isdigit():
        arg = int(round(float(arg)))
        if arg < 60 and arg != 0:
            text = LANG["too_often"]
            retur = {"text":text}
            return(retur) 

        globals()["CONFIG_DICT"]["WD_INTERVAL"] = arg
        with open(CONFIG_PATCH, "w") as f:
            f.write(yaml.dump(CONFIG_DICT, sort_keys=False))
        if arg != 0: text = LANG["set_refresh_interval"]+str(arg)
        else: text = LANG["wd_off"]
        retur = {"text":text}
        return(retur)

    else:
        text = LANG["current"]+str(CONFIG_DICT["WD_INTERVAL"])+'\n'+LANG["type"]+'/wd <seconds>'
        retur = {"text":text}
        return(retur)

def set_parallel_plots(arg=None):
    if arg and str(arg).isdigit():
        arg = int(round(float(arg)))
        if arg < 1 or arg > 30:
            text = LANG["paral_diap"]
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

        text = LANG["num_paral_plots"]+str(globals()["CONFIG_DICT"]["NUM_PARALLEL_PLOTS"])
        retur = {"text":text}
        return(retur)

    else:
        text = LANG["current"]+str(CONFIG_DICT["NUM_PARALLEL_PLOTS"])+'\n'+LANG["type"]+'/parallel_plots <int>'
        retur = {"text":text}
        return(retur)

def set_table(arg=None) -> None:
    if arg and str(arg).isdigit():
        arg = int(round(float(arg)))
        if arg < 1 or arg > 7:
            text = LANG["table_diap"]
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

        text = LANG["start_at_table"]+str(globals()["CONFIG_DICT"]["COMPUTING_TABLE"])
        retur = {"text":text}
        return(retur)

    else:
        text = LANG["current"]+str(CONFIG_DICT["COMPUTING_TABLE"])+'\n'+LANG["type"]+'/table <int>'
        retur = {"text":text}
        return(retur)

def set_plot_config(arg=None):
    keyboard = [[]]
    if CONFIG_DICT["SATA_AS_SSD"] == "no":
        keyboard[0].append(InlineKeyboardButton(LANG["use_SATA"], callback_data='plot_config(sata_as_ssd="yes")'))
    else: 
        keyboard[0].append(InlineKeyboardButton(LANG["not_use_SATA"], callback_data='plot_config(sata_as_ssd="no")'))

    if CONFIG_DICT["USE_K33"] == "no":
        keyboard[0].append(InlineKeyboardButton(LANG["use_K33"], callback_data='plot_config(use_k33="yes")'))
    else: 
        keyboard[0].append(InlineKeyboardButton(LANG["not_use_K33"], callback_data='plot_config(use_k33="no")'))
    
    text = "{0}\n{1} {2} (/parallel_plots)\n{3} {4} (/table)\n{5} {6}\n{7} {8}\n".format(
            LANG["plotting_config"], LANG["paral_plots"], CONFIG_DICT["NUM_PARALLEL_PLOTS"], 
            LANG["start_table"], CONFIG_DICT["COMPUTING_TABLE"], 
            LANG["using_sata_as_ssd"], CONFIG_DICT["SATA_AS_SSD"], LANG["using_k33"], CONFIG_DICT["USE_K33"])
                                                                
    retur = {"text":text, "keyboard":keyboard}
    return(retur)

def set_notify(arg=None, chat_id=None):
    if arg:
        if arg != "on" and arg != "off":
            text = LANG["type"]+'/notify <on/off>'
            retur = {"text":text}
            return(retur)
        if CONFIG_DICT["CHAT_IDS"][chat_id]:
            globals()["CONFIG_DICT"]["CHAT_IDS"][chat_id] = arg
            globals()["Q_for_message"].put(CONFIG_DICT)
            with open(CONFIG_PATCH, "w") as f:
                f.write(yaml.dump(CONFIG_DICT, sort_keys=False))
            text = "{0} {1} {2} {3}".format(LANG["notify_stat_for"], chat_id, LANG["now"], globals()["CONFIG_DICT"]["CHAT_IDS"][chat_id])
            retur = {"text":text}
            return(retur)
        else:
            text = LANG["unknown_user"]
            retur = {"text":text}
            return(retur)
    else:
        text = LANG["current"]+str(CONFIG_DICT["CHAT_IDS"][chat_id])+'\n'+LANG["type"]+'/notify <on/off>'
        retur = {"text":text}
        return(retur)

def set_filter(arg=None, chat_id=None):
    if (arg or arg == 0) and str(arg).isdigit():
        arg = int(round(float(arg)))
        if arg < 0:
            text = LANG["num_must_be_posit"]
            retur = {"text":text}
            return(retur)
        globals()["FILTER_CHAT_IDS"][chat_id] = arg 
        text = "{0} {1} {2} {3}".format(LANG["filter_stat"], chat_id, LANG["now"], FILTER_CHAT_IDS[chat_id])
        retur = {"text":text}
        return(retur)
    else:
        text = LANG["current"]+str(FILTER_CHAT_IDS[chat_id])+'\n'+LANG["type"]+'/filter <int>'
        retur = {"text":text}
        return(retur)

def check_plots_dirs(arg=None):
    if arg and int(arg)==1:
    #сначала удалим директории в которых не найдем плотов
        process = subprocess.run(['chia   plots show'], check=True, shell=True, stdout=subprocess.PIPE, universal_newlines=True)
        output = process.stdout
        plot_dirs = re.findall(r"\n(/.*)", output)
        plot_dirs_dict = {}
        for dir in plot_dirs:
            plot_dirs_dict[dir] = False
            plots_on = plots_on_disk(dir)
            for key in plots_on.keys():
                if key.isdigit():     
                    plot_dirs_dict[dir] = True
                    break
        text = ""
        for dir, have_plot in plot_dirs_dict.items():
            if not have_plot:
                process = subprocess.run(['chia   plots remove -d "'+dir+'"'], check=True, shell=True, stdout=subprocess.PIPE, universal_newlines=True)
                text += "removed: "+dir+"\n"
                plot_dirs.remove(dir)
    #добавим директории в которых найдем плоты
        text += "\n"
        disk_dict = disk_list(CONFIG_DICT["MIN_DISK_TOTAL"]*1000000000, 1)
        added_dirs_list = []
        for patch in disk_dict.keys():
            plots_on = plots_on_disk(patch)
            for key in plots_on.keys():
                match = re.findall(r"^(/.+)/plot-k\d{2}.+plot$", key)
                if match and not match[0] in plot_dirs and not match[0] in added_dirs_list:
                    process = subprocess.run(['chia   plots add -d "'+match[0]+'"'], check=True, shell=True, stdout=subprocess.PIPE, universal_newlines=True)
                    text += "added: "+match[0]+"\n"
                    added_dirs_list.append(match[0])
        if text == "\n":
            text += LANG["dirs_not_change"]
        retur = {"text":text}
        return(retur)
    else:
        text = LANG["for_dell_dirs_type"]
        retur = {"text":text}
        return(retur)

def show_log(arg=None):
    if arg:
        try:
            arg = float(arg)
        except(ValueError):
            text = LANG["type"]+'/log <float> (hours)'
            retur = {"text":text}
            return(retur)
        if arg < 0:
            text = LANG["num_must_be_posit"]
            retur = {"text":text}
            return(retur)
        log = []
        if os.path.exists(CONFIG_DICT["WATCHDOG_LOG"]):
            with open(CONFIG_DICT["WATCHDOG_LOG"]) as f:
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
        text = LANG["type"]+'/log <float> (hours)'
        retur = {"text":text}
        return(retur)

def power_limit(arg=None):
    if NVIDIA:
        if arg:
            try:
                arg = int(arg)
            except(ValueError):
                text = LANG["type"]+'/pl <int> (power limit)'
                retur = {"text":text}
                return(retur)
            if arg < 0:
                text = LANG["num_must_be_posit"]
                retur = {"text":text}
                return(retur)
            p = subprocess.Popen(['sudo', '-S', 'nvidia-smi', '-pl', str(arg)], stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            text = p.communicate(CONFIG_DICT["SUDO_PASS"] + '\n')[0]
            if "All done" in text:
                with open(CONFIG_PATCH) as f:
                    globals()["CONFIG_DICT"] = yaml.load(f.read(), Loader=yaml.FullLoader)
                globals()["CONFIG_DICT"]["POWER_LIMIT"] = arg
                with open(CONFIG_PATCH, "w") as f:
                    f.write(yaml.dump(CONFIG_DICT, sort_keys=False))
            retur = {"text":text}
            return(retur)
        
        else:
            text = LANG["current"]+str(NVIDIA)+'\n'+LANG["type"]+'/pl <int> (power limit)'
            retur = {"text":text}
            return(retur)
    text = "Please install Nvidia Drivers"
    retur = {"text":text}
    return(retur)

def balance_change(arg=None, farm=None):
    if int(farm) != 1:
        text = "Available only for full node"
        retur = {"text":text}
        return(retur)

    if arg:
        try:
            arg = float(arg)
        except(ValueError):
            text = LANG["type"]+'/balance_change <float> (chia coins)'
            retur = {"text":text}
            return(retur)

        cli = os.popen('chia   farm summary').read()
        adding_coin(adding_value=arg, cli=cli)
        text = ""
        retur = {"text":text}
        return(retur)
    
    else:
        text = LANG["type"]+'/balance_change <float> (chia coins)'
        retur = {"text":text}
        return(retur)

def harvester_restart(arg=None):
    if arg and int(arg)==1:
        command = 'chia  start harvester -r'.split()
        p = subprocess.Popen(command, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        text = p.communicate(CONFIG_DICT["SUDO_PASS"] + '\n')[0]
        retur = {"text":text}
        return(retur)
    else:
        text = LANG["for_restart_harvester"]
        retur = {"text":text}
        return(retur)

def change_pool(arg=None):
    if arg:
        try:
            arg = int(arg)
            if arg == 0:
                p = subprocess.Popen(['chia   plotnft leave -i 2'], shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                text = p.communicate("y" + '\n')[0]
                retur = {"text":text}
                return(retur)
        except(ValueError):
            if arg == "https://pool-ru.sweetchia.com" or arg == "https://eu1.pool.space":
                p = subprocess.Popen(['chia   plotnft join -i 2 -u '+arg], shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                text = p.communicate("y" + '\n')[0]
                retur = {"text":text}
                return(retur)
            else:
                text = LANG["type"]+'/pool <string> (pool adress or 0)'
                retur = {"text":text}
                return(retur)
    else:
        text = LANG["type"]+'/pool <string> (pool adress or 0)'
        retur = {"text":text}
        return(retur)

def set_win_progress(arg=None):
    if arg:
        try:
            arg = float(arg)
        except(ValueError):
            text = LANG["type"]+'/set_win_progress <float>'
            retur = {"text":text}
            return(retur)
        if arg < 0:
            text = LANG["num_must_be_posit"]
            retur = {"text":text}
            return(retur)
        globals()["WIN_PROGRESS"] = arg/100

        cli = os.popen('chia   farm summary').read()
        try:
            #Посчитаем сколько осталось до выигрыша
            convert = {"M":1*10**12, "G":1*10**9, "T":1*10**6, "P":1*10**3, "E":1}
            total_size_of_plots = re.findall(r"Total size of plots: (\d*.\d*)\s([MGTPE])iB", cli)
            net_space = re.findall(r"Estimated network space: (\d*.\d*)\s([MGTPE])iB", cli)
            sec_to_win = round((1/((float(total_size_of_plots[0][0])/convert[total_size_of_plots[0][1]])/(float(net_space[0][0])/convert[net_space[0][1]]) * 4608))*3600*24)
            partial_to_win = CONFIG_DICT["WD_INTERVAL"] / sec_to_win

            globals()["WIN_reGRESS"] = (1-partial_to_win)**(globals()["WIN_PROGRESS"] / partial_to_win)
            text = "{0} {1}%\n{2} {3}%\n".format(num_to_scale(arg, 19), round(arg, 2), num_to_scale((1-globals()["WIN_reGRESS"])*100, 19), round((1-globals()["WIN_reGRESS"])*100, 2))
        except: text = "error"
        retur = {"text":text}
        return(retur)
    else:
        text = LANG["for_set_win_progress"]
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

def mqtt_publish(text, node=1):
    if CONFIG_DICT["FULL_NODE"]:
        if "MQTT" in CONFIG_DICT:
            host = CONFIG_DICT["MQTT"]["HOSTNAME"]
            username = CONFIG_DICT["MQTT"]["USERNAME"]
            password = CONFIG_DICT["MQTT"]["PASS"]
            i = 0
            msgs = []
            one_dict = {}
            for key_or_value in text.split(";"):
                if i%2 == 0: 
                    one_dict["topic"] = "ferma/node"+str(node)+"/"+key_or_value
                    i+=1
                else: 
                    one_dict["payload"] = key_or_value
                    i+=1
                    msgs.append(one_dict)
                    one_dict = {}

            publish.multiple(msgs, hostname=host, auth = {'username':username, 'password':password})
    else:
        q = text
        data = {"data": 'mqtt_publish(text=q, node=node)', "q": q}
        socket_client(CONFIG_DICT["NODE_LIST"][1], CONFIG_DICT["FULL_NODE_PORT"], data)

def restart():
    mySocket.close()
    subprocess.call("python3 "+SCRIPT_DIR+"/restart_bot.py", shell=True)
    text = "restarting bot...wait please"
    retur = {"text":text}
    return(retur)

def set_farm(update: Update, context: CallbackContext) -> None:
    if not int(update.message.text) in CONFIG_DICT["NODE_LIST"]:
        reply_message(update, LANG["wrong_num"], reply_markup=REPLY_MARKUP[update['message']['chat']['id']])
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
            arg2 = arg
            command_dict_without_arg = {'/notify':'set_notify(chat_id='+chat_id+')',
                                        '/filter':'set_filter(chat_id='+chat_id+')',
                                        '/auto_power':'auto_power_start(chat_id='+chat_id+')'}
        else: 
            arg = context.args[0]
            if len(context.args) > 1: arg2 = context.args[1]
            else: arg2 = arg
            command_dict_without_arg = {}
        command_dict= {'/help':'help_command("'+arg+'")',
                        '/wd':'set_watchdog_interval("'+arg+'")',
                        '/parallel_plots':'set_parallel_plots("'+arg+'")',
                        '/table':'set_table("'+arg+'")',
                        '/notify':'set_notify(arg="'+arg+'", chat_id='+chat_id+')',
                        '/filter':'set_filter(arg="'+arg+'", chat_id='+chat_id+')',
                        '/log':'show_log("'+arg+'")',
                        '/set_plot_config':'set_plot_config("'+arg+'")',
                        '/set_win_progress':'set_win_progress("'+arg+'")',
                        '/check_plots_dirs':'check_plots_dirs("'+arg+'")',
                        '/pl':'power_limit("'+arg+'")',
                        '/pool':'change_pool("'+arg+'")',
                        '/balance_change':'balance_change(arg="'+arg+'", farm='+str(context.user_data["farm"])+')',
                        '/harvester_restart':'harvester_restart("'+arg+'")',
                        '/auto_power':'auto_power_start(min="'+arg+'", max="'+arg2+'", chat_id='+chat_id+')',
                        '/restart':'restart()'}
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
                text += LANG["no_data"]
            reply_message(update, text, reply_markup)
    else: start(update, context)
        
def main() -> None:
    """Start the bot."""
    updater = Updater(CONFIG_DICT["TELEGRAM_BOT_TOKEN"])

    conv_handler_start = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                PASSWORD: [MessageHandler(Filters.text , password)]},
            fallbacks=[CommandHandler('cancel', cancel)],
            conversation_timeout=(30)
        )
    conv_handler_language = ConversationHandler(
            entry_points=[CommandHandler('language', choose_language_1)],
            states={
                LANGUAGE: [MessageHandler(Filters.text , choose_language_2)]},
            fallbacks=[CommandHandler('cancel', cancel)],
            conversation_timeout=(15)
        )
    updater.dispatcher.add_handler(conv_handler_start)
    updater.dispatcher.add_handler(conv_handler_language)
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
    updater.dispatcher.add_handler(CommandHandler("set_win_progress", my_command_handler, USERS_FILTER))
    updater.dispatcher.add_handler(CommandHandler("check_plots_dirs", my_command_handler, USERS_FILTER))
    updater.dispatcher.add_handler(CommandHandler("pl", my_command_handler, USERS_FILTER))
    updater.dispatcher.add_handler(CommandHandler("pool", my_command_handler, USERS_FILTER))
    updater.dispatcher.add_handler(CommandHandler("harvester_restart", my_command_handler, USERS_FILTER))
    updater.dispatcher.add_handler(CommandHandler("auto_power", my_command_handler, USERS_FILTER))
    updater.dispatcher.add_handler(CommandHandler("restart", my_command_handler, USERS_FILTER))
    updater.dispatcher.add_handler(CommandHandler("balance_change", my_command_handler, USERS_FILTER))


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
                        if log_time_timestam >= log_time_old:
                            plots_check_time(line)
                            log_time_old = log_time_timestam
                    else: plots_check_time(line)
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
                message(key, "{0} {1}/{2}. {3} {4}. {5} {6}\n{7}".format(LANG["filter"],
                                            matches[0][2], matches[0][5], LANG["proofs"], 
                                            matches[0][3], LANG["ping"], 
                                            round(float(matches[0][4]), 2), datetime.datetime.fromtimestamp(time.mktime(datetime.datetime.now().timetuple()))), True)
                
        if not globals()["plot_count"] and matches[0][5]:
            globals()["plot_count"] = int(matches[0][5])
        if globals()["plot_count"] and (int(matches[0][5]) + 1) < int(globals()["plot_count"]):
            message_to_all("{0} {1} {2} {3}, {4}".format(LANG["decrease_plot_num"], globals()["plot_count"], LANG["on"], matches[0][5], LANG["check_discs"]), None)
        globals()["plot_count"] = matches[0][5]

        if int(matches[0][3]) > 5:
            message_to_all("{0} {1}".format(LANG["proof_find"], matches[0][1]), None)

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
            log = "{0}    {1}{2} {3} {4}/{5}\n".format(str(timestamp_now), LANG["long_ping"], matches[0][4], LANG["filter_pass"], matches[0][2], matches[0][5])
            f.write(log)
            f.close()

    # if "send_coin_at" in globals() and datetime.datetime.now() - globals()["send_coin_at"] < datetime.timedelta(seconds=300): pass   
    # else:
    #     matches = re.findall(r"Adding coin: {'amount': (\d+)", log)
    #     if matches:
    #         message_to_all("{0} {1}".format(LANG["wallet_in"], float(matches[0])/1000000000000), None)

    #         if round(float(matches[0])/1000000000000, 2) == 0.25 or round(float(matches[0])/1000000000000) == 2: globals()["WIN_PROGRESS"] = 0

    #         cli = os.popen('chia   farm summary').read()
    #         convert = {"M":1, "G":1*10**3, "T":1*10**6, "P":1*10**9, "E":1*10**12}

    #         shared_names = ["Local Harvester", "Remote Harvester for IP: 212.75.234.213"]
    #         try:
    #             start = cli.index("Local Harvester")
    #             end = cli.index("Estimated network space") -1
    #             total_size_of_plots = re.findall(r"Total size of plots: (\d*.\d*)\s([MGTPE])iB", cli)
    #             size_of_plots = re.findall(r"(.*Harvester.*)\n.*\d+ plots of size: (\d*.\d*)\s([MGTPE])iB", cli)

    #             share_size = 0
    #             for string in size_of_plots:
    #                 if string[0] in shared_names: share_size += float(string[1])*convert[string[2]]
    #             bds_money = (share_size/(float(total_size_of_plots[0][0])*convert[total_size_of_plots[0][1]]))*(float(matches[0])/1000000000000)/3 + (1-(share_size/(float(total_size_of_plots[0][0])*convert[total_size_of_plots[0][1]])))*(float(matches[0])/1000000000000)
    #             bds_money = round(bds_money, 6)
    #             cli1 = "no transaction"
    #             cli2 = "no transaction"
    #             other_money = round(((float(matches[0])/1000000000000) - bds_money - 0.000001), 6)
    #             if "XCH_ADDR_BDS89" in CONFIG_DICT and bds_money > 0.01:
    #                 cli1 = os.popen('chia   wallet send -a '+str(bds_money)+' -t '+str(CONFIG_DICT["XCH_ADDR_BDS89"])).read()
    #             if "XCH_ADDR_OTHER" in CONFIG_DICT and other_money > 0.01:
    #                 time.sleep(2)
    #                 cli2 = os.popen('chia   wallet send -a '+str(other_money)+' -t '+str(CONFIG_DICT["XCH_ADDR_OTHER"])).read()
    #             # write to file, if havn't adresses
    #             if "WRITE_BALANCES" in CONFIG_DICT and CONFIG_DICT["WRITE_BALANCES"] == True:
    #                 if not "XCH_ADDR_BDS89" in CONFIG_DICT and not "XCH_ADDR_OTHER" in CONFIG_DICT:
    #                     if os.path.exists(MONEY_PATCH):
    #                         with open(MONEY_PATCH) as f:
    #                             money = yaml.load(f.read(), Loader=yaml.FullLoader)
    #                     else:
    #                         money = {"bds89":0, "other":0}
    #                     money["bds89"] += bds_money
    #                     money["other"] += other_money
    #                     with open(MONEY_PATCH, "w") as f:
    #                         f.write(yaml.dump(money, sort_keys=False))




    #             message_to_all("{0} {1}\n{2}\n{3} {4}\n{5}\nINFO:\n{6}".format("bds89: ", bds_money, cli1, "other: ", other_money, cli2, cli[start:end]), None)
    #             globals()["send_coin_at"] = datetime.datetime.now()
    #         except:
    #             print("something wrong in send coin")
    #             pass
    matches = re.findall(
                r"Looking up qualities on (.+) took: (\d.\d+)", log
            )
    if matches:
        f = open(CONFIG_DICT["WATCHDOG_LOG"], 'a')

        dt = datetime.datetime.now()
        timestamp_now = datetime.datetime.fromtimestamp(time.mktime(dt.timetuple()))
        log = "{0}    {1}{2}. ({3} {4})\n".format(str(timestamp_now), LANG["long_ping"], matches[0][0], round(float(matches[0][1]), 2), LANG["sec"])
        f.write(log)
        f.close()

        message_to_all("{0} {1}. ({2} {3})".format(LANG["long_ping"], matches[0][0], round(float(matches[0][1]), 2), LANG["sec"]), True)

    matches = re.findall(
                r" ([WE][AR][R][NO][IR][N ][G ]) +(.+)$", log
            )
    if matches:
        f = open(CONFIG_DICT["WATCHDOG_LOG"], 'a')

        dt = datetime.datetime.now()
        timestamp_now = datetime.datetime.fromtimestamp(time.mktime(dt.timetuple()))
        log = "{0}    {1}    {2}\n".format(str(timestamp_now), matches[0][0], matches[0][1])
        f.write(log)
        f.close()

def del_trash():
    try:
        with open(CONFIG_DICT["PLOTS_FILE"], "rb") as f:
            all_plots = pickle.load(f)
        if not all_plots:
            print(LANG["no_plotted"])
            return
    except(FileNotFoundError):
        print(LANG["not_find_plot_file"])
        return

    for plot in all_plots:
        if plot.__class__.__name__ == "Plot":
            tmp = 0
            tmp2 = 0
            dst = 0
            print("{0} {1}:".format(LANG["clear_plot"], plot.name))
            #Удаляем темп файлы
            temp = plot.temp+"/temp"
            try:
                file_list = os.listdir(temp)
                for filename in file_list:
                    os.remove(temp+"/"+filename)
                    tmp += 1
                print("{0} {1} {2} {3}".format(LANG["deleted"], str(tmp), LANG["files_in"], temp))
            except(FileNotFoundError):
                print("{0} {0}".format(LANG["cant_dell_files_from"], temp))
            #Удаляем темп2 файлы
            if plot.temp2:
                temp2 = plot.temp2+"/plots"
                try:
                    file_list = os.listdir(temp2)
                    for filename in file_list:
                        if plot.name and filename.count(plot.name) and filename.count("2.tmp"):
                            os.remove(temp2+"/"+filename)
                            tmp2 += 1
                    print("{0} {1} {2} {3}".format(LANG["deleted"], str(tmp2), LANG["files_in"], temp2))
                except(FileNotFoundError):
                    print("{0} {1}".format(LANG["cant_dell_files_from"], temp2))
            #Удаляем dest файлы
            dest = plot.dest+"/plots"
            try:
                file_list = os.listdir(dest)
                for filename in file_list:
                    if plot.name and filename.count(plot.name) and filename.count("2.tmp"):
                        os.remove(dest+"/"+filename)
                        dst += 1
                print("{0} {1} {2} {3}".format(LANG["deleted"], str(dst), LANG["files_in"], dest))
            except(FileNotFoundError):
                print("{0} {1}".format(LANG["cant_dell_files_from"], dest))
            #Удаляем log файлы
            file_list = os.listdir(CONFIG_DICT["PLOTLOGPATCH"])
            for filename in file_list:
                if plot.name and filename.count(plot.name):
                    os.remove(CONFIG_DICT["PLOTLOGPATCH"]+"/"+filename)
            print("{0} {0}\n".format(LANG["dell_log_in"], CONFIG_DICT["PLOTLOGPATCH"]))
    #Удаляем plots_file.sys файл
    os.remove(CONFIG_DICT["PLOTS_FILE"])

def mqtt_on_message(client, userdata, message):
    try:
        globals()["MQTT_dict"][CONFIG_DICT["MQTT"]["TOPICS"][message.topic]] = json.loads(message.payload)
    except: pass 
def mqtt(topics, host, username, password):
    topics_list = list(topics)
    subscribe.callback(mqtt_on_message, topics_list, hostname=host, auth = {'username':username, 'password':password})

def set_APM():
    sudo_password = CONFIG_DICT["SUDO_PASS"]
    devices = disk_list(CONFIG_DICT["MIN_DISK_TOTAL"]*1000000000)
    prev_disks = []
    for dev_num in devices.keys():
        dev = re.findall(r"\D+", dev_num)[0]
        if not dev in prev_disks:
            prev_disks.append(dev)
            command = ("sudo -S hdparm -B 254 -S 0 "+dev).split()
            p = subprocess.Popen(command, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            cli = p.communicate(sudo_password + '\n')[0]
            if "not supported" in cli:
                HAVNT_SMART.append(dev)
                print("{}: not supported".format(dev))
            else: print("{}: 254".format(dev))

if __name__ == '__main__':
    param = sys.argv
    CONFIG_PATCH = get_script_dir()+"/config.yaml"
    MONEY_PATCH = get_script_dir()+"/money.yaml"
    with open(CONFIG_PATCH) as f:
        CONFIG_DICT = yaml.load(f.read(), Loader=yaml.FullLoader)

    SCRIPT_DIR = get_script_dir()
    #Найдем максимально время фазы 2, для вочдога.
    phase2 = phase2time()
    print("Phase 2 time: "+str(phase2))

    Q = Queue()
    Q_for_message = Queue()
    Q_for_create_plot_button = Queue()
    Q_for_move_plot_button = Queue()
    Q_for_dell_plot_button = Queue()

    plot_count = None

    K = 1024**3
    PLOTS_SIZES = {25:0.6, 32:101.375, 33:208.86, 34:429.8, 35:884.1}
    PLOTS_SIZES_PLOTTING = {25:1.8, 32:239, 33:521, 34:1041, 35:2175}

    FILTER_CHAT_IDS = {}
    REPLY_MARKUP = {}
    KEYBOARD = {}
    MESSAGES = {} #Запоминаем сообщения от пользователей, для последующего удаления из них кнопок, так же создаем переменные о фильтрах и клавиатурах для пользователей
    
    LANG = english
    START_TEXT = LANG["start_text"]
    language_to_harvesters(CONFIG_DICT["LANGUAGE"], True)

    plot_count_all_harvesters = 0

    HAVNT_SMART = []
    try:
        if param[1] != "-s":
            message_to_all(LANG["start_bot"], True)
        print(LANG["start_with_params"]+"\n")
    except(IndexError):
        print(LANG["start_without_params"]+"\n"+LANG["cancel_dell_plots"])
        #Задержка при запуске вместе с системой, что бы ты подумал
        t = 15
        while t > 0:       
            print(t)
            t -= 1
            time.sleep(1)
        if CONFIG_DICT["HARVESTER_MAC"]:
            send_magic_packet(*CONFIG_DICT["HARVESTER_MAC"])
        #Лог левел инфо
        if not os.path.exists(CONFIG_DICT["PLOTLOGPATCH"]):
            command = 'chia   configure -log-level "INFO"'.split()
            p = subprocess.Popen(command, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            cli = p.communicate(CONFIG_DICT["SUDO_PASS"] + '\n')[0]
            print(cli)
            harvester_restart(1)
            
        del_trash()
        message_to_all(LANG["start_bot"], True)
    set_APM()
    threading.Thread(target=cpu_use).start() #запускаем опрос загрузки cpu

    Process(target=plot_manager).start()
    que = {"AUTO_P":CONFIG_DICT["AUTO_P"], 
            "COMPUTING_TABLE": CONFIG_DICT["COMPUTING_TABLE"], 
            "NUM_PARALLEL_PLOTS": CONFIG_DICT["NUM_PARALLEL_PLOTS"],
            "SATA_AS_SSD": CONFIG_DICT["SATA_AS_SSD"],
            "USE_K33": CONFIG_DICT["USE_K33"]}
    Q.put(que)

    if "BINANCE_KEY" in CONFIG_DICT and "BINANCE_SECRET" in CONFIG_DICT:
        CONFIG_BINANCE = {
            "apiKey": CONFIG_DICT["BINANCE_KEY"],
            "secret": CONFIG_DICT["BINANCE_SECRET"],
            "rateLimit": 500,
            "enableRateLimit": True,
        }
    if "OKEX_KEY" in CONFIG_DICT and "OKEX_SECRET" in CONFIG_DICT and "OKEX_PASS" in CONFIG_DICT:
        CONFIG_OKEX = {
            "apiKey": CONFIG_DICT["OKEX_KEY"],
            "secret": CONFIG_DICT["OKEX_SECRET"],
            "password": CONFIG_DICT["OKEX_PASS"],
            "enableRateLimit": True,
        }

    #MQTT подписка
    if "MQTT" in CONFIG_DICT:
        threading.Thread(target=mqtt, args=(CONFIG_DICT["MQTT"]["TOPICS"],CONFIG_DICT["MQTT"]["HOSTNAME"],CONFIG_DICT["MQTT"]["USERNAME"],CONFIG_DICT["MQTT"]["PASS"],)).start()
        MQTT_dict = {}
    
    threading.Thread(target=LogParser, args=(CONFIG_DICT["LOGPATCH"],)).start()  #читаем логи
    # Process(target=app.run(host='0.0.0.0')).start()     -Flask
    threading.Thread(target=not_sleep).start()  #not_sleep
    threading.Thread(target=watchdog).start()  #WatchDog
    threading.Thread(target=smartdog).start()  #SmartDog
    # проверим есть ли драйвера nvidia
    if "POWER_LIMIT" in CONFIG_DICT: 
        pl = str(CONFIG_DICT["POWER_LIMIT"])
        p = subprocess.Popen(['sudo', '-S', 'nvidia-smi', '-pl', pl], stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        cli = p.communicate(CONFIG_DICT["SUDO_PASS"] + '\n')[0]
        if cli:
            NVIDIA = 151
        else: NVIDIA = None
    #Для фермы1
    if CONFIG_DICT["FULL_NODE"]:
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
    mySocket = False   #Переменная для закрытия сокета, при рестарте
