brewing
=======

The goal of this project is to marry the Devops philosophies, culture and practices with the art of brewing beer in order to brew a better beer.  We all really like beer and would love our finished product to be much more reliable and consistent.

Leveraging low cost hardware and open source software combined with our unique abilities as a group hopefully we can join together to create a better beer using the Devops "CAMS' principals:  Culture, Automation, Metrics, Sharing.

The overall idea for the brewhouse automation system thus far is:

- Smaller, more manageable batches that can be brewed AT WORK, in the office!!  ~3 gallon
- Single Vessel, BIAB (Brew in a Bag), Electric Element driven system
- 120v standard 20amp circuit capable
- Raspberry Pi based control
- Internet/Network Enabled for both access, control and logging/trending
- etc, etc, etc

current state
=======

The current version of jd-brewhouse.py is functional during the brewday phase.
Program Flow:

1. We build our recipe in your recipe buiding software of choice that can export in BeerXML format.
2. Save your recipe.xml file into github /recipes
3. Post processing script 'recipe_file_cleanup.py' is used to cleanup the file as it has a lot of nonsense (\n, \r, etc) that don't convert well into json.  Converts the file to json.
4. Rpi uses json.rtb (ready to brew) file as its input to populate all the brewday variables (steps, temps, timings, hops, additions, etc, etc).
5. Rpi has a 1-wire thermocouple attached which is inside the thermowell of the boil kettle.  Used for temp measurements throughout the process.
6. Rpi controls a 40amp SSR via GPIO output at 3.3v to switch on main power to an outlet which the boil kettle element is plugged into.
7. Rpi runs PID type control loop to ramp and maintain proper temperatures for each step without overshoot (i.e. sents power to GPIO when heat is low to fire up the boil kettle heating element).
8. Realtime logging/graphing is handled by sending data to cloud service: xively
9. Brew state info is held outside of RPi in cloud based Redis service.  This allows recovery/resume function without losing place if the script breaks or RPi dies during the brew session.
10. RPi sends SMS text message when its ready for brewer to do something manual (i.e. add grains, remove grains, etc)


There are a ton more things to do:  Recipe testing, Recipe suggestions based on predictec weather, all the fermentation process automation/tracking/alerting, web frontend, cleanup of current brew script, automation of water addition to the kettle, servo driven arms for grain/hop addition, automating stirring, etc, etc
