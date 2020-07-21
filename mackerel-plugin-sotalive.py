#!/usr/bin/env python3
# coding: utf-8
from datetime import datetime
import json
import os

if os.environ.get('MACKEREL_AGENT_PLUGIN_META','') == '1':
    print("# mackerel-agent-plugin")
    meta = {
        'graphs': {
            'sotawatchlive': {
                'Label': 'SOTAwatch Live!',
                'Unit' : 'integer',
                'Metrics': [
                    {
                        'Name':'SOTAwatch3 Status',
                        'Label':'SOTAwatch3 Status'
                    },
                    {
                        'Name':'Alerts',
                        'Label':'Alerts'
                    },
                    {
                        'Name':'Spots',
                        'Label':'Sposts'
                    },
                    {
                        'Name':'APRS Stations',
                        'Label':'APRS Stations'
                    },
                    {
                        'Name':'APRS Packets',
                        'Label':'APRS Packets'
                    }
                ]
            }
        }
    }
    print(json.dumps(meta))
                    
else:
    with open("/var/tmp/sotalive-stat.json","r") as f:
        jd = json.load(f)
        now = datetime.utcnow().strftime("%s")
        print("sotawatchlive.SOTAwatch3_Status\t{}\t{}".format(jd.get('SOTAWATCH',2),now))
        print("sotawatchlive.Alerts\t{}\t{}".format(jd.get('ALERTS',0),now))
        print("sotawatchlive.Spots\t{}\t{}".format(jd.get('SPOTS',0),now))
        print("sotawatchlive.APRS_Stations\t{}\t{}".format(jd.get('TRACKS',0),now))
        print("sotawatchlive.APRS_packets\t{}\t{}".format(jd.get('PACKETS',0),now))

