#!/usr/bin/env python
import aprslib
from datetime import  datetime, timedelta
from dateutil.parser import parse
import pyproj
import pytz
import re
import requests
import sqlite3
import schedule
import sys
import telnetlib
from threading import Thread, Lock
from time import sleep
import tweepy

from sotakeys import *
from last3 import *

debug = False
#debug = True

sotawatch_url = KEYS['SOTA_URL']
summit_db = KEYS['SUMMIT_DB']
beacon_db = KEYS['BEACON_DB']
alert_db = KEYS['ALERT_DB']
last3 = KEYS['LAST3']
last3dx = KEYS['LAST3DX']
aprs_user = KEYS['APRS_USER']
aprs_password = KEYS['APRS_PASSWD']
aprs_host = KEYS['APRS_HOST']
aprs_port = KEYS['APRS_PORT']
tweet_at = KEYS['TWEET_AT']
update_every = KEYS['UPDATE_EVERY']

tweet_api = None

aprs_filter = ""
aprs_beacon = None

localtz = pytz.timezone('Asia/Tokyo')
grs80 = pyproj.Geod(ellps='GRS80')
#3000m x 3000m
deltalat,deltalng = 0.002704*10,0.003311*10

def tweet(api, txt):
    if debug:
        print txt
    else:
        if len(txt) > 140:
            txt = txt[0:140]
	try:
            api.update_status(status=txt)
	except Exception, e:
            print >>sys.stderr, 'tweet error: %s ' % e
            print >>sys.stderr, 'txt = %s ' % txt 
            return

def tweet_with_media(api, fname, txt):
    if debug:
        print txt
    else:
        if len(txt) > 110:
            txt = txt[0:110]
        try:
            api.update_with_media(fname, status=txt)
        except Exception, e:
            print >>sys.stderr, 'tweet error %s ' % e
            print >>sys.stderr, 'txt = %s ' % txt 
	    return

def lookup_from_op(op):
    conn_beacon = sqlite3.connect(beacon_db)
    cur_beacon = conn_beacon.cursor()
    op = op[0:op.rfind('-')].strip()
    q = 'select * from beacons where operator = ?'
    cur_beacon.execute(q,(op,))
    for (_,_,_,_,_,_,_,_,l,_,mesg,_) in cur_beacon.fetchall():
        return mesg
    return "No Entries."

def lookup_summit(op,lat,lng):
    op = op[0:op.rfind('-')].strip()
    if op in KEYS['EXCLUDE_USER']:
        return (-1,"")
    
    if op in KEYS['TEST_USER']:
        mag = 10.0
    else:
        if len(KEYS['TEST_USER']) == 0:
               mag = 1.0
        else:
            return(-1,"")
        
    conn_summit = sqlite3.connect(summit_db)
    cur_summit = conn_summit.cursor()
    conn_beacon = sqlite3.connect(beacon_db)
    cur_beacon = conn_beacon.cursor()

    q = 'select * from beacons where operator = ?'
    cur_beacon.execute(q,(op,))
    state = -1
    for (_,_,_,_,_,_,_,_,state,_,_,_) in cur_beacon.fetchall():
        latu,latl = lat + deltalat*mag, lat - deltalat*mag
        lngu,lngl = lng + deltalng*mag, lng - deltalng*mag
        result = []

        for s in cur_summit.execute("select * from summits where (? > lat) and (? < lat) and (? > lng) and (? < lng)",(latu,latl,lngu,lngl,)):
            (code,lat1,lng1,pt,alt,name,desc,_,_)= s
            az,bkw_az,dist = grs80.inv(lng,lat,lng1,lat1)
            result.append((code,int(dist),int(az),pt,alt,name,desc))
        result.sort(key=lambda x:x[1])
        result = result[0:3]

        if len(result) > 0:
            (_,dist,_,_,_,_,_) = result[0]
            if dist <=100.0:
                if state < 3:
                    state = 3
                else:
                    state = 4
            elif dist <=300.0:
                if state < 1:
                    state = 1
                elif state ==1:
                    state = 2
            else:
                if state <= 0:
                    state = 0

            now = datetime.now(localtz).strftime("%H:%M")
            if state == 3 or state == 4:
                (code,dist,az,pt,alt,name,desc) = result[0]
                mesg = "Welcome to " + code +". "+ name + " " + str(alt) + "m "+ str(pt) + "pt.\n"+desc+"."
            elif state == 1 or state == 2:
                (code,dist,az,pt,alt,name,desc) = result[0]
                mesg = "Approacing " + code + " " + str(dist) +"m("+str(az)+"deg) to go."
            elif state == 0:
                mesg = now + " "
                for (code,dist,az,pt,alt,name,desc) in result:
                    mesg = mesg + code.split('/')[1] + ":"+ str(dist) + "m("+str(az)+") "
        else:
            mesg = "No Summits."
            
        q = 'update beacons set lastseen = ?, lat = ?, lng = ?, dist = ?, az = ?,level = ?,summit = ?,message = ?, type = ? where operator = ?'
        cur_beacon.execute(q,(now,lat,lng,dist,az,state,name,mesg,'APRS',op,))

        conn_beacon.commit()
        conn_beacon.close()
        conn_summit.close()

        return (state,mesg)
    
    conn_beacon.close()
    conn_summit.close()

    return (-1,"Oops!")

