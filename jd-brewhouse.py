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
API_KEY = "2pUA8p0bGmvdREAiK7hXIBp9SYpm8ZCDaS2wG0lBmc2uoaKl"
api = xively.XivelyAPIClient(API_KEY)
r=redis.StrictRedis(host='pub-redis-12700.eu-west-1-1.2.ec2.garantiadata.com', port=12700, db=0, password='brewhouse')

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


def Get_State():
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


def Setup_Redis_States():
    for state in state_handler:
        try:
            r.set(state+'_timestamp', '')
            r.set(state+'_complete', 'NO')
            r.set(state+'_state', 'OFF')
        except:
            print "Error Setting up State_Handlers in Redis"


def newmain():
    if (options.resume=='NO'):
        Setup_Redis_States()	
    Setup_GPIO()
    BOIL_TEMP = 20000
    BOIL_TIME = 1
    MASH_OUT_TEMP = 20000
    while True:
        current_state = Get_State()
        print "current state = %s" % current_state
        if (current_state=="strike_ramp"):
            r.set(current_state+'_timestamp', time.time())
            state_handler[current_state](STRIKE_TEMP)
            r.set(current_state+'_complete', 'YES')
        if (current_state=="strike_step"):
            r.set(current_state+'_timestamp', time.time())
            state_handler[current_state](STRIKE_TEMP, 0)
            r.set(current_state+'_complete', 'YES')
        if (current_state=="strike_hold"):
            r.set(current_state+'_timestamp', time.time())
            MSG = "Strike Temp Hit- Add Grains"
            Email_Status(MSG)
            state_handler[current_state](STRIKE_TEMP, 1)
            #r.set(current_state+'_complete', 'YES')
        if (current_state=="mash_step"):
            if (options.resume=='YES'):
                PREV_TIME_SPENT = float(time.time()) - float(r.get(current_state+'_timestamp'))
                print "Previous Time Spent: %d" % PREV_TIME_SPENT
                NEW_MASH_TIME = MASH_TIME - (PREV_TIME_SPENT/60)
                print 'mash time resumed', NEW_MASH_TIME
                state_handler[current_state](MASH_TEMP, NEW_MASH_TIME)
                RESUME = 'NO'
            else:
                r.set(current_state+'_timestamp', time.time())
                state_handler[current_state](MASH_TEMP, MASH_TIME)
            r.set(current_state+'_complete', 'YES')
        if (current_state=="mash_hold"):
            MSG = "MASH Complete - Ready for Mashout?"
            Email_Status(MSG)
            state_handler[current_state](MASH_TEMP, 1)
        if (current_state=="mashout_ramp"):
            state_handler[current_state](MASH_OUT_TEMP)
            r.set(current_state+'_complete', 'YES')
        if (current_state=="mashout_hold"):
            MSG = "MASHOUT Complete - Remove the Grains"
            Email_Status(MSG)
            state_handler[current_state](MASH_OUT_TEMP, 1)
        if (current_state=="boil_ramp"):
            state_handler[current_state](BOIL_TEMP+3000)
            r.set(current_state+'_complete', 'YES')
        if (current_state=="boil_step"):
            if (options.resume=='YES') and (r.get(current_state+'_timestamp') != ''):
                PREV_TIME_SPENT = float(time.time()) - float(r.get(current_state+'_timestamp'))
                print "Previous Time Spent: %d" % PREV_TIME_SPENT
                NEW_BOIL_TIME = BOIL_TIME - (PREV_TIME_SPENT/60)
                print 'Boil time resumed', NEW_BOIL_TIME
                state_handler[current_state](BOIL_TEMP, NEW_BOIL_TIME)
                RESUME = 'NO'
            else:
                r.set(current_state+'_timestamp', time.time())
                state_handler[current_state](BOIL_TEMP, BOIL_TIME)
            r.set(current_state+'_complete', 'YES')
        if (current_state=="boil_hold"):
            MSG = "BOIL Complete - Ready for Flameout?"
            Email_Status(MSG)
            state_handler[current_state](BOIL_TEMP, 1)

