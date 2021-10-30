import psutil, os, re


def files_on_disk(patch, size_all_files=0, depth=0, all_files=True):
    if depth > 2: return(size_all_files)
    depth += 1
    if not os.path.exists(patch):
        return(size_all_files)
    for name in os.listdir(patch):
        obj = patch+"/"+name
        try:
            if os.path.isfile(obj):
                match = re.findall(r"plot-k(\d{2})", name)
                if all_files: match = True
                if match:
                    size_all_files += os.path.getsize(obj)
                    continue
            if os.path.isdir(obj):
                size_all_files += files_on_disk(patch=obj, depth=depth)
        except(PermissionError):
            pass
    return(size_all_files)


disks = psutil.disk_partitions(all=False)
for disk in disks:
    du = psutil.disk_usage(disk.mountpoint)
    if du.total > 100000000000:
        used_f = files_on_disk(disk.mountpoint)
        total = du.total
        free = du.free
        diff = total - (used_f+free)
        if diff > 110000000:
            print("{0}\ntotal: {1} free+used: {2} diff: {3} MB".format(disk.mountpoint, du.total, used_f+free, (diff)/1000000))
        else: print(disk.mountpoint+": OK")
