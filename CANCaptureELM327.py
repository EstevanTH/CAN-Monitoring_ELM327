# Règle de conception : toujours attendre l'invite avant de redonner la main, sauf en cas d'exception.
# Règle de conception : une erreur de communication (sauf expiration) doit toujours engendrer une exception qui entraînera une nouvelle communication.
# Note: the ELM327 documentation informs that parasitic 0x00 bytes may occasionally be seen on the serial port. They are not ignored as recommended.
# Note: if at some point ATMA cannot be stopped by sending a character then the program may become stuck.

# TODO: if the wrong serial rate is set after a restart of the main loop but a prompt seems to be received, the program may be stuck forever. Better rate choice??



DEBUG_DISCONNECTED_SCANNER = False # dev (emulates process with no scanner)
DEBUG_DISCONNECTED_CAN_BUS = False # dev (ELM327 dialog only)

import threading
import serial
import re

from datetime import datetime
from time import sleep
from time import time
from time import perf_counter
from traceback import format_exc
from sys import exc_info
from threading import Lock
from CANCaptureFrameHandler import CANCaptureFrameHandler

from utility import execfile
from utility import execfileIfNeeded
from utility import printT
from utility import setConsoleColorWindows
from utility import setConsoleTitle
from utility import bytes_hex

from configselector import parametersFile
from configselector import sequenceFile

MAX_OBD_NEGOCIATION_TIME = 60

class CANFrame( tuple ):
	"""
	Represents a valid CAN frame
	The type and its components should be immutable (thread-safety).
	"""
	identifier = property( lambda self: self[0] )
	isExtended = property( lambda self: self[1] )
	isRTR = property( lambda self: self[2] )
	DLC = property( lambda self: self[3] )
	data = property( lambda self: self[4] )
	time = property( lambda self: self._time )
	def __new__( cls, identifier, isExtended, isRTR, DLC, data ):
		obj = super().__new__( cls, (
			int( identifier ),
			bool( isExtended ),
			bool( isRTR ),
			int( DLC ),
			bytes( data ), # immutable conversion
		) )
		obj._time = time()
		return obj
	def __str__( self ):
		info = (self.identifier, self.isRTR, self.DLC, bytes_hex( self.data ))
		if self.isExtended:
			return "CANFrame(identifier=0x%.8X <29-bit>, isRTR=%u, DLC=%u, data=%s)"%info
		else:
			return "CANFrame(identifier=0x%.3X <11-bit>, isRTR=%u, DLC=%u, data=%s)"%info

