#!/usr/bin/python3

import RPi.GPIO as GPIO
import requests
import os
import socket
import threading
import time

import config

class Source:
    MOTION = 0
    MANUAL = 1

class MotionSensorState:
    NOTTRIGGERED  = 0
    TRIGGEREDONCE = 2
    
class RelayServer(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)
        
        self._cmdQueue = []
        
    def run(self):
        
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("0.0.0.0", 42024))
            s.listen()
            while True:
                conn, addr = s.accept()
                print("New connection: ", addr)
                conn.settimeout(0.1)
                with conn:
                    while True:
                        if len(self._cmdQueue) == 0:
                            try:
                                data = conn.recv(256)
                                while len(data) < 5:
                                    data += conn.recv(256)
                                if "PING" in data.decode("ascii"):
                                    conn.sendall("PONG\n".encode("ascii"))
                            except socket.timeout:
                                pass
                            except:
                                print("Connection closed")
                                break
                            continue
                        
                        cmd = self._cmdQueue.pop()
                        try:
                            conn.sendall((cmd + "\n").encode("ascii"))
                        except:
                            self._cmdQueue.insert(0, cmd)
                            break
                            
                    conn.close()
                       
        
    def sendCommand(self, cmd):
        self._cmdQueue.append(cmd)
    
def currentTime():
    return int(time.time())

def sendMessage(msg):

    r = requests.get("{0}{1}/sendMessage?chat_id={2}&text={3}".format(config.telegramURL, config.telegramToken, config.telegramChatId, msg))

    return r.status_code == 200

def getMessages():
    global lastMessageTs
    global lastUpdateId

    msgs = []

    try:
        r = requests.get("{0}{1}/getUpdates?chat_id={2}&offset={3}".format(config.telegramURL, config.telegramToken, config.telegramChatId, lastUpdateId))

        updates = r.json()
    
        results = updates["result"]
    except:
        return msgs

    for update in results:
        lastUpdateId = update["update_id"]
        if update["message"]["date"] > lastMessageTs and 'text' in update["message"]:
            msgs.append(update["message"]["text"])
            lastMessageTs = update["message"]["date"]

    return msgs

def sendPhoto():
    os.system("fswebcam -r 640x480 --jpeg 85 -D 1 shot.jpg")

    f = open("shot.jpg", "rb")

    r = requests.post("{0}{1}/sendPhoto".format(config.telegramURL, config.telegramToken), data={"chat_id":config.telegramChatId}, files={"photo":f})

    f.close()

    os.remove("shot.jpg")
    
    
def sendVideo():
    os.system(" ffmpeg -t 10 -f v4l2 -framerate 25 -video_size 640x80 -i /dev/video0 video.mkv")

    f = open("video.mkv", "rb")

    r = requests.post("{0}{1}/sendVideo".format(config.telegramURL, config.telegramToken), data={"chat_id":config.telegramChatId}, files={"video":f})

    f.close()

    os.remove("video.mkv")
    
def takePhoto():
    relayServer.sendCommand("ON")
    
    sendPhoto()
    
    if switchOnTs == 0: relayServer.sendCommand("OFF")

def switchOn(source):
    global relayPin
    global switchOnTs
    
    #if source == Source.MOTION and switchOnTs > 0 : return

    relayServer.sendCommand("ON")
    switchOnTs = currentTime()

    if source == Source.MANUAL:
        sendPhoto()
    elif source == Source.MOTION:
        sendVideo()

def switchOff():
    global relayPin
    global switchOnTs

    relayServer.sendCommand("OFF")
    switchOnTs = 0
    sendMessage("OFF")

def shouldTurnSwitchOff():
    global switchOnTs

    return switchOnTs > 0 and currentTime() - switchOnTs > 10 * 60


# KODUN BASLANGICI
switchOnTs = 0

lastMessageTs = currentTime()
lastUpdateId = 0
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False) # Birden fazla setup cagirdiginda uyari gostermesin diye
relayPin = 2
PIRPin = 4
GPIO.setup(relayPin, GPIO.OUT)
GPIO.setup(PIRPin, GPIO.IN,  pull_up_down=GPIO.PUD_DOWN)
GPIO.output(relayPin, GPIO.HIGH)

relayServer = RelayServer()
relayServer.start()

msgCnt = 0
motionSensor = MotionSensorState.NOTTRIGGERED
while True:
    if msgCnt == 10:
        msgCnt = 0
        msgs = getMessages()

        for msg in msgs:
            if msg.upper() == "ON":
                print("ON")
                switchOn(Source.MANUAL)

            elif msg.upper() == "OFF":
                print("OFF")
                switchOff()
                
            elif msg.upper() == "PHOTO":
                print("PHOTO")
                takePhoto()
    else:
        msgCnt += 1

    if GPIO.input(PIRPin) == 1:
        if motionSensor == MotionSensorState.TRIGGEREDONCE:
            print("Hareket")
            switchOn(Source.MOTION)
        else:
            motionSensor = MotionSensorState.TRIGGEREDONCE
    else:
        motionSensor = MotionSensorState.NOTTRIGGERED

    if shouldTurnSwitchOff():
        print("OFF")
        switchOff()

    time.sleep(0.1)

