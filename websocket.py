import threading
import socket

from hashlib import sha1
from base64 import b64encode
from utility import printT
from traceback import format_exc

try:
	from http import HTTPStatus
except ImportError:
	import http.client as HTTPStatus # Python36 -> Python34


class WebSocketBadRequest(ValueError):
	pass


class WebSocket():
	# Constants
	OPCODE_FRAGMENT_CONTINUATION = 0x0
	OPCODE_TEXT = 0x1
	OPCODE_BINARY = 0x2
	OPCODE_CLOSE = 0x8
	OPCODE_PING = 0x9
	OPCODE_PONG = 0xA
	
	# Static attributes (do not modify)
	activeInstances = {}
	activeInstancesLock = threading.Lock()
	
	# Default attributes (do not modify)
	fragmentedOpcode = None
	fragments = None
	fragmentsTotalLen = 0
	
	# Configuration attributes
	maxReceivedLen = None
	allowFramesBinary = False
	allowFramesText = True
	
	@classmethod
	def prepareHeaders( self, requestHandler ):
		requestHandler.close_connection = True # no keep-alive
		headers = {}
		
		# Check that everything is correct
		
		if requestHandler.request_version<"HTTP/1.1":
			encoded = b"The protocol version must be HTTP/1.1"
			response = HTTPStatus.BAD_REQUEST
			contentType = "text/plain"
			return locals()
		
		SecWebSocketKey = requestHandler.headers.get( "Sec-WebSocket-Key", None )
		if SecWebSocketKey is None:
			encoded = b"Missing header Sec-WebSocket-Key"
			response = HTTPStatus.BAD_REQUEST
			contentType = "text/plain"
			return locals()
		
		SecWebSocketVersion = requestHandler.headers.get( "Sec-WebSocket-Version", None )
		if SecWebSocketVersion is None:
			encoded = b"Missing header Sec-WebSocket-Version"
			response = HTTPStatus.BAD_REQUEST
			contentType = "text/plain"
			return locals()
		
		# The request is correct, prepare the response
		
		headers["Upgrade"] = "websocket"
		headers["Connection"] = "Upgrade"
		if SecWebSocketVersion!="13":
			headers["Sec-WebSocket-Version"] = "13"
		headers["Sec-WebSocket-Accept"] = b64encode( sha1( SecWebSocketKey.encode()+b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11" ).digest() ).decode( encoding="ascii" )
		
		encoded = b""
		response = HTTPStatus.SWITCHING_PROTOCOLS
		contentType = None
		
		requestHandler.runWebSocket = True
		return locals()
	
	def __init__( self, requestHandler ):
		self.requestHandler = requestHandler
		self.rfile = requestHandler.rfile
		self.wfile = requestHandler.wfile
		self.wfile_lockWS = threading.Lock()
		requestHandler.connection.setsockopt( socket.IPPROTO_TCP, socket.TCP_NODELAY, True )
	
	def sendMessageRaw( self, content ): # thread-safe
		with self.wfile_lockWS:
			self.wfile.write( content )
	
	@classmethod
	def broadcastMessageRaw( self, content ): # thread-safe
		""" Send a raw frame on all instances of the given WebSocket class (including inherited)
		This function is a possible bottleneck """
		with WebSocket.activeInstancesLock:
			activeInstances = set( WebSocket.activeInstances.keys() )
		for instance in activeInstances:
			if isinstance( instance, self ):
				try:
					instance.sendMessageRaw( content )
				except:
					# Exceptions are captured because we might try to write on an inactive instance.
					pass
	
	@classmethod
	def buildMessageText( self, content ): # thread-safe
		# Conversion of input
		typeOfContent = type( content )
		if typeOfContent==str:
			content = content.encode( encoding="utf-8" )
		elif typeOfContent==bytearray:
			content = bytes( content )
		# Build the frame
		rawFrame = bytearray( [0b10000000|WebSocket.OPCODE_TEXT] ) # text, no fragmentation
		length = len( content )
		if length>=65536:
			rawFrame.extend( [127] )
			rawFrame.extend( length.to_bytes( 8, 'big', signed=False ) )
		elif length>=126:
			rawFrame.extend( [126] )
			rawFrame.extend( length.to_bytes( 2, 'big', signed=False ) )
		else:
			rawFrame.extend( [length] )
		rawFrame.extend( content )
		return rawFrame
	
	def sendMessageText( self, content ): # thread-safe
		self.sendMessageRaw( type( self ).buildMessageText( content ) )
	
	@classmethod
	def broadcastMessageText( self, content ): # thread-safe
		""" Send a text message on all instances
		This function is a possible bottleneck """
		self.broadcastMessageRaw( self.buildMessageText( content ) )
	
	def sendPong( self, content ): # thread-safe
		# Untested
		rawFrame = bytearray( [0b10000000|WebSocket.OPCODE_PONG] )
		rawFrame.extend( [len( content )] )
		rawFrame.extend( content )
		self.sendMessageRaw( self, rawFrame )
		printT( "Sent a PONG" ) # debug
	
	def _readBytes( self, count ): # blocking, non-thread-safe
		if count==0: # reading 0 bytes => empty but not EOF
			readBytes = b''
		else:
			readBytes = self.rfile.read( count )
			if len( readBytes )==0: # EOF
				raise StopIteration( "WebSocket lazy connection termination" )
		return readBytes
	
	def readFrame( self ): # blocking, non-thread-safe
		fragmentedOpcode = self.fragmentedOpcode
		
		readBytes = self._readBytes( 2 )
		flagFin = ( readBytes[0]&0b10000000 )!=0
		if flagFin:
			self.fragmentedOpcode = None
		#flagRSV1 = ( readBytes[0]&0b01000000 )!=0
		#flagRSV2 = ( readBytes[0]&0b00100000 )!=0
		#flagRSV3 = ( readBytes[0]&0b00010000 )!=0
		headerOpcode = readBytes[0]&0b00001111
		messageOpcode = headerOpcode
		fragmented = ( fragmentedOpcode is not None )
		isDataFrame = ( headerOpcode&0b1000 )==0
		if headerOpcode!=WebSocket.OPCODE_FRAGMENT_CONTINUATION:
			if fragmentedOpcode is not None:
				raise WebSocketBadRequest( "WebSocket new message frame received with unfinished fragmented message" )
		if headerOpcode==WebSocket.OPCODE_FRAGMENT_CONTINUATION:
			if ( not fragmented ) or ( self.fragments is None ):
				raise WebSocketBadRequest( "WebSocket fragment continuation frame received with no starting frame" )
			messageOpcode = fragmentedOpcode
		elif headerOpcode==WebSocket.OPCODE_TEXT:
			if not self.allowFramesText:
				raise WebSocketBadRequest( "Text WebSocket frames are not allowed" )
		elif headerOpcode==WebSocket.OPCODE_BINARY:
			if not self.allowFramesBinary:
				raise WebSocketBadRequest( "Binary WebSocket frames are not allowed" )
		elif isDataFrame:
			raise WebSocketBadRequest( "Unknown WebSocket data frames are not supported" )
		if isDataFrame:
			if not flagFin:
				# Setup a new unfinished message:
				self.fragmentedOpcode = headerOpcode
				self.fragments = None # start a new fresh list of fragments
				self.fragmentsTotalLen = 0
				fragmented = True
		flagMask = ( readBytes[1]&0b10000000 )!=0
		if not flagMask:
			raise WebSocketBadRequest( "The Mask bit is mandatory but unset in an incoming WebSocket frame" )
		headerPayloadLen = readBytes[1]&0b01111111
		if not isDataFrame:
			if headerPayloadLen>=126 or not flagFin:
				raise WebSocketBadRequest( "Fragmented WebSocket control frame received" )
		
		readBytes = None
		if headerPayloadLen==126:
			readBytes = self._readBytes( 2 )
			headerPayloadLen = int.from_bytes( readBytes, 'big', signed=False )
		elif headerPayloadLen==127:
			readBytes = self._readBytes( 8 )
			headerPayloadLen = int.from_bytes( readBytes, 'big', signed=False )
		if self.maxReceivedLen and ( headerPayloadLen+self.fragmentsTotalLen )>self.maxReceivedLen:
			raise WebSocketBadRequest( "Received a WebSocket message exceeding the maximum allowed message length" )
		
		readBytes = None
		headerMaskingKey = None
		if flagMask:
			readBytes = self._readBytes( 4 )
			headerMaskingKey = readBytes
		
		readBytes = None
		if headerMaskingKey is not None:
			readBytes = self._readBytes( headerPayloadLen )
			data = bytearray( readBytes )
			for byteInfo in enumerate( data ):
				k = byteInfo[0]
				data[k] = byteInfo[1]^headerMaskingKey[k%4]
		
		if fragmented:
			if self.fragments is None:
				self.fragments = []
				self.fragmentsTotalLen = 0
			self.fragments.append( data )
			self.fragmentsTotalLen += headerPayloadLen
		
		if isDataFrame:
			if flagFin:
				if fragmented:
					data = bytearray.join(bytearray(), self.fragments)
					self.fragments = None
					self.fragmentsTotalLen = 0
				try:
					self.handleMessage( data )
				except:
					printT( format_exc() )
		elif headerOpcode==WebSocket.OPCODE_PING:
			self.sendPong( data )
		elif headerOpcode==WebSocket.OPCODE_CLOSE:
			raise StopIteration( "WebSocket graceful connection termination" )
	
	def handleMessage( self, data ):
		printT( "Received:", data )
	
	def run( self ):
		with WebSocket.activeInstancesLock:
			WebSocket.activeInstances[self] = True
		try:
			while True:
				self.readFrame()
		except BaseException as e:
			raise e
		finally:
			with WebSocket.activeInstancesLock:
				del WebSocket.activeInstances[self]
