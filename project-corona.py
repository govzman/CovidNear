# -"- coding:utf-8 -"-

# импортирую библиотеки
import requests
import json
import os

from flask import Flask, request
import logging
import sqlite3
import time

# функция, вычисляющая расстояния до домов, и возвращающая текст с количеством домов 
# расстояние до которых меньше 1 километра, и говорящая адрес ближайшего дома + расстояние до него

def search(cords, rad=1):
    global cur
    dis = []  # список из дистанций

    result = cur.execute(
        "SELECT * FROM adresses WHERE (width >= " + str(int(cords[0].replace('.', '').ljust(10, '0')) -  # ищем в базе данных дома, которые попадают в радиус в 1 километр
                                                         900000 * rad) + ") AND (width <= " + str(int(cords[0].replace('.', '').ljust(10, '0')) + 900000 * rad) +
        ") AND (height >= " + str(int(cords[1].replace('.', '').ljust(10, '0')) -
                                 1562500 * rad) + ") AND (height <= " + str(int(cords[1].replace('.', '').ljust(10, '0')) + 1562500 * rad) + ")").fetchall()

    
    if len(result) > 0:  # проверка на то что дома впринципе есть
        for i in result:  # считаем расстояния через разницу координат
            distance = ((
                (i[2] - int(cords[1].replace('.', '').ljust(10, '0'))) / 900) ** 2 + (
                (i[3] - int(cords[0].replace('.', '').ljust(10, '0'))) / 1562.5) ** 2) ** 0.5
            dis.append(distance)
        text = "В радиусе 1 километра от этого дома " + \
            str(len(result))  # сколько домов всего
        # склонение слова для красоты
        if str(len(result))[-1] == '1' and str(len(result))[-2] != '1':
            text += ' зараженный'
        else:
            text += ' зараженных'
        # если расстояние до дома меньше 10 метров, то считает что заболевший в данном доме
        if int(round(min(dis), 0)) > 10:
            text += ', при этом ближайший дом находится по адресу: '
            # адрес дома
            text += result[dis.index(min(dis))][1].replace('Москва, ', '')
            text += ' на расстоянии в '
            text += str(int(round(min(dis), 0)))  # расстояние до него
            # тоже для красоты
            if str(int(round(min(dis), 0)))[-1] == '1' and str(int(round(min(dis), 0)))[-2] != '1':
                text += ' метр от этого дома.'
            elif str(int(round(min(dis), 0)))[-1] == '2' and str(int(round(min(dis), 0)))[-2] != '1':
                text += ' метра от этого дома.'
            elif str(int(round(min(dis), 0)))[-1] == '3' and str(int(round(min(dis), 0)))[-2] != '1':
                text += ' метра от этого дома.'
            elif str(int(round(min(dis), 0)))[-1] == '4' and str(int(round(min(dis), 0)))[-2] != '1':
                text += ' метра от этого дома.'
            else:
                text += ' метров от этого дома.'
        else:
            # случай, когда заболевший в данном доме
            text += ' и ближайший зараженный находится в этом доме!'
    else:
        text = 'В радиусе километра зараженных не обнаружено, поздравляю!' # случай, когда заболевших не найдено
    # спрашивает хочет ли еще узнать
    text += ' Назови новый адрес или скажи "Завершить диалог"'
    return text


app = Flask(__name__)


#logging.basicConfig(level=logging.DEBUG)


sessionStorage = {}

parts = {}  # 0 - узнаем адрес, 1 - говорим количество
#                  и ближайший адрес, 2 - спрашиваем хочет ли узнать еще

@app.route('/', methods=['POST'])
def main(): # функция коннекта
    # logging.info(f'Request: {request.json!r}')
    response = {
        'session': request.json['session'],
        'version': request.json['version'],
        'response': {
            'end_session': False
        }
    }
    handle_dialog(request.json, response)
    # logging.info(f'Response:  {response!r}')
    return json.dumps(response)

  