def parse_alerts(url):
    try:
        response = requests.get(url)
    except Exception, e:
        print >>sys.stderr, 'HTTP GET %s' % e
        return []
    
    result = []
    state = 'new'
    conn = sqlite3.connect(summit_db)
    cur = conn.cursor()
    
    for line in response.text.splitlines():
        if state == 'new' and "class=\"alertDate\">" in line:
            m = re.search('class=\"alertDate\">(.+)</span>',line)
            ald = m.group(1)
        elif state == 'new' and "<strong>Summit:</strong>" in line:
            m = re.search('Summit:</strong>\W(.+)\'',line)
            alert_sinfo = m.group(1)
        elif state == 'new' and "\"70px\">&nbsp" in line:
            m = re.search('&nbsp;([\d:]+)</td>$',line)
            alert_time = int(parse(ald + " " +m.group(1)).strftime("%s"))
            alert_start = alert_time - 3600
            alert_end= alert_time  + 10800
            state = 'operator'
        elif state == 'operator' and "<strong>" in line:
            m = re.search('<strong>(.+)</strong>',line)
            alert_callsign = m.group(1)
            m = re.match('(\w+)/(\w+)',alert_callsign)
            if m:
                if len(m.group(1)) > len(m.group(2)):
                    alert_operator = m.group(1)
                else:
                    alert_operator = m.group(2)
            else:
                alert_operator = alert_callsign
            state = 'summit'
        elif state == 'summit' and "<strong>" in line:
            m = re.search('<strong>(.+)</strong>',line)
            alert_summit = m.group(1)
            if "JA" in alert_summit:
                cur.execute('SELECT * from summits where code=?',(alert_summit,))
                for (_,_,_,pt,alt,name,desc,_,_) in cur.fetchall():
                    alert_sinfo = name + ", " +str(alt)+"m, "+str(pt)+" pt, " + desc
            state = 'freq'
        elif state == 'freq' and "<strong>" in line:
            m = re.search('<strong>(.+)</strong>',line)
            alert_freq = m.group(1)
            state = 'comment'
        elif state == 'comment' and "class=\"comment\">" in line:
            m = re.search('class=\"comment\">(.*)</span>',line)
            alert_comment = m.group(1)
            state = 'poster'
        elif state == 'poster' and "class=\"poster\">" in line:
            m = re.search('class=\"poster\">(.*)</span>',line)
            alert_poster = m.group(1)
   
            patplus = re.compile('S\+(\d+)',re.IGNORECASE)
            patminus = re.compile('S-(\d+)',re.IGNORECASE)
            for p in  patplus.findall(alert_comment):
                alert_end = alert_time + int(p)*3600
            for p in patminus.findall(alert_comment):
                alert_start = alert_time - int(p)*3600
            result.append({'time':alert_time,
                           'start':alert_start,
                           'end':alert_end,
                           'operator':alert_operator,
                           'callsign':alert_callsign,
                           'summit':alert_summit,
                           'summit_info':alert_sinfo,
                           'freq':alert_freq,
                           'comment':alert_comment,
                          'poster':alert_poster})
            state = 'new'
    conn.close()
    return result

