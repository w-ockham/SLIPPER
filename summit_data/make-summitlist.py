#!/usr/bin/env python3
# coding: utf-8
import csv
from datetime import datetime, timedelta
import sqlite3
import sys
import re

def read_dict(file):
    with open(file, newline = "") as f:
        read_dict = csv.reader(f, delimiter=",", quotechar='"')
        return_dict = {}

        for row in read_dict:
            return_dict[row[0]] = row[2]

    return return_dict

def import_db(tmpdb, continent, assoc_db, summit_db):
    conn_tmp = sqlite3.connect(tmpdb)
    cur_tmp = conn_tmp.cursor()
    conn_summit = sqlite3.connect(summit_db)
    cur_summit = conn_summit.cursor()
    conn_assoc = sqlite3.connect(assoc_db)
    cur_assoc = conn_assoc.cursor()

    cur_summit.execute("CREATE TABLE IF NOT EXISTS summits (code txt,lat real,lng real,point integer,bonus integer,alt integer,name text,name_k text,region text,region_k text,assoc text,continent text,actcount integer,actdate text,actcall text)")
    cur_summit.execute("CREATE INDEX IF NOT EXISTS summit_index on summits(lat,lng)")
    cur_summit.execute("CREATE INDEX IF NOT EXISTS summit_code_idx on summits(code)")
    cur_summit.execute("delete from summits")
    conn_summit.commit()

    cur_assoc.execute("CREATE TABLE IF NOT EXISTS associations(code text,association text,continent text,primary key(code))")
    cur_assoc.execute("CREATE INDEX IF NOT EXISTS assoc_index on associations(code)")
    cur_assoc.execute("delete from associations")
    conn_assoc.commit()

    ctable = read_dict(continent)
    i = 0
    now = int(datetime.utcnow().strftime("%s"))
    for s in cur_tmp.execute("select * from allsummits"):
        (code,assoc,region,sname,altm,altf,gr1,gr2,lng,lat,pt,bp,validfrom,validto,actcount,actdate,actcall)= s
        valid = int(datetime.strptime(validto,'%d/%m/%Y').strftime("%s"))
        if now < valid:
            try:
                m = re.match('(\w+)/(\w+)',code)
                continent = ctable[m.group(1)]
                q = "insert or replace into summits(code,lat,lng,point,bonus,alt,name,name_k,region,region_k,assoc,continent,actcount,actdate,actcall) values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                cur_summit.execute(q,(code,lat,lng,pt,bp,altm,sname,sname,region,region,assoc,continent,actcount,actdate,actcall))
                q = "insert or replace into associations(code, association,continent) values(?, ?, ?)"
                cur_assoc.execute(q,(code,assoc,continent))
                i+=1
            except KeyError as e:
                print("Association: '"+m.group(1)+"' not found")

    print(str(i) + " summits has been imported.")

    i = 0
    for s in cur_tmp.execute("select * from ja_summits"):
        (code,lat,lng,_,_,name,region,name_k,region_k) = s
        q = "update summits set lat = ?, lng = ?, name = ?, name_k = ?, region = ?, region_k = ? where code = ?"
        cur_summit.execute(q,(lat,lng,name,name_k,region,region_k,code))
        i+=1
    print(str(i) + " summits has been updated for JA association.")

    conn_summit.commit()
    conn_summit.close()
    conn_assoc.commit()
    conn_assoc.close()
    
if __name__ == "__main__":
    if len(sys.argv) == 5:
        import_db(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        print("Usage make_summitlist temp_db contient.csv association_db summit_db")
        