def handle_dialog(req, res): # диалог с пользователем
    user_id = req['session']['user_id']
    if req['session']['new']: # новая сессия
        res['response'][
            'text'] = 'Привет! Узнай сколько заболевших коронавирусом есть около тебя! ' + \
            'Назови адрес, про который хочешь узнать, правда я могу сказать только про Москву и окрестности'
        return

    try: # на всякий случай)
        if list(map(lambda x: x.lower(), req['request']['nlu']['tokens'])) == ['закончить', 'диалог'] or \
           list(map(lambda x: x.lower(), req['request']['nlu']['tokens'])) == ['завершить', 'диалог']:
            res['response']['text'] = 'Пока! Возвращайся за новой информацией завтра и старайся поменьше выходить из дома!'
            res['response']['tts'] = 'Пока! Возвращайся за новой информацией завтра и старайся поменьше выход+ить из дома!'
            res['response']['end_session'] = True
            return
    except Exception:
        pass
    try:
        # что ты умеешь? - обязательный вопрос в навыке Алисы
        if list(map(lambda x: x.lower(), req['request']['nlu']['tokens'])) == ['что', 'ты', 'умеешь'] or \
           list(map(lambda x: x.lower(), req['request']['nlu']['tokens'])) == ['помощь']:
            res['response']['text'] = 'Я умею определять сколько зараженных коронавирусом людей находятся в ' + \
                'радиусе 1 километра от тебя, для этого мне достаточно сказать адрес любого дома. Скажи мне адрес'
            return
    except Exception:
        pass
    try:
        for i, dat in enumerate(req['request']['nlu']['entities']):
            if dat['type'] == "YANDEX.GEO":
                
                if 'city' not in list(req['request']['nlu']['entities'][i]['value'].keys()):
                    # ищем спрашиваемый дом через API Яндекс.Карт
                    geocoder_request = "http://geocode-maps.yandex.ru/1.x/?apikey=40d1649f-0493-4b70-98ba-98533de7710b&geocode=Москва,+" + \
                        req['request']['nlu']['entities'][i]['value']['street'] + \
                        ",+" + \
                        req['request']['nlu']['entities'][i]['value']['house_number'] + \
                        "&format=json"

                else:
                    # случай, если будут спрашивать соседние города (Химки, Мытищи и тд)
                    geocoder_request = "http://geocode-maps.yandex.ru/1.x/?apikey=40d1649f-0493-4b70-98ba-98533de7710b&geocode=Москва,+" + \
                        req['request']['nlu']['entities'][i]['value']['city'] + ',+' + \
                        req['request']['nlu']['entities'][i]['value']['street'] + \
                        ",+" + \
                        req['request']['nlu']['entities'][i]['value']['house_number'] + \
                        "&format=json"

                response = requests.get(geocoder_request)
                if response:  # если адрес нашелся
                    json_response = response.json()
                    toponym = json_response["response"]["GeoObjectCollection"]["featureMember"][0]["GeoObject"]
                    toponym_coordinates = toponym["Point"]["pos"]
                    timek = time.time()
                    res['response']['text'] = search(
                        toponym_coordinates.split())
                    print(time.time() - timek)
                else:  # если не нашелся
                    res['response']['text'] = 'Мне очень жаль, но такого адреса нет, скажите еще раз'
                return
        # пользователь сказал не адрес
        res['response']['text'] = 'Кажется, это не адрес. Назовите адрес еще раз'
    except Exception as e:
        print(e)
        res['response']['text'] = "Не совсем тебя поняла. Назови адрес еще раз"



def make_data():  # ручная функция (в программе не используется), чтобы составлять базу данных (береться по адресу coronavirus.mash.ru/data.json)
    data = json.loads(open('data.json', mode='rb').read())
    
    con = sqlite3.connect('data_covid.db')
    cur = con.cursor()
    
    for i in range(len(data['features'])):
        cur.execute(
            "INSERT INTO adresses(id,adress,height,width) VALUES(" + str(i) + ",'" +
            data['features'][i]['properties']['hintContent'] + "'," +
            data['features'][i]['geometry']['coordinates'][0].replace('.', '').ljust(10, '0') +
            "," + data['features'][i]['geometry']['coordinates'][1].replace('.', '').ljust(10, '0') + ")")
    
    con.commit()
    con.close()
    

if __name__ == '__main__':  # для Heroku
    con = sqlite3.connect('data_covid.db', check_same_thread=False)  # база данных
    cur = con.cursor()
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

