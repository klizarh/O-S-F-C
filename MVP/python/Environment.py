# Build dictionary structure variables for the environment
# A python file is generated that is 'read' by the logging program.
# Author: Howard Webb
# Data: 2/21/2018

import os
import uuid
import json

# Resolve the MVP python directory for writing env.py.
# Prefer MVP_DIR env var; fall back to /home/pi/MVP for Pi compatibility.
_MVP_DIR = os.environ.get('MVP_DIR', '/home/pi/MVP')
_ENV_FILE = os.path.join(_MVP_DIR, 'python', 'env.py')

def setup():
    '''One time setup of the environment - get UUID of Field"'''
    env={}
    env['field']=getField()
    env['thermostat'] = setTargetTemperature()
    env['lights'] = setLights()
    saveDict('env', _ENV_FILE, env)

def getField():
    '''Create Field UUID and Plots'''
    field={}
    field['field_id']=str(uuid.uuid4())
    return field

def setTargetTemperature(targetTemp=25):
    '''
       targetTemp is the desired temperature (may be the average for the day)
       setPoint is the temperature the thermostat reacts to
    '''        
    return {'targetTemp':targetTemp}

def setLights(on='06:30:00', off='22:00:00'):
	lights = {'On':on, 'Off': off}
	return lights

def prettyPrint(txt):
    '''Dump json in nice format'''
    #print type(txt)
    print(json.dumps(txt, indent=4, sort_keys=True))

def saveDict(name, file_name, dict):
    #print(values)
    f = open(file_name, 'w+')
    tmp=name+'='+str(dict)
    f.write(tmp)
    f.close()    
    
def test():
    setup()
    from env import env
    prettyPrint(env)

if __name__=="__main__":
    test()
    
