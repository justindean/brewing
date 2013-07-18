import os
import time
from optparse import OptionParser
from subprocess import Popen, PIPE, call
import xively
import datetime
import RPi.GPIO as GPIO
import json
from time import sleep
import smtplib
import redis

#setup up 1-wire probes in linux (**validate this is still needed**)--prob do this in some kind of init/main script not the logger
os.system('modprobe w1-gpio')
os.system('modprobe w1-therm')

FEED_ID = "192066180"
API_KEY = "blah"
api = xively.XivelyAPIClient(API_KEY)
r=redis.StrictRedis(host='pub-redis-12700.eu-west-1-1.2.ec2.garantiadata.com', port=12700, db=0, password='blah')

parser = OptionParser()
parser.add_option("-r", "--recipe", type=str, default = 'recipe.json.rtb')
parser.add_option("--resume", type=str, default = 'NO')
parser.add_option("-p", "--prop", type=int, default = 6)
parser.add_option("-i", "--integral", type=int, default = 2)
parser.add_option("-b", "--bias", type=int, default = 22)
parser.add_option("-m", "--manual", type=str, default = 'NO')
parser.add_option("--mash_temp", type=int, default = 67)
parser.add_option("--mash_time", type=int, default = 60)
parser.add_option("--boil_time", type=int, default = 60)
parser.add_option("--strike_temp", type=int, default = 70)
parser.add_option("--boil_temp", type=int, default = (((212 - 32)*5) / 9) * 1000)
parser.add_option("--mashout_temp", type=int, default = (((168 - 32)*5) / 9) * 1000)
(options, args) = parser.parse_args()
P = options.prop
I = options.integral
B = options.bias
recipefile = options.recipe

#some vars for the control loop
interror=0
pwr_cnt=1
pwr_tot=0

#Parse recipe file and build global brew variables
f = open(recipefile, 'r')
data = f.read()
recipedata = json.loads(data)
MASH_TEMP = float(recipedata["RECIPES"]["RECIPE"]['MASH']['MASH_STEPS']['MASH_STEP']['STEP_TEMP']) * 1000
MASH_TIME = float(recipedata["RECIPES"]["RECIPE"]['MASH']['MASH_STEPS']['MASH_STEP']['STEP_TIME'])
STRIKE_TEMP = (((float(recipedata["RECIPES"]["RECIPE"]['MASH']['MASH_STEPS']['MASH_STEP']['INFUSE_TEMP'].strip(' F')) - 32) * 5) / 9) * 1000
STRIKE_VOLUME = float(recipedata["RECIPES"]["RECIPE"]['MASH']['MASH_STEPS']['MASH_STEP']['INFUSE_AMOUNT'])
BOIL_VOLUME = float(recipedata["RECIPES"]["RECIPE"]['EQUIPMENT']['BOIL_SIZE'])
BATCH_VOLUME = float(recipedata["RECIPES"]["RECIPE"]['EQUIPMENT']['BATCH_SIZE'])
BOIL_TIME = float(recipedata["RECIPES"]["RECIPE"]['EQUIPMENT']['BOIL_TIME'])
WHIRLFLOCK_TIME = BOIL_TIME - 10
MASH_OUT_TEMP = (((168 - 32)*5) / 9) * 1000
BOIL_TEMP = (((212 - 32)*5) / 9) * 1000
current_step_target = STRIKE_TEMP #change this for mash, mashout, boil
target_temp = int(current_step_target * 1000)

if (options.manual=='YES'):
    STRIKE_TEMP = options.strike_temp * 1000
    MASH_TEMP = options.mash_temp * 1000
    MASH_TIME = options.mash_time
    BOIL_TIME = options.boil_time
    BOIL_TEMP = options.boil_temp
    MASH_OUT_TEMP = options.mashout_temp

#function to initialize GPIO pin(s) for outbound 3.3v use
def Setup_GPIO():
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(12, GPIO.OUT)

#function to reset the GPIO pin(s) back to INPUT and turn them off. The gpio cleanup function is missing for some reason.
def Reset_GPIO():
    GPIO.output(12,0)
    GPIO.setup(12, GPIO.IN)

def turn_heat_on():
    GPIO.output(12,GPIO.HIGH)
    print "TURNING UP TH HEAT"

def turn_heat_off():
    GPIO.output(12,0)
    print "Turning the heat off!"

#fuction to get temperature data from 1-wire file the popen way
def temperature_data():
    pipe = Popen(["cat","/sys/bus/w1/devices/28-000005009b14/w1_slave"], stdout=PIPE)
    results = pipe.communicate()[0]
    print results
    result_list = results.split("=")
    print result_list
    temp_milliCelcius = int(result_list[-1])
    print temp_milliCelcius

#function to get temperature data from 1-wire file and convert to celcius
def get_temp_data_file():
    tempfile = open('/sys/bus/w1/devices/28-000005009b14/w1_slave', 'r')
    temprawdata = tempfile.read()
    tempfile.close()
    tempsplitdata = temprawdata.split("=")
    temp_milli_celcius = tempsplitdata[2]
    print tempsplitdata
    print temp_milli_celcius
    #temp_celcius = float(temp_milli_celcius) / 1000
    #print temp_celcius
    return temp_milli_celcius

