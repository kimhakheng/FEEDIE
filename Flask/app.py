#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# ********************************************
# User Interface Model v1
# for feeding robot arm
# By Ye Liu
# Aug 14 2018
# ********************************************

import cv2
import nltk
import serial
import pyautogui as pag
from redis import StrictRedis
from flask import Flask, render_template, Response, request, jsonify


# ser = serial.Serial('/dev/cu.usbmodem14341', 9600)

# Redis initialization
redis = StrictRedis(host='localhost', port=6379, db=0)
redis.set('count', '0')
redis.set('classifier', '')


class VideoCamera(object):
    def __init__(self):
        self.video = cv2.VideoCapture(0)

        self.color = (0, 255, 0)
        self.font = cv2.FONT_HERSHEY_SIMPLEX

        self.faceClassfier = cv2.CascadeClassifier(
            '/usr/local/share/OpenCV/haarcascades/haarcascade_frontalface_alt2.xml')
        self.breadClassfier = cv2.CascadeClassifier(
            '/Volumes/Data/Git/Feeding-Robot-Demo/Classifier/cascade_bread_11stages.xml')
        self.classifier = self.faceClassfier

    def __del__(self):
        self.video.release()

    def get_frame(self):
        ok, frame = self.video.read()
        if not ok:
            print('frame not found')
            return

        # Create gray level image
        grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Read command from redis
        command = redis.get('classifier')

        # Change classifier
        if command == b'bread':
            self.classifier = self.breadClassfier
        else:
            self.classifier = self.faceClassfier

        # Object recognition
        if self.classifier:
            faceRects = self.classifier.detectMultiScale(
                grey, scaleFactor=1.1, minNeighbors=3, minSize=(150, 150))

            if len(faceRects):
                (x, y, w, h) = faceRects[0]
                center_x = int(x + w / 2)
                center_y = int(y + h / 2)

                if command == b'bread':
                    if center_x > 570 and center_x < 700:
                        count = int(redis.get('count'))
                        count += 1
                        if count >= 20:
                            # Send pick message
                            self.ser.write('p'.encode())
                            # Switch back to face classifier
                            redis.set('classifier', 'feed')
                        else:
                            redis.set('count', str(count))
                    else:
                        redis.set('count', '0')
                elif command == b'feed':
                    if center_x > 570 and center_x < 700 and center_y > 410 and center_y < 530:
                        count = int(redis.get('count'))
                        count += 1
                        if count >= 15:
                            # Send feed message
                            self.ser.write('e'.encode())
                            # Switch back to face classifier
                            redis.set('classifier', '')
                        else:
                            redis.set('count', str(count))
                    else:
                        redis.set('count', '0')

                # Send serial data
                # coordinate = 'c' + str(center_x) + ',' + str(center_y) + 'q'
                # ser.write(coordinate.encode())
                # print('Send:', coordinate)

                # Receive serial data
                # res = ser.readline()
                # print('Receive:', res.decode())

                cv2.rectangle(frame, (x - 10, y - 10),
                              (x + w + 10, y + h + 10), self.color, 2)

                cv2.putText(frame, 'Size: %d%%' % int(
                    100 * h / frame.shape[0]), (x + 5, y + 30), self.font, 1, (255, 0, 255), 3)

        ret, jpeg = cv2.imencode('.jpg', frame)
        return jpeg.tobytes()


app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html')


def gen(camera):
    while True:
        frame = camera.get_frame()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')


@app.route('/video_feed')
def video_feed():
    return Response(gen(VideoCamera()),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/app_init')
def app_init():
    redis.set('status', '')
    return 'Success'


@app.route('/status')
def status():
    status = redis.get('classifier')
    if not status:
        return 'Searching for face'
    elif status == 'feed':
        return 'Feeding'
    else:
        return ''


@app.route('/start_recording', methods=['GET'])
def start_recording():
    recording = redis.get('status')
    print(recording)
    if not recording:
        pag.hotkey('ctrlleft', 'shiftleft', 'q')
        redis.set('status', 'recording')
    return 'Success'


@app.route('/speech_recognition', methods=['GET'])
def speech_recognition():
    input = request.args.get('input')

    words = nltk.word_tokenize(input)
    tagged_words = nltk.pos_tag(words)

    for item in tagged_words:
        if item[0] == 'bread':
            print('Keyword: bread\n')

            recording = redis.get('status')
            if recording:
                pag.hotkey('ctrlleft', 'shiftleft', 'q')
                redis.set('status', '')

            # Send 'object' message
            # ser.write('o'.encode())

            # Switch classifier
            redis.set('classifier', 'bread')

            return jsonify({'keyword': 'bread'})

    for item in tagged_words:
        if item[1] == 'NN' and item[0] not in ['piece', 'cup',
                                               'bottle', 'bar', 'spoon', 'bowl', 'oh', 'please']:
            print('Keyword:', item[0], '\n')

            # if item[0] == 'hello':
            #     # Send 'hello' message
            #     ser.write('h'.encode())

            return jsonify({'keyword': item[0]})

    return jsonify({'keyword': ''})


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)
