import psutil, os, re, subprocess, sys

param = sys.argv
def files_on_disk(patch, size_all_files=0, depth=0, all_files=True):
    if depth > 2: return(size_all_files)
    depth += 1
    if not os.path.exists(patch):
        return(size_all_files)
    avg = {25:0,32:0,33:0,34:0,35:0}
    num = {25:0,32:0,33:0,34:0,35:0}
    for name in os.listdir(patch):
        obj = patch+"/"+name
        try:
            if os.path.isfile(obj):
                
                match = re.findall(r"plot-k(\d{2})", name)
                if match:
                    avg[int(match[0])] += os.path.getsize(obj)
                    num[int(match[0])] += 1
                if all_files: match = True
                if match:
                    size_all_files += os.path.getsize(obj)
                    continue
            if os.path.isdir(obj):
                size_all_files += files_on_disk(patch=obj, depth=depth)
        except(PermissionError):
            pass
    for key, value in avg.items():
        if num[key] != 0:
            print(value/num[key]/1.024**3/1000000000)
    return(size_all_files)


disks = psutil.disk_partitions(all=False)
for disk in disks:
    if '-s' in param:
        p = subprocess.Popen(['sudo', '-S', 'hdparm', '-S', '0', disk.device], stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        text = p.communicate('0' + '\n')[0]
        print(text)
    else:
        du = psutil.disk_usage(disk.mountpoint)
        if du.total > 100000000000:
            used_f = files_on_disk(disk.mountpoint)
            total = du.total
            free = du.free
            diff = total - (used_f+free)
            if diff > 110000000:
                print("{0}\ntotal: {1} free+used: {2} diff: {3} MB".format(disk.mountpoint, du.total, used_f+free, (diff)/1000000))
            else: print(disk.mountpoint+": OK")
