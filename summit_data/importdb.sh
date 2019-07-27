#!/bin/bash
PATH=/usr/local/sbin:/usr/bin:/bin
rm tmp.csv tmpdb.db *-new
sed -e '1,1d' summitslist.csv > tmp.csv
sqlite3 tmpdb.db -separator , ".import tmp.csv allsummits"
sqlite3 tmpdb.db ".read continent.txt"
./make-summitlist.py