#function to return a datastream object.  If one exists it returns it, if not, it creates it.
def get_datastream(feed):
    try:
        datastream = feed.datastreams.get("TemperatureSensor")
        return datastream
    except:
        datastream = feed.datastreams.create("TemperatureSensor", tags="temperature")
        return datastream


#function that updates xively feeds directly from reading file of temp probe
def update_graphs():
    feed = api.feeds.get(FEED_ID)
    datastream = get_datastream(feed)
    datastream.max_value = None
    datastream.min_value = None
    #while True:
    temp_milli_celcius = get_temp_data_file()
    temp_sensor_celcius = float(temp_milli_celcius) / 1000
    datastream.current_value = temp_sensor_celcius
    datastream.at = datetime.datetime.utcnow()
    print "graph while loop"
    try:
        datastream.update()
    except requests.HTTPError as e:
        print "HTTPError({0}): {1}]".format(e.errno, e.strerror)
    #time.sleep(10) #figure this out...cant have it sleep on logging part

#lighter version of the xively updater function that you feed the current temp 
def update_graphs_lite(current_temp):
     feed = api.feeds.get(FEED_ID)
     datastream = get_datastream(feed)
     datastream.max_value = None
     datastream.min_value = None
     temp_sensor_celcius = float(current_temp) / 1000
     datastream.current_value = temp_sensor_celcius
     datastream.at = datetime.datetime.utcnow()
     try:
         datastream.update()
     except requests.HTTPError as e:
         print "HTTPError({0}): {1}]".format(e.errno, e.strerror)

def Email_Status(MSG):
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login('@gmail.com', 'xxxxxx')
        server.sendmail('JD-BREWHOUSE', 'xxxxxxxx@vtext.com', MSG)
    except:
        print "Email Status Failed"

def Ramp_Up(target_temp):
    current_temp = int(get_temp_data_file())
    while (target_temp - current_temp > 6000):
        print "Ramping temperature up.  Current temp is %d and ramping to target of %d" % (current_temp/1000, target_temp/1000)
        update_graphs_lite(current_temp)
        turn_heat_on()
        sleep(10)
        current_temp = int(get_temp_data_file())
        print "Current temp is now %d" % current_temp
    print "Ramp up Complete"    

def Boil_Control(target_temp, current_step_time):
    current_temp = int(get_temp_data_file())
    stop_timer = time.time()+(current_step_time*60)
    while time.time() < stop_timer:
        print "BOILING - Current temp is %d, target temp is %d and time left on boil is %d seconds" % (current_temp/1000, target_temp/1000, (stop_timer - time.time()))
        update_graphs_lite(current_temp)
        turn_heat_on()
        sleep(10)
        current_temp = int(get_temp_data_file())
        print "Current temp is now %d" % current_temp
    print "Boil Complete"    


def PID_Control_Loop(target_temp, current_step_time):
    interror = 0
    heater_state = "off"
    print "Now entering PID Control Loop Function"   
    STEP_BREAKOUT = False
    if (current_step_time==0):
	    STEP_BREAKOUT = True
	    current_step_time = 180
    stop_timer = time.time()+(current_step_time*60)
    print target_temp, current_step_time
    while time.time() < stop_timer:
        current_temp = int(get_temp_data_file())
        update_graphs_lite(current_temp)
        print "You are in PID timer-while loop: Current Temp is %d and target temp is %d and step time left is %d seconds" % (current_temp/1000, target_temp/1000, (stop_timer - time.time()))
        print "stop timer is %d and time.time is %d" % (stop_timer, time.time())
        error = target_temp - current_temp
        interror = interror + error
        power = B + ((P * error) + ((I * interror)/100))/100
        print "power is %d" % power
        for x in range(1,10):
            print x
            if (power > x**2): #May need tuning, still overshoots by power of 30, holds steady after that though
                if (heater_state=="off"):
                    heater_state = "on"
                    print "State = ON"
                    turn_heat_on()
                else:
                    print "Leaving the Heat ON"
            else:
                if (heater_state=="on"):
                    heater_state="off"
                    print "State is OFF"
                    turn_heat_off()
            sleep(1)        
        if (power < 100):
            sleep(10)
        if (power <= 0) and (STEP_BREAKOUT==True):
            print "Target Temp has been hit; Breaking out of PID loop"
	    break


def Get_State(r):
    for step in sorted(state_order, key=lambda i: i[1]):
        complete_status = r.get(step[0]+'_complete')
        if (complete_status=='NO'):
            r.set(step[0]+'_state', 'ON')
            print step[0]
            return step[0]
            break
    else:
        return 'COMPLETE'


