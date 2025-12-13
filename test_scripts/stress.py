import multiprocessing as mp
import time, psutil

def cpu_worker():
    while True: a = sum(i*i for i in range(10**7))

def mem_worker(max_gb=8):
    mem = []
    while psutil.virtual_memory().available > max_gb*10**9:
        mem.append([0.0]*(10**7))
        time.sleep(0.01)

if __name__ == "__main__":
    mp.set_start_method('spawn')
    procs = [mp.Process(target=cpu_worker) for _ in range(mp.cpu_count())]
    procs.append(mp.Process(target=mem_worker))
    for p in procs: p.start()
    try: time.sleep(3600)
    except KeyboardInterrupt: [p.terminate() for p in procs]
