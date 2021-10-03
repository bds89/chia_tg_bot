from subprocess import Popen, PIPE
import re, yaml, sys, os, pickle, inspect, time, datetime, socket

def get_script_dir(follow_symlinks=True):
    if getattr(sys, 'frozen', False): # py2exe, PyInstaller, cx_Freeze
        path = os.path.abspath(sys.executable)
    else:
        path = inspect.getabsfile(get_script_dir)
    if follow_symlinks:
        path = os.path.realpath(path)
    return os.path.dirname(path)

def socket_client(host, port, request):

        mySocket = socket.socket()
        mySocket.settimeout(10)
        try:
            mySocket.connect((host,port))
            mySocket.settimeout(None)
        except(ConnectionRefusedError, OSError):
            text = "Can't connect to "+str(host)+"\n"
            retur = {"text":text}
            return retur
        mySocket.send(pickle.dumps(request))
        data = mySocket.recv(2048)
        while data:
            try: 
                data_unpickle = pickle.loads(data)
                break
            except: 
                dat = mySocket.recv(2048)
                if not dat:
                    break
                data += dat
        if not data:
            data = {"text": "Not received data\n"}
            mySocket.close()
            return data
        mySocket.close()
        return data_unpickle

#search all plots, search only old plots, dell plots   
def plots_on_disk(patch, list={"num_del":0}, old=False, dell=False, size=False, depth=0):
    if depth > CONFIG_DICT["DEPTH"]: return(list)
    depth += 1
    if len(list) == 1 and "num_del" in list:
        list={"num_del":0}
    if not os.path.exists(patch):
        return(list)
    for name in os.listdir(patch):
        obj = patch+"/"+name
        try:
            if os.path.isfile(obj):
                match = re.findall(r"plot-k(\d{2}).+plot$", name)
                if match:
                    if old and os.path.getmtime(obj) > time.mktime(datetime.date(2021,7,8).timetuple()):
                        continue
                    if dell and int(match[0]) == int(size):
                        if list["num_del"] >= int(dell):
                            if len(list) == 1 and "num_del" in list:
                                list={}
                            return(list)
                        os.remove(obj)
                        list["num_del"] += 1
                        list[obj] = "del"
                        continue
                    list[obj] = match[0]
                    if match[0] in list:
                        list[match[0]] += 1
                    else:
                        list[match[0]] = 1
            if os.path.isdir(obj):
                list.update(plots_on_disk(patch=obj, list=list, old=old, dell=dell, size=size, depth=depth))
        except(PermissionError):
            pass
    if len(list) == 1 and "num_del" in list:
        list={}
    return(list)

class Plots:
    def __init__(self, id, source, size, num, dest, num_est):
        self.id = id
        self.source = source
        self.size = size        
        self.dest = dest
        self.num = num
        self.num_est = num_est

class Plot:
    def __init__(self, name, temp, dest, cmd, size, threads, temp2=None):
        self.name = name
        self.temp = temp
        self.temp2 = temp2        
        self.dest = dest
        self.pid = os.getpid()
        self.cmd = cmd
        self.size = size
        self.threads = threads
      
def run(command):
    process = Popen(command, stdout=PIPE, shell=True, encoding="utf-8")
    while True:
        line = process.stdout.readline().rstrip()
        if not line and process.poll() != None:
            break
        yield line

#для работы импортированных функций из этого файла
CONFIG_PATCH = get_script_dir()+"/config.yaml"
with open(CONFIG_PATCH) as f:
    CONFIG_DICT = yaml.load(f.read(), Loader=yaml.FullLoader)  

