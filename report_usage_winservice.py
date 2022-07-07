import time
import json
import traceback
from datetime import datetime
import threading
import sys
from influxdb import InfluxDBClient
import psutil
import argparse
import GPUtil
import setproctitle
import win32serviceutil
import win32service
import win32event
import servicemanager


class AppServerSvc (win32serviceutil.ServiceFramework):
    _svc_name_ = "HWMonitor"
    _svc_display_name_ = "InfluxDB HWMonitor"

    def __init__(self,args):
        win32serviceutil.ServiceFramework.__init__(self,args)
        
        self.nickname = '5700G+3060'
        self.previous_net = None
        self.interval = 3
        self.disk_list = [
            'c:',
            'd:',
            'e:',
            ]
            
        self.is_running = True
        self.dbclient = None

    def SvcStop(self):
        self.is_running = False
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        

    def SvcDoRun(self):
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                              servicemanager.PYS_SERVICE_STARTED,
                              (self._svc_name_,''))
        self.is_running = True
        self.main()
        
    def gen_hw_usage(self):
        time.sleep(self.interval)
        res = {}
        res['cpu'] = psutil.cpu_percent(percpu=True)
        res['cpu_total'] = psutil.cpu_percent()
        res['ram'] = psutil.virtual_memory()._asdict()

        def gen_disk_usage(disk):
            d = psutil.disk_usage(disk)
            return {'id': disk, 'total': d.total, 'used': d.used, 'free': d.free, 'percent': d.percent}

        res['disk'] = [gen_disk_usage(i) for i in self.disk_list]
        
        current_net = psutil.net_io_counters(pernic=True)
        if_info = psutil.net_if_stats()
        
        res['net'] = []
        
        for if_stat in if_info:
            if if_info[if_stat].speed > 0:
                res['net'].append({
                    'id': if_stat,
                    'bandwidth': if_info[if_stat].speed, # Mbps
                    'recv_bytes_ps': (current_net[if_stat].bytes_recv - self.previous_net[if_stat].bytes_recv) * 8 / self.interval if self.previous_net is not None else 0, # bps
                    'sent_bytes_ps': (current_net[if_stat].bytes_sent - self.previous_net[if_stat].bytes_sent) * 8 / self.interval if self.previous_net is not None else 0 # bps
                })
        
        self.previous_net = current_net
        
        try: 
            res['gpu'] = [{'id': gpu.id, 'load': gpu.load, 'mem_used': gpu.memoryUsed, 'mem_total': gpu.memoryTotal, 'mem_util': gpu.memoryUtil} for gpu in GPUtil.getGPUs()]
        except:
            res['gpu'] = []
        return res
    
    # single worker
    def fetch_hw_info(self):
        nickname = self.nickname
        def parse_info_to_json(r):
            info = r
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

            def parse_disk(js):
                js['free'] = int(js['free'])
                js['total'] = int(js['total'])
                js['used'] = int(js['used'])
                js['percent']= float(js['percent'])
                del js['id']
                return js


            net_body = [get_common_body("net", net['id'], parse_net(net)) for net in info['net']]

            if 'disk' in info:
                disk_body = [get_common_body("disk", d['id'], parse_disk(d)) for d in info['disk']]
            else:
                disk_body = []

            if 'gpu' in info:
                gpu_body = [get_common_body("gpu", f"gpu{j['id']}", parse_gpu(j)) for j in info['gpu']]
            else:
                gpu_body = []

            return cpu_body + ram_body + gpu_body + net_body + disk_body

        while self.is_running:
            try:
                r = self.gen_hw_usage()
                points = parse_info_to_json(r)
                self.dbclient.write_points(points, time_precision='ms')
            except:
                print(f"Server: {nickname}:")
                traceback.print_exc()
                print('*' * 8)
                break

    def main(self):
        retry_delay = 15
        while self.is_running:
            try:
                self.dbclient = InfluxDBClient('localhost', 8086, 'python', 'python&input', 'monitor')
                self.fetch_hw_info()
                self.dbclient.close()
            except:
                print(f"[{self.nickname}]: Found some error, try again after {retry_delay}s", file=sys.stderr)
                traceback.print_exc()
                time.sleep(retry_delay)
        self.dbclient.close()


if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(AppServerSvc)
