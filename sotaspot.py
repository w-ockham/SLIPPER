#!/usr/bin/env python
import ConfigParser
import sys
import re
import time
from datetime import datetime
import tweepy 
import sqlite3
import urllib2
import random
from sotakeys import *   
from last3 import *

CONFIG='/home/ubuntu/pi/twitter/sota.cfg'
LASTSPOT='/home/ubuntu/pi/twitter/lastspot.txt'
LASTSPOTDX='/home/ubuntu/pi/twitter/lastspotdx.txt'
SPOTSDB='/home/ubuntu/pi/twitter/sotaspots.db'

def dbstore(db,code,lat,log,freq,text):
    now =int(time.mktime((datetime.now()).timetuple()))
    now_12= now - 3600*12
    cur = db.cursor()
    cur.execute("select * from sotaspots where dates>? AND summit_code = ?",(now_12,code))
    if len(cur.fetchall())==0:
        cur.execute("insert into sotaspots values(? ,? ,? ,? ,? ,? )",
                    (now,code,str(lat),str(log),freq,text))
        db.commit()
        return True
    return False
    
def main():
    try:
        config = ConfigParser.SafeConfigParser()
        config.read(CONFIG)
        since_id = config.getint('sotawatch','since_id')
    except Exception, e:
        print >>sys.stderr, 'Error: Could not read config file: %s' % e
        sys.exit(1)

    try:
        db = sqlite3.connect(SPOTSDB)
    except Exception, e:
        print >>sys.stderr, 'SPOTSDB error: %s' % e
        sys.exit(1)

    try:
        auth = tweepy.OAuthHandler(KEYS['Consumerkey'],KEYS['Consumersecret'])  
        auth.set_access_token(KEYS['Accesstoken'], KEYS['Accesstokensecret'])  
        api = tweepy.API(auth)  
        mentions = [
            x for x in \
            tweepy.Cursor(api.user_timeline,id='SOTAwatch', since_id = since_id).items()
        ]
    except Exception, e:
        print >>sys.stderr, 'access error: %s' % e
        sys.exit(1)

    try:
        for mention in reversed(mentions):
            text = mention.text.encode('utf-8')
            match = re.search(r'\son\s(\S+)\s\((.+?)\).*([\d|\.]+?)',text)
            if match :
                (code,summit,freq) = (match.group(1),match.group(2),
                                      match.group(3))
                if re.search(KEYS['Areas'],match.group(1)) :
                    prfx = ""
                    readlast3(LASTSPOT)
                    addnewstation(text)
                    writelast3(LASTSPOT)
                    if len(prfx+text) <=140:
                        api.update_status(status=prfx+text)
                        if mention.coordinates and mention.place:
                            [lo, la] = mention.coordinates['coordinates']
                            pl = mention.place.full_name
                            if dbstore(db,code,lo,la,freq,text):
                                g = str(la)+","+str(lo)
                                gmstr = KEYS['MapURL'].format(place=g,locate=g)
                                api.update_status(status=prfx+ summit
                                                  + " ("+ code +") "
                                                  + pl + " "+ gmstr)
                else :
                    readlast3(LASTSPOTDX)
                    addnewstation(text)
                    writelast3(LASTSPOTDX)
            since_id = mention.id
        db.close()
    except Exception, e:
        db.close()
        ty,obj,tb = sys.exc_info()
        print >>sys.stderr, 'Error: %s' % e
        print (ty, tb.tb_lineno)
        sys.exit(1)

    #sys.exit(0)
    try:
        config.set('sotawatch', 'since_id', str(since_id))
        config.write(open(CONFIG, 'w'))
    except Exception, e:
        print >>sys.stderr, 'Error: Could not write to config file: %s' % e
        sys.exit(1)

if __name__ == '__main__':
    main()