newmain()
# File based approach prior to using Key Value (Redis) and keeping Brew States
# Possible variation of this method for non-internet connected brew day

#def OLDmain():
#    Setup_GPIO()
#    #update_graphs()
#    MASH_OUT = 'HOLD'
#    GRAIN_OUT = 'HOLD'
#    FLAME_OUT = 'HOLD'
#    grainfile = open('grainfile.txt', 'w')
#    mashfile = open('mashfile.txt', 'w')
#    grainoutfile = open('grainoutfile.txt', 'w')
#    flameoutfile = open('flameoutfile.txt', 'w')
#    grainfile.write(GRAIN_IN)
#    mashfile.write(MASH_OUT)
#    grainoutfile.write(GRAIN_OUT)
#    flameoutfile.write(FLAME_OUT)
#    grainfile.close()
#    mashfile.close()
#    grainoutfile.close()
#    flameoutfile.close()
#    MSG = "Starting Strike Temp Ramp"
#    Email_Status(MSG)
#    Ramp_Up(STRIKE_TEMP)
#    print "Starting the Strike Temp PID Loop to %d C" % STRIKE_TEMP
#    #Starting Strike Water
#    PID_Control_Loop(STRIKE_TEMP, 0)
#    while (GRAIN_IN=='HOLD'):
#        PID_Control_Loop(STRIKE_TEMP, 1)
#        print "waiting for you to update grainfile step"
#	MSG = "Strike Temp Hit- Update grainfile" 
#	Email_Status(MSG)
#	print GRAIN_IN
#	grainfile = open('grainfile.txt', 'r')
#	GRAIN_IN = grainfile.read().strip('\n')
#	grainfile.close()
#	print GRAIN_IN
#   print "Moving from Strike step to Mash Step"
#    #Starting Mash
#    PID_Control_Loop(MASH_TEMP, MASH_TIME)
#    while (MASH_OUT=='HOLD'):
#        PID_Control_Loop(MASH_TEMP, 1)
#        print "Hanging in mashout hold mode - waiting for you to update mashfile step"
 #       MSG = "Time to Start Mashout - Update mashfile"
 #       Email_Status(MSG)
#	print MASH_OUT
#	mashfile = open('mashfile.txt', 'r')
#	MASH_OUT = mashfile.read().strip('\n')
#	mashfile.close()
#	print MASH_OUT
#   print "Starting MASHOUT RAMP-UP Step"	
#    #Starting Mashout
#    Ramp_Up(MASH_OUT_TEMP)
#    print "Starting MASHOUT PID LOOP"
#    PID_Control_Loop(MASH_OUT_TEMP, 0)
#    while (GRAIN_OUT=='HOLD'):
#        PID_Control_Loop(MASH_OUT_TEMP, 1)
#        print "Hanging in mashout hold mode - waiting for you to update grainoutfile step"
#        MSG = "MASHOUT Temp Hit: Pull Grain and Update grainoutfile" 
#        Email_Status(MSG)
#	print GRAIN_OUT
#	grainoutfile = open('grainoutfile.txt', 'r')
#	GRAIN_OUT = grainoutfile.read().strip('\n')
#	grainoutfile.close()
#	print GRAIN_OUT
 #   print "Ramping Boil"
 #   Ramp_Up(BOIL_TEMP + 3000)
#    print "Done ramping Boil starting PID_BOIL LOOP"
#    MSG = "Done ramping Boil - Get ready to boil!"
#    Email_Status(MSG)
#    while (FLAME_OUT=='HOLD'):
#        Boil_Control(BOIL_TEMP, 1)
#        print "Hanging in BOIL mode - waiting for you to update BOILfile step if you think its actually done and ready for flameout"
#        MSG = "Boil is Complete- Update flameoutfile"
#        Email_Status(MSG)
#	print FLAME_OUT
#	flameoutfile = open('flameoutfile.txt', 'r')
#	FLAME_OUT = flameoutfile.read().strip('\n')
#	flameoutfile.close()
#	print FLAME_OUT
 #   turn_heat_off()
 #   print "the HEAT IS OFF!!!"
