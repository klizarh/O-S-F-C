# Temperature chart with data from CouchDB
# Author: Howard Webb
# Date: 3/5/2018

import pygal
from couchdb import Server
import json
from datetime import datetime
from MVP_Util import UTCStrToLDT
<<<<<<< Updated upstream
=======
from LogUtil import get_logger

logger = get_logger('HumidityChart')
>>>>>>> Stashed changes

#Use a view in CouchDB to get the data
#use the first key for attribute type
#order descending so when limit the results will get the latest at the top

def getResults(test=False):
    '''Run a Mango query to get the data'''
    ts = datetime.utcnow().isoformat()[:19]
    payload={"selector":{"start_date.timestamp":{"$lt":ts}, "status.status_qualifier":"Success", "activity_type":"Environment_Observation", "subject.name":"Air","subject.attribute.name": "Humidity"}, "fields":["start_date.timestamp", "subject.attribute.value"], "sort":[{"start_date.timestamp":"desc"}], "limit":250}        
    db_name = 'mvp_data'
    if test:
        print payload
    server = Server()
    db = server[db_name]
    return db.find(payload)
    
def buildChart(data):
    '''Build the chard from array data'''
    v_lst=[]
    ts_lst=[]
    for row in data:
#        print row["start_date"]["timestamp"], row["subject"]["attribute"]["value"]
        v_lst.append(float(row["subject"]["attribute"]["value"]))
        ts_lst.append(UTCStrToLDT(row["start_date"]["timestamp"]))


    line_chart = pygal.Line()
    line_chart.title = 'Humidity'
    line_chart.y_title="Percent"
    line_chart.x_title="Timestamp (hover over to display date)"
    #need to reverse order to go from earliest to latest
    ts_lst.reverse()
    line_chart.x_labels = ts_lst
    #need to reverse order to go from earliest to latest
    v_lst.reverse()
    line_chart.add('Humidity', v_lst)
    line_chart.render_to_file('/home/pi/MVP/web/humidity_chart.svg')

def buildTempChart():
    data=getResults(True)
    r_cnt=len(data)    
    if r_cnt>0:
        msg = "{} {} {}".format(datetime.now(), "Records:", r_cnt)
        logger.debug(msg)
        buildChart(data)
    else:
        msg = "{} {} {}".format(datetime.now(), "No records selected:", data.reason)
        logger.warning(msg)

def test():
    data=getResults()
    r_cnt=len(data)    
    if r_cnt>0:
        msg = "{} {} {}".format(datetime.now(), "Records:", r_cnt)
        logger.debug(msg)
        buildChart(data)
    else:
        msg = "{} {} {}".format(datetime.now(), "No Data, Reason:", data.reason)
        logger.debug(msg)

if __name__=="__main__":
    buildTempChart()

