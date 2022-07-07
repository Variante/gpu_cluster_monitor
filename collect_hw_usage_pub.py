import paramiko
import time
import json
import traceback
from datetime import datetime
import threading
import sys
from influxdb import InfluxDBClient

# Configs
# IP address, nick name (anything you want), port, username, command
py_cmd = "python3 gen_hw_usage.py -l 5"
servers = [
    ('server address', 'server nickname', 22, 'username', conda_cmd),
]

pub_key = 'YOUR PATH TO/id_rsa.pub'

# influxdb addr, port, username, password, dataset
dbclient = InfluxDBClient('localhost', 8086, 'python', 'python&input', 'monitor')

# *******************************************************************************************
# function
is_running = True

# single worker
def fetch_hw_info(db_client, server, nickname, port, username, cmd):
    client = paramiko.SSHClient()
    client.load_system_host_keys(filename=pub_key)
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(server, username=username, port=port, timeout=30)
    print(f"Connection to {nickname} established")
    stdin, stdout, stderr = client.exec_command(cmd)

    def parse_info_to_json(r):
        info = json.loads(r)
        # print(info['cpu'])

        ts = datetime.utcnow().isoformat()

        def get_common_body(measurement, name, fields):
            return {
                "measurement": measurement,
                "tags": {
                    "host": nickname,
                    measurement: name
                 },
                "time": ts,
                "fields": fields
            }

        cpu_body = [get_common_body("cpu", f"cpu{i:d}", {"value": j}) for i, j in enumerate(info['cpu'])]
        cpu_body.append(get_common_body("cpu", f"cpu-total", {"value": info['cpu_total']}))

        ram_body = [{
            "measurement": "ram",
            "tags": {
                "host": nickname
             },
            "time": ts,
            "fields": info['ram']
        }]

        def parse_gpu(js):
            js['mem_available'] = js['mem_total'] - js['mem_used']
            del js['id']
            return js

        def parse_net(js):
            js['recv_bytes_ps'] = float(js['recv_bytes_ps'])
            js['sent_bytes_ps'] = float(js['sent_bytes_ps'])
            del js['id']
            return js

        net_body = [get_common_body("net", net['id'], parse_net(net)) for net in info['net']]

        if 'gpu' in info:
            gpu_body = [get_common_body("gpu", f"gpu{j['id']}", parse_gpu(j)) for j in info['gpu']]
        else:
            gpu_body = []
 
        return cpu_body + ram_body + gpu_body + net_body

    while is_running:
        try:
            r = stdout.readline()
            # if stdout.channel.exit_status_ready():
            #     break
            if len(r):
                if db_client is not None:
                    points = parse_info_to_json(r)
                    db_client.write_points(points, time_precision='ms')
                    # print(r)
                else:
                    print(r)
            if stdout.channel.exit_status_ready():
                break
        except:
            print(f"Server: {nickname}:")
            traceback.print_exc()
            print('*' * 8)
            break
    client.close()


def fetch_loop(*args):
    print(args)
    retry_delay = 5
    while is_running:
        fetch_hw_info(*args)
        if is_running:
            print(f"[{args[2]}]: Found some error, try again after {retry_delay}s", file=sys.stderr)
            time.sleep(retry_delay)

# ****************************************************************************************************


thres = [threading.Thread(target=fetch_loop, args=(dbclient, *server_info,)) for server_info in servers]

for i, j in enumerate(servers):
    print(f"Connect to {j[1]}")
    thres[i].start()

try:
    while True:
        time.sleep(1)
except:
    pass

is_running = False
print("Stop all threads")

for i, j in enumerate(servers):
    print(f"Disconnect from {j[1]}")
    thres[i].join()

dbclient.close()
print("All threads done")