def update_alerts():
    global aprs_filter
    conn = sqlite3.connect(alert_db)
    conn2 = sqlite3.connect(beacon_db)
    cur = conn.cursor()
    cur2 = conn2.cursor()
    q = 'create table if not exists alerts (time int,start int,end int,operator text,callsign text,summit text,summit_info text,freq text,comment text,poster text)'
    cur.execute(q)
    q = 'delete from alerts'
    cur.execute(q)
    conn.commit()

    res = parse_alerts(sotawatch_url)
    operators = []
    now = int(datetime.utcnow().strftime("%s"))

    q = 'delete from beacons where end < ?'
    cur2.execute(q,(now,))
    conn2.commit()

    for d in res:
        q = 'insert into alerts(time,start,end,operator,callsign,summit,summit_info,freq,comment,poster) values (?,?,?,?,?,?,?,?,?,?)'
        cur.execute(q,(d['time'],d['start'],d['end'],
                       d['operator'],d['callsign'],
                       d['summit'],d['summit_info'],d['freq'],
                       d['comment'],d['poster']))
        if now >= d['start'] and now <= d['end']:
            if not d['operator'] in operators:
                operators.append(d['operator'])
                q = 'insert or ignore into beacons (start,end,operator,lastseen,lat,lng,dist,az,level,summit,message,type) values (?,?,?,?,?,?,?,?,?,?,?,?)'
                cur2.execute(q,(d['start'],d['end'],d['operator'],
                                -1,'','',-1,0,-1,
                                d['summit'],d['summit_info'],'SW2'))

    for user in KEYS['TEST_USER']:
        d = {'time':now,'start':now-3600,'end':now+10800,
             'operator':user,'callsign':user,'summit':'JA/KN-999',
             'summit_info':'Nowhere','freq':'14-cw',
             'comment':'TEST','poster':'(Posted By JL1NIE)'}
        if not d['operator'] in operators:
            operators.append(d['operator'])
            q = 'insert or ignore into beacons (start,end,operator,lastseen,lat,lng,dist,az,level,summit,message,type) values (?,?,?,?,?,?,?,?,?,?,?,?)'
            cur2.execute(q,(d['start'],d['end'],d['operator'],
                            -1,'','',-1,0,-1,
                            d['summit'],d['summit_info'],'SW2'))
        
    conn.commit()
    conn2.commit()
    conn.close()
    conn2.close()

    aprs_filter =  "b/"+ "*/".join(operators) +"*"

    if aprs_beacon:
        aprs_beacon.set_filter(aprs_filter)
        
def tweet_alerts():
    today = datetime.now(localtz).strftime("%d %B %Y")
    conn = sqlite3.connect(alert_db)
    cur = conn.cursor()
    start = int(datetime.utcnow().strftime("%s")) - 3600 * 4
    end = int(datetime.utcnow().strftime("%s")) + 3600 * 16
    q = 'select * from alerts where time >= ? and time <= ? and summit like ?'
    cur.execute(q,(start,end,'JA%',))
    rows = cur.fetchall()

    if len(rows) == 0:
        tweet(tweet_api,"SOTAwatch alerts:\nNo activations are currently scheduled on " + today)
    elif len(rows) == 1:
        tweet(tweet_api,"SOTAwatch alerts:\nAn activation is currently scheduled on " + today)
    else:
        tweet(tweet_api,"SOTAwatch alerts:\n"+str(len(rows))+" activations are currently scheduled on " + today)
        
    for (tm,_,_,_,call,summit,info,freq,comment,poster) in rows:
        tm = datetime.fromtimestamp(int(tm)).strftime("%H:%M")
        mesg = tm + " " + call + " on\n" + summit + " " + freq + "\n" + info + "\n" + comment + " " + poster
        tweet(tweet_api,mesg)
    conn.close()

def get_new_msgno():
    global _thlock
    global _ackpool
    global _senderpool
    global _count

    _thlock.acquire()
    _count = _count - 1
    if _count == 99:
        _count = 999
    _senderpool.add(_count)
    _thlock.release()
    return _count

def ack_received(msgno):
    global _thlock
    global _ackpool
    global _senderpool
    global _count

    if debug:
        print _senderpool
        print _ackpool

    if msgno in _ackpool:
        _thlock.acquire()
        _ackpool.discard(msgno)
        _thlock.release()
        return True
    return False

def push_msgno(msgno):
    global _thlock
    global _ackpool
    global _senderpool
    global _count

    if msgno in _senderpool:
        _thlock.acquire()
        _ackpool.add(msgno)
        _thlock.release()
        return True
    return False

def discard_ack(msgno):
    global _thlock
    global _ackpool
    global _senderpool
    global _count

    _thlock.acquire()
    _ackpool.discard(msgno)
    _senderpool.discard(msgno)
    _thlock.release()
    
def aprs_worker():
    global aprs_beacon
    global _thlock
    global _ackpool
    global _senderpool
    global _count
    
    _thlock = Lock()
    _ackpool = {0}
    _senderpool = {0}
    _count = 999
    aprs_beacon = aprslib.IS(aprs_user, host=aprs_host,
                             passwd=aprs_password, port=aprs_port)
    aprs_beacon.connect(blocking=True)
    aprs_beacon.consumer(callback, immortal=True, raw=True)

