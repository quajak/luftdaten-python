#!/usr/bin/env python3

import sys
import os
import yaml
from datetime import datetime

# Import-Pfade setzen
sys.path.append(os.path.join(sys.path[0],"sds011"))
sys.path.append(os.path.join(sys.path[0],"bme280"))

import time
import json
import requests
import numpy as np
from sds011 import SDS011
from Adafruit_BME280 import *

# Config
with open("config.yml", 'r') as ymlfile:
    config = yaml.load(ymlfile)

# Logging
import logging
logging.basicConfig(level=logging.DEBUG)

#bme280 = BME280(
#    address=0x76,
#    t_mode=BME280_OSAMPLE_8,
#    p_mode=BME280_OSAMPLE_8,
#    h_mode=BME280_OSAMPLE_8,
#)

# Create an instance of your bme280
dusty = SDS011('/dev/ttyUSB0')

# Now we have some details about it
print("SDS011 initialized: device_id={} firmware={}".format(dusty.device_id,dusty.firmware))

# Set dutycyle to nocycle (permanent)
dusty.dutycycle = 0

class Measurement:
    def __init__(self):
        pm25_values = []
        pm10_values = []
        dusty.workstate = SDS011.WorkStates.Measuring
        try:
            for a in range(8):
                values = dusty.get_values()
                if values is not None:
                    pm10_values.append(values[0])
                    pm25_values.append(values[1])
        finally:
            dusty.workstate = SDS011.WorkStates.Sleeping

        self.pm25_value  = np.mean(pm25_values)
        self.pm10_value  = np.mean(pm10_values)
        self.temperature = 0#bme280.read_temperature()
        self.humidity    = 0#bme280.read_humidity()
        self.pressure    = 0#bme280.read_pressure()

    def sendInflux(self):
        cfg = config['influxdb']

        if not cfg['enabled']:
            return

        data = "feinstaub,node={} SDS_P1={:0.2f},SDS_P2={:0.2f},BME280_temperature={:0.2f},BME280_pressure={:0.2f},BME280_humidity={:0.2f}".format(
            cfg['node'],
            self.pm10_value,
            self.pm25_value,
            self.temperature,
            self.pressure,
            self.humidity,
        )

        requests.post(cfg['url'],
            auth=(cfg['username'], cfg['password']),
            data=data,
        )

    def sendLuftdaten(self):
        if not config['luftdaten']['enabled']:
            return

        self.__pushLuftdaten('https://api-rrd.madavi.de/data.php', 0, {
            "SDS_P1":             self.pm10_value,
            "SDS_P2":             self.pm25_value,
            "BME280_temperature": self.temperature,
            "BME280_pressure":    self.pressure,
            "BME280_humidity":    self.humidity,
        })
        self.__pushLuftdaten('https://api.luftdaten.info/v1/push-sensor-data/', 1, {
            "P1": self.pm10_value,
            "P2": self.pm25_value,
        })
        self.__pushLuftdaten('https://api.luftdaten.info/v1/push-sensor-data/', 11, {
            "temperature": self.temperature,
            "pressure":    self.pressure,
            "humidity":    self.humidity,
        })
        

        requests.post("https://pacific-headland-14893.herokuapp.com/push-sensor-data/", json= {
        "timestamp": str(datetime.now()),
        "location":{
        "latitude":"50.123",
        "longitude": "8.706"
        }, 
        "sensor" : {
        "id":170418
        },
        "sensordatavalues": [{
        "value":self.pm10_value,
		"value_type": "P1"
        },
		{
		"value":self.pm25_value,
		"value_type": "P2"
		}]
        )
        
        
    def __pushLuftdaten(self, url, pin, values):
        requests.post(url,
            json={
                "software_version": "python-dusty 0.0.1",
                "sensordatavalues": [{"value_type": key, "value": val} for key, val in values.items()],
            },
            headers={
                "X-PIN":    str(pin),
                "X-Sensor": sensorID,
            }
        )

# extracts serial from cpuinfo
def getSerial():
    with open('/proc/cpuinfo','r') as f:
        for line in f:
            if line[0:6]=='Serial':
                print(line[10:26])
    raise Exception('CPU serial not found')

def run():
    m = Measurement()

    logging.debug('pm2.5     = {:f} '.format(m.pm25_value))
    logging.debug('pm10      = {:f} '.format(m.pm10_value))
    logging.debug('Temp      = {:0.2f} deg C'.format(m.temperature))
    logging.debug('Humidity  = {:0.2f} %'.format(m.humidity))
    logging.debug('Pressure  = {:0.2f} hPa'.format(m.pressure/100))

    m.sendLuftdaten()
    m.sendInflux()


sensorID  = "raspi-" + getSerial()
starttime = time.time()

while True:
    logging.debug("running ...")
    run()
    time.sleep(10)

logging.debug("Stopped")
