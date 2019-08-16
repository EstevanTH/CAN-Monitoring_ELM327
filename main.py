#!/usr/bin/python3

# Load parameters
from utility import execfileIfNeeded
from configselector import parametersFile
parameters = {}
parametersFileInfo = {}
execfileIfNeeded( parametersFile, parameters, parametersFileInfo )

# Initialize vehicle data with a multithread lock
from threading import Lock
vehicleData = ({},Lock())

# Run the CAN frame exporters
from CANToNetwork import CANToNetworkThread
canExporter = CANToNetworkThread()
canExporter.start()

# Run the ELM327 manager
from CANCaptureELM327 import CANCaptureELM327Thread
vehicleInterface = CANCaptureELM327Thread( vehicleData )
vehicleInterface.attachCanExporter( canExporter )
vehicleInterface.start()

# Run the HTTP server
from CANCaptureHTTPServer import CANCaptureHTTPServerThread
httpServers = []
for httpBinding in parameters["httpBindings"]:
	httpd = CANCaptureHTTPServerThread( vehicleData, vehicleInterface, ipAddress=httpBinding["address"], tcpPort=httpBinding["port"] )
	httpServers.append( httpd )
	httpd.start()
del httpd

# Reload the parameters
from utility import printT
def reloadParameters():
	if execfileIfNeeded( parametersFile, parameters, parametersFileInfo ):
		for httpBinding in parameters["httpBindings"]:
			for httpd in httpServers:
				httpdParameters = httpd.getParameters()
				# Reload HTTP parameters for the HTTP server matching address & port:
				if httpBinding["address"]==httpdParameters["ipAddress"] and httpBinding["port"]==httpdParameters["tcpPort"]:
					break
		printT( "[main.py] Parameters have been reloaded." )

# Main work in an endless loop
try:
	from time import sleep
	while True:
		sleep( 3 )
		reloadParameters()
except KeyboardInterrupt:
	printT( "Exiting..." )
	canExporter.terminate()
except BaseException as e:
	printT( e )
