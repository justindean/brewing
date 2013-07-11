import os
from time import sleep
from optparse import OptionParser
from subprocess import Popen, PIPE, call
import xively
import datetime
import RPi.GPIO as GPIO


#setup up 1-wire probes in linux (**validate this is still needed**)--prob do this in some kind of init/main script not the logger
os.system('modprobe w1-gpio')
os.system('modprobe w1-therm')

FEED_ID = "192066180"
API_KEY = "2pUA8p0bGmvdREAiK7hXIBp9SYpm8ZCDaS2wG0lBmc2uoaKl"

api = xively.XivelyAPIClient(API_KEY)

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

parser = OptionParser()
parser.add_option("-t", "--target", type=int, default = 55)
parser.add_option("-p", "--prop", type=int, default = 6)
parser.add_option("-i", "--integral", type=int, default = 2)
parser.add_option("-b", "--bias", type=int, default = 22)
(options, args) = parser.parse_args()
print "The Target Temp is %d" % (options.target)
P = options.prop
I = options.integral
B = options.bias
#some vars for the control loop
interror=0
pwr_cnt=1
pwr_tot=0

target_temp = int(options.target * 1000)

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

def Ramp_Up():
    current_temp = int(get_temp_data_file())
    while (target_temp - current_temp > 6000):
        print "Ramping temperature up.  Current temp is %d" % current_temp
        update_graphs_lite(current_temp)
        turn_heat_on()
        sleep(10)
        current_temp = int(get_temp_data_file())
        print "Current temp is now %d" % current_temp
    print "Ramp up Complete"    

def PID_Control_Loop():
    interror = 0
    heater_state = "off"
    print "Now entering PID Control Loop"   
    print "interror = %d" % interror
    while True:
        current_temp = int(get_temp_data_file())
        update_graphs_lite(current_temp)
        print "Current Temp is %d and target temp is %d" % (current_temp,target_temp)
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
                    print "leave on the heat"
            else:
                if (heater_state=="on"):
                    heater_state="off"
                    print "State is OFF"
                    turn_heat_off()
            sleep(1)        
        if (power < 100):
            sleep(10)

def main():
    Setup_GPIO()
    #update_graphs()
    Ramp_Up()
    PID_Control_Loop()

main()        




