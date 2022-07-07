# gpu_cluster_monitor

A gpu cluster monitor built with Python, InfluxDB and Grafana. 

中文用户可以查看这个[blog](https://www.bilibili.com/read/cv12910447). 文中版本与本仓库相比略早，但本质是一样的。

## How it looks
![Demo](/demo.png)
Tested with Grafana 8.1.2 + Influxdb 1.8.9 on Ubuntu 20.04 LTS.


## How it works

The monitor machine keeps ssh connections with one or more gpu nodes and exec status collection scripts.
Then the collected data is stored by influxdb and visualized by grafana.

## Before we start
* GPU Node

These are the machines we are interested in.
```
pip install psutil GPUtil setproctitle
```

* Monitor

This is the machine that holds influxdb and grafana.
```
pip install paramiko influxdb
```

## How to deploy

### Install Grafana and InfluxDB on the Monitor machine.
```
wget https://dl.influxdata.com/influxdb/releases/influxdb_1.8.9_amd64.deb
sudo dpkg -i influxdb_1.8.9_amd64.deb
sudo apt-get install -y adduser libfontconfig1
wget https://dl.grafana.com/oss/release/grafana_8.1.2_amd64.deb
sudo dpkg -i grafana_8.1.2_amd64.deb
```

And start the services

```
sudo service influxdb start
sudo service influxdb status
sudo update-rc.d influxdb defaults
sudo service grafana-server start
sudo service grafana-server status
sudo update-rc.d grafana-server defaults
```

### Config InfluxDB

Open influxdb-cli
```
influx
```

You should see something like this
```
Connected to http://localhost:8086 version 1.8.10
InfluxDB shell version: 1.8.10
>
```

Create DB
```
> CREATE DATABASE "monitor" WITH DURATION 30d REPLICATION 1 NAME "one_month"
```
The DB should keep the data for only 30 days. 
For more information, check: https://docs.influxdata.com/influxdb/v1.8/query_language/manage-database/

Create user with proper permission
```
> CREATE USER python WITH PASSWORD 'python'
> GRANT ALL ON monitor TO python
```

### Config Grafana

Login http://localhost:3000 with admin/admin 

Add the DB we just created as a data source
```
URL = http://localhost:8086
Database = monitor
User = python
Password = python
```

Import panel from this ![JSON file](/Servers-1639853401172.json).

### Setup SSH connection

On the monitor machine
```
ssh-keygen
ssh-copy-id <your GPU node>
```

### Run data collection

On the monitor machine, edit `collect_hw_usage_pub.py` first and run
```
python3 collect_hw_usage_pub.py
```

And it should work now.

For windows machines, please use `report_usage_winservice.py` to report the usage to the InfluxDB server. After installation it runs as a service.