def send_ack_worker(aprs, msgno):
    for i in range(2):
        if debug:
            print "SendingAck("+ str(i) + "):" + msgno
        else:
            aprs.sendall(msgno)
            sleep(30)
    
def send_ack(aprs, callfrom, msgno):
    ack = aprs_user+">APRS,TCPIP*::"+callfrom+":ack"+str(msgno)
    th = Thread(name="AckWoker",target=send_ack_worker,args =(aprs,ack))
    th.start()
    
def send_message(aprs, callfrom, message):
    header = aprs_user+">APRS,TCPIP*::"+callfrom+":"
    if len(message)>67:
        message = message[0:67]
    if debug:
        print "Sending: "+ header + message
    else:
        aprs.sendall(header+message)

def send_message_worker(aprs, callfrom, message):
    msgno = get_new_msgno()
    message = message + '{' + str(msgno)
    for i in range(10):
        if debug:
            print "Sending("+ str(i) + "):" + message
        else:
            aprs.sendall(message)
        sleep(30)
        if ack_received(msgno):
            break
    discard_ack(msgno)
        
def send_message_with_ack(aprs, callfrom, message):
    header = aprs_user+">APRS,TCPIP*::"+callfrom+":"
    if len(message)>67:
        message = message[0:67]
    if debug:
        print "Sending:" + header + message
    else:
        th = Thread(name="MessageWorker",target=send_message_worker,args=(aprs, callfrom, header+message))
        th.start()

def send_long_message_worker(aprs, callfrom, message):
    for m in message.splitlines():
        send_message_with_ack(aprs, callfrom, m)
        sleep(2)

def send_long_message_with_ack(aprs, callfrom, message):
    th = Thread(name="LongMessageWorker",target=send_long_message_worker,args=(aprs, callfrom, message))
    th.start()
    
def send_summit_message(callfrom, lat ,lng):
    state,mesg = lookup_summit(callfrom,lat,lng)
    if state == 3: # On Summit
        mesg = mesg + "\n" + readlast3(last3)
        send_long_message_with_ack(aprs_beacon,callfrom,mesg)
    elif state == 1:# Approaching Summit
        send_long_message_with_ack(aprs_beacon,callfrom,mesg)
    
def callback(packet):
    msg = aprslib.parse(packet)
    callfrom = msg['from'] + "      "
    callfrom = callfrom[0:9]
    if debug:
        print "Receive:"+callfrom+ ":"+msg['format']+"-"+msg['raw']
    if msg['format'] in  ['uncompressed','compressed','mic-e']:
        lat = msg['latitude']
        lng = msg['longitude']
        send_summit_message(callfrom, lat, lng)
    elif msg['format'] in ['message']:
        m = re.search('ack(\d+)',msg['raw'])
        if m:
            push_msgno(int(m.group(1)))
        else:
            m = re.search('{(\d+)',msg['raw'])
            if m:
                send_ack(aprs_beacon,callfrom,int(m.group(1)))

            if re.search('DX',msg['message_text'],re.IGNORECASE):
                res = readlast3(last3dx)
            elif re.search('LOC',msg['message_text'],re.IGNORECASE):
                res = lookup_from_op(callfrom)
            else:
                res = readlast3(last3)
            send_message_with_ack(aprs_beacon,callfrom,res)

def setup_db():
    conn_beacon = sqlite3.connect(beacon_db)
    cur_beacon = conn_beacon.cursor()

    q ='create table if not exists beacons (start int,end int,operator text,lastseen int,lat text,lng text,dist int,az int,level int,summit text,message text,type text)'
    cur_beacon.execute(q)
    q ='delete from beacons'
    cur_beacon.execute(q)
    conn_beacon.commit()

    update_alerts()
    
def main():
    global tweet_api
    
    aprs = Thread(target=aprs_worker, args=())
    aprs.start()

    setup_db()
        
    try:
        auth = tweepy.OAuthHandler(KEYS['Consumerkey'], KEYS['Consumersecret'])
        auth.set_access_token(KEYS['Accesstoken'], KEYS['Accesstokensecret'])
        tweet_api = tweepy.API(auth)
    except Exception, e:
        print >>sys.stderr, 'access error: %s' % e
        sys.exit(1)

    schedule.every(update_every).minutes.do(update_alerts)
    schedule.every().day.at(tweet_at).do(tweet_alerts)

    while True:
        schedule.run_pending()
        sleep(30)

if __name__ == '__main__':
  main()