# initialize handler states for brewing process
state_handler = {
    'strike_ramp':Ramp_Up,
    'strike_step':PID_Control_Loop,
    'strike_hold':PID_Control_Loop,
    'mash_step':PID_Control_Loop,
    'mash_hold':PID_Control_Loop,
    'mashout_ramp':Ramp_Up,
    'mashout_hold':PID_Control_Loop,
    'boil_ramp':Ramp_Up,
    'boil_step':PID_Control_Loop,
    'boil_hold':PID_Control_Loop
    }

state_order = [
    ('strike_ramp',1),
    ('strike_step',2),
    ('strike_hold',3),
    ('mash_step',4),
    ('mash_hold',5),
    ('mashout_ramp',6),
    ('mashout_hold',7),
    ('boil_ramp',8),
    ('boil_step',9),
    ('boil_hold',10)
    ]


def Setup_Redis_States(r):
    for state in state_handler:
        try:
            r.set(state+'_timestamp', '')
            r.set(state+'_complete', 'NO')
            r.set(state+'_state', 'OFF')
        except:
            print "Error Setting up State_Handlers in Redis"

class BrewSession(object):
    def __init__(self):
        self.r = redis.StrictRedis(host='pub-redis-12700.eu-west-1-1.2.ec2.garantiadata.com', port=12700, db=0, password='blah') 
        self.state_handler = {    
            'strike_ramp':self.strike_ramp,
            'strike_step':self.strike_step,
            'strike_hold':self.strike_hold,
            'mash_step':self.mash_step,
            'mash_hold':self.mash_hold,
            'mashout_ramp':self.mashout_ramp,
            'mashout_hold':self.mashout_hold,
            'boil_ramp':self.boil_ramp,
            'boil_step':self.boil_step,
            'boil_hold':self.boil_hold
            }

    def strike_ramp(self):
        self.r.set(self.current_state+'_timestamp', time.time())
        Ramp_Up(STRIKE_TEMP)
        self.r.set(self.current_state+'_complete', 'YES')

    def strike_step(self):
        self.r.set(self.current_state+'_timestamp', time.time())
        state_handler[self.current_state](STRIKE_TEMP, 0)
        self.r.set(self.current_state+'_complete', 'YES')

    def strike_hold(self):
        self.r.set(self.current_state+'_timestamp', time.time())
        MSG = "Strike Temp Hit- Add Grains"
        Email_Status(MSG)
        state_handler[self.current_state](STRIKE_TEMP, 1)
    
    def mash_step(self):
        if (options.resume=='YES'):
            PREV_TIME_SPENT = float(time.time()) - float(r.get(self.current_state+'_timestamp'))
            print "Previous Time Spent: %d" % PREV_TIME_SPENT
            NEW_MASH_TIME = MASH_TIME - (PREV_TIME_SPENT/60)
            print 'mash time resumed', NEW_MASH_TIME
            state_handler[self.current_state](MASH_TEMP, NEW_MASH_TIME)
            RESUME = 'NO'
        else:
            self.r.set(self.current_state+'_timestamp', time.time())
            state_handler[self.current_state](MASH_TEMP, MASH_TIME)
            self.r.set(self.current_state+'_complete', 'YES')
    
    def mash_hold(self):
        MSG = "MASH Complete - Ready for Mashout?"
        Email_Status(MSG)
        state_handler[self.current_state](MASH_TEMP, 1)

    def mashout_ramp(self):
        state_handler[self.current_state](MASH_OUT_TEMP)
        self.r.set(self.current_state+'_complete', 'YES')

    def mashout_hold(self):
        MSG = "MASHOUT Complete - Remove the Grains"
        Email_Status(MSG)
        state_handler[self.current_state](MASH_OUT_TEMP, 1)

    def boil_ramp(self):
        state_handler[self.current_state](BOIL_TEMP+3000)
        self.r.set(self.current_state+'_complete', 'YES')

    def boil_step(self):
        if (options.resume=='YES') and (r.get(self.current_state+'_timestamp') != ''):
            PREV_TIME_SPENT = float(time.time()) - float(r.get(self.current_state+'_timestamp'))
            print "Previous Time Spent: %d" % PREV_TIME_SPENT
            NEW_BOIL_TIME = BOIL_TIME - (PREV_TIME_SPENT/60)
            print 'Boil time resumed', NEW_BOIL_TIME
            state_handler[self.current_state](BOIL_TEMP, NEW_BOIL_TIME)
            RESUME = 'NO'
        else:
            self.r.set(self.current_state+'_timestamp', time.time())
            state_handler[self.current_state](BOIL_TEMP, BOIL_TIME)
            self.r.set(self.current_state+'_complete', 'YES')

    def boil_hold(self):
        MSG = "BOIL Complete - Ready for Flameout?"
        Email_Status(MSG)
        state_handler[self.current_state](BOIL_TEMP, 1)

    def run(self):
        if (options.resume=='NO'):
            Setup_Redis_States(self.r)
        Setup_GPIO()
        while True:
            self.current_state = Get_State(self.r)
            self.state_handler[self.current_state]()


brewsession = BrewSession()
brewsession.run()