class CANCaptureELM327Thread( threading.Thread ):
	daemon = True # exit immediatly on program exit
	
	def __init__( self, vehicleData ):
		threading.Thread.__init__( self )
		self.readBuffer = bytearray()
		self.parametersFileInfo = {}
		self.sequenceFileInfo = {}
		self.pidResponseCallbacks = {}
		self.lastResponseDatas = {}
		self.ser = None
		self.sequence = []
		self.filter1RemoteLock = Lock()
		self.frameHandler = CANCaptureFrameHandler( self )
		try:
			self.frameHandler.start()
		except RuntimeError:
			pass
	
	canExporter = None
	def attachCanExporter( self, canExporter ):
		self.canExporter = canExporter
	
	def reloadParameters( self ):
		parameters = {}
		if execfileIfNeeded( parametersFile, parameters, self.parametersFileInfo ):
			### Serial port ###
			self.serialPort = parameters["serialPort"]
			self.serialBaudRateInitial = parameters["serialBaudRateInitial"]
			self.serialBaudRateDesired = parameters["serialBaudRateDesired"]
			self.serialBaudRateDesiredForce = parameters["serialBaudRateDesiredForce"]
			self.serialLocalBufferEnabled = parameters["serialLocalBufferEnabled"]
			if self.serialLocalBufferEnabled:
				self.serialLocalBufferAccuATMA = parameters["serialLocalBufferAccuATMA"]
				self.serialLocalBufferMinFillATMA = parameters["serialLocalBufferMinFillATMA"]
				self.serialLocalBufferWaitTimeATMA = parameters["serialLocalBufferWaitTimeATMA"]
			else:
				self.serialLocalBufferAccuATMA = None
				self.serialLocalBufferMinFillATMA = None
				self.serialLocalBufferWaitTimeATMA = None
			self.serialShowSentBytes = parameters["serialShowSentBytes"]
			self.serialShowReceivedBytes = parameters["serialShowReceivedBytes"]
			
			### CAN bus ###
			self.testObdCompliant = parameters["canBusTestObdCompliant"]
			self.scannerATSP = parameters["ATSP"]
			#self.obdShowIncorrectResult = parameters["obdShowIncorrectResult"]
			scannerATBRD = round( 4000000/self.serialBaudRateDesired )
			if scannerATBRD>0xFF:
				printT( "The parameter serialBaudRateDesired is set to an insufficient value!" )
			self.scannerATBRD = b"ATBRD"+bytes( "%.2X"%round( 4000000/self.serialBaudRateDesired ), "ascii" )+b"\x0D" # desired baudrate
			if self.canExporter is not None:
				self.canExporter.setParameters( parameters )
			self.allowMixedIdentifiers = parameters["canBusAllowMixedIdentifiers"]
			self.inactivityTimeout = parameters["canBusInactivityTimeout"]
			if DEBUG_DISCONNECTED_CAN_BUS:
				self.inactivityTimeout = 20.
			self.stopMonitoringWait = parameters["canBusStopMonitoringWait"]
			self.stopMonitoringMaxAttempts = parameters["canBusStopMonitoringMaxAttempts"]
			self.maxStraightInvalidFrames = parameters["canBusMaxStraightInvalidFrames"]
			self.maskOver = parameters["canBusMaskOver"]
			if self.maskOver is None:
				self.maskOver = 0x1FFFFFFF
			# USER1 CAN bus specification:
			scannerATPB = 0
			if parameters["ATPB_11bit"]:
				scannerATPB |= 0b1000000000000000
			if parameters["ATPB_variableDataLength"]:
				scannerATPB |= 0b0100000000000000
			if self.allowMixedIdentifiers:
				scannerATPB |= 0b0010000000000000
			ATPB_dataFormat = parameters["ATPB_dataFormat"]
			if ATPB_dataFormat==None:
				pass
			elif ATPB_dataFormat=="ISO 15765-4":
				scannerATPB |= 0b0000000100000000
			elif ATPB_dataFormat=="SAE J1939":
				scannerATPB |= 0b0000001000000000
			else:
				raise NotImplementedError( 'Unknown CAN data format "%s"'%(ATPB_dataFormat,) )
			scannerATPB |= self.selectATPB_rate( parameters["ATPB_rate"] )
			self.scannerATPB = ( "%.4X"%(scannerATPB,) ).encode( "ascii" )
			
			printT( "[CANCaptureELM327.py] Parameters have been reloaded." )
	
	def reloadSequence( self ):
		if execfileIfNeeded( sequenceFile, {"canBus":self}, self.sequenceFileInfo ):
			printT( "The CAN sequence has been reloaded." )
	
	## Filters
	
	filter1RemoteChanged = True
	filter1RemoteMask = 0x00000000
	filter1RemoteResult = 0x00000000
	def setFilter1Remote( self, mask, maskingResult ):
		""" Set new filter mask to be used ELM327-side & computer-side """
		with self.filter1RemoteLock:
			self.filter1RemoteChanged = True
			self.filter1RemoteMask = mask or 0x00000000
			self.filter1RemoteResult = maskingResult or 0x00000000
	
	def getFilter1Remote( self ):
		""" Get filter mask used ELM327-side & computer-side """
		with self.filter1RemoteLock:
			return (self.filter1RemoteMask, self.filter1RemoteResult)
	
	filter1Whitelist = None # please copy locally; type: set / NoneType
	def setFilter1Local( self, whitelist ):
		""" Set new filter whitelist to be used computer-side """
		# No lock required (filter1Whitelist never modified)
		if whitelist is not None:
			self.filter1Whitelist = set( whitelist )
		else:
			self.filter1Whitelist = None
	
	def getFilter1Local( self ):
		""" Get filter whitelist used computer-side """
		try:
			return set( self.filter1Whitelist )
		except TypeError:
			return None
	
	def setFilter1( self, whitelist ):
		""" Set new filter whitelist to be used both computer-side and ELM327-side """
		if whitelist is not None:
			op1 = 0x1FFFFFFF
			op2 = 0x1FFFFFFF
			op3 = 0x00000000
			for identifier in whitelist:
				op1 &= identifier
				op2 &= ~identifier
				op3 |= identifier
			mask = ( op1|op2 )&0x1FFFFFFF
			result = op3&mask
		else:
			mask = 0x00000000
			result = 0x00000000
		self.setFilter1Remote( mask, result )
		self.setFilter1Local( whitelist )
	
	filter2Blacklist = None # please copy locally; type: set / NoneType
	def setFilter2( self, blacklist ):
		""" Set new filter blacklist to be used computer-side """
		# No lock required (filter2Blacklist never modified)
		if blacklist is not None:
			self.filter2Blacklist = set( blacklist )
		else:
			self.filter2Blacklist = None
	
	def getFilter2( self ):
		""" Get filter blacklist used computer-side """
		try:
			return set( self.filter2Blacklist )
		except TypeError:
			return None
	
	def passesFilters( self, frame ):
		""" Indicates if a frame passes the filters in place
		This method must be thread-safe!
		"""
		identifier = frame.identifier
		
		with self.filter1RemoteLock:
			filter1RemoteMask = self.filter1RemoteMask
			filter1RemoteResult = self.filter1RemoteResult
		if ( identifier&filter1RemoteMask )!=filter1RemoteResult:
			return False
		
		filter1Whitelist = self.filter1Whitelist
		if ( filter1Whitelist is not None ) and ( identifier not in filter1Whitelist ):
			return False
		
		filter2Blacklist = self.filter2Blacklist
		if ( filter2Blacklist is not None ) and ( identifier in filter2Blacklist ):
			return False
		
		return True
	
	## END Filters
	
	def write( self, data ):
		if self.serialShowSentBytes:
			printT( "    PC :", data.decode( "ascii", "replace" ) )
		return self.ser.write( data )
	def read( self, *, minReadCount=1, retryDelayIfEmpty=None ):
		"""
		Read 1 byte from the input buffer
		Reduced number of I/O operations (CPU optimization)
		- minReadCount: wait for this number of bytes or a timeout (not a length guarantee)
		- retryDelayIfEmpty: effective timeout (in seconds) when the timeout of the I/O operation is short (low delay)
		"""
		if self.serialLocalBufferEnabled:
			'''
			Optimiser encore : en cas de gros débit, c'est le manque de puissance CPU qui fera que le buffet de réception n'est pas vide, donc on ne résout pas l'utilisation CPU excessive ; on évite seulement les pertes de données.
			Il faut par exemple ajouter un temps d'attente paramétré si self.ser.in_waiting < minReadCount (très court, de valeur éventuellement calculée par rapport au débit => durée d'envoi d'octets).
			Attention, le code qui suit la lecture est lui aussi intensif, puisqu'il n'y avait plus d'erreurs de décodage quand la trame est mise à False.
			'''
			if not self.readBuffer:
				# The buffer is empty, fetching new bytes.
				# The awaiting bytes count is not unlimited so there should be no excessive memory usage.
				if retryDelayIfEmpty is not None:
					readStartedAt = perf_counter()
				while True:
					newBytes = self.ser.read( max( minReadCount, self.ser.in_waiting ) )
					if newBytes:
						# bytes received: append new bytes
						self.readBuffer.extend( newBytes )
						break
					elif retryDelayIfEmpty is None \
					  or ( perf_counter()-readStartedAt )>retryDelayIfEmpty:
						# nothing received
						break
			if self.readBuffer:
				# The buffer contains something, taking out the first byte.
				result = bytes( [self.readBuffer.pop( 0 )] )
			else:
				# The buffer contains nothing.
				result = b""
		else:
			result = self.ser.read()
		if self.serialShowReceivedBytes:
			if len( result )!=0:
				printT( "ELM327 :", result.decode( "ascii", "replace" ) )
			else:
				printT( "ELM327 : <timeout>" )
		return result
	def flushInput( self, bytesToRead=255 ):
		self.readBuffer.clear()
		self.ser.reset_input_buffer()
		self.ser.read( bytesToRead )
	
	# Reading of bytes until getting the prompt '>'; nothing must arrive after it.
	# Returns True if the prompt has been found.
	def waitForPrompt( self, errorMessageOnFailure=None, maxBytesToRead=32, noSilentTest=False ):
		# An exception is thrown only when exceerrorMessageOnFailure is defined (character string).
		failure = False
		for numByte in range( maxBytesToRead ):
			newByte = self.read()
			if len( newByte )==0: # no prompt (timeout)
				failure = True
				break
			elif newByte==b'>':
				break
		self.ser.timeout = 0.5
		if not failure and ( noSilentTest or len( self.read() )==0 ):
			return True
		elif errorMessageOnFailure is None:
			return False
		else:
			raise Exception( errorMessageOnFailure )
	
	# Reading of an answer until getting the prompt '>' (returns immediately after that)
	# Returns the last non-empty line if the prompt is found, or False on timeout or if too many received bytes
	# There is a restart after a given number of failures.
	def readAnwer( self, errorMessageOnFailure=None, maxBytesToRead=64 ):
		lines = []
		# Reading of incoming lines
		currentLine = bytearray()
		for numByte in range( maxBytesToRead ):
			newByte = self.read()
			if len( newByte )==0:
				return False # no prompt (failure)
			newByteInt = newByte[0]
			if newByte==b'\x0D' or newByte==b'>':
				lines.append( currentLine.decode( "ascii", "replace" ) )
				currentLine = bytearray()
				if newByte==b'>':
					break
			elif newByteInt>0x00 and newByteInt<0x80:
				currentLine.extend( newByte )
		else: # exceeded max length
			self.flushInput( 255 ) # flush with delay
			return False
		# Selection of the last non-empty line (considering length > 1)
		for i in range( len( lines )-1, -1, -1 ):
			line = lines[i]
			if len( line )>1:
				return line
		return lines[len( lines )-1]
	
	def stopMonitoring( self, stopMonitoringReason ):
		""" Interrupts ATMA and displays the reason """
		if self.stopMonitoringAttempts>self.stopMonitoringMaxAttempts:
			raise ConnectionError( "Failed %u times to interrupt ATMA"%(self.stopMonitoringAttempts,) )
		self.write( b"\x0D" )
		self.stopMonitoringAttempts += 1
		if stopMonitoringReason:
			printT( "Interrupted monitoring: "+stopMonitoringReason )
	
	canFrameRegex11 = re.compile( b"^([0-7][0-9A-F]{2})([0-9A-F])(?:(RTR)|([0-9A-F]*))", re.IGNORECASE )
	canFrameRegex29 = re.compile( b"^([0-1][0-9A-F]{7})([0-9A-F])(?:(RTR)|([0-9A-F]*))", re.IGNORECASE )
	
	straightInvalidFramesCount = 0
	def readFrame( self, maxBytesPerLine=128 ):
		"""
		Read a line that should contain a frame (during ATMA operation)
		Return a CANFrame on success
		Return False if invalid frame
		Return None if nothing read
		Throws a MemoryError if received "BUFFER FULL"
		Throws a InterruptedError if received "STOPPED"
		Throws a ConnectionAbortedError if prompt received in other cases
		Throws a ValueError if invalid bytes received
		Throws a ChildProcessError if unexpected reboot
		Bug: When ATMA is interrupted, frames can be truncated but still seem valid (especially 29-bit-identifier frames decoded as 11-bit ones).
		"""
		canFrame = None
		# Read an incoming line
		if self.serialLocalBufferAccuATMA:
			# short I/O timeout (several attempts until effective timeout)
			self.ser.timeout = self.serialLocalBufferWaitTimeATMA
		else:
			# I/O timeout = effective timeout
			self.ser.timeout = self.inactivityTimeout
		currentLine = bytearray()
		timedOutEmpty = False
		try:
			for numByte in range( maxBytesPerLine ):
				if self.serialLocalBufferAccuATMA:
					newByte = self.read( minReadCount=self.serialLocalBufferMinFillATMA, retryDelayIfEmpty=self.inactivityTimeout )
				else:
					newByte = self.read()
				if len( newByte )==0:
					if len( currentLine )==0:
						timedOutEmpty = True
					#printT( "readFrame() - len( newByte )==0" ) # debug
					break
				newByteInt = newByte[0]
				if newByte==b'\x0D':
					break # end of line
				elif newByte==b'>':
					raise ConnectionAbortedError( "ELM327: Unexpected prompt during ATMA reading" )
				elif newByte==b'\x00' or newByte==b' ':
					pass # ignore spaces and nulls
				elif newByteInt>0x00 and newByteInt<0x80:
					currentLine.extend( newByte )
				else:
					raise ValueError( "ELM327: Received an illegal byte during ATMA processing!" )
			else: # exceeded max length
				raise ValueError( "ELM327: Received too many bytes in a single line during ATMA processing!" )
			# Decode the line
			if not timedOutEmpty:
				# Note: spaces are removed, messages are spaceless.
				# Note: receiving a 29-bit frame on an 11-bit CAN bus & vice-versa are not documented but seem to be accepted, so they are handled as they come.
				if len( currentLine )==0:
					canFrame = False # nothing on the line (like corrupted frame)
					printT( "ELM327: Received an empty ATMA line" )
				elif b"ELM327" in currentLine:
					raise ChildProcessError( "ELM327: Detected a reboot during ATMA processing!" )
				elif b"BUFFERFULL" in currentLine:
					raise MemoryError( "ELM327: Received a BUFFER FULL alert during ATMA processing!" )
				elif b"STOPPED" in currentLine:
					raise InterruptedError( "ELM327: Received a STOPPED alert during ATMA processing!" )
				elif b"<RXERROR" in currentLine:
					canFrame = False # corrupted frame (ignored frame)
				elif b"<DATAERROR" in currentLine:
					# Warning: incorrect CRCs may produce "DATA ERROR" but no way to distinguish them!
					pass
				if canFrame is None: # frame not corrupted
					canFrameIsRTR = False
					if b"RTR" in currentLine:
						canFrameIsRTR = True
					# Try parsing the frame with both identifier lengths
					for canFrameIsExtended in self.allowMixedIdentifiers and (self.canBusIsExtended, not self.canBusIsExtended) or (self.canBusIsExtended,):
						canFrameRegex = canFrameIsExtended and self.canFrameRegex29 or self.canFrameRegex11
						canFramePieces = canFrameRegex.match( currentLine )
						if canFramePieces:
							canFrameData = None
							try:
								if canFrameIsRTR:
									canFrameData = b''
								else:
									canFrameData = bytes.fromhex( canFramePieces.group( 4 ).decode( "ascii", "replace" ) )
								# Note: canFrameData must have a maximum of 8 bytes, otherwise readings are incorrect.
							except ValueError:
								# The 11-bit identifier has an odd number of digits.
								# The 29-bit identifier has an even number of digits.
								# This exception is raised for wrong identifier sizes + for some incomplete lines.
								continue # incomplete byte in frame (ignored frame)
							canFrameIdentifier = int( canFramePieces.group( 1 ), base=16 )
							if canFrameIdentifier>( canFrameIsExtended and 0x1FFFFFFF or 0x7FF ):
								continue # invalid identifier (over maximum)
							elif canFrameIdentifier<0:
								continue # invalid identifier (negative)
							canFrameDLC = int( canFramePieces.group( 2 ), base=16 )
							if not canFrameIsRTR:
								canFrameLengthActual = len( canFrameData )
								if canFrameLengthActual>8:
									continue # impossible frame containing more than 8 bytes (ignored frame)
								canFrameLength = ( canFrameDLC<=8 ) and canFrameDLC or 8 # DLC, truncated to 8 bytes (max transmitted length)
								if canFrameLengthActual<canFrameLength:
									continue # DLC comparison: missing bytes in frame (ignored frame)
								if canFrameLengthActual>canFrameLength:
									continue # impossible: data length longer than DLC
							canFrame = CANFrame(
								identifier=canFrameIdentifier,
								isExtended=canFrameIsExtended,
								isRTR=canFrameIsRTR,
								DLC=canFrameDLC,
								data=canFrameData,
							)
							# canFrame = False # debug: pretend malformed frame instead of processing it
							break
					else:
						canFrame = False
						printT( "ELM327: Cannot decode ATMA line: %s"%(str( currentLine ),) )
		finally:
			exceptionType = exc_info()[0]
			if exceptionType is None:
				# Will continue: ready for next call of this function
				self.straightInvalidFramesCount = 0
				if timedOutEmpty:
					# Will recover (nothing received): restore timeout
					self.ser.timeout = 0.5
			elif exceptionType==MemoryError or exceptionType==InterruptedError:
				# Will recover (no problem): restore timeout + wait for prompt
				promptTimeoutMessage = None
				if exceptionType==MemoryError:
					promptTimeoutMessage = "ELM327: No prompt after BUFFER FULL alert during ATMA processing!"
				elif exceptionType==InterruptedError:
					promptTimeoutMessage = "ELM327: No prompt after STOPPED alert during ATMA processing!"
				self.ser.timeout = 0.5
				# The prompt may show up anywhere, wait for it when not included in currentLine:
				if b'>' not in currentLine:
					self.waitForPrompt( promptTimeoutMessage, 64, noSilentTest=True )
			elif exceptionType==ValueError:
				# Will recover (invalid bytes received): restore timeout + wait for prompt
				if self.straightInvalidFramesCount>self.maxStraightInvalidFrames:
					self.stopMonitoring( "Received more than %u invalid CAN frames in a row"%(self.straightInvalidFramesCount) )
					self.straightInvalidFramesCount = 0
				self.ser.timeout = 0.5
				self.waitForPrompt( "ELM327: No prompt received after stopping ATMA (ValueError)", 16777215 )
				self.straightInvalidFramesCount += 1
			elif exceptionType==ConnectionAbortedError:
				# Will recover (prompt received): restore timeout
				self.ser.timeout = 0.5
			else:
				# Impossible recover: restore timeout just in case
				self.ser.timeout = 0.5
		return canFrame
	
	# Apply the desired baudrate
	def applyDesiredBaudRate( self ):
		if self.ser.baudrate!=self.serialBaudRateDesired:
			printT( "Switching baud rate (",self.scannerATBRD ,")..." )
			self.write( b"ATBRT00\x0D" )
			self.waitForPrompt( "No prompt after ATBRT00!" )
			self.write( self.scannerATBRD )
			self.ser.timeout = 2
			receivedO = False
			receivedOK = False
			unsupported = False
			newByte = None
			# Wait for "OK"
			for numByte in range( 8 ):
				newByte = self.read()
				if len( newByte )==0 or newByte==b'>':
					raise Exception( "No answer or invalid answer while applying the desired baudrate!" )
				elif newByte==b'?': # unsupported
					printT( "This chip version does not support changing the serial link bitrate, or wrong argument in "+self.scannerATBRD.decode( "ascii" )+"." )
					self.ser.timeout = 0.5
					unsupported = True
					self.waitForPrompt( "No prompt after unsupported ATBRD!" )
					break
				elif newByte==b'O':
					receivedO = True
				elif newByte==b'K':
					if receivedO:
						receivedOK = True
						break
				else:
					receivedO = False
			if unsupported:
				return False
			elif not receivedOK:
				raise Exception( "Invalid answer while applying the desired baudrate!" )
			# Switch baudrate
			self.ser.baudrate = self.serialBaudRateDesired
			# Wait for "ELM327" (without order checking)
			unsupported = False
			receivedStepsATI = {
				b'E': False,
				b'L': False,
				b'M': False,
				b'3': False,
				b'2': False,
				b'7': False,
			}
			receivedATI = False
			for numByte in range( 8 ):
				newByte = self.read()
				if len( newByte )==0:
					unsupported = True
					break
				elif newByte==b'7':
					receivedStepsATI[newByte] = True
					for byte in receivedStepsATI.keys():
						if not receivedStepsATI[byte]:
							unsupported = True
					if not unsupported:
						receivedATI = True
					else:
						self.waitForPrompt()
						self.ser.timeout = 0.5
					break
				elif newByte in receivedStepsATI:
					receivedStepsATI[newByte] = True
				else:
					for byte in receivedStepsATI.keys():
						receivedStepsATI[byte] = False
			# Wait for <CR>
			receivedCR = False
			if receivedATI and not unsupported:
				for numByte in range( 8 ):
					newByte = self.read()
					if newByte==b"\x0D":
						receivedCR = True
						break
			if ( not receivedATI ) or ( not receivedCR ) or unsupported:
				printT( "The communication did not work after applying the desired baudrate!" )
				self.ser.baudrate = self.serialBaudRateInitial
				self.waitForPrompt()
				self.ser.timeout = 0.5
				return False
			# Send confirmation
			self.write( b"\x0D" )
			self.ser.timeout = 0.5
			# Wait for prompt and reset waiting delay
			self.waitForPrompt( "No prompt after setting the desired baudrate!" )
			self.write( b"ATBRT0F\x0D" )
			self.waitForPrompt( "No prompt after ATBRT0F!" )
		return True
	
	def selectATPB_rate( self, expectedRate ):
		""" Select the most suitable bitrate for USER1 (B) protocol """
		try:
			from math import inf
		except ImportError:
			inf = float( "inf" )
		expectedRate = float( expectedRate )
		# Calculate all possible rates
		rates = {}
		for mul8by7 in (False, True):
			ratio = 1.
			if mul8by7:
				ratio = 8./7.
			for divider in range( 1,0x41 ): # dividers from 1 to 0x40
				ATPB = divider
				if mul8by7:
					ATPB |= 0b0001000000000000
				rates[ATPB] = (500.*ratio/float( divider ), mul8by7)
		# Select the closest rate:
		selGap = inf
		selRate = 0.
		selATPB = None
		selMul8by7 = None
		for rateInfo in rates.items():
			ATPB = rateInfo[0]
			rate = rateInfo[1][0]
			mul8by7 = rateInfo[1][1]
			gap = abs( rate-expectedRate )
			if gap<selGap:
				selGap = gap
				selRate = rate
				selATPB = ATPB
				selMul8by7 = mul8by7
		printT( "Selected USER1 CAN rate: %.2f kb/s"%(selRate,) )
		self.User1Mul8by7 = selMul8by7
		return selATPB
	
	def handleNewFrame( self, frame ):
		self.frameHandler.handleNewFrame( frame )
	
	def fakeProcessNoScanner( self ):
		""" Simulates arriving CAN frames """
		printT( "Entered %s.fakeProcessNoScanner()"%(type( self ).__name__,) )
		from random import randint
		fakeIdentifiers = {0x020, 0x220, 0x221, 0x560, 0x56a, 0x56b} # random identifiers
		counterLoop = 0
		while True:
			durationCreation = 0.
			durationDispatch = 0.
			for canFrameIdentifier in fakeIdentifiers:
				canFrameData = bytearray( b"\x00\x00\x00\x00\x00" )
				canFrameData.append( canFrameIdentifier%256 )
				canFrameData.append( randint( 0,0xFF ) )
				canFrameData.append( counterLoop%256 )
				timewatchStart = perf_counter()
				canFrame = CANFrame(
					identifier=canFrameIdentifier,
					isExtended=False,
					isRTR=False,
					DLC=8,
					data=canFrameData,
				)
				durationCreation += perf_counter()-timewatchStart
				timewatchStart = perf_counter()
				self.handleNewFrame( canFrame )
				durationDispatch += perf_counter()-timewatchStart
				sleep( 0.001 )
			counterLoop += 1
			# printT( "Creation duration per frame: %10.5f us"%(durationCreation*1000000./len( fakeIdentifiers ),) )
			# printT( "Dispatch duration per frame: %10.5f us"%(durationDispatch*1000000./len( fakeIdentifiers ),) )
	
	busSpecificationRegex = re.compile( r"^(.+) \(CAN (11|29)/([0-9]+)\)" )
	
	def run( self ):
		self.reloadParameters()
		self.reloadSequence()
		lastReloadAttempt = int( time() )
		self.lastPid = -1
		if DEBUG_DISCONNECTED_SCANNER:
			self.fakeProcessNoScanner()
		self.ser = serial.Serial( port=None, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, xonxoff=False, rtscts=False, write_timeout=None, dsrdtr=False, inter_byte_timeout=None )
		self.ser.exclusive = True # silently fails if "exclusive" does not exist
		isFirstAttempt = True
		while True:
			setConsoleColorWindows( "4F" )
			setConsoleTitle( "ELM327 CAN "+self.serialPort+": Disconnected" )
			if self.ser.is_open:
				self.ser.close()
			if not isFirstAttempt:
				sleep( 1 )
			try:
				# Startup
				if not self.ser.is_open:
					# Configure and open the serial port
					self.reloadParameters()
					printT( "New connection to "+self.serialPort+"..." )
					self.ser.port = self.serialPort
					self.ser.open()
					# Communication attempt
					self.ser.baudrate = self.serialBaudRateInitial
					self.ser.timeout = 0.5
					connectionConfirmed = False
					while not connectionConfirmed:
						self.write( b"ATH\x0D" ) # command that does nothing
						connectionConfirmed = self.waitForPrompt( noSilentTest=True )
						# Alternate between initial and desired baudrates
						if not connectionConfirmed:
							self.reloadParameters()
							if self.ser.baudrate==self.serialBaudRateInitial:
								self.ser.baudrate = self.serialBaudRateDesired
							else:
								self.ser.baudrate = self.serialBaudRateInitial
					printT( "Connection works at "+str( self.ser.baudrate )+" b/s" )
					# Reset
					if self.ser.baudrate==self.serialBaudRateDesired:
						# Note: on my Icar01 ELM327 V1.5, ATWS resets the baud rate. This is a workaround.
						self.write( b"ATD\x0D" )
					else:
						self.write( b"ATWS\x0D" )
					self.ser.timeout = 5
					self.waitForPrompt( "No prompt after ATWS or ATD!" ) # resets the timeout to 0.5
					# TODO - alternate rate instead of keeping serialBaudRateInitial
					# Apply output parameters
					self.write( b"ATE0\x0D" ) # no echo
					self.waitForPrompt( "No prompt after ATE0!" )
					self.write( b"ATL0\x0D" ) # no <LF> after <CR>
					self.waitForPrompt( "No prompt after ATL0!" )
					self.write( b"ATS0\x0D" ) # no spaces
					self.waitForPrompt( "No prompt after ATS0!" )
					self.write( b"ATR1\x0D" ) # wait for response after sending message
					self.waitForPrompt( "No prompt after ATR1!" )
					self.write( b"ATD1\x0D" ) # display DLC of CAN frames between identifier & data
					self.waitForPrompt( "No prompt after ATD1!" )
					self.write( b"ATCAF0\x0D" ) # raw CAN data formatting
					self.waitForPrompt( "No prompt after ATCAF0!" )
					self.write( b"ATH1\x0D" ) # send CAN headers (otherwise identifiers not shown!)
					self.waitForPrompt( "No prompt after ATH1!" )
					self.write( b"ATJHF0\x0D" ) # send J1939 SAE identifiers as ordinary CAN identifiers
					self.waitForPrompt( "No prompt after ATJHF0!" )
					self.write( b"ATJS\x0D" ) # disable byte-reordering for J1939 SAE
					self.waitForPrompt( "No prompt after ATJS!" )
					# Setup the CAN bus characteristics
					self.write( b"ATCSM1\x0D" ) # CAN spy mode
					self.waitForPrompt( "No prompt after ATCSM1!" )
					self.write( b"ATPB"+self.scannerATPB+b"\x0D" ) # configuration of the USER1 CAN bus specification
					self.waitForPrompt( "No prompt after ATPB!" )
					self.write( b"ATSP"+self.scannerATSP+b"\x0D" ) # selection of the CAN bus specification
					self.waitForPrompt( "No prompt after ATSP!" )
					# Attempt to contact the ECU
					printT( "Contacting the ECU..." )
					self.ser.timeout = max( MAX_OBD_NEGOCIATION_TIME, self.inactivityTimeout ) # very conservative (1st request)
					if not DEBUG_DISCONNECTED_CAN_BUS:
						if self.testObdCompliant:
							busConnectionConfirmed = False
							while not busConnectionConfirmed:
								self.write( b"0100\x0D" ) # test OBD request
								busConfirmAnswer = self.readAnwer( "No prompt after 0100!" )
								if "ERROR" in busConfirmAnswer: # BUS ERROR or CAN ERROR
									continue
								elif "UNABLE" in busConfirmAnswer: # UNABLE TO CONNECT
									continue
								else:
									busConnectionConfirmed = True
					# Get the found bus information
					self.ser.timeout = 0.5
					self.write( b"ATDP\x0D" ) # return active bus protocol
					busSpecification = self.readAnwer( "No prompt after ATDP!" )
					busSpecificationPieces = self.busSpecificationRegex.search( busSpecification )
					if busSpecificationPieces:
						self.canBusFamily = busSpecificationPieces.group( 1 )
						self.canBusIsExtended = ( busSpecificationPieces.group( 2 )=="29" )
						self.canBusRate = float( busSpecificationPieces.group( 3 ) )
						if "USER1" in self.canBusFamily and self.User1Mul8by7:
							self.canBusRate *= 8./7. # ATDP reports the rate unaffected by 8/7
						printT( "Connected to CAN bus: %u-bit, %.2f kb/s (%s)"%(self.canBusIsExtended and 29 or 11, self.canBusRate, self.canBusFamily) )
					else:
						raise Exception( "The found OBD bus does not seem to be a CAN bus: %s"%(busSpecification,) )
					# Apply the desired baudrate
					if not self.applyDesiredBaudRate():
						if self.serialBaudRateDesiredForce:
							raise Exception( "The desired baud rate could not be selected!" )
					printT( "Connection established at "+str( self.ser.baudrate )+" b/s" )
					setConsoleColorWindows( "2F" )
					setConsoleTitle( "ELM327 "+self.serialPort+" CAN: "+str( self.ser.baudrate )+" b/s" )
				# Read CAN frames until thread exit
				counter = 0 # counts the number of straight monitoring episodes
				self.filter1RemoteChanged = True # unknown state: re-apply ELM327-side filter
				while True:
					try:
						if self.filter1RemoteChanged:
							with self.filter1RemoteLock:
								self.write( b"ATCF "+bytes( "%.8X"%(self.filter1RemoteResult&self.maskOver,), "ascii" )+b"\x0D" )
								self.waitForPrompt( "No prompt after ATCF!" )
								self.write( b"ATCM "+bytes( "%.8X"%(self.filter1RemoteMask&self.maskOver,), "ascii" )+b"\x0D" )
								self.waitForPrompt( "No prompt after ATCM!" )
								self.filter1RemoteChanged = False
						self.straightInvalidFramesCount = 0
						self.write( b"ATMA\x0D" ) # start monitoring (may fail with "?" error, no particular handling needed)
						self.stopMonitoringAttempts = 0
						stopMonitoringNextAttempt = None
						while True:
							# Live-refresh of configuration:
							if int( time() )!=lastReloadAttempt:
								if counter%2==0:
									self.reloadSequence()
								else:
									self.reloadParameters()
								lastReloadAttempt = int( time() )
							# Read the next frame
							frame = self.readFrame()
							stopMonitoringReason = None # if set, monitoring is stopped
							if self.filter1RemoteChanged:
								stopMonitoringReason = "Changed identifier mask"
							if frame is None: # nothing read
								stopMonitoringReason = "Nothing received while monitoring"
							elif frame==False: # invalid frame
								pass
							else:
								self.handleNewFrame( frame )
							if stopMonitoringReason:
								stopMonitoringTime = perf_counter()
								if stopMonitoringNextAttempt is None \
								or stopMonitoringTime>=stopMonitoringNextAttempt:
									self.stopMonitoring( stopMonitoringReason )
									stopMonitoringNextAttempt = stopMonitoringTime+self.stopMonitoringWait
					except BaseException as e:
						if type( e ) in (MemoryError, InterruptedError, ConnectionAbortedError):
							printT( e )
						else:
							raise e
					# Update the sequence counter:
					counter = counter+1
			except serial.SerialException as e:
				printT( e )
				isFirstAttempt = False
			except:
				printT( format_exc() )
				isFirstAttempt = False
