#!/usr/bin/env python3
# coding: utf-8
from datetime import datetime
import json
import os

if True or os.environ.get('MACKEREL_AGENT_PLUGIN_META','') == '1':
    print("# mackerel-agent-plugin")
    meta = {
        'graphs': {
            'sotawatchlive': {
                'Label': 'SOTAwatch Live!',
                'Unit' : 'integer',
                'Metrics': [
                    {
                        'Name':'sotawatch',
                        'Label':'SOTAwatch3 Status'
                    },
                    {
                        'Name':'alerts',
                        'Label':'Alerts'
                    },
                    {
                        'Name':'spots',
                        'Label':'Sposts'
                    },
                    {
                        'Name':'aprs',
                        'Label':'Beacon available'
                    },
                    {
                        'Name':'beacon',
                        'Label':'APRS packets'
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
        print("sotawatchlive.sotawatch\t{}\t{}".format(jd.get('SOTAWATCH',2),now))
        print("sotawatchlive.alerts\t{}\t{}".format(jd.get('ALERTS',0),now))
        print("sotawatchlive.spots\t{}\t{}".format(jd.get('SPOTS',0),now))
        print("sotawatchlive.aprs\t{}\t{}".format(jd.get('TRACKS',0),now))
        print("sotawatchlive.beacon\t{}\t{}".format(jd.get('PACKETS',0),now))

