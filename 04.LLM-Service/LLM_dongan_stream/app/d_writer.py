# d_writer.py - sends D from 30 to 100 at 1s interval to server /ingest
import time, requests, os, sys

SERVER = os.environ.get('SERVER_URL', 'http://127.0.0.1:8000/ingest')
START = 20
END = 100
INTERVAL = 0.2

def run():
    d = START
    try:
        while d <= END:
            payload = {'D': d, 'ts': time.time()}
            try:
                r = requests.post(SERVER, json=payload, timeout=5)
                print(f"POST D={d} -> {r.status_code} {r.text}")
            except Exception as e:
                print("POST error:", e)
            d += 1
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        print("Interrupted. Stopping.")

if __name__ == '__main__':
    print("D writer starting, SERVER:", SERVER)
    run()


# d_write.py
# """
# D value simulator.
# - 기본 시퀀스: [20, 40, 30, 60, 20, 100]
# - 각 목표(target)으로 1씩 증감하면서 interval(초) 간격으로 서버 /ingest 에 POST
# - 실행 예: python d_write.py
# - 옵션:
#     --url URL        : 서버 ingest URL (기본 http://127.0.0.1:8000/ingest)
#     --interval FLOAT : 간격(초) (기본 0.2)
#     --loop N         : 시퀀스 반복 횟수 (기본 1, 0이면 무한)
# """
# import time
# import requests
# import argparse
# import sys
# from time import time as now_ts

# DEFAULT_SEQ = [20, 40, 25, 60, 20, 100]

# def send_ingest(url, D):
#     payload = {"D": D, "ts": now_ts()}
#     try:
#         r = requests.post(url, json=payload, timeout=1.5)
#         # not failing on non-200, but print status
#         print(f"POST {url} -> D={D} status={r.status_code}")
#     except Exception as e:
#         print(f"POST {url} -> D={D} FAILED: {e}")

# def run_sequence(url, seq, interval, loop):
#     if not seq:
#         print("Empty sequence.")
#         return
#     current = seq[0]
#     print(f"Starting D simulator. start={current}, interval={interval}s, loop={loop if loop!=0 else '∞'}")
#     # send initial value
#     send_ingest(url, current)
#     time.sleep(interval)
#     iteration = 0
#     while True:
#         for target in seq[1:]:
#             step = 1 if target > current else -1
#             while current != target:
#                 current += step
#                 send_ingest(url, current)
#                 time.sleep(interval)
#         iteration += 1
#         if loop > 0 and iteration >= loop:
#             print("Finished requested loops.")
#             return
#         if loop == 0:
#             # infinite: repeat sequence starting from first element
#             # ensure we "jump" to first element only by stepping
#             first = seq[0]
#             step = 1 if first > current else -1
#             while current != first:
#                 current += step
#                 send_ingest(url, current)
#                 time.sleep(interval)
#             # then continue the outer for-loop naturally (it will start from seq[1:])
#             continue
#         # if loop>1: prepare for next loop by moving from last target to first target
#         if loop > 1:
#             first = seq[0]
#             if current != first:
#                 step = 1 if first > current else -1
#                 while current != first:
#                     current += step
#                     send_ingest(url, current)
#                     time.sleep(interval)
#         # next loop will start automatically

# if __name__ == "__main__":
#     p = argparse.ArgumentParser(description="D value simulator for /ingest endpoint")
#     p.add_argument("--url", type=str, default="http://127.0.0.1:8000/ingest", help="Ingest endpoint URL")
#     p.add_argument("--interval", type=float, default=0.2, help="Interval in seconds between steps")
#     p.add_argument("--loop", type=int, default=1, help="How many times to run the full sequence (0 = infinite)")
#     p.add_argument("--seq", type=str, default=",".join(map(str, DEFAULT_SEQ)), help="Comma-separated sequence of targets, e.g. '20,40,30,60,20,100'")
#     args = p.parse_args()

#     try:
#         seq = [int(s.strip()) for s in args.seq.split(",") if s.strip()!='']
#     except Exception as e:
#         print("Invalid --seq value:", e)
#         sys.exit(1)

#     run_sequence(args.url, seq, args.interval, args.loop)