if __name__ == '__main__':
    plot_finish = False
    param = sys.argv
    command =  "/usr/lib/chia-blockchain/resources/app.asar.unpacked/daemon/chia plots create"
    command += " -f "+CONFIG_DICT["F_KEY"]
    command += " -c "+CONFIG_DICT["POOL_KEY"]

    for p in param:
        if p[:3] == "-t ":
            temp_0 = p[3:]
            temp = temp_0+"/temp"
            continue
        if p[:3] == "-2 ":
            temp2_0 = p[3:]
            temp2 = temp2_0+"/plots"
            continue
        if p[:3] == "-d ":
            dest_0 = p[3:]
            dest = dest_0+"/plots"
            continue
        if p[:3] == "-z ":
            size = p[3:]
            continue
        if p[:3] == "-r ":
            threads = p[3:]
            continue
    command += " -k "+str(size)
    ram_sizes = {"25":512, "32":3390, "33":7400, "34":14800, "35":29600}
    command += " -b "+str(ram_sizes[str(size)])
    command += " -r "+threads
    try:
        os.mkdir(temp)
    except(OSError):
        pass
    command += " -t '"+temp+"'"

    if temp2_0:
        try:
            os.mkdir(temp2)
        except(OSError):
            pass
        command += " -2 '"+temp2+"'"
    try:
        os.mkdir(dest)
    except(OSError):
        pass
    command += " -d '"+dest+"'"

    filepatch = CONFIG_DICT["PLOTLOGPATCH"]
    filename = None
    before = ""
    print(command)
    for log in run(command):
        if not filename:
            if re.search(r"ID: (.+)", log):
                filename = re.findall(r"ID: (.+)", log)[0]
                p = Plot(filename, temp_0, dest_0, command, size, threads, temp2_0)
                try:
                    with open(CONFIG_DICT["PLOTS_FILE"], "rb") as f:
                        all_plots = pickle.load(f)
                except(FileNotFoundError):
                    all_plots = []
                all_plots.append(p)
                with open(CONFIG_DICT["PLOTS_FILE"], "wb") as f:
                    pickle.dump(all_plots, f)
            else:
                before += log+"\n"
                continue
        try:
            f = open(filepatch+"/"+filename+".log", 'a')
            if before:
                f.write(before+log+"\n")
                before = ""
            else:
                f.write(log+"\n")
        except(FileNotFoundError):
            f = open(filepatch+"/"+filename+".log", 'w')
            if before:
                f.write(before+log+"\n")
                before = ""
            else:
                f.write(log+"\n")
        f.close()
        if re.search(r"Total time = (\w+.\w+)", log):
            total_time = re.findall(r"Total time = (\w+.\w+)", log)[0]
            print("Plot created from {0} to {1} in {2} s.".format(temp, dest, str(total_time)))
            plot_finish = True
    #Удалим запись о плоте
    #Если закрылся неожиданно, удалим файлы
    if not plot_finish and filename:
        os.remove(filepatch+"/"+filename+".log")
        #Удаляем темп файлы
        try:
            file_list = os.listdir(temp)
            for file in file_list:
                if file.count(filename):
                    os.remove(temp+"/"+file)
        except(FileNotFoundError): pass
        #Удаляем темп2 файлы
        if temp2_0:
            try:
                file_list = os.listdir(temp2)
                for file in file_list:
                    if file.count(filename) and file.count("2.tmp"):
                        os.remove(temp2+"/"+file)
            except(FileNotFoundError): pass
        #Удаляем dest файлы
        try:
            file_list = os.listdir(dest)
            for file in file_list:
                if file.count(filename) and file.count("2.tmp"):
                    os.remove(dest+"/"+file)
        except(FileNotFoundError): pass

        print("Plot "+temp+"\n["+str(temp2)+"\n➜ "+dest+" (k"+size+") was terminated")
    #Удалим запись о плоте
    with open(CONFIG_DICT["PLOTS_FILE"], "rb") as f:
        all_plots = pickle.load(f)
    for plot in all_plots:
        if plot.__class__.__name__ == "Plot":
            if plot.name == filename:
                all_plots.remove(plot)
                break
    with open(CONFIG_DICT["PLOTS_FILE"],"wb") as f:
        pickle.dump(all_plots, f)